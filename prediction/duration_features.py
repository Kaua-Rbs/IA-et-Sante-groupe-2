"""Preparation partagee des variables de duree, avant encodage ML."""
import re
import unicodedata
import numpy as np
import pandas as pd

MISSING = '__MISSING__'


def normalize_value(value):
    if pd.isna(value) or not str(value).strip():
        return MISSING
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', text).strip().upper()


def engineer_features(frame, columns):
    """Table EDA -> variables requises; date_inter doit etre la date proposee."""
    result = pd.DataFrame(index=frame.index)
    codes = ['cim_diag_pr', 'ccam_1']
    for col in ['sexe', 'interv_type', 'anesth_type', 'anesth_loco_reg', 'praticien', 'nom_chir'] + codes:
        family = 'cim_diag_family' if col == 'cim_diag_pr' else col + '_family'
        if col in columns or family in columns or col + '_missing' in columns:
            values = frame[col].map(normalize_value)
            if col in codes:
                values = values.map(lambda value: MISSING if value == MISSING else re.sub(r'[^A-Z0-9]', '', value) or MISSING)
            result[col] = values
            if col in codes:
                result[family] = values.where(values.eq(MISSING), values.str[:3 if col == 'cim_diag_pr' else 4])
            if col.startswith('anesth'):
                result[col + '_missing'] = values.eq(MISSING).astype('int8')
    if 'age_years' in columns:
        result['age_years'] = pd.to_numeric(frame['age_years'], errors='coerce')
    if any(col.startswith('intervention_') for col in columns):
        dates = pd.to_datetime(frame['date_inter'], errors='raise')
        if dates.isna().any():
            raise ValueError('Date proposee manquante')
        for label, values, period in [('month', dates.dt.month - 1, 12), ('weekday', dates.dt.weekday, 7)]:
            result[f'intervention_{label}_sin'] = np.sin(2 * np.pi * values / period)
            result[f'intervention_{label}_cos'] = np.cos(2 * np.pi * values / period)
        result['intervention_is_weekend'] = dates.dt.weekday.ge(5).astype('int8')
    for target, prefix, maximum in [('num_secondary_diagnoses', 'cim_assoc_', 5), ('num_ccam_codes', 'ccam_', 4)]:
        if target in columns:
            count = pd.Series(0, index=frame.index, dtype='int8')
            for i in range(1, maximum + 1):
                col = f'{prefix}{i}'
                if col in frame:
                    count += (frame[col].notna() & frame[col].astype('string').str.strip().ne('')).astype('int8')
            result[target] = count
    return result[columns]


def fit_category_mapping(frame, categorical_columns, min_count=10):
    """Frequences apprises uniquement sur train, avant regroupement."""
    return {col: set(frame[col].value_counts().loc[lambda counts: counts >= min_count].index)
            for col in categorical_columns}


def apply_category_mapping(frame, mapping):
    result = frame.copy()
    for col, frequent in mapping.items():
        if col in result:
            result[col] = result[col].where(result[col].isin(frequent) | result[col].eq(MISSING), '__RARE__')
    return result
