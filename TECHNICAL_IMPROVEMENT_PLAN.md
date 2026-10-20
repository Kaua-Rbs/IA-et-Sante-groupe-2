# Technical improvement plan

Assessment date: 19 October 2026. Status: diagnosis and proposals only; implementation awaits team selection.

## Technical decision summary — expanded assessment

The first implementation should be a **bounded feasibility-first SA experiment with full-stay bed evaluation**, compared with current SA on the same saved synthetic instances and seeds. The main opportunity is to correct what the solver rewards and measures before adding algorithms. The current weighted vacation objective can prefer an infeasible schedule even when a feasible assignment exists. This is stronger evidence for a correction than an expectation that a hybrid should outperform SA.

The earlier T1–T10 engineering backlog remains below for traceability. The scientific ranking in the following sections supersedes its ordering: release/security/documentation tasks are useful but do not outrank scheduling correctness and decision-quality experiments for improving the technical project.

No modification or experiment described below has been implemented or run. New arithmetic is limited to reading existing aggregate CSVs; mathematical examples below are analytical demonstrations, not measured optimizer runs.

## Seven-area technical diagnosis

### 1. Operating-room occupancy prediction

**Current code:** `surgery_duration.py`, `duration_features.py`, preprocessing notebooks, `interface/api/ai/trained.py`, `interface/api/ai/validate_web_models.py`.

The target is individual **room occupancy duration**, not incision time, session utilization, or admission waiting time. `surgery_duration.py` compares simple medians and multiple estimators, selects using validation (MAE within 0.2 minutes of the best, then training speed), and separates validation selection from later conformal calibration by time and patient. `FIXED_FEATURES` excludes proposed-operation calendar features. Identifiers are excluded. These are useful existing safeguards, not missing features to reimplement.

**Saved evidence:** the existing aggregate `final-article/english/evidence/external-critique/prediction-baselines.csv` records MAE 14.3331 minutes for the selected histogram gradient boosting model, 18.1480 for intervention-type median, 19.5891 for procedure median, and 29.1078 for global median. These are existing results, not inference rerun here. The audit reports full-feature P80/P95 held-out coverage of 80.97%/94.12%, while masking unavailable web fields gives MAE 17.9005 and P95 coverage 60.2%; masking intervention type too gives MAE 22.6238. This is a significant deployment-input mismatch, not evidence that ML has no value.

**Remaining assumptions/limitations:** anesthesia type, practitioner, and historical surgeon names are populated in retrospective training but unavailable in the web adapter. Other fields, including diagnosis and procedure counts, need a decision-time availability check; a field present in a hospital extract is not automatically known at consultation. The code explicitly treats principal CCAM as preoperative under the project's stated assumption; do not label it leakage without contrary evidence. The exact room prediction model does not prove the availability of all associated diagnoses or ancillary CCAM codes. Current masking sensitivity estimates distribution shift; it does not evaluate a model trained for that feature set.

**Best ML modification:** train one deliberately restricted consultation-feature model and recalibrate it on correspondingly restricted validation inputs; compare against a train-only intervention-type median and the current model under identical masking. More hyperparameter search is lower value. Missing-feature flags and train-derived category maps must be rebuilt for the new feature contract. Do not repeatedly choose features on the already inspected 2022 test scores; use validation for selection, then report the frozen test comparison as a previously examined retrospective benchmark, not pristine prospective confirmation.

**Missing validation:** signed error, MAE and upper-bound coverage by duration tail and sufficiently large clinical groups, interval width versus coverage, unknown-category/missingness rates, and downstream decision quality. Individual P95 bounds do not guarantee a 95% feasible session. Conservative bounds can reduce throughput legitimately. Prefer a separate point-versus-buffer policy comparison over silently replacing point predictions with P95 everywhere.

**No confirmed new estimator bug:** this inspection does not identify a defect explaining the residual 14-minute MAE. The improvement hypothesis is realistic features and decision-aligned validation, not guaranteed superiority from retraining.

### 2. Length-of-stay prediction and bed occupancy

**Current model:** `los_model.py` validates chronological, patient-disjoint partitions, fits XGBoost on `log1p(inclusive total LOS)`, clips the inverse prediction to at least one day, and calibrates a symmetric absolute-residual interval using 2021. The minimum calibration sample guard is now present. Log squared-error fitting does not directly minimize original-scale MAE, long-stay underestimation, or downstream bed overflow; inverse transformation is not generally an unbiased conditional mean. This is an objective choice to evaluate, not an automatic coding error.

The newer model and the legacy bridge artifact are distinct. The context documents' 0.452-day newer-model claim and 0.412-day legacy claim cannot be exchanged. Neither fitted model performance nor calibration was reproduced here. No `resources/` or `artifacts/` directory was found in this worktree during this assessment; this is not a claim that artifacts are absent everywhere.

**Complete convention audit:**

| Path | Representation and behavior | Assessment |
|---|---|---|
| Preprocessing / `los_model.py` | Total inclusive admission-to-discharge days, minimum one | Appropriate only with an explicit target definition |
| `bridge_los.py` on main | Match patient/date; subtract known operation minus admission days; clip to one; round point; convert inclusive postoperative days to offset by subtracting one | Earlier identifier/off-by-one defects corrected; median imputation and duplicate averaging remain policy choices |
| `PlanningProblem._occupation` | Occupy operation day through operation day + offset, inclusive | Correct endpoint convention; clips at last vacation day, which remains a defect for full-stay claims |
| `hospital_sim/predictions.py::apply` | Subtract preoperative days; retain inclusive postoperative days, point rounded and upper ceiled | Main correction present; differs from web point rounding |
| `hospital_sim/historical_data.py` | Observed postoperative LOS = discharge minus operation + one | Consistent inclusive observed target |
| `hospital_sim/ward.py` | Admit on operation day; release at start of operation day + inclusive LOS; report bed days within experiment horizon | Consistent with occupying discharge calendar day; end-of-experiment occupancy still needs explicit tail follow-up |
| `interface/api/clinical/service.py` | Ceil total inclusive LOS; scheduling assumes admission is the operation day | Coherent simplified workflow for new same-day admissions, not a general preoperative-bed model |
| Web cohort and confirmation validators | Inclusive stay through discharge checked against individual units, including after operation window | Existing protection; not evidence the research objective has full-tail accounting |
| Legacy v3 LOS experiments | Older bridge used total LOS as postoperative offset without subtracting preoperative days or one | Historical results remain uncorrected; cannot be relabeled as main results |

