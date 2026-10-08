"""Interactive dashboard for the preprocessed operating-room dataset.

Run from the repository root with:
    streamlit run dashboard.py
"""

from pathlib import Path
import unicodedata

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


DATA_FILE = Path("resources/donnees_bloc_pretraitees.parquet")
MISSING_LABEL = "(Missing)"
SENSITIVE_COLUMNS = {"no_cas", "id_patient", "praticien", "nom_chir"}

FILTER_PRIORITY = [
    "interv_type",
    "anesth_type",
    "anesth_loco_reg",
    "sexe",
    "ghm_code",
    "cim_diag_pr",
    "ccam_1",
    "annee",
]

MEASURE_LABELS = {
    "room_duration_min": "Room duration (minutes)",
    "duree_sejour_corrigee": "Corrected length of stay (days)",
    "age_years": "Age (years)",
    "entry_to_incision_min": "Room entry to incision (minutes)",
    "preop_wait_min": "Preoperative wait (minutes)",
}


st.set_page_config(
    page_title="Operating-room activity dashboard",
    page_icon="🏥",
    layout="wide",
)


@st.cache_data(show_spinner="Loading the preprocessed data…")
def load_data(path: Path) -> pd.DataFrame:
    """Load the typed dataset created by the EDA notebook."""
    return pd.read_parquet(path, engine="pyarrow")


def readable_name(column: str) -> str:
    """Return a compact display label for a snake-case column name."""
    return MEASURE_LABELS.get(column, column.replace("_", " ").title())


def normalized_text(value: object) -> str:
    """Normalize a value for accent- and case-insensitive default matching."""
    return (
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode()
        .casefold()
    )


def display_series(series: pd.Series) -> pd.Series:
    """Create consistent labels for categorical filtering and plotting."""
    return series.astype("string").fillna(MISSING_LABEL)


def median_text(frame: pd.DataFrame, column: str, suffix: str) -> str:
    """Format a median without failing when a measure is entirely missing."""
    if column not in frame:
        return "N/A"
    value = pd.to_numeric(frame[column], errors="coerce").median()
    return "N/A" if pd.isna(value) else f"{value:,.1f} {suffix}"


