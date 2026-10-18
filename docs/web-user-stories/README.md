# KYST illustrated user stories

These materials are tracked in the integration branch for team reference and
reuse in the final presentation. See the [team summary](../web-integration-summary.md)
for a brief description of the application changes.

Open `output/pdf/kyst-user-stories.pdf` for the six-page shareable guide.
Open `index.html` in a browser for larger screenshot panels and expandable
consultation and bed-forecast views. Keep the `images/` folder beside the HTML.

The guide is in English and retains the application's French labels.
All screenshots were taken from the application using an isolated SQLite
database populated with synthetic patients. No source hospital records were
read to create the demonstration, and no application database is included.
Previously trained duration and LOS artifacts were used for prediction.

## Contents

- `user-stories.md`: editable narrative and links to complete captures.
- `stories.json`: structured narrative, assumptions and source revision.
- `images/`: original browser screenshots, including complete page captures.
- `capture-regions.json`: observed panel bounds; the build script adjusts the
  sticky navigation offset after visual checking of full-page captures.
- `build_guide.py`: builds the Markdown, HTML, JSON and PDF from those captures.

To rebuild, use Python with `reportlab` and `Pillow`, plus DejaVu Sans fonts at
`/usr/share/fonts/truetype/dejavu/`, then run `python build_guide.py`.

Screenshots show a demonstration of implemented workflows. The Mesa scenarios
use chosen multipliers for execution durations; they are separate from the
historical experiment campaign and do not establish clinical model accuracy.
The application sources and the historical datasets were not modified.