**Critical nuance:** preoperative elapsed days are known for an already admitted patient at operation-time replanning. Historical realized admission dates are not necessarily known at the earlier consultation when the plan is proposed. Using actual elapsed preoperative days in a consultation experiment can create hindsight even though target columns are excluded from feature matrices. Define the decision time explicitly, or use planned admission dates available then. Do not subtract observed preoperative days from a baseline already trained on postoperative LOS.

**Other limitations:** `HospitalWardModel` starts empty, offers at most currently free beds, orders earlier arrivals before predicted LOS, and reserves beds only when surgery starts. Predicted LOS influences ordering within arrival cohorts, not a full multi-day bed reservation optimization. A weak LOS effect in this simulator may reflect limited use of predictions. End summaries truncate occupied bed days to the requested experiment end and report still-admitted cases; that is valid finite-horizon reporting, not full follow-up. Add a no-new-arrivals drain period for tail outcomes if selected.

**Strongest changes:** full-stay research occupancy and an explicit rounding/decision-time contract first; train-only median baseline plus long-stay and subgroup interval evaluation second. Conditional/quantile LOS models are a later experiment, not an assumed cure. A marginal conformal interval neither establishes uniform uncertainty nor bounded real tails, especially under temporal distribution shift.

### 3. Scheduling optimization and feasibility

**Two different implemented problems must stay separate.** The vacation optimizer uses `5 * OR-overload-minutes + 3 * bed-overload-days + 0.05 * load-standard-deviation`. `hospital_sim/room_problem.py` instead decodes a room assignment with an SPT ordering and a bounded service-first objective: unstarted cases, predicted overtime, then changed waiting assignments. The latter already implements a form of lexicographic prioritization; proposing it as absent everywhere would be incorrect.

**Confirmed formulation defect for hard feasibility:** finite weighted penalties can rank infeasible assignments above feasible ones. An exact synthetic counterexample for the current vacation formula: two one-day patients each need 1,000 minutes; two sessions on days 0/1 each have capacity 2,000; patient 1 is restricted to day 0 and patient 2 can choose either day; bed capacities are `[2, 0]`. Both on day 0 is feasible with loads `[2000, 0]`, standard deviation 1,000, and cost **50**. Spreading them gives loads `[1000, 1000]` and cost **3**, from one unavailable bed on day 1. Current optimization therefore prefers a physically invalid plan. No search sophistication repairs an objective that rewards that choice. This should become a deterministic regression fixture after approval.

**Other direct findings:** absent-specialty fallback and incomplete assignment validation remain (T1). Occupancy is truncated (T2). Every patient must be assigned in `PlanningProblem`; explicit deferral is absent. Random starts and single reassign/same-specialty swaps provide no general finite-budget feasibility guarantee. A one-step hard rejection of every infeasible neighbor can trap search between disconnected feasible allocations; hard output validation alone does not create a good search procedure.

**Structural diagnosis before algorithm ranking:** compute compatible session sets; reject empty sets; flag a patient longer than every allowed residual session; calculate per-specialty or common-compatible-subset demand exceeding available capacity and mandatory bed demand exceeding supply. Necessary aggregate bounds are not sufficient for indivisible packing and calendar constraints. Prove small instances feasible/infeasible by enumeration; plant a known feasible assignment in larger generated instances. Label an unproved case as unresolved, not structurally infeasible. Emergency margins, existing confirmed occupancy and closures must be deducted before these checks.

**Modification:** introduce an opt-in feasibility-first comparison where all complete valid zero-overload assignments outrank every violating assignment, with full-stay accounting and a separate feasible incumbent. Use a bounded scalar encoding compatible with existing float-fitness methods, or a carefully isolated comparator; do not pass tuples into SA's arithmetic. Maintain meaningful normalized violation magnitudes for escaping infeasible regions. Once feasible, improve balance without losing the feasible incumbent. An inexpensive greedy construction and relocate/swap repair can improve the success rate, but measure its evaluations and runtime. Keep the existing mode for historical reproducibility.

**Deferrals:** introduce only in a later selected change with explicit `unassigned` records, urgency/wait constraints, and coverage conservation. Within validated hard-feasible schedules, maximize served/priority value before soft balance. Dropping all patients cannot count as success. The web adapter already returns unassigned cases after capacity filtering; that filtering can discard good alternatives because it is not a repair search. Never change the public `Solution` mapping to use a sentinel vacation without updating every decoder and integration.

### 4. Hybrid metaheuristics and MAS

`optimiseur/optimizer.py` implements SA, tabu, tabu–SA, genetic, ACO and three additional hybrids; `multiagent.py` supplies cooperating search agents. Shared controlled evaluation and warm-start hooks now exist in `search_control.py`. Main already corrected accounting/seeding/compatibility issues identified in the context documents; older campaign CSVs have not thereby been regenerated.

