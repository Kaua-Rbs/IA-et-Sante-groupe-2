# AI-Assisted Operating-Room Scheduling

This repository contains a student engineering project on the prediction and optimization of hospital operating-room activity. The project aims to turn historical hospital data into operational decision support for planning interventions, operating-room sessions, and surgical-bed capacity.

The central problem is that several scarce and interdependent resources must be coordinated at once: patients, surgeons, operating rooms, specialty sessions, care teams, and inpatient or ambulatory beds. Optimizing only the operating room can overload the wards, while optimizing only bed occupancy can leave operating-room capacity underused.

## Project vision

Current scheduling often follows a **push-flow** logic: an intervention is first placed according to the surgeon's schedule, after which the hospital must find the necessary room and bed capacity. This project explores a **pull-flow** approach in which predicted capacity is used to propose better admission and intervention dates.

The intended decision-support system should:

- predict a patient's length of stay and operating-room time;
- estimate whether ambulatory or conventional inpatient capacity is required;
- propose one or more suitable admission dates from forecast room and bed capacity;
- assign interventions to specialty-compatible operating-room sessions;
- use session time effectively while retaining a margin for emergencies and delays;
- account for weekends, holidays, existing appointments, and resource availability;
- explain why a scheduling change or date is recommended;
- preserve the clinician's final decision.

This is therefore a problem at the intersection of machine learning, combinatorial optimization, operations research, and simulation.

## Data

The supplied workbook contains **14,649 hospital cases and 30 columns**. It includes:

- admission, discharge, birth, and intervention dates;
- anonymized case and patient identifiers;
- principal and associated CIM-10 diagnosis codes;
- CCAM medical-procedure codes;
- GHM and GHS classifications;
- practitioner and surgeon fields;
- preoperative, room-entry, incision, and room-exit times;
- anesthesia information, length of stay, and intervention type.

See [`data_dictionary_donees_bloc.md`](data_dictionary_donees_bloc.md) for column-level definitions, relationships, validation findings, and remaining interpretation questions.

### Confidentiality

The project data is not versioned. The entire `resources/` directory is excluded through `.gitignore` because it contains the source workbook and internal project documents.

Although the patient identifier is anonymized or pseudonymized, the workbook still contains dates, repeated patient identifiers, and personnel-related fields. Treat it as confidential: use it only in an authorized environment, do not commit it, and do not expose row-level records in notebooks, figures, logs, or the final report.

## Current state

The repository includes exploratory analysis and an initial simulation benchmark:

- [`EDA_donees_bloc.ipynb`](EDA_donees_bloc.ipynb) provides an executable data-analysis and initial cleaning workflow;
- [`preprocessing_los.ipynb`](preprocessing_los.ipynb) creates a leakage-conscious length-of-stay modeling table;
- [`preprocessing_surgery_duration.ipynb`](preprocessing_surgery_duration.ipynb) creates a leakage-conscious operating-room-duration modeling table;
- [`dashboard.py`](dashboard.py) provides an interactive, aggregate view of the preprocessed data;
- [`data_dictionary_donees_bloc.md`](data_dictionary_donees_bloc.md) documents and validates the workbook schema;
- [`docs/patient-workflow.md`](docs/patient-workflow.md) provides a first activity-diagram draft of the planned surgical-patient journey;
- [`requirements.txt`](requirements.txt) lists the Python dependencies required by the notebooks, dashboard, and Mesa simulation.

The notebook covers schema inspection, missing values, duplicate rows, derived ages and durations, monthly and weekday activity, common clinical categories, operating-room timing, and duration comparisons by intervention type. Identifier columns are omitted from row-level previews and charts.

An initial asynchronous coordination skeleton is available in [`hospital_sim/`](hospital_sim/),
with adapter interfaces, versioned state, explicit proposal validation and acceptance, and a
synthetic disruption demonstration. See the [coordination-core guide](docs/coordination-core.md)
for its boundaries and integration points. A room-only Mesa simulation now connects the cleaned
workbook to this coordinator and compares static and reactive baseline schedules.

