"""Tests a multi-stage pre-processing pipeline. Only checks the end result, not the intermediate files.

Set the bash env variable `DO_USE_LOCAL_SCRIPTS=1` to use the local py files, rather than the installed
scripts.

In this test, the following stages are run:
  - filter_patients
  - add_time_derived_measurements
  - fit_outlier_detection
  - occlude_outliers
  - fit_normalization
  - fit_vocabulary_indices
  - normalization
  - tokenization
  - tensorization

The stage configuration arguments will be as given in the yaml block below:
"""


from nested_ragged_tensors.ragged_numpy import JointNestedRaggedTensorDict

from .transform_tester_base import (
    ADD_TIME_DERIVED_MEASUREMENTS_SCRIPT,
    AGGREGATE_CODE_METADATA_SCRIPT,
    FILTER_PATIENTS_SCRIPT,
    FIT_VOCABULARY_INDICES_SCRIPT,
    NORMALIZATION_SCRIPT,
    OCCLUDE_OUTLIERS_SCRIPT,
    TENSORIZATION_SCRIPT,
    TOKENIZATION_SCRIPT,
    multi_stage_transform_tester,
    parse_shards_yaml,
)

MEDS_CODE_METADATA_FILE = """
code,description,parent_codes
EYE_COLOR//BLUE,"Blue Eyes. Less common than brown.",
EYE_COLOR//BROWN,"Brown Eyes. The most common eye color.",
EYE_COLOR//HAZEL,"Hazel eyes. These are uncommon",
HR,"Heart Rate",LOINC/8867-4
TEMP,"Body Temperature",LOINC/8310-5
"""

STAGE_CONFIG_YAML = """
filter_patients:
  min_events_per_patient: 5
add_time_derived_measurements:
  age:
    DOB_code: "DOB" # This is the MEDS official code for BIRTH
    age_code: "AGE"
    age_unit: "years"
  time_of_day:
    time_of_day_code: "TIME_OF_DAY"
    endpoints: [6, 12, 18, 24]
fit_outlier_detection:
  aggregations:
    - "values/n_occurrences"
    - "values/sum"
    - "values/sum_sqd"
occlude_outliers:
  stddev_cutoff: 1
fit_normalization:
  aggregations:
    - "code/n_occurrences"
    - "code/n_patients"
    - "values/n_occurrences"
    - "values/sum"
    - "values/sum_sqd"
"""

# After filtering out patients with fewer than 5 events:
WANT_POST_FILTER = parse_shards_yaml(
    """
  "filter_patients/train/0": |-2
    patient_id,time,code,numeric_value
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

  "filter_patients/train/1": |-2
    patient_id,time,code,numeric_value

  "filter_patients/tuning/0": |-2
    patient_id,time,code,numeric_value

  "filter_patients/held_out/0": |-2
    patient_id,time,code,numeric_value
    1500733,,EYE_COLOR//BROWN,
    1500733,,HEIGHT,158.60131573580904
    1500733,"07/20/1986, 00:00:00",DOB,
    1500733,"06/03/2010, 14:54:38",ADMISSION//ORTHOPEDIC,
    1500733,"06/03/2010, 14:54:38",HR,91.4
    1500733,"06/03/2010, 14:54:38",TEMP,100.0
    1500733,"06/03/2010, 15:39:49",HR,84.4
    1500733,"06/03/2010, 15:39:49",TEMP,100.3
    1500733,"06/03/2010, 16:20:49",HR,90.1
    1500733,"06/03/2010, 16:20:49",TEMP,100.1
    1500733,"06/03/2010, 16:44:26",DISCHARGE,
"""
)