**Mechanism hypotheses worth testing:** SA's default `alpha=0.95` cools from 50 to about 0.003 after 190 iterations, long before a large evaluation allowance ends; hybrid `alpha=0.97` cools per neighborhood iteration rather than per evaluation, with 15 default neighbors. Comparable iteration counts therefore imply different effort and temperature trajectories. Tabu records a reassignment destination as its move key, which is not necessarily an inverse-move prohibition; immediate-return behavior deserves a deterministic test before claiming classical tabu tenure. The hybrid first selects the best admissible neighbor and then applies Metropolis rejection; this can discard exploratory moves that pure tabu would take. These are plausible explanations for weak hybrids, not established bugs or proof that changing them improves results.

MAS coordinates agents in creation order; Mesa agents do not themselves establish parallel speedup. Shared best migration can reduce diversity, and nested searches consume overhead and effort. Equal seeds do not imply identical random neighborhoods across methods. Equal objective evaluations and equal wall time answer different questions and should both be recorded, not conflated. Native time-budget loops may finish an entire neighborhood or agent step before checking elapsed time; actual effort matters.

**Legitimate negative results:** simpler SA winning under a short budget, limited benefit from extra hybrid layers, and workload-dependent rankings are scientifically plausible. The v3 fragmented workload's lower hybrid cost is conditional on one workload, unequal default effort and remaining overload. The original selected feasible v2 means favor SA on six instances. Neither observation is an implementation failure by itself. Do not tune a hybrid until it wins on the same held-out benchmark used for reporting.

**Best next comparison:** SA versus tabu and tabu–SA using the same valid instance manifest and starting plan, evaluation budget, deadline guard, and operational evaluator; add MAS only after that harness is stable. Freeze temperature scaling from development instances. A large ten-method retuning campaign is low priority before the deadline.

### 5. Reactive rescheduling

**New saved-data arithmetic:** reread the existing 576-row `final-article/english/evidence/campaign/runs.csv`. Pair rows by `(instance_id, method, seed, scenario)` and compare reactive minus static for outage scenarios. This is reaggregation of prior saved results, not new execution:

| Saved group | Pairs | Mean completed difference | Mean overtime difference, min | Fewer / more completed pairs |
|---|---:|---:|---:|---:|
| Small | 18 | −0.0556 | −19.1667 | 3 / 2 |
| Historical | 54 | −0.1481 | −7.8704 | 8 / 0 |
| Large | 72 | −0.7222 | +116.0000 | 34 / 14 |

Mean extra evaluations are 1,666.67 per outage pair in each group, pooled across the included methods. These means are descriptive, not independent-workload confidence intervals. Exact attribution requires inspecting individual saved schedules/events. Reduced overtime with fewer completed cases is not automatically an improvement; large-instance deterioration warrants investigation.

**Code evidence:** `simulation.py::step` marks `availability_changed` at outage start/end only. Ordinary completion and turnover events are logged but do not trigger a solve. `run_day` pauses simulation time while awaiting the solver; solver CPU cost is reported but not translated into real operational delay. Execution obeys scheduled start times, so an unexpectedly free room can idle until its planned next start in the static path. The reactive policy is principally outage-triggered replanning, not continuous response to all duration surprises.

The decoder reorders waiting cases by shortest predicted duration and optimizes room assignments, not an arbitrary case permutation. Running/completed cases are fixed by `ObservationAdapter` and `RoomValidator`; future waiting commitments are movable, and the tertiary change count includes time changes as well as room changes. This is weaker than a clinician-defined near-term freeze window. Cases may start before closing and finish after it; overtime is an allowed trade-off, not a violated hard finish constraint. Closures prohibit starts but do not interrupt ongoing operations. Those semantics need to match the claimed disruption.

**Root-cause hypotheses:** locally improved predicted throughput can worsen realized execution under errors; repacking changes which long cases are started near closing; no near-term freeze, no explicit comparison against a revalidated keep-plan continuation, limited move encoding, and extra reactive search effort confound attribution. The existing objective is service-first already, so simply claiming that balance was optimized ahead of completed cases would be wrong for this path. Predicted service priority does not guarantee realized service improvement.

**Modification to investigate after feasibility work:** at each outage, compare a feasible continuation of the incumbent with the candidate using the same current-information objective; retain the better candidate, then test an optional near-term freeze. Inspect accepted schedules and realized traces for the worst paired losses. Add completion/overrun triggers as a separate ablation with debounce and a total-day compute limit. Never select a candidate using hidden realized durations. No claim that a predicted no-regression rule guarantees no realized regression.

### 6. Prediction-to-scheduling integration

`bridge_los.py` now actually uses room predictions rather than observed room durations, and main's patient/date matching and inclusive-to-postoperative conversion are corrected. `tests/test_prediction_ward.py` includes hidden-outcome invariance and bridge fixtures. Preserve those tests. Historical LOS v3 instead used observed room times and synthetic LOS scenarios around predictions; it is not the desired held-out median-versus-ML operational experiment.

`joint_experiment.py` can already run median/model/oracle modes with identical configured methods and resources, private realized outcomes, and output-directory overwrite protection. It is a useful starting point, but **not yet a fully controlled causal comparison**:

- Median estimates in `historical_data.py` use 2019–2021; ML uses 2019–2020 fit and 2021 calibration/selection. Train patient eligibility is not the same manifest.
- `_heldout_source_keys` intersects only the room model test cohort, not the LOS test partition. Loading prediction rows from calendar year 2022 alone is not enough to establish LOS patient-disjoint evaluation.
- `mode=model` changes both room and LOS predictions simultaneously. It cannot isolate which estimator helped.
- Full retrospective EDA features are passed to raw prediction; these are not equivalent to the reduced consultation form.
- Current historical dates/resources are a controlled replay assumption; observed intervention date is not evidence of when an unscheduled future case became ready. Future historical preoperative elapsed days must not leak into consultation-time decisions.
- Ward ordering/reservation semantics limit what better LOS estimates can influence, as described above.