The [optimizer package](optimiseur/README.md) supplies five metaheuristics, a standalone CLI, charts, a Tkinter interface, and an [explanatory notebook](notebooks/guide_optimisation.ipynb). Trained ML models and an operational decision-support application remain to be integrated. The simulation uses historical median duration estimates and compares the baseline with all five methods through a shared room decoder. See [the assembly guide](docs/metaheuristics-mesa-assembly.md).

## Repository structure

```text
.
├── EDA_donees_bloc.ipynb          # Initial exploratory data analysis
├── preprocessing_los.ipynb        # Length-of-stay model preprocessing
├── preprocessing_surgery_duration.ipynb # Surgery-duration model preprocessing
├── dashboard.py                    # Interactive aggregate-data dashboard
├── data_dictionary_donees_bloc.md # Description of the 30 source columns
├── docs/
│   └── patient-workflow.md        # Versioned patient-journey diagram
├── requirements.txt               # Python analysis dependencies
├── resources/                     # Local-only data and project briefs (ignored)
└── README.md
```

## Getting started

### 1. Create a Python environment

Python 3.12 or newer is required to install the full dependencies, including Mesa 3.5.1.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

### 2. Obtain the data

Obtain the workbook through the team's authorized sharing channel and keep it inside the ignored `resources/` directory:

```text
resources/donees bloc anonyme pour centrale 2026.xlsx
```

The notebook expects the workbook at this location through its `DATA_FILE` configuration:

```python
DATA_FILE = Path("resources/donees bloc anonyme pour centrale 2026.xlsx")
```

When executed, the notebook writes the fully preprocessed table to the ignored Parquet file
`resources/donnees_bloc_pretraitees.parquet`. The export runs after all exclusions and derived
measures, preserves numeric and datetime types, and does not overwrite the source workbook.

### 3. Start JupyterLab

From the repository root:

```bash
jupyter lab
```

Open `EDA_donees_bloc.ipynb`, select the virtual-environment kernel, and run the cells in order.

### 4. Prepare model datasets

After running the EDA notebook, run the two model-specific preprocessing notebooks:

- `preprocessing_los.ipynb` writes `resources/model_los_dataset.parquet`;
- `preprocessing_surgery_duration.ipynb` writes `resources/model_surgery_duration_dataset.parquet`.

Both outputs contain patient-disjoint temporal train, validation, and test splits. Columns beginning
with `split_` are audit metadata and must not be passed to a model. The notebooks retain categorical
features as strings so their encoding can be fitted inside each model pipeline without leakage.

### 5. Start the dashboard

After the notebook has created the preprocessed Parquet file, run:

```bash
streamlit run dashboard.py
```

Use the sidebar to select a variable and one or more values—for example,
`interv_type = Varices`. The dashboard compares the selection with the complete dataset, shows
room-time and corrected-stay distributions, provides other numeric measures, breaks the selection
down by a second category, and plots activity over time. It intentionally presents aggregate
results only and does not expose patient or staff-level rows.

## Planned methodology

The expected work is organized into four main stages:

1. **Understand and prepare the data** — assess quality, clarify business rules, engineer durations and capacity indicators, and model the patient workflow from admission to discharge.
1. **Predict operational quantities** — estimate length of stay, operating-room duration, and the type of capacity needed for a future patient.
1. **Formulate the scheduling problem** — define decision variables, resource and compatibility constraints, emergency margins, and objectives for room utilization and bed-occupancy smoothing.
1. **Optimize and evaluate schedules** — implement and compare tabu search, simulated annealing, and genetic algorithms on small and large problem instances.

Evaluation should report both optimization quality and operational impact, including room utilization, bed-occupancy variability, delays or waiting time, constraint violations, robustness to unexpected events, and computation time.

## Contributing

For the six-person team, keep runnable code, analysis, and future report sources on `main`. Make changes on short-lived branches and merge them through reviewed pull requests. Do not commit directly to `main`.

### Branches