WANT_POST_TIME_DERIVED = parse_shards_yaml(
    """
  "add_time_derived_measurements/train/0": |-2
    patient_id,time,code,numeric_value
    239684,,EYE_COLOR//BROWN,
    239684,,HEIGHT,175.271115221764
    239684,"12/28/1980, 00:00:00","TIME_OF_DAY//[00,06)",
    239684,"12/28/1980, 00:00:00",DOB,
    239684,"05/11/2010, 17:41:51","TIME_OF_DAY//[12,18)",
    239684,"05/11/2010, 17:41:51",AGE,29.36883360091833
    239684,"05/11/2010, 17:41:51",ADMISSION//CARDIAC,
    239684,"05/11/2010, 17:41:51",HR,102.6
    239684,"05/11/2010, 17:41:51",TEMP,96.0
    239684,"05/11/2010, 17:48:48","TIME_OF_DAY//[12,18)",
    239684,"05/11/2010, 17:48:48",AGE,29.36884681513314
    239684,"05/11/2010, 17:48:48",HR,105.1
    239684,"05/11/2010, 17:48:48",TEMP,96.2
    239684,"05/11/2010, 18:25:35","TIME_OF_DAY//[18,24)",
    239684,"05/11/2010, 18:25:35",AGE,29.36891675223647
    239684,"05/11/2010, 18:25:35",HR,113.4
    239684,"05/11/2010, 18:25:35",TEMP,95.8
    239684,"05/11/2010, 18:57:18","TIME_OF_DAY//[18,24)",
    239684,"05/11/2010, 18:57:18",AGE,29.36897705595538
    239684,"05/11/2010, 18:57:18",HR,112.6
    239684,"05/11/2010, 18:57:18",TEMP,95.5
    239684,"05/11/2010, 19:27:19","TIME_OF_DAY//[18,24)",
    239684,"05/11/2010, 19:27:19",AGE,29.369034127420306
    239684,"05/11/2010, 19:27:19",DISCHARGE,
    1195293,,EYE_COLOR//BLUE,
    1195293,,HEIGHT,164.6868838269085
    1195293,"06/20/1978, 00:00:00","TIME_OF_DAY//[00,06)",
    1195293,"06/20/1978, 00:00:00",DOB,
    1195293,"06/20/2010, 19:23:52","TIME_OF_DAY//[18,24)",
    1195293,"06/20/2010, 19:23:52",AGE,32.002896271955265
    1195293,"06/20/2010, 19:23:52",ADMISSION//CARDIAC,
    1195293,"06/20/2010, 19:23:52",HR,109.0
    1195293,"06/20/2010, 19:23:52",TEMP,100.0
    1195293,"06/20/2010, 19:25:32","TIME_OF_DAY//[18,24)",
    1195293,"06/20/2010, 19:25:32",AGE,32.00289944083172
    1195293,"06/20/2010, 19:25:32",HR,114.1
    1195293,"06/20/2010, 19:25:32",TEMP,100.0
    1195293,"06/20/2010, 19:45:19","TIME_OF_DAY//[18,24)",
    1195293,"06/20/2010, 19:45:19",AGE,32.00293705539522
    1195293,"06/20/2010, 19:45:19",HR,119.8
    1195293,"06/20/2010, 19:45:19",TEMP,99.9
    1195293,"06/20/2010, 20:12:31","TIME_OF_DAY//[18,24)",
    1195293,"06/20/2010, 20:12:31",AGE,32.002988771458945
    1195293,"06/20/2010, 20:12:31",HR,112.5
    1195293,"06/20/2010, 20:12:31",TEMP,99.8
    1195293,"06/20/2010, 20:24:44","TIME_OF_DAY//[18,24)",
    1195293,"06/20/2010, 20:24:44",AGE,32.00301199932335
    1195293,"06/20/2010, 20:24:44",HR,107.7
    1195293,"06/20/2010, 20:24:44",TEMP,100.0
    1195293,"06/20/2010, 20:41:33","TIME_OF_DAY//[18,24)",
    1195293,"06/20/2010, 20:41:33",AGE,32.003043973286765
    1195293,"06/20/2010, 20:41:33",HR,107.5
    1195293,"06/20/2010, 20:41:33",TEMP,100.4
    1195293,"06/20/2010, 20:50:04","TIME_OF_DAY//[18,24)",
    1195293,"06/20/2010, 20:50:04",AGE,32.00306016624544
    1195293,"06/20/2010, 20:50:04",DISCHARGE,

  "add_time_derived_measurements/train/1": |-2
    patient_id,time,code,numeric_value

  "add_time_derived_measurements/tuning/0": |-2
    patient_id,time,code,numeric_value

  "add_time_derived_measurements/held_out/0": |-2
    patient_id,time,code,numeric_value
    1500733,,EYE_COLOR//BROWN,
    1500733,,HEIGHT,158.60131573580904
    1500733,"07/20/1986, 00:00:00","TIME_OF_DAY//[00,06)",
    1500733,"07/20/1986, 00:00:00",DOB,
    1500733,"06/03/2010, 14:54:38","TIME_OF_DAY//[12,18)",
    1500733,"06/03/2010, 14:54:38",AGE,23.873531791091356
    1500733,"06/03/2010, 14:54:38",ADMISSION//ORTHOPEDIC,
    1500733,"06/03/2010, 14:54:38",HR,91.4
    1500733,"06/03/2010, 14:54:38",TEMP,100.0
    1500733,"06/03/2010, 15:39:49","TIME_OF_DAY//[12,18)",
    1500733,"06/03/2010, 15:39:49",AGE,23.873617699332012
    1500733,"06/03/2010, 15:39:49",HR,84.4
    1500733,"06/03/2010, 15:39:49",TEMP,100.3
    1500733,"06/03/2010, 16:20:49","TIME_OF_DAY//[12,18)",
    1500733,"06/03/2010, 16:20:49",AGE,23.873695653692767
    1500733,"06/03/2010, 16:20:49",HR,90.1
    1500733,"06/03/2010, 16:20:49",TEMP,100.1
    1500733,"06/03/2010, 16:44:26","TIME_OF_DAY//[12,18)",
    1500733,"06/03/2010, 16:44:26",AGE,23.873740556672114
    1500733,"06/03/2010, 16:44:26",DISCHARGE,
"""
)