**Controlled experiment is feasible in principle:** freeze a common patient-disjoint held-out cohort eligible for both tasks; derive baseline and ML from matched training eligibility and features; hold LOS constant while changing room estimator first. Use one solver and equal budgets, actual room/LOS outcomes only inside the evaluator, identical resources/readiness/closures, and a shared scenario manifest. A subsequent 2×2 room-estimator × LOS-estimator experiment isolates both effects. Oracle mode is an information reference, not a proved optimum. Do not require an oracle result to dominate every heuristic realization.

**Preconditions:** recover authorized artifacts and verify their schemas/hashes/split provenance; define baseline fitting period, decision time and input availability. These inputs are not present in this worktree, so a real-data comparison cannot be promised as the first deadline task. A room-only version can avoid the missing LOS artifact by holding bed demand fixed or explicitly limiting its claim to room operations.

### 7. Experimental protocol and benchmarking

The repository has useful harness infrastructure, but protocol generations differ. `optimiseur/benchmark.py` principally saves fitness/runtime; it does not establish hard feasibility or retain the whole instance/schedule provenance in its long table. `hospital_sim/experiment.py` is stronger: paired static/reactive execution shares an initial plan, saved schedules and stopping information. It uses controlled per-solve budgets; reactive receives extra solves, not an equal total-day effort allocation. `joint_experiment.py` records model/data fingerprints but needs the cohort and baseline corrections above.

**Already corrected on main:** controlled evaluation accounting, ACO initial seeding, warm-start guards, coordination lifecycle/history/state behavior, patient options preserved under disruptions, and accepted care-type/confirmed-capacity handling are documented in UPDATE_IMPACT and visible in the integrated paths. Do not diagnose those historical issues as still universally present.

**Historical limitations that remain historical:** unequal default iteration effort in v3; one workload with repeated search seeds; truncated optimization despite full reevaluation; missing fitted LOS evidence and joint manifests; changed matched-only cohorts; OR-component lower bounds presented too strongly; synthetic scenario distributions mistaken for calibrated outcome distributions. None is corrected by editing main or by rereading a CSV. Existing values remain useful when scoped accurately.

**Protocol improvements:** save input hashes, generation seeds, solver seeds, raw assignment validity, full-tail violation components, deferred case count, runtime, evaluation count, stop reason, and code/dependency versions. Use tiny exact references, planted-feasible workloads, deliberately infeasible stress cases, and multiple independent workload seeds. Compare paired instance-level differences; search seeds quantify solver variability conditional on an instance. Do not report a new algorithm improvement from only lower weighted cost, lower utilization due to fewer cases, or a best-observed score labeled optimal.

## Scientific priorities and delivery assessment

Estimates below assume a working isolated environment and focused review. The stated submission deadline is 20 October 2026; assessment date is 19 October. These are scope estimates, not a promise of available working hours. Stop if prerequisites consume the validation window.

| Rank / ID | Problem, hypothesis and proposed modification | Expected measurable benefit | Files | Effort | Regression/validation and integration risk | Safe before deadline? |
|---|---|---|---|---|---|---|
| 1 / S1 | Weighted balance can beat feasibility; add opt-in feasibility-first scoring and a feasible incumbent, with full-tail evaluation | Eliminate known invalid preference; measure feasible-run rate and time/evaluations to first feasible | `optimiseur/optimizer.py`, `search_control.py`, new synthetic harness, `tests/test_optimizer.py` | 6–10 focused hours including bounded experiment | Exact counterexample, full-tail checker, current-versus-new seeded comparison; medium risk if default changes, low–medium if opt-in and schemas preserved | Yes, conditional on environment and all checks; recommended first |
| 2 / S2 | Tail clipping hides demand; separate operation/evaluation horizon and validate capacities (prerequisite portion of S1) | Correct bed-overload totals, no false feasible labels after final vacation | `optimizer.py`, `ai/cohort.py`, bridge tests | 3–6 hours standalone | Final-day stay, tail closure, existing occupancy, same-day discharge; medium semantics risk | Yes as bounded opt-in correction; do not rebuild every caller |
| 3 / S3 | Prediction quality not linked to observed scheduling benefit; build matched median-vs-ML room experiment with LOS fixed | Paired completed/unstarted, overtime, waits and feasibility deltas on real held-out cases | `joint_experiment.py`, `historical_data.py`, `predictions.py`, artifact manifests | 1–2 days after inputs verified | Cohort equality, outcomes-invariance, common train eligibility/features/budgets; medium experimental integration risk | Conditional; not if artifact recovery or retraining is needed |
| 4 / S4 | Reactive losses unlocalized; trace worst losses and add incumbent-continuation comparison before accepting replan | Lower realized loss rate tested on common disruptions, not promised | `simulation.py`, `room_problem.py`, `scheduling.py`, reactive tests | 1–2 days | Running/completed freeze, feasible continuation, outage handling, CPU counters, common initial plans; medium risk | Trace diagnosis feasible; full policy validation likely too broad |
| 5 / S5 | Full-feature training differs from consultation; train/recalibrate restricted room model before tuning | Restricted-input MAE, tail bias and coverage against frozen baselines | `surgery_duration.py`, `duration_features.py`, web adapter, validation script | 1–2 days with authorized data | Same split, train-only mappings, independent calibration, validation-selected variant; medium model/schema risk | Only with complete local data/environment; not first task |
| 6 / S6 | LOS evidence incomplete and loss not aligned to beds; recover provenance, add median/tail/coverage baseline evaluation | Reproducible LOS baseline gap and demand error; identify where retraining is justified | `los_model.py`, `predictions.py`, `ward.py`, validation script | 0.5–1 day recovery/evaluation; longer if training | Inclusive/preop tests, LOS-specific held-out eligibility, long-stay signed error and interval width; low read-only/medium retrain risk | Recovery yes; unplanned retraining no |
| 7 / S7 | Unequal budget/default cooling and hidden hybrid overhead; common-start SA/tabu/hybrid comparison | Feasible success rate and objective quality per evaluation and second | `benchmark.py`, `search_control.py`, `optimizer.py`, `multiagent.py` | 1–2 days | Actual effort caps including nested calls, unchanged legacy behavior, independent development seeds; medium integration risk | Small bounded SA/hybrid comparison possible; ten-method tuning no |
| 8 / S8 | Explicit service/deferral/repair absent in vacation representation; add capacity-aware construction, repair and explicit deferral contract | More valid served cases and clear infeasibility, not merely lower penalties | `optimizer.py`, `aleas.py`, bridges, decoders | 2–4 days | Case conservation, priorities, feasible/infeasible witnesses, API compatibility; high risk | Full deferral redesign no; small repair ablation only if S1 succeeds early |

