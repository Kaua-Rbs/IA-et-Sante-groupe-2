# Final verified model improvements — 20 October 2026

## Completed outcome

Implemented consultation-feature model training, missing-input inference fixes,
versioned artifacts, a strict opt-in prediction-to-S1/S2 bridge, regression tests,
and a small paired historical scheduling experiment. No existing model, original
checkout, historical output, web default, booking interface or final article was
replaced. No merge, push or deployment occurred.

**The OR model improves accuracy under the reduced consultation input contract.
LOS ML does not beat the train-only intervention median. The scheduling pilot
shows a tradeoff: less start delay, more overtime, nearly unchanged throughput.**
Both model families are loadable and usable through the existing prediction
adapters. This is verified project functionality, not clinical deployment approval.

## Data provenance and leakage controls

Authorized inputs were read in place from `../IA-et-Sante-groupe-2`:

- `resources/model_surgery_duration_dataset.parquet` (13,311 rows).
- `resources/model_los_dataset.parquet` (13,380 rows).
- `resources/donnees_bloc_pretraitees.parquet` for raw-inference matching.
- `results/surgery_duration_model.joblib`, the existing OR model.

Their SHA-256 fingerprints are in the result manifests. No patient rows, source
identifiers, per-patient predictions, real schedules or raw data were exported.
The five new artifacts contain fitted models and train-derived category/group
statistics; handle them as private project artifacts rather than public data.

The existing chronological, patient-disjoint partitions were checked. Models fit
2019–2020 only. Consultation candidates were selected on early 2021 validation;
later 2021, excluding patients shared with selection, calibrated uncertainty.
2022 was used for reporting, never fitting or selecting candidates. However,
**2022 results were already inspected in earlier project work: this is not a new
blind external test.** There was no parameter search against the five failed
optimization runs or against this scheduling pilot.

| Task | Train | Selection | Calibration | Test |
|---|---:|---:|---:|---:|
| OR | 7,079 | 1,678 | 1,400 | 3,043 |
| LOS | 7,124 | 1,684 | 1,402 | 3,059 |

111 validation rows per task were excluded from later calibration to enforce
selection/calibration patient separation. The full-feature LOS reproduction uses
the existing fixed recipe and all 3,197 validation rows for calibration; its
protocol is separate from consultation candidate selection.

The seven restricted features are age, sex, planned intervention type, principal
CIM diagnosis and family, principal CCAM procedure and family. Staff, anesthesia,
secondary diagnosis counts, additional procedure counts, dates, actual duration,
admission/discharge and identifiers are excluded. The project consultation API
supports these raw fields, but historical diagnostic/procedure codes have no
verified capture timestamps. Treat them as consultation-available **under the
project input contract**, not as proof of prospective availability. Planned codes
may differ from final billing codes. Exact training age also differs from the
web application's birth-year approximation. These limitations require prospective
validation and prevent a clinical effectiveness claim.

## Confirmed defects corrected and compatibility

1. `duration_features.py`: an omitted optional raw categorical field, notably an
   absent `ccam_1`, previously raised `KeyError`; absent age did too. Missing
   columns now receive the same missing category/NaN as explicit null inputs.
   Existing normalization and rarity mapping are retained.
2. `los_model.py`: the loader previously exponentiated every model output. This
   made a correctly serialized direct-target median baseline return wrong units.
   It now honors explicit `log_target=False`; artifacts without that flag retain
   historical log-target behavior. Nonfinite, negative and nonscalar interval
   widths are rejected.
3. `surgery_duration.py`: adds support for versioned one-sided residual bounds
   around the point model. Historical saved quantile-model bounds retain their
   original arithmetic and ordering. This is an artifact-format extension, not
   a claim that the previous quantile implementation was defective.

Default artifact paths, legacy optimizer objectives, legacy LOS rounding bridges,
frontend, API adapter source and booking behavior are unchanged. No model was
automatically substituted because it was newer.

## OR prediction results

| Model/input condition | Test MAE, minutes |
|---|---:|
| Existing full-feature retrospective model | 14.3331 |
| Existing model with unavailable web fields masked | 17.9005 |
| Train-only intervention median | 18.1480 |
| **Selected consultation HGB, log target** | **16.6217** |
| Consultation HGB, absolute loss, not selected | 16.5491 |

The selected model improves MAE by 1.279 minutes (7.14%) against the masked
existing model and 1.526 minutes (8.41%) against intervention medians. It does
not improve on the full-feature 14.33-minute result. Two fixed HGB candidates
were evaluated; log-target HGB won early-2021 validation (17.2712 vs 17.3097).
The absolute-loss candidate was not substituted after seeing its slightly better
2022 result. Fixed 200 iterations, 15 leaves, seed 42; no extensive tuning.