FIT_OUTLIERS_NEW_METADATA = """
>>> import polars as pl
>>> VALS = pl.col("numeric_value").drop_nulls().drop_nans()
>>> post_outliers = (
...     pl.concat(POST_TIME_DERIVED_YAML.values(), how='vertical')
...     .group_by("code")
...     .agg(
...         VALS.len().alias("values/n_occurrences"),
...         VALS.sum().alias("values/sum"),
...         (VALS**2).sum().alias("values/sum_sqd")
...     )
...     .filter(pl.col("values/n_occurrences") > 0)
... )
>>> post_outliers
┌────────┬──────────────────────┬─────────────┬────────────────┐
│ code   ┆ values/n_occurrences ┆ values/sum  ┆ values/sum_sqd │
│ ---    ┆ ---                  ┆ ---         ┆ ---            │
│ str    ┆ u32                  ┆ f32         ┆ f32            │
╞════════╪══════════════════════╪═════════════╪════════════════╡
│ HR     ┆ 13                   ┆ 1370.200073 ┆ 145770.0625    │
│ TEMP   ┆ 13                   ┆ 1284.000122 ┆ 126868.632812  │
│ AGE    ┆ 16                   ┆ 466.360046  ┆ 13761.804688   │
│ HEIGHT ┆ 3                    ┆ 498.559326  ┆ 82996.109375   │
└────────┴──────────────────────┴─────────────┴────────────────┘
# This implies the following means and standard deviations
>>> mean_col = pl.col("values/sum") / pl.col("values/n_occurrences")
>>> stddev_col = (pl.col("values/sum_sqd") / pl.col("values/n_occurrences") - mean_col**2) ** 0.5
>>> post_outliers.select("code", mean_col.alias("values/mean"), stddev_col.alias("values/std"))
shape: (4, 3)
┌────────┬─────────────┬────────────┐
│ code   ┆ values/mean ┆ values/std │
│ ---    ┆ ---         ┆ ---        │
│ str    ┆ f64         ┆ f64        │
╞════════╪═════════════╪════════════╡
│ AGE    ┆ 29.147503   ┆ 3.2459     │
│ HR     ┆ 105.400006  ┆ 10.194143  │
│ TEMP   ┆ 98.76924    ┆ 1.939794   │
│ HEIGHT ┆ 166.186442  ┆ 6.887399   │
└────────┴─────────────┴────────────┘
>>> post_outliers.select(
...     "code",
...     (mean_col + stddev_col).alias("values/inlier_upper_bound"),
...     (mean_col - stddev_col).alias("values/inlier_lower_bound")
... )
shape: (4, 3)
┌────────┬───────────────────────────┬───────────────────────────┐
│ code   ┆ values/inlier_upper_bound ┆ values/inlier_lower_bound │
│ ---    ┆ ---                       ┆ ---                       │
│ str    ┆ f64                       ┆ f64                       │
╞════════╪═══════════════════════════╪═══════════════════════════╡
│ AGE    ┆ 32.393403                 ┆ 25.901603                 │
│ HR     ┆ 115.594148                ┆ 95.205863                 │
│ TEMP   ┆ 100.709034                ┆ 96.829447                 │
│ HEIGHT ┆ 173.073841                ┆ 159.299043                │
└────────┴───────────────────────────┴───────────────────────────┘
"""

