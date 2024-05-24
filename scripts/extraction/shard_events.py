#!/usr/bin/env python

import random
import time
from collections.abc import Sequence
from datetime import datetime
from functools import partial
from pathlib import Path

import hydra
import polars as pl
from loguru import logger
from omegaconf import DictConfig, OmegaConf
from tqdm.auto import tqdm

from MEDS_polars_functions.mapper import wrap as rwlock_wrap
from MEDS_polars_functions.utils import hydra_loguru_init

ROW_IDX_NAME = "__row_idx"


def scan_with_row_idx(columns: Sequence[str], cfg: DictConfig, fp: Path) -> pl.LazyFrame:
    match fp.suffix.lower():
        case ".csv":
            logger.debug(f"Reading {fp} as CSV.")
            df = pl.scan_csv(fp, row_index_name=ROW_IDX_NAME, infer_schema_length=cfg["infer_schema_length"])
        case ".parquet":
            logger.debug(f"Reading {fp} as Parquet.")
            df = pl.scan_parquet(fp, row_index_name=ROW_IDX_NAME)
        case _:
            raise ValueError(f"Unsupported file type: {fp.suffix}")
    if cfg.subselect_columns:
        df = df.select(pl.col(columns))
    return df


def is_col_field(field: str | None) -> bool:
    # Check if the string field starts with "col(" and ends with ")"
    # indicating a specialized column format in configuration.
    if field is None:
        return False
    return field.startswith("col(") and field.endswith(")")


def parse_col_field(field: str) -> str:
    # Extracts the actual column name from a string formatted as "col(column_name)".
    return field[4:-1]


def retrieve_columns(
    files: Sequence[Path], cfg: DictConfig, event_conversion_cfg: DictConfig
) -> dict[Path, list[str]]:
    """Extracts and organizes column names from configuration for a list of files.

    This function processes each file specified in the 'files' list, reading the
    event conversion configurations that are specific to each file based on its
    stem (filename without the extension). It compiles a list of column names
    needed for each file from the configuration, which includes both general
    columns like row index and patient ID, as well as specific columns defined
    for medical events and timestamps formatted in a special 'col(column_name)' syntax.

    Args:
        files (Sequence[Path]): A sequence of Path objects representing the
            file paths to process.
        cfg (DictConfig): A dictionary configuration that might be used for
            further expansion (not used in the current implementation).
        event_conversion_cfg (DictConfig): A dictionary configuration where
            each key is a filename stem and each value is a dictionary containing
            configuration details for different codes or events, specifying
            which columns to retrieve for each file.

    Returns:
        dict[Path, list[str]]: A dictionary mapping each file path to a list
        of unique column names necessary for processing the file.
        The list of columns includes generic columns and those specified in the 'event_conversion_cfg'.
    """

    # Initialize a dictionary to store file paths as keys and lists of column names as values.
    file_to_columns = {}

    for f in files:
        # Access the event conversion config specific to the stem (filename without extension) of the file.
        file_meds_cfg = event_conversion_cfg[f.stem]

        # Start with a list containing default columns such as row index and patient ID column.
        file_columns = [ROW_IDX_NAME, event_conversion_cfg.patient_id_col]

        # Loop through each configuration item for the current file.
        for code_cfg in file_meds_cfg.values():
            # If the config has a 'code' key and it contains column fields, parse and add them.
            if "code" in code_cfg:
                file_columns += [parse_col_field(field) for field in code_cfg["code"] if is_col_field(field)]

            # If there is a timestamp field in the 'col()' format, parse and add it.
            if "timestamp" in code_cfg and is_col_field(code_cfg["timestamp"]):
                file_columns.append(parse_col_field(code_cfg["timestamp"]))

        # Store unique column names for each file to prevent duplicates.
        file_to_columns[f] = list(set(file_columns))

    return file_to_columns