One-sided calibrated coverage is 79.82% for P80 and 95.70% for P95 overall.
This does not guarantee session-level capacity compliance. On 397 actual
procedures >=120 minutes, MAE is 36.05 minutes, bias -32.04, underprediction
90.43%, and P95 coverage only 73.55%. Long procedures remain difficult.
Missing intervention type worsens MAE to 20.7493 minutes; optional availability
of this input materially limits real-world usefulness.

## LOS prediction results and provenance

No saved LOS artifact was found at the inspected default model paths in the
original and relevant local worktrees. A new artifact was therefore trained
from the authorized LOS Parquet using the current `los_model.py` recipe. This
does not reproduce or validate older LOS numbers from a different implementation.

| Model/input condition | Test MAE, inclusive hospital days |
|---|---:|
| New full-feature reproduction of current recipe | 0.45045 |
| Same full-feature artifact with unavailable web fields masked | 0.65264 |
| **Train-only intervention median** | **0.48611** |
| Consultation-only fixed-recipe XGB | 0.50562 |

Consultation XGB improves on a masked full-feature artifact but loses to the
median on both selection (0.45902 vs 0.43023) and test. Prefer the consultation
median if choosing solely by validation MAE. Preserve the XGB as a research
candidate; do not present it as a baseline-beating LOS improvement. The current
full-feature reproduction has RMSE 0.75834 days and R² 0.78392, but requires
features that may be unavailable at consultation.

Consultation XGB's nominal 90% interval covers 89.24% overall, versus 89.34%
for the full-feature reproduction. Among 67 actual stays >=7 days, consultation
MAE is 2.4645 days, bias -2.4580, underprediction 98.51%, and interval coverage
25.37%. Median tail MAE is 2.8657 days. Good marginal coverage masks poor tail
coverage; these intervals cannot establish safe bed planning for long stays.

Independent raw-calendar verification matched all 13,380 LOS targets exactly to
`(discharge-admission).days+1`, with no invalid preoperative intervals. Raw and
prepared inference matched exactly on all 3,059 test cases for the consultation
ML, consultation median and full-feature reproduction artifacts.

All LOS points are **inclusive admission-to-discharge calendar days**. An actual
or explicitly modeled preoperative elapsed time must be subtracted before
postoperative capacity accounting; at consultation, future elapsed days are not
known and must not be inferred from future observations.

## Prediction-to-S1/S2 integration

`prediction_planning.prediction_problem(...)` is an isolated optional bridge:

- Requires unique aligned prediction/patient indices and valid patient/session
  identifiers. Original IDs remain in tables; optimizer assignments are positional.
- Requires finite positive OR minutes, inclusive LOS >=1 and explicitly aligned
  nonnegative integer **known** preoperative days. Default preoperative days=0.
- Uses `ceil(minutes)` and `max(1, ceil(total_inclusive_LOS-known_preop_days))-1`
  as the postoperative day offset. Offset 0 occupies the surgery day only.
- Allows explicit point/P80/P95 OR and point/upper LOS choices, with no hidden
  default risk inflation in existing callers.
- Requires a full residual bed-capacity vector through all modeled discharges;
  reservations and existing patients must already have been deducted by callers.
  No future capacity is guessed, copied or extrapolated.
- Returns an opt-in feasibility-first `FullStayPlanningProblem`; independent
  `validate_full_stay` remains the calendar verification oracle.

A synthetic complete path loaded the actual saved consultation models, used P95
OR / upper LOS, created S1/S2 inputs with 60 explicitly supplied bed days, and
passed independent validation. Unit tests separately cover same-day discharge,
preoperative subtraction, final-day tail occupancy, missing tail capacities,
misalignment and invalid predictions. Clinical reservations/HTTP booking were
not exercised and this bridge was not integrated into live booking.

## Controlled scheduling pilot: actual results

`experiments/final_prediction_scheduling.py` compares intervention medians and
the validation-selected consultation OR model, both trained on exactly the
same OR training rows. Raw/prepared inference parity was exact for all 3,043
uniquely matched test rows in both arms. All 13,311 model rows matched uniquely
to raw EDA patient/day keys, with target agreement; no ambiguous keys existed.

Predeclared bounded design: first eight chronological held-out dates with >=8
eligible cases, cap30 by source-case ordering; 100 distinct cases, one- and
two-room scenarios, seeds7101/7102, identical positional round-robin initial
assignments, 500 fitness evaluations including initialization, T0=1, alpha=.95,
10-second search cap, 08:00–16:00 window, 15-minute turnover, static execution.
No actual duration was supplied to the scheduling request, initializer, model
or optimizer. Realized room durations were used only by the execution simulator.

