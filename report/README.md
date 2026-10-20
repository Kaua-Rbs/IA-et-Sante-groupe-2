# Fil rouge Report

English Elsevier article integrating the data and LOS contributions with
verified room/Mesa experiments and a separate median/oracle comparison.
All content follows the eleven items in
`resources/Sommaire du rapport Fil rouge.pdf`: Elsevier front matter is item 1,
and numbered sections run from Introduction (2) to References (11).
The data audit is nested under Experimental Design.

The room campaign contains 576 execution replays from 144 initial plans.
The separate duration-information campaign contains 1152 replays from 288
initial plans; its median reruns are not pooled with the first campaign.
Attribution and interpretation are recorded in [INCORPORATION.md](INCORPORATION.md),
with source scope in [SOURCES.md](SOURCES.md). The author list names all six
team members; the study does not establish clinical validation. Learned room-duration models are
reviewed at the protocol level; the reported room experiments use medians
or explicit oracle information.

## Building the report

From the repository root:

```bash
python3 report/build.py
```

Or from `report/`:

```bash
make pdf
```

The script selects the first available engine in this order: `latexmk`,
`pdflatex` with `bibtex`, or `tectonic`. Use `--engine tectonic` and
`--tectonic /path/to/tectonic` to select an engine explicitly. The script
also recognises the Tectonic bundled with the ChatGPT application on this
machine. No additional Python packages are required.

With a conventional TeX distribution, install Latin Modern, `microtype`,
`booktabs`, `tabularx`, `float`, `placeins`, `xurl`, `hyperref` and `natbib`. English uses LaTeX's
default language settings. Tectonic downloads missing TeX resources on the first build, so
network access may be required. Sources are copied to `report/build/` before
compilation. The final PDF is written to `output/pdf/rapport-fil-rouge.pdf`.
These generated files are ignored by Git.

For Overleaf, upload the `.tex`, `.bib`, `.cls` and `.bst` files together
with the `sections/`, `tables/` and `figures/` directories,
then select `main.tex` and pdfLaTeX. Neither
`resources/` nor the hospital datasets are required.

## Contents

- `main.tex`: preamble, title, abstract, keywords and active sections.
- `sections/02-introduction.tex`: background, research question, scope and contributions.
- `sections/03-literature-review.tex`: review and comparison table.
- `sections/04-problem-description.tex`: decisions, resources, constraints and performance criteria.
- `sections/05-mathematical-formulation.tex`: aggregate and room formulations with distinct objectives.
- `sections/06-hybrid-approach.tex`: hybrid algorithm, shared search profile and Mesa acceptance loop.
- `sections/07-experimental-design.tex`: data/prediction design, LOS and room protocols, verification and detailed audit.
- `sections/08-results.tex`: LOS, room execution and duration-information results.
- `sections/09-discussion.tex`: interpretation, managerial implications and limitations.
- `sections/10-conclusion.tex`: findings, limitations and research directions.
- `contributions/`: exact source texts, scripts and result CSVs with commit/file hashes.
- `INCORPORATION.md`: attribution, integration map and evidence-based corrections.
- `scripts/check_report.py`: structure, citations, figure and pinned-source checks.
- `scripts/summarise_los_results.py`, `scripts/summarise_room_results.py`: reproducible table and figure generation.
- `tables/`, `figures/`: generated aggregate report assets.
- `bibliography.bib`: 27 cited references, including attributed internal studies.
- `SOURCES.md`: provenance and scope of the consulted sources.
- `vendor/elsarticle/`: original sources of the supplied template.
- `elsarticle.cls`, `elsarticle-harv.bst`: class and style usable without `resources/`.

## Supplied template and licence

The report is based on `resources/elsarticle/elsarticle-template-harv.tex`,
using author-year citations, Elsevier's `elsarticle` class version 3.4 of
4 April 2024, and `elsarticle-harv.bst`. `main.tex` adapts the template to
the project. The example journal name has been replaced with the project
name; this document is not presented as a submission to EJOR.

The article uses Elsevier's single-column `3p` layout, 10-point body text, 8-point references and A4 paper. The outline gives an indicative 15-to-20-page target; final editorial
review removes repeated exposition while retaining both experiment families.
The unmodified source archive is not included in the PDF.

The original `elsarticle.dtx`, `elsarticle.ins`, author-year template and
README are retained in `vendor/elsarticle/`. The class was extracted from
the `.dtx` using the supplied `.ins` installer, without modifying its code;
the `.bst` is copied verbatim. The Elsevier notices and LPPL version 1.3 or
later licence are preserved. With TeX installed, regenerate the class by
running `latex elsarticle.ins` in that directory, then copy the resulting
`elsarticle.cls` to the root of `report/`.

## Scientific scope

The text distinguishes the original session-and-bed model from the
operational room model coupled with Mesa. Their scores are not transferred
between models. It also distinguishes hybrid Tabu-Simulated Annealing
from rescheduling within the simulation. Realised durations are not solver
inputs in the normal planning scenario.

Descriptions of the project refer to the code and documentation on the
starting branch `feat/mesa-historical-simulation`, at commit `7894aea`.
Bibliographic references support the literature review; internal documents
describe the implementation without providing clinical validation. The
pre-existing local change to `preprocessing_los.ipynb` is outside the report's
scope. No private dataset is copied into this directory.

## Regenerating the LOS assets

From the repository root, use the existing project environment:

```bash
venv/bin/python report/scripts/summarise_los_results.py
python3 report/build.py
```

Asset generation uses Matplotlib and NumPy from the project environment.
It reads pinned aggregate CSVs, checks their numerical identities and seed
pairing, and regenerates three tables, three figures and a JSON summary.
Ordinary PDF builds use the included assets and need no additional Python
packages. No hospital workbook, individual record, model artefact or private
prediction is copied into the source archive. The integration reuses saved
results; it does not claim to rerun model training or the original campaign.

## Regenerating and auditing the room-study assets

```bash
venv/bin/python report/scripts/summarise_room_results.py
python3 report/build.py
```

This uses pinned shareable aggregates in `contributions/room-study/`, verifies
file hashes, paired run coverage, case conservation and no-closure equivalence,
and generates five tables, one figure and a JSON summary. It does not need
private workbooks, saved ML models or episode logs.

For the optional independent check of the original local episode exports:

```bash
venv/bin/python report/scripts/audit_room_results.py
```

That check needs the existing ignored directories
`artifacts/comparison-2026-09-28/` and `artifacts/full-duration-comparison/`.
It checks 1728 execution records and their shared initial schedules. Only
an aggregate audit receipt is written into the report; episode records remain
outside version control. Running this audit does not rerun the campaigns.

## Pre-push checks

From the repository root:

```bash
python3 report/scripts/check_report.py
venv/bin/python report/scripts/summarise_los_results.py
venv/bin/python report/scripts/summarise_room_results.py
python3 report/build.py
```

The checker validates the eleven-part outline, references, abstract/keywords,
figure inputs and 24 pinned source-file hashes. Local writing notes, build
files, PDFs and private hospital inputs are excluded from the report's Git
file set. The report can be compiled from its source and included assets
without `resources/`, `artifacts/` or the contribution archive.