Engineering T3–T9 below remain useful support work. They do not substitute for these measurable technical improvements.

## Single recommended experiment: feasibility-first SA under full-stay validation

**Question:** on provably feasible workloads, does changing the vacation objective to prefer feasibility recover more valid schedules than current weighted SA at the same evaluation allowance? Does it avoid falsely labeling tail-overload cases feasible? This directly tests a demonstrated mathematical failure and requires no patient data, fitted artifact or new optimizer dependency.

**Minimal implementation boundary after approval:** an opt-in objective/evaluation mode, full-tail capacity input, independent validator, and a standalone reproducible synthetic experiment. Keep default historical behavior and all result paths unchanged. Do not implement deferral sentinels, new MAS agents, web policy changes, retraining or a solver rewrite in this first experiment. Validate output membership/coverage, but do not turn a missing-case dictionary into an apparently better partial plan.

**Three comparison arms, one protocol:**

1. A: current weighted objective and truncated occupancy, unchanged baseline.
2. B: weighted objective with full-tail occupancy, to isolate accounting correction.
3. C: full-tail feasibility-first objective, to isolate objective correction.

All three use the same SA implementation, documented temperature settings, starting assignment, allowed-session sets, instance, and solver seed. Keep an independent best-feasible incumbent in C. Preserve a smooth violation gradient in infeasible states; do not use a discontinuous giant penalty with the old fixed temperature without checking its numerical behavior. Report that a new objective rescales SA acceptance and is part of the intervention; no claim of algorithm superiority. If a repair/warm start is added, make it a separately labeled ablation charged to the same budget, not an unreported advantage.

**Reproducible inputs:**

- Include the two-patient analytical counterexample above and tiny exact-enumeration fixtures with interior feasible and infeasible states.
- Generate 12 planted-feasible workloads from workload seeds `1100..1111`: four slack, four near capacity, four with late multi-day stays and declining tail bed capacity. Build patients/resources around a saved feasible witness; keep that witness out of solver initialization and use it only in validation. Use compatible patient options in every arm so the experiment isolates scoring rather than the absent-specialty bug.
- Include four separately labeled provably infeasible cases: no allowed specialty, indivisible duration exceeding every option, aggregate specialty deficit, mandatory bed deficit. Reject malformed/no-option input separately; compare search only on representable instances. Never score these as algorithm failures to discover a nonexistent complete schedule.
- Use solver seeds `0..4` and 3,000 objective evaluations per arm, including initialization and repair if any. The main comparison is 180 runs on 12 feasible workloads; tiny fixtures and infeasible diagnostics are additional checks. A small hard wall-clock safety cap is recorded; capped runs are censored/flagged, never silently treated as fully budgeted. Save manifests and complete synthetic schedules in a new empty output directory.

**Independent evaluation:** use a simple calendar loop, separate from `_occupation`, to count every occupied day through discharge and every session's assigned minutes. Validate coverage, compatibility and identifiers before capacity. Use the same full-tail evaluator for all arms, including A. Record predicted/realized distinction: in this first deterministic synthetic correction experiment, supplied durations are exact scenario requirements, so it tests planning feasibility, not ML benefit or robustness to unknown clinical outcomes. A predeclared private-duration stress check can assess robustness later, but is not needed to establish the correctness fix.

**Outcomes:** feasible-run fraction; time/evaluations to first feasible; OR overload minutes; bed overload days through final discharge; served/unassigned case counts; load balance among feasible plans; runtime/evaluations/termination reason. Include operational consequences explicitly: how many assigned operations fit actual session capacity and whether the full-stay bed plan can accommodate all patients. Do not call the assignment count completed surgeries; no minute-level execution is performed by this experiment. If execution throughput is required, use the existing room simulator in a separate selected follow-up rather than inventing a completion proxy.

**Acceptance and interpretation:**

- Required correctness: the feasible counterexample ranks ahead of the infeasible balanced assignment in C, full-tail diagnostics match independent enumeration/calendar counts, and no invalid plan receives a feasible label. Test same-day discharge, preoperative conversion, missing assignment, capacity-vector length and end-of-horizon occupancy.
- Required comparability: same instance/start/budget manifest, all evaluations accounted for, and no changes to legacy-mode objective values or existing synthetic bridge/coordination/web tests.
- Empirical success: C has a higher feasible-run rate than A across the declared workloads and no increase in invalid outputs; report paired per-workload differences and all seeds. Do not promise a universal or statistically significant improvement from 12 workloads. If B explains the gain/loss, attribute it to accounting rather than feasibility-first scoring.
- If C corrects ranking but does not improve discovery, the engineering correction is still real, but the search-performance hypothesis failed. Then examine feasible initialization/repair and objective-temperature scaling; do not launch an unbounded tuning exercise or hide negative results.
- No feasibility guarantee for every possible input is claimed. Proved feasibility of a workload and empirical success of a heuristic are distinct.