Create a branch for one clearly defined task and use a descriptive `<area>/<topic>` name, for example:

```text
eda/timing-quality
model/length-of-stay
optim/tabu-search
report/data-analysis
fix/missing-timestamps
```

Start from an up-to-date `main`, keep the branch focused, and delete it after merging. If a branch lives for more than a few days, synchronize it with `main` regularly to detect conflicts early.

### Atomic commits

Each commit should represent one logical, reviewable change. A commit should not mix unrelated refactoring, analysis, documentation, and formatting changes. It should leave the repository in a usable state whenever possible.

Before committing:

- review the staged diff with `git diff --staged`;
- use `git add -p` when a file contains several unrelated changes;
- exclude temporary files, generated artifacts, credentials, and confidential data;
- run the checks relevant to the files being changed.

### Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) with an optional scope:

```text
<type>(<scope>): <short imperative description>
```

Common types for this project are:

- `feat`: add a new capability, analysis, model, or optimization method;
- `fix`: correct incorrect behavior or a data-processing error;
- `docs`: change documentation or report content only;
- `refactor`: restructure code without changing its behavior;
- `test`: add or update tests;
- `perf`: improve performance;
- `chore`: maintain tooling, dependencies, or repository configuration.

Examples:

```text
feat(eda): add operating-room duration analysis
fix(data): handle procedures crossing midnight
docs(report): describe the tabu-search formulation
refactor(optim): extract the schedule scoring function
chore(deps): add scikit-learn dependency
```

Keep the first line concise, use the imperative mood, and explain the motivation or important trade-offs in the commit body when the reason is not obvious. Mark incompatible changes with `!` and a `BREAKING CHANGE:` footer.

### Pull requests and review

A pull request should be small enough to review comfortably and should contain:

- a short explanation of the problem and the chosen solution;
- the affected data, model, notebook, or report section;
- instructions for reproducing or validating the result;
- relevant metrics, plots, or screenshots when behavior changes;
- any assumptions, limitations, privacy implications, or follow-up work.

At least one teammate should approve a pull request before it is merged. Reviewers should check correctness, reproducibility, readability, confidentiality, and consistency with the project objectives. Resolve discussions rather than silently dismissing them, and prefer squash merging when a branch contains fix-up commits that are not useful to the permanent history.

### Notebooks, data, and report files

- Keep notebooks executable from top to bottom and document required inputs.
- Remove debugging cells and clear unnecessary outputs before committing.
- Do not display or commit row-level patient, case, practitioner, or surgeon information.
- Put reusable processing or modeling logic in Python modules once it becomes too large for a notebook.
- Do not commit the contents of `resources/`, local environments, caches, generated PDFs, or LaTeX auxiliary files.
- Give generated figures descriptive names and record the code and parameters used to produce them.
- Split the LaTeX report into one file per section and agree on section ownership to reduce merge conflicts.

## Important interpretation limits

Several business rules must be confirmed before modeling results can be used operationally, particularly the meaning of zero-valued timestamps, whether interventions can cross midnight, the precise role represented by `Praticien`, and whether `Date Inter` is always the principal intervention date.

All current analyses are exploratory. Any future recommendation system must be validated on real hospital workflows and should support—not replace—clinical and operational judgment.

## Mesa simulation on historical workloads

A room-only Mesa 3.5.1 experiment connects the cleaned Excel dataset to the
coordination core. It compares static and reactive scheduling under
explicit resource assumptions. Python 3.12+ is required for this experiment.

```bash
python -m pip install -r requirements.txt
python -m hospital_sim.experiment --output artifacts/mesa-first-run
```

See [the simulation guide](docs/mesa-historical-simulation.md) for data mapping,
assumptions, commands, metrics, and the adapter interface for future metaheuristics.

Run all methods with `--methods baseline annealing tabu genetic hybrid aco`.
The [assembly guide](docs/metaheuristics-mesa-assembly.md) provides exact small
benchmarks, generated 100/300-case workloads, and paired comparison commands.
