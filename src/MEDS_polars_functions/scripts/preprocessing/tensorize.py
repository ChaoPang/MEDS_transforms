#!/usr/bin/env python
import json
import random
from importlib.resources import files
from pathlib import Path

import hydra
import polars as pl
from loguru import logger
from nested_ragged_tensors.ragged_numpy import JointNestedRaggedTensorDict
from omegaconf import DictConfig, OmegaConf

from MEDS_polars_functions.mapper import rwlock_wrap
from MEDS_polars_functions.tensorize import convert_to_NRT
from MEDS_polars_functions.utils import hydra_loguru_init

config_yaml = files("MEDS_polars_functions").joinpath("configs/preprocess.yaml")


@hydra.main(version_base=None, config_path=str(config_yaml.parent), config_name=config_yaml.stem)
def main(cfg: DictConfig):
    """TODO."""

    hydra_loguru_init()

    logger.info(
        f"Running with config:\n{OmegaConf.to_yaml(cfg)}\n"
        f"Stage: {cfg.stage}\n\n"
        f"Stage config:\n{OmegaConf.to_yaml(cfg.stage_cfg)}"
    )

    input_dir = Path(cfg.stage_cfg.data_input_dir)
    output_dir = Path(cfg.stage_cfg.output_dir)

    shards = json.loads((Path(cfg.input_dir) / "splits.json").read_text())

    patient_splits = list(shards.keys())
    random.shuffle(patient_splits)

    for sp in patient_splits:
        in_fp = input_dir / "event_seqs" / f"{sp}.parquet"
        out_fp = output_dir / f"{sp}.nrt"

        logger.info(f"Tensorizing {str(in_fp.resolve())} into {str(out_fp.resolve())}")

        rwlock_wrap(
            in_fp,
            out_fp,
            pl.scan_parquet,
            JointNestedRaggedTensorDict.save,
            convert_to_NRT,
            do_return=False,
            cache_intermediate=False,
            do_overwrite=cfg.do_overwrite,
        )

    logger.info(f"Done with {cfg.stage}")


if __name__ == "__main__":
    main()