LOS is intentionally fixed to one day in both arms; 30 explicitly available
beds make these <=30-case daily cohorts nonbinding. Bed overload=0 is a
**constructed fixed-LOS scenario property, not a measured real ward outcome**.
Actual LOS, multi-day bed pressure and reactive rescheduling were not tested.
This uses the project's room-allocation SA/simulator, not a new S1/S2 clinical
deployment. The room problem explicitly permits deferrals and finishing after
closing; its feasible-plan rates must not be conflated with S1/S2 feasibility.

| Rooms | Arm | Completed/day | Unstarted/day | Actual overtime incl. turnover, min/day | Total start delay, min/day |
|---:|---|---:|---:|---:|---:|
| 1 | Median | 6.3750 | 6.1250 | 41.625 | 150.875 |
| 1 | ML | 6.3750 | 6.1250 | 54.125 | 124.750 |
| 2 | Median | 10.6250 | 1.8750 | 79.250 | 300.6875 |
| 2 | ML | 10.6875 | 1.8125 | 98.000 | 214.1875 |

ML-minus-median: one room, unchanged completed count, +12.5 minutes overtime,
-26.125 minutes total start delay; two rooms, +0.0625 completed/day,
+18.75 minutes overtime, -86.5 minutes total start delay. Overtime sums room
minutes and includes turnover. Both arms underpredict on this cohort (median
bias -8.63 vs ML -4.93 minutes); lower average prediction error does not ensure
better ordering or overtime outcomes for individual cases.

The 64 runs used 32,000 evaluations with no search deadline stop, no execution
validation failure, and complete accounting of completed+unstarted patients.
Search runtime is about 0.02–0.03 seconds/run; total per-run simulation runtime
about 0.34–0.37 seconds. No inference throughput benchmark is claimed. Average
results group the two solver seeds within each daily cohort: **n=8 cohorts**,
not 64 independent hospital instances. Same-day seeds and resource conditions
are correlated. No significance or general clinical benefit is claimed.

Predicted complete/no-overtime plans were 0% for one-room arms, 25% for
two-room median and 12.5% for two-room ML. These are capacity-limited room
scenarios, not planted-feasible optimization tests. The pilot provides evidence
of tradeoffs and a reproducible evaluation path, not uniform ML superiority.
Historical feature capture timing remains unverified, so it is conditional
retrospective evidence rather than a verified decision-time clinical trial.

## Executed verification

- Final regression: **184 tests run; 183 passed, 1 skipped**, exit0. Includes
  new synthetic tests plus OR inference, LOS partitions/bridge, ward/simulation,
  optimizer, S1/S2, hybrid, coordination, data bridges and CLI integration.
- Existing S1/S2 original experiment: independently replayed 180 returned plans
  and 152 feasible incumbents; hashes/budgets/starts verified, exit0.
- Larger S1/S2 experiment: independently replayed 132 plans and126 incumbents;
  hashes/matched-arm blocks verified, exit0. No rerun or overwrite of old outputs.
- Five artifacts: serialization/reload parity, finite all-missing raw inputs,
  two actual adapter probes each (including missing intervention and no CCAM).
- Loaded-model synthetic S1/S2 end-to-end validation passed.
- Scheduling:64 runs, all500 evaluations, no validation failure or search timeout.
- `git diff --check` passed for tracked changes. Source compilation and package
  hashes are recorded in the submission audit.

The HTTP server, database concurrency and live booking path were not tested.
Only the existing adapter classes were imported and executed. Local SQLModel
dependencies were installed into ignored `.deps`, not into the original venv.
Serialized artifacts were verified on the recorded library versions only;
loading in older teammate environments has not been established. Use the
provided version pins in a separate environment.

## Reproduction and canonical outputs

Run from this worktree with the recorded Python3.14.2/package environment.
Use **new empty output/artifact directories**; the scripts refuse overwrites.
Set `PYTHONDONTWRITEBYTECODE=1`; add `.deps` to `PYTHONPATH` if using the local
ignored dependency directory. Windows test/temp/threadpool operations required
execution permissions unavailable in the restricted sandbox.

```powershell
python -B -m experiments.train_consultation_models --source ../IA-et-Sante-groupe-2 --output experiments/results/REPRO-models --artifacts artifacts/ml-models/REPRO-models
python -B -m experiments.verify_final_models --source ../IA-et-Sante-groupe-2 --artifacts artifacts/ml-models/final-2026-10-20-v3 --output experiments/results/REPRO-verification
python -B -m experiments.final_prediction_scheduling --source ../IA-et-Sante-groupe-2 --artifacts artifacts/ml-models/final-2026-10-20-v3 --output experiments/results/REPRO-scheduling
python -B -m experiments.run_final_model_checks --output experiments/results/REPRO-tests
python -B -m experiments.summarize_final_models --models experiments/results/final-consultation-2026-10-20-v3 --scheduling experiments/results/final-scheduling-2026-10-20-v2 --verification experiments/results/final-artifact-verification-2026-10-20-v3 --output experiments/results/REPRO-analysis
```

