"""
data_bridge.py
--------------
Pont entre le jeu de donnees reel pretraite par le notebook
``EDA_donees_bloc.ipynb`` et le modele attendu par ``optimizer.py``.

Le notebook EDA produit ``resources/donnees_bloc_pretraitees.parquet`` (une
ligne = une intervention). Le moteur d'optimisation, lui, attend deux tables :

- patients  : patient_id, specialite, duree_operatoire, duree_sejour
- vacations : vacation_id, jour, specialite, capacite_min

Ce module fabrique ces deux tables a partir du Parquet, sans jamais modifier
le notebook ni le classeur source.

Points de vigilance :

- Le notebook EDA ne contient pas de colonne ``specialite`` : elle est
  reconstruite par ``derive_specialite`` (proxy a valider cliniquement, voir
  la docstring). Le resultat n'a pas valeur de verite medicale.
- Les identifiants patients / cas / praticiens sont ecartes ici.
- Les interventions de la fenetre d'horizon choisie deviennent les patients
  a planifier ; les vacations sont generees (jour x specialite).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_PARQUET = Path("resources/donnees_bloc_pretraitees.parquet")
IDENTIFIER_COLUMNS = ["no_cas", "id_patient", "praticien", "nom_chir"]
SPECIALITE_AUTRE = "Autre"


def load_preprocessed(path: str | Path = DEFAULT_PARQUET) -> pd.DataFrame:
    """Charge le Parquet produit par le notebook EDA."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path.resolve()} introuvable. Executez d'abord EDA_donees_bloc.ipynb "
            "pour produire le Parquet pretraite."
        )
    return pd.read_parquet(path, engine="pyarrow")


def derive_specialite(
    df: pd.DataFrame,
    specialite_col: str | None = None,
    max_specialites: int = 6,
) -> pd.Series:
    """Reconstruit une specialite grossiere a partir des champs disponibles.

    Ordre de priorite :
    1. ``specialite_col`` si fourni et present ;
    2. premiere lettre du code CCAM principal (zone anatomique/fonctionnelle) ;
    3. racine du code GHM ;
    4. ``interv_type`` brut ;
    5. constante "Non classe".

    Les modalites au-dela de ``max_specialites`` sont regroupees dans "Autre"
    pour garder un nombre raisonnable de vacations compatibles. Ceci est un
    PROXY : la correspondance specialite chirurgicale reelle doit etre validee
    par un clinicien avant toute conclusion operationnelle.
    """
    if specialite_col and specialite_col in df.columns:
        raw = df[specialite_col].astype("string")
    elif "ccam_1" in df.columns:
        raw = df["ccam_1"].astype("string").str.strip().str[:1]
    elif "ghm_code" in df.columns:
        raw = df["ghm_code"].astype("string").str.strip().str[:3]
    elif "interv_type" in df.columns:
        raw = df["interv_type"].astype("string")
    else:
        return pd.Series(["Non classe"] * len(df), index=df.index, dtype="string")

    raw = raw.str.strip().replace({"": pd.NA, "<NA>": pd.NA})
    raw = raw.fillna("Non classe")
    top = raw.value_counts().head(max_specialites).index
    return raw.where(raw.isin(top), SPECIALITE_AUTRE).astype("string")


def _fill_by_group(series: pd.Series, groups: pd.Series) -> pd.Series:
    """Remplace les valeurs manquantes par la mediane du groupe, puis globale."""
    med_group = series.groupby(groups).transform("median")
    filled = series.fillna(med_group)
    return filled.fillna(series.median())