**Deadline gate:** first establish an isolated environment and run a tiny smoke fixture. If setup plus implementation leaves insufficient time for the relevant regression suites and the bounded experiment, deliver only the independently tested accounting/validation correction, with no performance claim. If even that cannot be validated, preserve the current system and defer implementation. A new real-data ML campaign cannot safely be promised from the presently absent worktree inputs.

**Recommended next action:** approve S1 with S2's necessary full-tail portion as the first bounded change. Do not start with retraining, hybrid retuning or a new reactive policy. The highest-value later experiment is S3, conditional on artifact and cohort provenance.

## Scope and baseline

- Dedicated worktree: `IA-et-Sante-improvements`, branch `improvement/technical-audit`.
- Inspected HEAD and fetched `origin/main`: both `a35efde96adaaef96449ddc18918894f9c654eae`. No fetch was performed; this identifies the available integrated baseline, not live remote state.
- Initial working tree was clean. No applicable `AGENTS.md` was found within this worktree.
- Context read: `../IA-et-Sante-groupe-2/audit_2026-10-18/PROJECT_AUDIT.md` and `../IA-et-Sante-rapport-final/final-article/UPDATE_IMPACT.md`.
- Only this plan is created. No source, existing model, dataset, experimental result, notebook, article, or sibling worktree is changed. No training, benchmark campaign, deployment, merge, checkout, or dependency installation is performed.

The integrated repository already contains prediction code, ten optimization methods, historical/ward simulation, coordination, FastAPI planning, a Svelte application, and CI. The October 18 audit's statement that research engines are absent from main is obsolete. The impact document correctly distinguishes corrected main adapters from the older LOS experiment branch. Do not import that branch wholesale or treat its saved experiments as evaluations of current main.

## Verification and confidence

This assessment reads source, configuration, CI, test definitions, and the two context documents. A read-only AST parse passed for **all 97 Python files** in this checkout, using `python -B`; this establishes syntax only.

Runtime research/API suites, frontend checks/build, container builds, PostgreSQL races, fitted-model inference, and campaigns were **not rerun**. The available `python` resolves to the original repository's virtual environment; it was used only for standard-library syntax parsing, without importing project modules or writing bytecode. No local `uv` or `pnpm` executable was found. Existing documents' test counts and model metrics are historical evidence, not newly verified results. This assessment does not establish current CI status, dependency availability, deployed behavior, or artifact validity.

Findings below distinguish directly observed implementation behavior from risks requiring execution. Priorities are for this prototype: P0 means address before relying on the affected guarantee or shared deployment; P1 means a valuable next improvement; P2 means defer until the earlier work is selected and validated. Effort is relative engineering scope, not a delivery promise: S = localized, M = several modules/tests, L = protocol or architectural change.

## Prioritized shortlist

| ID | Priority | Improvement | Evidence / confidence | Effort | Main effect |
|---|---|---|---|---|---|
| T1 | P0 | Enforce research input and assignment validity | Direct source finding | M | Prevent incompatible or malformed schedules being treated as valid |
| T2 | P0 | Separate scheduling horizon from bed follow-up | Direct source finding | M–L | Expose capacity violations after the final operation day |
| T3 | P0 | Make research tests a release prerequisite | Direct CI finding | S | Prevent publishing after a failed research job |
| T4 | P0 for shared deployment | Reject placeholder signing keys in deployment mode | Direct configuration finding | S | Prevent use of the public default key |
| T5 | P1 | Exercise booking concurrency in PostgreSQL CI | Existing check; runtime guarantee unverified here | M | Continuously validate reservation serialization |
| T6 | P1 | Make model/adapter evidence explicit and reproducible | Source plus documented evidence gaps | M | Avoid transferring retrospective accuracy to reduced web inputs |
| T7 | P1 | Bound and clarify replanning worker ownership | Direct single-process design; race not reproduced | M | Make restart/failure behavior testable and deployment limits enforceable |
| T8 | P1 | Align dependency and onboarding documentation | Direct documentation/configuration finding | S–M | Reproduce the integrated system from a clean checkout |
| T9 | P1 before persistent schema upgrades | Introduce versioned database migrations | Direct bootstrap finding | M | Upgrade existing installations without manual schema repair |
| T10 | P2 | Compare schedulers under a shared, auditable protocol | Context evidence; no new benchmark | L | Improve scientific comparison without rewriting historical results |

## Detailed diagnosis and proposed acceptance criteria

### T1 — Validate research feasibility independently of fitness

**Observed:** `optimiseur/optimizer.py::PlanningProblem.__init__` falls back to every vacation when a patient's specialty has no matching vacation. Explicit `patient_options` validates index bounds and nonemptiness but does not intersect options with specialty compatibility. `fitness()` and `violations()` evaluate capacity for supplied dictionary entries; neither is a complete validator for assignment coverage and compatibility. Capacity remains a weighted soft penalty. A low cost does not establish feasibility, and zero reported capacity overflow alone does not establish a complete, specialty-compatible assignment.

**Boundary:** `interface/api/ai/cohort.py::optimize_cohort` supplies per-case compatible options and independently filters assignments against actual vacation and bed-unit capacity, including the full stay. `planning/service.py::check_still_feasible` revalidates bookings. The research findings do not prove that the web booking path admits the same invalid schedules.

**Proposal:** add a shared research validation result covering complete patient coverage, identifiers, option/specialty membership, finite nonnegative durations/capacities, capacity-vector shape, and resource violations. Reject unsupported input early. Return an explicit infeasible/unassigned outcome when no compatible session exists. Keep optimization cost distinct from validation; select any hard-feasibility or repair policy separately.

