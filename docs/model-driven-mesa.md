# Model-driven room and bed simulation

This extension connects the operating-room duration model and a reproducible
length-of-stay (LOS) model to the combined optimizer/Mesa code. It compares
three information settings on the **same episodes and observed outcomes**:

| Mode | Room duration supplied to the scheduler | LOS supplied to bed admission |
|---|---|---|
| `median` | 2019–2021 procedure median, with training-wide fallback | 2019–2021 median postoperative bed days, with fallback |
| `model` | HistGradientBoosting point estimate (optional P80/P95) | XGBoost total-stay prediction minus known days already admitted (optional upper bound) |
| `oracle` | observed 2022 room duration | observed 2022 postoperative bed days |

The oracle deliberately reveals future outcomes and is an information benchmark,
not a deployable method or a mathematical optimum. All modes receive the same
arrivals, synthetic room/bed capacity, closures and solver settings.

## Models and data boundary

`surgery_duration.py` and `duration_features.py` come from
`model/or-occupation`. Training uses 7,079 interventions from 2019–2020;
2021 is split chronologically between model selection and optional interval
calibration; 3,043 patient-disjoint 2022 interventions are held out. The
selected local model is HistGradientBoosting on log duration: test MAE
**14.33 minutes**, RMSE **21.27 minutes**, R² **0.673**. Its optional
P80/P95 bounds cover 81.0%/94.1% of this test cohort. These are results of
the current local protocol, not the older table in the source branch.

The LOS branch provided `bridge_los.py` but referenced a missing saved model.
`los_model.py` trains a new, explicitly identified XGBoost model on the
existing LOS Parquet: 7,124 rows from 2019–2020 train it, 3,197 rows from
2021 calibrate a symmetric 90% interval, and 3,059 patient-disjoint 2022
rows test it. The local test MAE is **0.452 days**, R² **0.783**, and interval
coverage **89.1%** with a 1.123-day half-width. It is **not** the unpublished
model behind the other branch's 0.412-day MAE and 1.02-day interval.

Both saved model artifacts stay under ignored `artifacts/`. During inference,
the EDA Parquet supplies candidate planning features. The internal `no_cas`
key joins predictions to cleaned-workbook episodes; neither this key nor
patient/personnel identifiers enter exported results. The models do use
recorded practitioner/surgeon categories internally, so the artifacts must
remain private. The feature lists exclude actual room times, duration,
discharge and LOS. Clinical review must confirm that diagnosis, CCAM,
anesthesia and personnel fields were actually available before each planning
decision; until then, these are retrospective model estimates, not validated
prospective predictions. The `model_test`
cohort restricts comparisons to the 3,043 cases in both 2022 test sets.
Predictions on the full 2022 workbook are also possible, but include returning
patients excluded from the patient-disjoint test evaluation.

The updated `bridge_los.py` prepares the vacation optimizer's patient table
using **both** predicted room duration and predicted LOS. It no longer reads
observed room duration from the EDA Parquet for scheduling. It subtracts
already elapsed admission days when estimating postoperative bed use. The vacation
optimizer's cost remains distinct from the Mesa execution metrics.

## Cross-day Mesa behavior

`hospital_sim.joint_experiment` wraps the established one-minute Mesa room
simulation with a persistent Mesa ward model:

1. Episodes arrive on their recorded intervention date. Unstarted episodes
   wait for a later operating date.
2. At the start of each operating date, observed discharges release beds.
   The ward offers at most the number of currently free beds. Older waiting
   cohorts go first; within a cohort, shorter **predicted remaining stay** goes first.
3. The existing room scheduler, validator and coordinator plan these offered
   cases. Static or reactive replanning handles temporary room closure.
4. Only cases that actually start consume a bed. The bed is released after
   the hidden **observed** inclusive postoperative stay. An incorrect prediction can therefore
   change which cases get offered and how many beds remain on later days.

This is a minimal bed feedback model. It does not reconstruct the hospital's
real bed stock or its occupancy before the first simulated date. Every surgery,
including ambulatory cases, consumes one synthetic bed on its start date.
The workbook defines total LOS from admission to discharge; for bed use after
surgery, the model subtracts days from admission to intervention, and execution
uses discharge date minus intervention date plus one. Known admission date is
therefore part of the planning assumption.
No staff, specialty, emergency or future-arrival constraints are modeled in
this runner. The daily admission policy does not optimize future bed
reservations; predicted LOS ranks cases within an arrival cohort. It can leave
a bed unused if a selected case does not start that day. These assumptions
must be revisited before operational claims.

