"""Tests the full end-to-end extraction process."""

import rootutils

root = rootutils.setup_root(__file__, dotenv=True, pythonpath=True, cwd=True)

import json
import subprocess
import tempfile
from io import StringIO
from pathlib import Path

import polars as pl
from polars.testing import assert_frame_equal

# Test data (inputs)

SUBJECTS_CSV = """
MRN,dob,eye_color,height
1195293,06/20/1978,BLUE,164.6868838269085
239684,12/28/1980,BROWN,175.271115221764
1500733,07/20/1986,BROWN,158.60131573580904
814703,03/28/1976,HAZEL,156.48559093209357
754281,12/19/1988,BROWN,166.22261567137025
68729,03/09/1978,HAZEL,160.3953106166676
"""

ADMIT_VITALS_CSV = """
MRN,admit_date,disch_date,department,vitals_date,HR,temp
239684,"05/11/2010, 17:41:51","05/11/2010, 19:27:19",CARDIAC,"05/11/2010, 18:57:18",112.6,95.5
754281,"01/03/2010, 06:27:59","01/03/2010, 08:22:13",PULMONARY,"01/03/2010, 06:27:59",142.0,99.8
814703,"02/05/2010, 05:55:39","02/05/2010, 07:02:30",ORTHOPEDIC,"02/05/2010, 05:55:39",170.2,100.1
239684,"05/11/2010, 17:41:51","05/11/2010, 19:27:19",CARDIAC,"05/11/2010, 18:25:35",113.4,95.8
68729,"05/26/2010, 02:30:56","05/26/2010, 04:51:52",PULMONARY,"05/26/2010, 02:30:56",86.0,97.8
1195293,"06/20/2010, 19:23:52","06/20/2010, 20:50:04",CARDIAC,"06/20/2010, 20:12:31",112.5,99.8
1500733,"06/03/2010, 14:54:38","06/03/2010, 16:44:26",ORTHOPEDIC,"06/03/2010, 16:20:49",90.1,100.1
239684,"05/11/2010, 17:41:51","05/11/2010, 19:27:19",CARDIAC,"05/11/2010, 17:48:48",105.1,96.2
239684,"05/11/2010, 17:41:51","05/11/2010, 19:27:19",CARDIAC,"05/11/2010, 17:41:51",102.6,96.0
1195293,"06/20/2010, 19:23:52","06/20/2010, 20:50:04",CARDIAC,"06/20/2010, 19:25:32",114.1,100.0
1500733,"06/03/2010, 14:54:38","06/03/2010, 16:44:26",ORTHOPEDIC,"06/03/2010, 14:54:38",91.4,100.0
1195293,"06/20/2010, 19:23:52","06/20/2010, 20:50:04",CARDIAC,"06/20/2010, 20:41:33",107.5,100.4
1195293,"06/20/2010, 19:23:52","06/20/2010, 20:50:04",CARDIAC,"06/20/2010, 20:24:44",107.7,100.0
1195293,"06/20/2010, 19:23:52","06/20/2010, 20:50:04",CARDIAC,"06/20/2010, 19:45:19",119.8,99.9
1195293,"06/20/2010, 19:23:52","06/20/2010, 20:50:04",CARDIAC,"06/20/2010, 19:23:52",109.0,100.0
1500733,"06/03/2010, 14:54:38","06/03/2010, 16:44:26",ORTHOPEDIC,"06/03/2010, 15:39:49",84.4,100.3
"""

EVENT_CFGS_YAML = """
patient_id_col: MRN
subjects:
  eye_color:
    code:
      - EYE_COLOR
      - col(eye_color)
    timestamp: null
  height:
    code: HEIGHT
    timestamp: null
    numerical_value: height
  dob:
    code: DOB
    timestamp: col(dob)
    timestamp_format: "%m/%d/%Y"
admit_vitals:
  admissions:
    code:
      - ADMISSION
      - col(department)
    timestamp: col(admit_date)
    timestamp_format: "%m/%d/%Y, %H:%M:%S"
  discharge:
    code: DISCHARGE
    timestamp: col(disch_date)
    timestamp_format: "%m/%d/%Y, %H:%M:%S"
  HR:
    code: HR
    timestamp: col(vitals_date)
    timestamp_format: "%m/%d/%Y, %H:%M:%S"
    numerical_value: HR
  temp:
    code: TEMP
    timestamp: col(vitals_date)
    timestamp_format: "%m/%d/%Y, %H:%M:%S"
    numerical_value: temp
"""

# Test data (expected outputs) -- ALL OF THIS MAY CHANGE IF THE SEED OR DATA CHANGES
EXPECTED_SPLITS = {
    "train/0": [239684, 1195293],
    "train/1": [68729, 814703],
    "tuning/0": [754281],
    "held_out/0": [1500733],
}