**Acceptance:** synthetic cases cover missing specialty, incompatible explicit option, missing/extra assignment, empty workload/session sets, invalid numbers and vector lengths. An incompatible assignment cannot receive a feasible label. Existing valid small-instance objective values remain unchanged unless a separately selected objective change requires versioning.

### T2 — Account for postoperative bed demand beyond the operation horizon

**Observed:** `PlanningProblem.n_days` is derived from vacation days. `_occupation()` clips discharge to `self.n_days`; both fitness and violation reporting omit later occupancy. Moving a long stay late in the operation window can therefore conceal bed demand. This is an implementation fact, not a newly measured performance effect.

The web cohort adapter also optimizes an aggregate bed surrogate only over vacation dates, then checks each actual unit through discharge. That final check protects presentation of assignments, but the search can still prefer candidates that it later drops. It also allocates conventional cases before ambulatory cases and cannot directly optimize unit-specific bed feasibility.

**Proposal:** introduce an explicit bed evaluation horizon with defined tail capacities and existing occupancy. Keep the operation calendar independent. Report truncated and full-follow-up diagnostics with clear labels. Preserve a versioned legacy evaluation mode for reproducing historical results. First fix full-stay accounting; a richer unit-level search should be a later, separately measured extension.

**Acceptance:** a final-day operation with a multi-day stay and a tail capacity reduction reports the expected overload on every affected day. Same-day discharge uses one occupied calendar day. Capacity arrays have explicit length requirements. Web assignments continue to pass full-stay validation. A synthetic fixture demonstrates the distinction between search cost, assignments retained after validation, and unassigned cases.

**Dependency/risk:** agree tail capacity semantics before implementation. Objective values and rankings can change; never overwrite old experiment outputs or relabel them as corrected runs.

### T3 — Close the release test dependency gap

**Observed:** `.github/workflows/ci.yaml` runs research, API, and frontend jobs. `publish.needs` contains only `[api, app]`, although the API image bundles `optimiseur/` and `hospital_sim/`. On a release event, a research failure does not itself block publication after the two listed prerequisites succeed.

**Proposal:** require the research job as well. Preserve existing commit-pinned actions and frozen API/frontend installs. Add container smoke validation if selected, rather than inferring image health from source tests alone.

**Acceptance:** inspect/validate the workflow dependency graph; demonstrate in an isolated CI branch that a failing required research job prevents publish eligibility. Do not create a real release or push an image to test this change.

### T4 — Enforce deployment configuration invariants

**Observed:** `interface/api/config.py` warns but continues when `SECRET_KEY` equals the documented placeholder. JWT creation uses this key in `accounts/security.py`. Several operational settings, including `EMERGENCY_MARGIN`, are unbounded configuration values; invalid values can distort available capacity. Replanning limits already use bounded Pydantic fields and provide a useful pattern.

**Proposal:** introduce an explicit deployment/demo distinction, reject placeholder or empty keys in shared deployment, and validate scheduling settings such as a margin in `[0, 1)`, positive proposal count, and supported horizon. Keep an intentional, documented local fixture mode.

**Acceptance:** invalid deployment configuration fails before serving requests; valid fixture and trained configurations start in isolated tests. Verify errors do not print secrets. No real credential rotation or deployment is included in this proposal.

### T5 — Continuously test actual booking transactions on PostgreSQL

**Observed:** `planning/service.py::lock_proposal_resources` locks request, vacation, bed unit, and operating room rows; confirmation rechecks feasibility before acceptance. `tests/check_postgres_concurrency.py` already contains a guarded disposable-database race check. CI currently runs `pytest` without a PostgreSQL service or an invocation of this standalone check. The existing documentation reports a prior successful run; that is not continuous regression coverage.

**Proposal:** retain the disposable-database guards and run the existing scenario in a dedicated CI job. Extend meaningful races to competing room capacity, duplicate confirmation of one request, and relevant capacity mutations. Review lock ordering across mutation paths before asserting stronger transaction guarantees. Avoid relying on SQLite tests to establish PostgreSQL locking behavior.

**Acceptance:** concurrent confirmations for one remaining bed yield exactly one booking and one rejection; add equivalent room/request assertions. Exercise the actual endpoint transaction path as well as lower-level helpers. No deadlock or duplicate booking occurs in controlled scenarios. Tests use only marked disposable databases and synthetic records.

### T6 — Record the prediction contract and artifact provenance

**Observed:** `ai/trained.py::_raw_features` deliberately supplies missing anesthesia/practitioner/surgeon fields. Room adapters return the point estimate and omit the model's upper bounds. LOS is rounded up in `clinical/service.py`, while the care type is a deterministic `LOS <= 1` rule; this is not an independently evaluated learned classifier. Artifact hashes and source/model versions already exist, and trained startup fails when artifacts cannot load. Preserve those safeguards.

`bridge_los.py` on main already matches patient/date and subtracts preoperative elapsed days before converting inclusive LOS to offsets. It still averages duplicate patient/date predictions and imputes unmatched rows with medians; match rate is reported but per-case matching provenance is not retained in the returned patient frame. Do not reintroduce the older branch's identifier or LOS behavior.

**Proposal:** define an artifact manifest containing target/unit, feature schema, package versions, artifact hash, calibration provenance, and approved input mode. Use synthetic stub artifacts for adapter tests. Preserve matched/imputed status and aggregate counts; decide explicitly when insufficient matching should fail. Separately document the room point/upper-bound scheduling choice and LOS rounding rule; changing either is an experimental policy decision.