## Reproduce locally

Install `requirements.txt` in Python 3.12+; Mesa remains pinned to 3.5.1.
From the repository root after generating the ignored EDA/model Parquets:

```bash
venv/bin/python surgery_duration.py --train-bounds --out artifacts/ml-models
venv/bin/python los_model.py --artifact artifacts/ml-models/los_regressor.joblib
venv/bin/python -m hospital_sim.joint_experiment \
  --date-range 2022-01-03 2022-01-31 --cohort model_test \
  --rooms 2 --bed-capacity 42 --methods baseline \
  --policies reactive --output artifacts/joint-january-reproduction
```

Choose a new empty output directory for each run. In an isolated worktree,
pass absolute `--input`, `--eda-input`, `--surgery-data`, and training `--data`
paths to the ignored resources in the primary checkout. The runner records
dataset/model/code fingerprints, assumptions, daily aggregate bed metrics,
room execution records and a `summary.csv`. No source dataset is modified.
Use `--methods tabu` (or another room method) to run the same model inputs
through a metaheuristic. `--room-risk p80|p95` and `--los-risk upper` allow
conservative planning; those settings require the saved bounds.

For a room-only comparison against the original oracle campaign, use
`python -m hospital_sim.experiment --duration-mode model` with the same
instances, rooms, method, solver seed and budget as the `median` and `oracle`
runs. Predicted LOS is carried in that request but does not alter the
room-only objective. The cross-day runner is needed to observe bed effects.

## Initial paired results

These are **baseline scheduler, seed 0, reactive closure**, January 3–31,
2022, 279 patient-disjoint cases and two synthetic rooms. Results are local
exploratory runs, not a full multi-seed algorithm comparison. The saved
`summary.csv` and `manifest.json` files are in ignored
`artifacts/joint-final-42beds/` and `artifacts/joint-final-10beds/`.

| Beds | Mode | Surgeries completed | Waiting at horizon | Overtime, min |
|---:|---|---:|---:|---:|
| 42 | Median | 246 | 33 | 2,364 |
| 42 | Model | 251 | 28 | 2,716 |
| 42 | Oracle | 260 | 19 | 3,048 |
| 10 | Median | 111 | 168 | 80 |
| 10 | Model | 108 | 171 | 132 |
| 10 | Oracle | 115 | 164 | 8 |

With 42 beds, the model closes **5 of the median mode's 14-case gap** to the
oracle, but completes 9 fewer surgeries than the oracle. More completed
surgeries also bring more overtime than the median mode. With only 10 beds,
the model completes three fewer cases than medians and seven fewer than the
oracle. This sensitivity is why the model
cannot yet be described as achieving oracle performance.

A conservative model run on the same 42-bed workload (`--room-risk p80
--los-risk upper`) completed **226/279** cases with **1,837** overtime minutes.
The larger duration buffers reduced overtime but sharply reduced throughput;
they do not close the oracle gap under this admission policy.

The Tabu room scheduler also runs through this interface. On January 3–7
with 42 beds, 58 cases, seed 0 and 200 evaluations, median and model modes
each completed **50/58**, while the oracle completed **55/58**. Overtime was
578, 364 and 819 minutes respectively. This is an integration smoke test,
not a tuned multi-seed comparison.

The 300-case room-only generated workload (one instance seed, baseline,
reactive closure) completed all 300 cases in each mode. Overtime was 417
minutes with medians, 408 with model predictions and 195 with oracle
knowledge. This workload samples all 2022 cases, so it is not limited to
the patient-disjoint model test cohort.

## Validation

```bash
venv/bin/python -m unittest discover -t . -s tests -q
```

Tests cover the prediction/outcome boundary, the vacation bridge, bed
admission and release, waiting-case conservation, existing room scheduling
and all earlier optimizer/coordinator behavior. The local ML artifacts are
not versioned; retrain before reproducing these numbers on another machine.