def build_patients(
    df: pd.DataFrame,
    specialite_col: str | None = None,
    duration_col: str = "room_duration_min",
    stay_col: str = "duree_sejour_corrigee",
    date_col: str = "date_inter",
    max_specialites: int = 6,
    min_duree_min: int = 15,
) -> pd.DataFrame:
    """Construit la table patients au format de ``optimizer.py``.

    - ``duree_operatoire``  <- duree d'occupation de salle (minutes)
    - ``duree_sejour``      <- duree de sejour corrigee (jours, incluse)
    - ``specialite``        <- proxy derive (voir ``derive_specialite``)
    """
    specialite = derive_specialite(df, specialite_col, max_specialites)

    for col in (duration_col, stay_col):
        if col not in df.columns:
            raise ValueError(
                f"Colonne '{col}' absente du Parquet EDA. Colonnes disponibles : {list(df.columns)}"
            )

    duree = pd.to_numeric(df[duration_col], errors="coerce")
    duree = _fill_by_group(duree, specialite)
    duree = duree.fillna(min_duree_min).clip(lower=min_duree_min).round().astype(int)

    sejour = pd.to_numeric(df[stay_col], errors="coerce")
    sejour = _fill_by_group(sejour, specialite)
    sejour = sejour.fillna(0).clip(lower=0).round().astype(int)

    patients = pd.DataFrame(
        {
            "patient_id": np.arange(len(df)),
            "specialite": specialite.to_numpy(),
            "duree_operatoire": duree.to_numpy(),
            "duree_sejour": sejour.to_numpy(),
        }
    )
    if date_col in df.columns:
        patients["date_inter"] = pd.to_datetime(df[date_col], errors="coerce").to_numpy()
    return patients


def build_vacations(
    specialites,
    n_days: int,
    capacite_min: int = 480,
    vacations_par_jour_par_specialite: int = 1,
) -> pd.DataFrame:
    """Genere les vacations (jour x specialite) pour un horizon donne."""
    rows = []
    vac_id = 0
    for jour in range(n_days):
        for spec in specialites:
            for _ in range(vacations_par_jour_par_specialite):
                rows.append(
                    {"vacation_id": vac_id, "jour": jour, "specialite": spec, "capacite_min": capacite_min}
                )
                vac_id += 1
    return pd.DataFrame(rows)


def select_horizon(
    patients: pd.DataFrame,
    horizon_jours: int = 5,
    date_col: str = "date_inter",
) -> tuple[pd.DataFrame, dict]:
    """Restreint la table patients aux ``horizon_jours`` dernieres dates
    d'intervention et reindexe ces dates en jours 0..n-1.

    Renvoie (patients_fenetre, contexte) ou le contexte decrit les dates
    retenues. Les patients sans date sont ignores.
    """
    if date_col not in patients.columns:
        return patients.reset_index(drop=True), {"dates": None}

    with_dates = patients.dropna(subset=[date_col]).copy()
    dates = sorted(pd.to_datetime(with_dates[date_col]).dt.normalize().unique())
    dates = dates[-horizon_jours:]
    mapping = {d: i for i, d in enumerate(dates)}

    with_dates["jour_origine"] = with_dates[date_col].dt.normalize().map(mapping)
    window = with_dates.dropna(subset=["jour_origine"]).copy()
    window["jour_origine"] = window["jour_origine"].astype(int)
    window = window.drop(columns=[date_col]).reset_index(drop=True)
    window["patient_id"] = np.arange(len(window))
    return window, {"dates": dates, "mapping": mapping, "n_days": len(dates)}


def prepare_inputs(
    path: str | Path = DEFAULT_PARQUET,
    horizon_jours: int = 5,
    capacite_min: int = 480,
    specialite_col: str | None = None,
    max_specialites: int = 6,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Pipeline complet : Parquet EDA -> (patients, vacations, contexte)."""
    raw = load_preprocessed(path)
    patients_all = build_patients(raw, specialite_col=specialite_col, max_specialites=max_specialites)
    patients, context = select_horizon(patients_all, horizon_jours=horizon_jours)

    specialites = sorted(patients["specialite"].dropna().unique().tolist())
    n_days = context.get("n_days") or 1
    vacations = build_vacations(specialites, n_days=n_days, capacite_min=capacite_min)

    context.update(
        {
            "n_patients": len(patients),
            "n_vacations": len(vacations),
            "specialites": specialites,
            "capacite_min": capacite_min,
        }
    )
    return patients, vacations, context