Canonical completed directories:

- `experiments/results/final-consultation-2026-10-20-v3`: metrics, manifest, report.
- `artifacts/ml-models/final-2026-10-20-v3`: five versioned models and full LOS metadata.
- `experiments/results/final-scheduling-2026-10-20-v2`:64 aggregate runs, cohort
  differences, manifest and summary. No real schedules or patient predictions.
- `experiments/results/final-artifact-verification-2026-10-20-v3`: actual adapter,
  model-to-S1/S2, raw LOS/calendar and tail diagnostics with package versions.
- `experiments/results/final-model-analysis-2026-10-20-v3`: comparison tables,
  CSVs, PNG/SVG prediction-error and scheduling-tradeoff figures.
- `experiments/results/final-model-checks-2026-10-20-v1`: executed test/replay logs
  and child exit codes.

Preserved noncanonical attempts are excluded from submission: trainingv1 failed
on sandbox threadpool permissions; trainingv2 exposed the direct-target LOS
loader bug and is incomplete; schedulingv1 failed on this new script's mistaken
RunResult attribute before producing runs. The corrected experiment ranv2.
Earlier artifact-verification and analysis directories completed but were
superseded by synthetic S1/S2, independent LOS calendar checks and clarifications.
No hyperparameter or model
selection changes were made in these retries. Directoryv3 identifies the
successful training attempt; filenamev1 identifies the fixed recipe version.

## Changed source/test files and why

| File | Actual change |
|---|---|
| `duration_features.py` | Missing-column inference handling; no preprocessing recipe replacement |
| `surgery_duration.py` | Backward-compatible point-residual bounds support |
| `los_model.py` | Direct/log target distinction and valid interval-width checks |
| `consultation_features.py` | Explicit conservative seven-feature/raw-field whitelist |
| `prediction_planning.py` | Optional prediction/LOS-unit bridge into S1/S2 with explicit capacities |
| `tests/test_final_models.py` | Eight synthetic regression tests for these changes |
| `experiments/train_consultation_models.py` | Bounded validation-selected training, baselines, calibration, aggregate evaluation, hashes |
| `experiments/final_prediction_scheduling.py` | Paired held-out OR-only scheduling pilot with raw parity checks |
| `experiments/verify_final_models.py` | Real artifact/adapter and synthetic model-to-S1/S2 checks; tail diagnostics |
| `experiments/run_final_model_checks.py` | Test/replay execution with real exit codes and logs |
| `experiments/summarize_final_models.py` | Reproducible aggregate comparison figures and tables |
| `experiments/final_model_requirements.txt` | Exact core versions used; optional display/tool versions in audit |
| `experiments/package_final_models.py` | Explicit-allowlist, private-data-excluding submission packaging and hash audit |

`.gitignore` and earlier S1/S2 files were already changed before this final model
task. See `experiments/COMMIT_FILES.txt` for the prior S1/S2 contribution. The new
precise list is `FINAL_MODEL_SUBMISSION_FILES.txt`; model paths are separately
listed in `FINAL_MODEL_ARTIFACT_FILES.txt` and remain ignored/private.

Final packaged deliverables (ZIP CRC/integrity and per-file SHA-256 checked):

- `artifacts/submission/final-models-2026-10-20-v2/s1s2-and-final-model-code-results.zip`
  includes the existing synthetic S1/S2 contribution plus this task's source,
  tests, documentation, figures and aggregate results. Overlay on the current
  repository; it is not a standalone checkout.
- `artifacts/submission/final-models-2026-10-20-v2/PRIVATE-versioned-models.zip`
  contains only the five successful versioned artifacts and LOS metadata, with
  no patient rows. Keep this separate from public Git and use it only for the
  authorized private project submission.
- `artifacts/submission/final-models-2026-10-20-v2/SUBMISSION_AUDIT.json`
  records file hashes, test counts, evaluation counts and package integrity.

Earlier packagev1 is superseded; usev2. Do not `git add experiments/` wholesale:
the exact allowlist excludes unsuccessful/superseded attempts and local caches.

## Submission recommendation and remaining work

Submit the correctness fixes, restricted model recipe/artifacts, aggregate
results and negative/mixed findings for review. Preserve the existing full-input
OR model. Offer the consultation OR model only as an explicit alternative;
select the median LOS baseline for a validation-MAE-only comparison. Do not
switch defaults or claim safe long-stay capacity prediction.

The most valuable follow-up is an independently held-out, timestamp-verified
consultation cohort with risk-aware schedule evaluation, including actual LOS
and reservations. Long-case underprediction and conditional interval coverage
need attention before deployment. A capacity-aware initialization/repair strategy
remains an optimization follow-up; this task did not tune S1/S2 or rewrite its
already-validated objectives. Extensive new model development was deliberately
avoided within the submission window.