MEDS_OUTPUT_TRAIN_0 = """
patient_id,timestamp,code,numerical_value
239684,,EYE_COLOR//BROWN,
239684,,HEIGHT,175.271115221764
239684,"12/28/1980, 00:00:00",DOB,
239684,"05/11/2010, 17:41:51",ADMISSION//CARDIAC,
239684,"05/11/2010, 17:41:51",HR,102.6
239684,"05/11/2010, 17:41:51",TEMP,96.0
239684,"05/11/2010, 17:48:48",HR,105.1
239684,"05/11/2010, 17:48:48",TEMP,96.2
239684,"05/11/2010, 18:25:35",HR,113.4
239684,"05/11/2010, 18:25:35",TEMP,95.8
239684,"05/11/2010, 18:57:18",HR,112.6
239684,"05/11/2010, 18:57:18",TEMP,95.5
239684,"05/11/2010, 19:27:19",DISCHARGE,
1195293,,EYE_COLOR//BLUE,
1195293,,HEIGHT,164.6868838269085
1195293,"06/20/1978, 00:00:00",DOB,
1195293,"06/20/2010, 19:23:52",ADMISSION//CARDIAC,
1195293,"06/20/2010, 19:23:52",HR,109.0
1195293,"06/20/2010, 19:23:52",TEMP,100.0
1195293,"06/20/2010, 19:25:32",HR,114.1
1195293,"06/20/2010, 19:25:32",TEMP,100.0
1195293,"06/20/2010, 19:45:19",HR,119.8
1195293,"06/20/2010, 19:45:19",TEMP,99.9
1195293,"06/20/2010, 20:12:31",HR,112.5
1195293,"06/20/2010, 20:12:31",TEMP,99.8
1195293,"06/20/2010, 20:24:44",HR,107.7
1195293,"06/20/2010, 20:24:44",TEMP,100.0
1195293,"06/20/2010, 20:41:33",HR,107.5
1195293,"06/20/2010, 20:41:33",TEMP,100.4
1195293,"06/20/2010, 20:50:04",DISCHARGE,
"""


def get_expected_output(df: str) -> pl.DataFrame:
    return (
        pl.read_csv(source=StringIO(df))
        .select(
            "patient_id",
            pl.col("timestamp").str.strptime(pl.Datetime, "%m/%d/%Y, %H:%M:%S").alias("timestamp"),
            pl.col("code").cast(pl.Categorical),
            "numerical_value",
        )
        .sort(by=["patient_id", "timestamp"])
    )


MEDS_OUTPUTS = {
    "train/0": get_expected_output(MEDS_OUTPUT_TRAIN_0),
    "train/1": None,
    "tuning/0": None,
    "held_out/0": None,
}


def run_command(script: Path, hydra_kwargs: dict[str, str], test_name: str):
    script = str(script.resolve())
    command_parts = ["python", script] + [f"{k}={v}" for k, v in hydra_kwargs.items()]
    command_out = subprocess.run(" ".join(command_parts), shell=True, capture_output=True)
    stderr = command_out.stderr.decode()
    stdout = command_out.stdout.decode()
    if command_out.returncode != 0:
        raise AssertionError(f"{test_name} failed!\nstderr:\n{stderr}\nstdout:\n{stdout}")
    return stderr, stdout


def assert_df_equal(df1: pl.DataFrame, df2: pl.DataFrame, msg: str = None, **kwargs):
    try:
        assert_frame_equal(df1, df2, **kwargs)
    except AssertionError as e:
        print(f"df1:\n{df1}")
        print(f"df2:\n{df2}")
        raise AssertionError(msg) from e