def distribution_figure(
    all_data: pd.Series,
    selected_data: pd.Series,
    label: str,
    show_comparison: bool,
) -> go.Figure:
    """Build comparable normalized histograms with compact box plots."""
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.78, 0.22],
    )

    if show_comparison:
        figure.add_trace(
            go.Histogram(
                x=all_data,
                name="All cases",
                nbinsx=35,
                histnorm="probability",
                marker_color="#CBD5E1",
                opacity=0.75,
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Box(
                x=all_data,
                name="All cases",
                marker_color="#94A3B8",
                boxpoints=False,
                showlegend=False,
            ),
            row=2,
            col=1,
        )

    figure.add_trace(
        go.Histogram(
            x=selected_data,
            name="Current selection",
            nbinsx=35,
            histnorm="probability",
            marker_color="#2563EB",
            opacity=0.72,
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Box(
            x=selected_data,
            name="Current selection",
            marker_color="#2563EB",
            boxpoints=False,
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    figure.update_layout(
        title=label,
        barmode="overlay",
        height=390,
        margin=dict(l=20, r=20, t=55, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    figure.update_yaxes(title_text="Share of cases", tickformat=".0%", row=1, col=1)
    figure.update_yaxes(title_text="", showticklabels=False, row=2, col=1)
    figure.update_xaxes(title_text=label, row=2, col=1)
    return figure


st.title("Operating-room activity dashboard")
st.caption(
    "Explore distributions for a selected clinical or operational category. "
    "Only aggregate results are shown; patient and staff-level records are not displayed."
)

if not DATA_FILE.exists():
    st.error(
        f"Preprocessed data was not found at `{DATA_FILE}`. Run all cells in "
        "`EDA_donees_bloc.ipynb` first to create it."
    )
    st.stop()

try:
    data = load_data(DATA_FILE)
except Exception as error:
    st.error(f"The preprocessed data could not be loaded: {error}")
    st.stop()

fallback_filters = [
    column
    for column in data.select_dtypes(include=["object", "string", "category"]).columns
    if column not in SENSITIVE_COLUMNS and 1 < data[column].nunique(dropna=False) <= 500
]
filter_columns = [column for column in FILTER_PRIORITY if column in data]
filter_columns.extend(column for column in fallback_filters if column not in filter_columns)

if not filter_columns:
    st.error("No suitable categorical columns were found in the preprocessed dataset.")
    st.stop()

st.sidebar.header("Filter cases")
filter_column = st.sidebar.selectbox(
    "Variable",
    options=filter_columns,
    format_func=readable_name,
)

filter_labels = display_series(data[filter_column])
filter_counts = filter_labels.value_counts()
filter_options = sorted(filter_counts.index.tolist(), key=normalized_text)

default_values: list[str] = []
if filter_column == "interv_type":
    default_values = [
        value for value in filter_options if "varic" in normalized_text(value)
    ][:1]
if not default_values and len(filter_counts):
    default_values = [str(filter_counts.index[0])]

selected_values = st.sidebar.multiselect(
    "Value",
    options=filter_options,
    default=default_values,
    format_func=lambda value: f"{value} ({filter_counts[value]:,})",
    key=f"selected_values_{filter_column}",
    help="Select one or more values. Clear the selection to include all cases.",
)

if selected_values:
    selection_mask = filter_labels.isin(selected_values)
    selected = data.loc[selection_mask].copy()
    selection_description = ", ".join(map(str, selected_values))
    show_comparison = len(selected) < len(data)
else:
    selected = data.copy()
    selection_description = "All values"
    show_comparison = False

st.sidebar.divider()
available_measures = [column for column in MEASURE_LABELS if column in data]
default_measures = [
    column
    for column in ["room_duration_min", "duree_sejour_corrigee"]
    if column in available_measures
]
selected_measures = st.sidebar.multiselect(
    "Numeric distributions",
    options=available_measures,
    default=default_measures,
    format_func=readable_name,
)
trim_extremes = st.sidebar.checkbox(
    "Trim chart extremes (1st–99th percentiles)",
    value=True,
    help="This affects charts only. KPIs and summary statistics continue to use every row.",
)

st.subheader(f"{readable_name(filter_column)}: {selection_description}")

kpi_columns = st.columns(5)
kpi_columns[0].metric("Cases", f"{len(selected):,}")
kpi_columns[1].metric("Share of dataset", f"{len(selected) / len(data):.1%}")
kpi_columns[2].metric(
    "Median room duration",
    median_text(selected, "room_duration_min", "min"),
)
kpi_columns[3].metric(
    "Median corrected stay",
    median_text(selected, "duree_sejour_corrigee", "days"),
)
kpi_columns[4].metric("Median age", median_text(selected, "age_years", "years"))

distribution_tab, category_tab, activity_tab = st.tabs(
    ["Numeric distributions", "Category breakdown", "Activity over time"]
)

with distribution_tab:
    if not selected_measures:
        st.info("Choose at least one numeric distribution in the sidebar.")
    else:
        if trim_extremes:
            st.caption(
                "Charts are restricted to the overall 1st–99th percentile range so that "
                "extreme values do not compress the main distribution. Summary statistics below are untrimmed."
            )

        chart_columns = st.columns(2)
        for index, measure in enumerate(selected_measures):
            all_values = pd.to_numeric(data[measure], errors="coerce").dropna()
            selected_values_numeric = pd.to_numeric(selected[measure], errors="coerce").dropna()

            if trim_extremes and not all_values.empty:
                lower, upper = all_values.quantile([0.01, 0.99])
                all_chart_values = all_values[all_values.between(lower, upper)]
                selected_chart_values = selected_values_numeric[
                    selected_values_numeric.between(lower, upper)
                ]
            else:
                all_chart_values = all_values
                selected_chart_values = selected_values_numeric

            with chart_columns[index % 2]:
                if selected_chart_values.empty:
                    st.warning(f"No usable values for {readable_name(measure)}.")
                else:
                    figure = distribution_figure(
                        all_chart_values,
                        selected_chart_values,
                        readable_name(measure),
                        show_comparison,
                    )
                    st.plotly_chart(figure, width="stretch")

        summary_rows = []
        for measure in selected_measures:
            values = pd.to_numeric(selected[measure], errors="coerce").dropna()
            summary_rows.append(
                {
                    "Measure": readable_name(measure),
                    "Available cases": len(values),
                    "Missing (%)": (1 - len(values) / len(selected)) * 100 if len(selected) else np.nan,
                    "Mean": values.mean(),
                    "Median": values.median(),
                    "90th percentile": values.quantile(0.9),
                    "Maximum": values.max(),
                }
            )
        summary_table = pd.DataFrame(summary_rows).set_index("Measure")
        st.dataframe(
            summary_table.style.format(
                {
                    "Available cases": "{:,.0f}",
                    "Missing (%)": "{:.1f}",
                    "Mean": "{:.1f}",
                    "Median": "{:.1f}",
                    "90th percentile": "{:.1f}",
                    "Maximum": "{:.1f}",
                },
                na_rep="N/A",
            ),
            width="stretch",
        )

with category_tab:
    breakdown_options = [column for column in filter_columns if column != filter_column]
    if not breakdown_options:
        st.info("No additional categorical variable is available for a breakdown.")
    else:
        default_breakdown = (
            breakdown_options.index("anesth_type")
            if "anesth_type" in breakdown_options
            else 0
        )
        breakdown_column = st.selectbox(
            "Break selection down by",
            options=breakdown_options,
            index=default_breakdown,
            format_func=readable_name,
        )
        category_limit = st.slider("Number of categories", 5, 30, 15)
        breakdown = (
            display_series(selected[breakdown_column])
            .value_counts()
            .head(category_limit)
            .rename_axis("category")
            .reset_index(name="cases")
        )
        breakdown["share"] = breakdown["cases"] / len(selected) if len(selected) else np.nan
        breakdown = breakdown.sort_values("cases")

        category_figure = px.bar(
            breakdown,
            x="cases",
            y="category",
            orientation="h",
            text=breakdown["share"].map(lambda value: f"{value:.1%}"),
            labels={"cases": "Cases", "category": readable_name(breakdown_column)},
            title=f"Most common {readable_name(breakdown_column).lower()} values",
        )
        category_figure.update_traces(marker_color="#0F766E", textposition="outside")
        category_figure.update_layout(
            height=max(380, 28 * len(breakdown)),
            margin=dict(l=20, r=60, t=55, b=20),
        )
        st.plotly_chart(category_figure, width="stretch")

with activity_tab:
    if "date_inter" not in selected:
        st.info("Intervention dates are not available in the preprocessed dataset.")
    else:
        selected_dates = pd.to_datetime(selected["date_inter"], errors="coerce")
        selected_monthly = (
            selected_dates.dropna().to_frame("date_inter").set_index("date_inter").resample("MS").size()
        )
        activity = selected_monthly.rename("Current selection").to_frame()

        if show_comparison:
            all_dates = pd.to_datetime(data["date_inter"], errors="coerce")
            all_monthly = (
                all_dates.dropna().to_frame("date_inter").set_index("date_inter").resample("MS").size()
            )
            activity = activity.join(all_monthly.rename("All cases"), how="outer")

        activity = activity.fillna(0).rename_axis("Month").reset_index()
        activity_long = activity.melt(
            id_vars="Month",
            var_name="Population",
            value_name="Cases",
        )
        activity_figure = px.line(
            activity_long,
            x="Month",
            y="Cases",
            color="Population",
            markers=True,
            title="Interventions per month",
            color_discrete_map={
                "Current selection": "#2563EB",
                "All cases": "#94A3B8",
            },
        )
        activity_figure.update_layout(
            height=450,
            margin=dict(l=20, r=20, t=55, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        )
        st.plotly_chart(activity_figure, width="stretch")

st.caption(
    "This dashboard is exploratory. Zero-time conventions and other unresolved data-quality "
    "assumptions should be confirmed before operational or clinical use."
)
