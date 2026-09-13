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

The repository is currently at the exploratory-analysis stage:

- [`EDA_donees_bloc.ipynb`](EDA_donees_bloc.ipynb) provides an initial, unexecuted data-analysis workflow;
- [`data_dictionary_donees_bloc.md`](data_dictionary_donees_bloc.md) documents and validates the workbook schema;
- [`docs/patient-workflow.md`](docs/patient-workflow.md) provides a first activity-diagram draft of the planned surgical-patient journey;
- [`report/`](report/) contains the collaborative LaTeX report and its local build instructions;
- [`requirements.txt`](requirements.txt) lists the Python dependencies required by the notebook.

The notebook covers schema inspection, missing values, duplicate rows, derived ages and durations, monthly and weekday activity, common clinical categories, operating-room timing, and duration comparisons by intervention type. Identifier columns are omitted from row-level previews and charts.

Predictive models, scheduling algorithms, comparative experiments, and an end-user application have not yet been implemented.

## Repository structure

```text
.
├── EDA_donees_bloc.ipynb          # Initial exploratory data analysis
├── data_dictionary_donees_bloc.md # Description of the 30 source columns
├── docs/
│   └── patient-workflow.md        # Versioned patient-journey diagram
├── report/                         # Collaborative LaTeX report sources
├── requirements.txt               # Python analysis dependencies
├── resources/                     # Local-only data and project briefs (ignored)
└── README.md
```

## Getting started

### 1. Create a Python environment

Python 3.10 or newer is recommended.

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

The notebook currently looks for the workbook in its working directory. Before running it, update its `DATA_FILE` configuration cell to:

```python
DATA_FILE = Path("resources/donees bloc anonyme pour centrale 2026.xlsx")
```

### 3. Start JupyterLab

From the repository root:

```bash
jupyter lab
```

Open `EDA_donees_bloc.ipynb`, select the virtual-environment kernel, and run the cells in order.

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