WANT_POST_OCCLUDE_OUTLIERS = parse_shards_yaml(
    """
  "occlude_outliers/train/0": |-2
    patient_id,time,code,numeric_value,numeric_value/is_inlier
    239684,,EYE_COLOR//BROWN,,
    239684,,HEIGHT,,false
    239684,"12/28/1980, 00:00:00","TIME_OF_DAY//[00,06)",,
    239684,"12/28/1980, 00:00:00",DOB,,
    239684,"05/11/2010, 17:41:51","TIME_OF_DAY//[12,18)",,
    239684,"05/11/2010, 17:41:51",AGE,29.36883360091833,true
    239684,"05/11/2010, 17:41:51",ADMISSION//CARDIAC,,
    239684,"05/11/2010, 17:41:51",HR,102.6,true
    239684,"05/11/2010, 17:41:51",TEMP,,false
    239684,"05/11/2010, 17:48:48","TIME_OF_DAY//[12,18)",,
    239684,"05/11/2010, 17:48:48",AGE,29.36884681513314,true
    239684,"05/11/2010, 17:48:48",HR,105.1,true
    239684,"05/11/2010, 17:48:48",TEMP,,false
    239684,"05/11/2010, 18:25:35","TIME_OF_DAY//[18,24)",,
    239684,"05/11/2010, 18:25:35",AGE,29.36891675223647,true
    239684,"05/11/2010, 18:25:35",HR,113.4,true
    239684,"05/11/2010, 18:25:35",TEMP,,false
    239684,"05/11/2010, 18:57:18","TIME_OF_DAY//[18,24)",,
    239684,"05/11/2010, 18:57:18",AGE,29.36897705595538,true
    239684,"05/11/2010, 18:57:18",HR,112.6,true
    239684,"05/11/2010, 18:57:18",TEMP,,false
    239684,"05/11/2010, 19:27:19","TIME_OF_DAY//[18,24)",,
    239684,"05/11/2010, 19:27:19",AGE,29.369034127420306,true
    239684,"05/11/2010, 19:27:19",DISCHARGE,,
    1195293,,EYE_COLOR//BLUE,,
    1195293,,HEIGHT,164.6868838269085,true
    1195293,"06/20/1978, 00:00:00","TIME_OF_DAY//[00,06)",,
    1195293,"06/20/1978, 00:00:00",DOB,,
    1195293,"06/20/2010, 19:23:52","TIME_OF_DAY//[18,24)",,
    1195293,"06/20/2010, 19:23:52",AGE,32.002896271955265,true
    1195293,"06/20/2010, 19:23:52",ADMISSION//CARDIAC,,
    1195293,"06/20/2010, 19:23:52",HR,109.0,true
    1195293,"06/20/2010, 19:23:52",TEMP,100.0,true
    1195293,"06/20/2010, 19:25:32","TIME_OF_DAY//[18,24)",,
    1195293,"06/20/2010, 19:25:32",AGE,32.00289944083172,true
    1195293,"06/20/2010, 19:25:32",HR,114.1,true
    1195293,"06/20/2010, 19:25:32",TEMP,100.0,true
    1195293,"06/20/2010, 19:45:19","TIME_OF_DAY//[18,24)",,
    1195293,"06/20/2010, 19:45:19",AGE,32.00293705539522,true
    1195293,"06/20/2010, 19:45:19",HR,,false
    1195293,"06/20/2010, 19:45:19",TEMP,99.9,true
    1195293,"06/20/2010, 20:12:31","TIME_OF_DAY//[18,24)",,
    1195293,"06/20/2010, 20:12:31",AGE,32.002988771458945,true
    1195293,"06/20/2010, 20:12:31",HR,112.5,true
    1195293,"06/20/2010, 20:12:31",TEMP,99.8,true
    1195293,"06/20/2010, 20:24:44","TIME_OF_DAY//[18,24)",
    1195293,"06/20/2010, 20:24:44",AGE,32.00301199932335,true
    1195293,"06/20/2010, 20:24:44",HR,107.7,true
    1195293,"06/20/2010, 20:24:44",TEMP,100.0,true
    1195293,"06/20/2010, 20:41:33","TIME_OF_DAY//[18,24)",,
    1195293,"06/20/2010, 20:41:33",AGE,32.003043973286765,true
    1195293,"06/20/2010, 20:41:33",HR,107.5,true
    1195293,"06/20/2010, 20:41:33",TEMP,100.4,true
    1195293,"06/20/2010, 20:50:04","TIME_OF_DAY//[18,24)",,
    1195293,"06/20/2010, 20:50:04",AGE,32.00306016624544,true
    1195293,"06/20/2010, 20:50:04",DISCHARGE,,

  "occlude_outliers/train/1": |-2
    patient_id,time,code,numeric_value

  "occlude_outliers/tuning/0": |-2
    patient_id,time,code,numeric_value

  "occlude_outliers/held_out/0": |-2
    patient_id,time,code,numeric_value,numeric_value/is_inlier
    1500733,,EYE_COLOR//BROWN,,
    1500733,,HEIGHT,,false
    1500733,"07/20/1986, 00:00:00","TIME_OF_DAY//[00,06)",,
    1500733,"07/20/1986, 00:00:00",DOB,,
    1500733,"06/03/2010, 14:54:38","TIME_OF_DAY//[12,18)",,
    1500733,"06/03/2010, 14:54:38",AGE,,false
    1500733,"06/03/2010, 14:54:38",ADMISSION//ORTHOPEDIC,,
    1500733,"06/03/2010, 14:54:38",HR,,false
    1500733,"06/03/2010, 14:54:38",TEMP,100.0,true
    1500733,"06/03/2010, 15:39:49","TIME_OF_DAY//[12,18)",,
    1500733,"06/03/2010, 15:39:49",AGE,,false
    1500733,"06/03/2010, 15:39:49",HR,,false
    1500733,"06/03/2010, 15:39:49",TEMP,100.3,true
    1500733,"06/03/2010, 16:20:49","TIME_OF_DAY//[12,18)",,
    1500733,"06/03/2010, 16:20:49",AGE,,false
    1500733,"06/03/2010, 16:20:49",HR,,false
    1500733,"06/03/2010, 16:20:49",TEMP,100.1,true
    1500733,"06/03/2010, 16:44:26","TIME_OF_DAY//[12,18)",,
    1500733,"06/03/2010, 16:44:26",AGE,,false
    1500733,"06/03/2010, 16:44:26",DISCHARGE,,
"""
)


