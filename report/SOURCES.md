# Source Provenance for the Initial Draft

Sources consulted and bibliographic metadata checked on 19 October 2026.
This is a focused selection rather than an exhaustive systematic review.
Claims about methods are restricted to the content actually accessible;
external quantitative results are not transferred to this project.

## Cited publications

| BibTeX key | Source consulted | Use and scope |
| --- | --- | --- |
| `cardoen2010` | [Publisher article and abstract](https://doi.org/10.1016/j.ejor.2009.04.011) | Classification of problems, resources, criteria and uncertainty; experimental results are not reproduced. |
| `guerriero2011` | [Publisher abstract](https://link.springer.com/article/10.1007/s10729-010-9143-6) | Overview of optimisation and simulation models; abstract access, without detailed analysis of the studies reviewed. |
| `cardoen2009` | [Publisher record and abstract](https://www.sciencedirect.com/science/article/abs/pii/S0305054808002384) | Example of branch-and-price for day-care sequencing with recovery resources; no claims about solved instance sizes or computational performance. |
| `fei2010` | [Detailed abstract in the UCLouvain institutional repository](https://research.dial.uclouvain.be/entities/publication/51f9e17e-a90d-497e-9fb6-37099bdadf8a) | Two phases, set partitioning, a column-generation heuristic and a hybrid genetic algorithm; the record does not provide full-text access. |
| `denton2007` | [Publisher page](https://link.springer.com/article/10.1007/s10729-006-9005-4) and [article in the author's archive](https://btdenton.engin.umich.edu/wp-content/uploads/sites/138/2015/08/Denton-2007.pdf) | Sequencing and scheduling under uncertainty; methodological reference without reproducing numerical results. |
| `kirkpatrick1983` | [Original article, Science](https://doi.org/10.1126/science.220.4598.671) | Simulated annealing and acceptance of deteriorating moves. |
| `glover1989` | [Original article, INFORMS](https://doi.org/10.1287/ijoc.1.3.190) | Tabu memory and exploration beyond local improvement. |
| `dorigo1996` | [Original article, IEEE](https://doi.org/10.1109/3477.484436) | General pheromone and probabilistic construction mechanisms; no hospital application is attributed to this article. |
| `vieira2025` | Local PDF `resources/2501.10243v2.pdf` and [matching arXiv version](https://arxiv.org/abs/2501.10243v2) | Abstract and presentation of RKO, a shared decoder, annealing, BRKGA/Q-learning and iterated local search. The bibliography cites the supplied preprint rather than a later published version. |
| `rachuba2026` | Local PDF `resources/s00291-024-00797-5.pdf` and [publisher text and metadata](https://link.springer.com/article/10.1007/s00291-024-00797-5) | Integrated planning and resource interdependencies. The local PDF bears the 2024 online-publication date; current metadata gives OR Spectrum 48, 733-786 (2026), which determines the citation year and key. |
| `schouten2023` | [Publisher text](https://link.springer.com/article/10.1007/s10916-023-01912-9) and [TU Delft record](https://research.tudelft.nl/en/publications/operating-room-performance-optimization-metrics-a-systematic-revi/) | Diversity of metrics and care in interpreting optimisation; not used to establish the completeness of this review's corpus. |
| `dupre2025` | Local PDF `resources/OT-LOS_Prediction_Dupre_Main.pdf`, particularly the abstract and target definitions | Room occupancy and hospital length of stay in emergency surgery, residual errors and limits to transferability. DOI 10.1007/s10877-025-01341-8 is also recorded in the HAL PDF. |
| `lex2025` | Local PDF `resources/medinform-v13-e70857.pdf` and [publisher text](https://medinform.jmir.org/2025/1/e70857/) | Prediction followed by optimisation, overtime/underutilisation trade-offs and retrospective design. |
| `lex2026` | Local PDF `resources/bmjhci-33-1.pdf` | Prediction followed by optimisation in arthroplasty, single-centre design and evaluation of simulated schedules; DOI 10.1136/bmjhci-2024-101420. |

## Internal project sources

Code reference at the start of drafting: commit `7894aea` on
`feat/mesa-historical-simulation`. These sources support the description
of the project and its limitations; they are not scientific publications:

- `AGENTS.md` and `optimiseur/optimizer.py`: session-and-bed model,
  five methods, and maximised fitness equal to the negative of cost.
- `optimiseur/data_bridge.py`: retrospective session-model inputs, generated
  operating sessions and speciality proxy. `PlanningProblem._occupation`
  in `optimiseur/optimizer.py` defines inclusive, horizon-truncated bed counting;
  `PlanningProblem.fitness` defines soft capacity penalties rather than hard limits.
- `hospital_sim/room_problem.py` and `hospital_sim/metaheuristics.py`:
  assignments, decoder, objective and adapters.
- `hospital_sim/historical_data.py` and `hospital_sim/simulation.py`:
  predicted/realised information and execution.
- `hospital_sim/domain.py`, `hospital_sim/scheduling.py` and
  `hospital_sim/instances.py`: room configuration, proposal validation,
  fixed commitments, start-based closures and the distinct oracle scenario.
  These files, together with `room_problem.py`, are the implementation
  references for Section 4, Problem Description. Metric definitions are
  checked against `simulation.metrics`, including the utilisation denominator
  and the restriction of start-delay statistics to initially assigned cases.
- `docs/metaheuristics-mesa-assembly.md`,
  `docs/metaheuristics-mesa-comparison-fr.md` and
  `docs/mesa-historical-simulation.md`: scope, information control,
  rescheduling events and comparison limitations.

The supplied report outline and `resources/elsarticle/` directory provide
structure and formatting references. Their instructions are not scientific
findings. Other PDFs are not cited solely because they are present in the
corpus. No patient records or hospital identifiers are included in the report.

## Report-branch incorporation (20 October 2026)

Substantive text from `report/latex` at `8708301f03d4f365e4ec25025fb59cff4f437d93`
and the original/updated LOS reports from `model/los-bridge` at
`d2dc2260d7b9c4b1ed2a49e6889b08fe0c484888` are incorporated in English.
Exact source copies, experiment scripts and aggregate result CSVs are stored
under `contributions/`, with hashes in `contributions/manifest.json`.
[INCORPORATION.md](INCORPORATION.md) maps the material into the article and
records the changes in interpretation needed to agree with the code and CSVs.
The source texts are internal contributions, not peer-reviewed publications.

The additional bibliography entries from the older report were checked against
publisher/author records: Al Amin et al. (10.1007/s12351-024-00884-z), Wang et al.
(10.1016/j.orhc.2021.100323), Carter and Ketabi (10.1016/j.orhc.2023.100411),
Ahmadian et al. (10.1007/s00500-025-10620-0), Merghani et al.
(10.7759/cureus.79400), and the Carnegie Mellon institutional account of
Shehadeh et al. (10.1016/j.ejor.2025.07.006). Kayvanfar et al.'s publisher
record identifies 10.1016/j.eswa.2026.134018; its online-2026/volume-2027
status is retained. Only its broad predictive-prescriptive framing is used;
no detailed BioBERT, calibration or numerical result is asserted here.

The LOS report's methodological references are retained: Chen and Guestrin,
XGBoost (10.1145/2939672.2939785; author preprint arXiv:1603.02754), and
Papadopoulos et al., Inductive Confidence Machines for Regression
(10.1007/3-540-36755-1_29). The model's reported performance and conformal
coverage remain attributed to the source contribution pending artefact-level
verification. All new scheduling tables and figures use pinned aggregate CSVs,
not patient records or the original report's rounded tables.

## Project and experiment review (20 October 2026)

The source review covered the current room model, decoder, coordinator,
Mesa execution, historical adapter, instance generator and budget control;
the two model-preprocessing notebooks; campaign scripts and tests; and the
cached `model/or-occupation` branch at
`a9607f9bc3247bcb8e8af094c04e797ee69505e7`.
Its `surgery_duration.py` and `docs/surgery_duration_review.md` distinguish
current selection/calibration from historical metric tables. This report
uses that protocol description, not unverified current-model performance.
The pre-existing local LOS-notebook change was read but not modified.

Two separate room campaigns are pinned under `contributions/room-study/`:

- Primary: `docs/comparison-results/{runs.csv,initial-plans.csv,provenance.json}`,
  576 executions and 144 initial plans. Its implementation fingerprint is
  `e6c05b88a7bff50e1e89fe083aa0dca6b9b8c06c7a2b510047cd700f315f75f0`.
- Duration information: aggregate `combined-summary.csv` and selected manifest
  fields from `artifacts/full-duration-comparison/`, 1152 executions and 288
  initial plans. Its fingerprint is
  `92078c6a81c41aa8ac607d122c2703ab9ec4e99bb34140add047c8adfc0aa280`,
  matching the simulation/optimiser source snapshot inspected at `7894aea`. Its manifests
  mark the source checkout dirty; commit alone would not identify that source.

Both identify campaign commit `1ee8d0860cb72aaba25f8536929871773fbcea45`,
with fingerprints distinguishing the evaluated source versions. The normal
median rerun and oracle observations are paired within the second campaign;
median observations are not pooled across campaigns. Original raw exports
remain ignored. The current review checked 1728 local executions and regenerated
all room tables from aggregates. That source snapshot also passed the project suite:
94 tests, 92 passing and two optional tests skipped, followed by the headless
30-patient/five-day demo and its small exact reference. These are implementation
checks and local experiment evidence, not independent clinical validation.