def test_extraction():
    with tempfile.TemporaryDirectory() as d:
        raw_cohort_dir = Path(d) / "raw_cohort"
        MEDS_cohort_dir = Path(d) / "MEDS_cohort"

        # Create the directories
        raw_cohort_dir.mkdir()
        MEDS_cohort_dir.mkdir()

        subjects_csv = raw_cohort_dir / "subjects.csv"
        admit_vitals_csv = raw_cohort_dir / "admit_vitals.csv"
        event_cfgs_yaml = raw_cohort_dir / "event_cfgs.yaml"

        # Write the CSV files
        subjects_csv.write_text(SUBJECTS_CSV)
        admit_vitals_csv.write_text(ADMIT_VITALS_CSV)

        # Mix things up -- have one CSV be also in parquet format.
        admit_vitals_parquet = raw_cohort_dir / "admit_vitals.parquet"
        pl.read_csv(admit_vitals_csv).write_parquet(admit_vitals_parquet, use_pyarrow=True)

        # Write the event config YAML
        event_cfgs_yaml.write_text(EVENT_CFGS_YAML)

        # Run the extraction script
        #   1. Sub-shard the data (this will be a null operation in this case, but it is worth doing just in
        #      case.
        #   2. Collect the patient splits.
        #   3. Extract the events and sub-shard by patient.
        #   4. Merge to the final output.

        extraction_config_kwargs = {
            "raw_cohort_dir": str(raw_cohort_dir.resolve()),
            "MEDS_cohort_dir": str(MEDS_cohort_dir.resolve()),
            "event_conversion_config_fp": str(event_cfgs_yaml.resolve()),
            "split_fracs.train": 4 / 6,
            "split_fracs.tuning": 1 / 6,
            "split_fracs.held_out": 1 / 6,
            "row_chunksize": 10,
            "n_patients_per_shard": 2,
            "hydra.verbose": True,
        }

        extraction_root = root / "scripts" / "extraction"

        all_stderrs = []
        all_stdouts = []

        # Step 1: Sub-shard the data
        stderr, stdout = run_command(
            extraction_root / "shard_events.py", extraction_config_kwargs, "shard_events"
        )

        all_stderrs.append(stderr)
        all_stdouts.append(stdout)

        subsharded_dir = MEDS_cohort_dir / "sub_sharded"

        out_files = list(subsharded_dir.glob("*/*.parquet"))
        assert len(out_files) == 3, f"Expected 3 output files, got {len(out_files)}."

        # Checking specific out files:
        #   1. subjects.parquet
        subjects_out = subsharded_dir / "subjects" / "[0-7).parquet"
        assert subjects_out.is_file(), f"Expected {subjects_out} to exist."

        assert_df_equal(
            pl.read_parquet(subjects_out, glob=False),
            pl.read_csv(subjects_csv),
            "Subjects should be equal after sub-sharding",
        )

        #   2. admit_vitals.parquet
        df_chunks = []
        for chunk in ["[0-10)", "[10-16)"]:
            admit_vitals_chunk_fp = subsharded_dir / "admit_vitals" / f"{chunk}.parquet"
            assert admit_vitals_chunk_fp.is_file(), f"Expected {admit_vitals_chunk_fp} to exist."

            df_chunks.append(pl.read_parquet(admit_vitals_chunk_fp, glob=False))
        assert_df_equal(
            pl.concat(df_chunks),
            pl.read_csv(admit_vitals_csv),
            "Admit vitals should be equal after sub-sharding",
        )

        # Step 2: Collect the patient splits
        stderr, stdout = run_command(
            extraction_root / "split_and_shard_patients.py",
            extraction_config_kwargs,
            "split_and_shard_patients",
        )

        all_stderrs.append(stderr)
        all_stdouts.append(stdout)

        splits_fp = MEDS_cohort_dir / "splits.json"
        assert splits_fp.is_file(), f"Expected splits @ {str(splits_fp.resolve())} to exist."

        splits = json.loads(splits_fp.read_text())
        expected_keys = ["train/0", "train/1", "tuning/0", "held_out/0"]

        expected_keys_str = ", ".join(f"'{k}'" for k in expected_keys)
        got_keys_str = ", ".join(f"'{k}'" for k in splits.keys())

        assert set(splits.keys()) == set(expected_keys), (
            f"Expected splits to have keys {expected_keys_str}.\n" f"Got keys: {got_keys_str}"
        )

        assert splits == EXPECTED_SPLITS, (
            f"Expected splits to be {EXPECTED_SPLITS}, got {splits}. NOTE THIS MAY CHANGE IF THE SEED OR "
            "DATA CHANGES -- FAILURE HERE MAY BE JUST DUE TO A NON-DETERMINISTIC SPLIT AND THE TEST NEEDING "
            "TO BE UPDATED."
        )

        # Step 3: Extract the events and sub-shard by patient
        stderr, stdout = run_command(
            extraction_root / "convert_to_sharded_events.py",
            extraction_config_kwargs,
            "convert_events",
        )
        all_stderrs.append(stderr)
        all_stdouts.append(stdout)

        patient_subsharded_folder = MEDS_cohort_dir / "patient_sub_sharded_events"
        assert patient_subsharded_folder.is_dir(), f"Expected {patient_subsharded_folder} to be a directory."

        # We'll skip checking these outputs explicitly, as we can check them more directly after we merge them

        # Step 4: Merge to the final output
        stderr, stdout = run_command(
            extraction_root / "merge_to_MEDS_cohort.py",
            extraction_config_kwargs,
            "merge_sharded_events",
        )
        all_stderrs.append(stderr)
        all_stdouts.append(stdout)

        full_stderr = "\n".join(all_stderrs)
        full_stdout = "\n".join(all_stdouts)

        # Check the final output
        output_folder = MEDS_cohort_dir / "final_cohort"
        try:
            for split, expected_df in MEDS_OUTPUTS.items():
                if expected_df is None:
                    continue

                fp = output_folder / f"{split}.parquet"
                assert fp.is_file(), f"Expected {fp} to exist."

                got_df = pl.read_parquet(fp, glob=False)
                assert_df_equal(
                    got_df,
                    expected_df,
                    f"Expected output for split {split} to be equal to the expected output.",
                    check_column_order=False,
                )
        except AssertionError as e:
            print(f"Failed on split {split}")
            print(f"stderr:\n{full_stderr}")
            print(f"stdout:\n{full_stdout}")
            raise e