WANT_NRTs = {
    "data/train/1.nrt": JointNestedRaggedTensorDict({}),  # this shard was fully filtered out.
    "data/tuning/0.nrt": JointNestedRaggedTensorDict({}),  # this shard was fully filtered out.
}


def test_pipeline():
    multi_stage_transform_tester(
        transform_scripts=[
            FILTER_PATIENTS_SCRIPT,
            ADD_TIME_DERIVED_MEASUREMENTS_SCRIPT,
            AGGREGATE_CODE_METADATA_SCRIPT,
            OCCLUDE_OUTLIERS_SCRIPT,
            AGGREGATE_CODE_METADATA_SCRIPT,
            FIT_VOCABULARY_INDICES_SCRIPT,
            NORMALIZATION_SCRIPT,
            TOKENIZATION_SCRIPT,
            TENSORIZATION_SCRIPT,
        ],
        stage_names=[
            "filter_patients",
            "add_time_derived_measurements",
            "fit_outlier_detection",
            "occlude_outliers",
            "fit_normalization",
            "fit_vocabulary_indices",
            "normalization",
            "tokenization",
            "tensorization",
        ],
        stage_configs=STAGE_CONFIG_YAML,
        want_data={
            **WANT_POST_FILTER,
            **WANT_POST_TIME_DERIVED,
            **WANT_POST_OCCLUDE_OUTLIERS,
            **WANT_NRTs,
        },
        outputs_from_cohort_dir=True,
        input_code_metadata=MEDS_CODE_METADATA_FILE,
    )