def filter_to_row_chunk(df: pl.LazyFrame, start: int, end: int) -> pl.LazyFrame:
    return df.filter(pl.col(ROW_IDX_NAME).is_between(start, end, closed="left")).drop(ROW_IDX_NAME)


def write_fn(df: pl.LazyFrame, out_fp: Path) -> None:
    df.collect().write_parquet(out_fp, use_pyarrow=True)


@hydra.main(version_base=None, config_path="../../configs", config_name="extraction")
def main(cfg: DictConfig):
    """Runs the input data re-sharding process. Can be parallelized across output shards.

    Output shards are simply row-chunks of the input data. There is no randomization or re-ordering of the
    input data. Read contention on the input files may render additional parallelism beyond one worker per
    input file ineffective.
    """
    hydra_loguru_init()

    raw_cohort_dir = Path(cfg.raw_cohort_dir)
    MEDS_cohort_dir = Path(cfg.MEDS_cohort_dir)
    row_chunksize = cfg.row_chunksize

    input_files_to_subshard = []
    for fmt in ["parquet", "csv"]:
        files_in_fmt = list(raw_cohort_dir.glob(f"*.{fmt}"))
        for f in files_in_fmt:
            if f.stem in [x.stem for x in input_files_to_subshard]:
                logger.warning(f"Skipping {f} as it has already been added in a preferred format.")
            else:
                input_files_to_subshard.append(f)

    # Select subset of files that we wish to pull events from
    event_conversion_cfg_fp = Path(cfg.event_conversion_config_fp)
    if not event_conversion_cfg_fp.exists():
        raise FileNotFoundError(f"Event conversion config file not found: {event_conversion_cfg_fp}")
    logger.info(f"Reading event conversion config from {event_conversion_cfg_fp}")
    event_conversion_cfg = OmegaConf.load(event_conversion_cfg_fp)
    input_files_to_subshard = [f for f in input_files_to_subshard if f.stem in event_conversion_cfg.keys()]
    table_to_columns = retrieve_columns(input_files_to_subshard, cfg, event_conversion_cfg)

    logger.info(f"Starting event sub-sharding. Sub-sharding {len(input_files_to_subshard)} files.")
    logger.info(
        f"Will read raw data from {str(raw_cohort_dir.resolve())}/$IN_FILE.parquet and write sub-sharded "
        f"data to {str(MEDS_cohort_dir.resolve())}/sub_sharded/$IN_FILE/$ROW_START-$ROW_END.parquet"
    )

    random.shuffle(input_files_to_subshard)

    start = time.time()
    for input_file in tqdm(input_files_to_subshard, position=0, desc="Iterating through files", leave=True):
        columns = table_to_columns[input_file]
        out_dir = MEDS_cohort_dir / "sub_sharded" / input_file.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Processing {input_file} to {out_dir}.")

        df = scan_with_row_idx(columns, cfg, input_file)
        row_count = df.select(pl.len()).collect().item()

        row_shards = list(range(0, row_count, row_chunksize))
        random.shuffle(row_shards)
        logger.info(f"Splitting {input_file} into {len(row_shards)} row-chunks of size {row_chunksize}.")

        datetime.now()
        for i, st in enumerate(tqdm(row_shards, position=1, desc=f"Sub-sharding file {f.stem}")):
            end = min(st + row_chunksize, row_count)
            out_fp = out_dir / f"[{st}-{end}).parquet"

            compute_fn = partial(filter_to_row_chunk, start=st, end=end)
            logger.info(
                f"Writing file {i+1}/{len(row_shards)}: {input_file} row-chunk [{st}-{end}) to {out_fp}."
            )
            rwlock_wrap(
                input_file,
                out_fp,
                partial(scan_with_row_idx, columns, cfg),
                write_fn,
                compute_fn,
                do_overwrite=cfg.do_overwrite,
            )
    end = time.time()
    logger.info(f"Sub-sharding completed in {end - start:.2f} seconds.")


if __name__ == "__main__":
    main()