**Acceptance:** synthetic tests verify missing-feature mapping, units, same-day/preoperative LOS semantics, duplicate-key policy, imputation provenance, malformed artifact handling, and deterministic versions. Any later authorized real-data validation uses the existing `ai/validate_web_models.py` or a reviewed extension and saves aggregate evidence only. No claim that the documented full-feature MAE or calibration applies to consultation inputs without evaluation.

**Evidence limit:** the context documents report missing LOS fitted evidence and missing joint manifests. This assessment did not recover or validate them. Do not substitute a report repeating a metric for a fitted artifact or recreate models during this phase.

### T7 — Keep replanning ownership explicit

**Observed:** `planning/replanning.py` persists events/runs but uses a process-local `threading.Lock`. Startup and processing call `recover_interrupted_runs`, which marks running records interrupted. The design explicitly requires one API process; the Docker command currently enforces one worker. A second process/replica would not share the lock and could misclassify live work. Failed batches remain visible and retry depends on a later change/retry. This is a documented limitation, not a reproduced race.

**Proposal:** initially enforce and document single-owner operation, failed-run visibility, explicit retry, and bounded shutdown behavior. If multiple replicas are needed, design a database claim/lease and idempotent publication protocol as a separate change. Do not simply increase worker count.

**Acceptance:** isolated restart, publication failure, and retry tests preserve confirmed bookings and earlier valid proposals; pending work remains discoverable. A controlled two-owner test is required before claiming multi-process support. Preserve the current practice of logging exception types rather than sensitive exception text.

### T8 — Make clean installation and project state reproducible

**Observed:** root `README.md` still says the project is exploratory and predictive models, scheduling, and the operational application are unimplemented. `TEST_PLAN.md` mixes older five-method descriptions with extensions. Root research dependencies use open lower bounds; API and frontend have lockfiles and frozen installs. Research CI therefore resolves a less reproducible environment than the application jobs. No package-index availability or install failure was checked here.

**Proposal:** update the component map, research/API/frontend setup commands, fixture/trained distinction, single-worker limit, optional confidential-data tests, and separate suite commands. Lock or constrain the research environment for the selected Python version; avoid requiring every notebook dependency for a minimal runtime test job where practical. Reconcile shared prediction/simulation dependency ranges with the API lock through actual clean installation.

**Acceptance:** a clean isolated checkout can install and run documented synthetic research/API checks and frontend check/build with recorded tool versions. Report skips by reason, especially missing data and display. Documentation links resolve; artifact acquisition remains through authorized channels. Do not copy the original worktree's environment or confidential files as a shortcut.

### T9 — Plan persistent schema evolution

**Observed:** `bootstrap.py::init_db` calls `SQLModel.metadata.create_all` and explicitly leaves migrations as a TODO. Table creation does not provide a versioned upgrade path for changed existing columns or constraints.

**Proposal:** introduce a baseline and reviewed migrations before changing a persistent deployed schema. Keep disposable test initialization straightforward. Define backup/restore and upgrade handling for the supported database engines.

**Acceptance:** synthetic empty-database initialization and upgrade from the baseline preserve bookings, predictions, queue records, and role mappings. A failed migration leaves a documented recovery path. Never run migration experiments against the original or deployed database.

### T10 — Improve comparison evidence after correctness work

**Context:** the impact document finds a conditional hybrid advantage on one fragmented legacy workload with unequal search effort and positive overload. It also distinguishes OR load from bed load, predicted scenario outcomes from observed outcomes, and full reevaluation from truncated optimization. Those distinctions remain essential.

**Proposal:** if selected later, compare a simple baseline, SA, and selected hybrid(s) on multiple independent synthetic workloads under both explicit evaluation and wall-time budgets. Save protocol version, seeds, resource calendar, LOS convention, method settings, objective components, full-stay feasibility, deferred cases, runtime, and termination reason. Use paired workload-level analysis; repeated search seeds are not independent hospital workloads. Profile before optimizing hot loops or adding methods.

**Acceptance:** synthetic protocol smoke tests establish deterministic fixed-evaluation runs and complete manifests; time-budget runs report actual effort. Keep separate directories for new campaigns. Any confidential-data/model campaign needs a separately selected scope and remains outside this assessment. Existing results and article tables remain unchanged.

## Recommended selection and sequencing

1. **First review batch:** T1, T2, and T3. T1/T2 address the most concrete research correctness gaps; T3 is a small independent release safeguard. Review T2's calendar and compatibility policy before coding. If a shared deployment is imminent, include T4 in this batch.
2. **Validation batch:** T5 plus synthetic portions of T6, with T8's isolated environment setup. This makes booking and adapter guarantees reviewable without real patient data or retraining.
3. **Operational batch:** T7 and T9 when restart, replica, or persistent-schema requirements justify them. Preserve the single-worker restriction until a replacement is validated.
4. **Research batch:** T10 only after the corrected protocol is stable and a separate campaign is selected. New algorithms and wholesale refactors are lower value than correctness and comparable evidence at this stage.

Each selected change should be a focused reviewable diff with its own relevant synthetic checks. Record any semantic change under a new protocol version. A passing syntax check or fixture suite must never be presented as clinical validation, model reproduction, or proof of hospital benefit.

## Review decisions still needed

- Select the first improvement IDs; no implementation is authorized by this document.
- For T1: decide whether unmatched specialties fail immediately or become explicitly unassigned; do not silently allow incompatible assignments.
- For T2: specify capacity after the operation calendar and whether legacy mode remains the default for historical commands.
- For T4/T7/T9: identify whether the next target is a local demonstration or a shared persistent service. This determines urgency, rather than assuming production requirements.
- For T6/T10: choose whether artifact recovery and new experiments are in scope later. Neither is required to approve the initial synthetic correctness work.

Assessment output is limited to this plan. The original repository, final-report worktree, models, datasets, results, and article are preserved.
