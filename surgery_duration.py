"""Comparaison des modeles de prediction de duree de salle."""
from pathlib import Path
import argparse
import json
import time
import hashlib
import joblib
from duration_features import engineer_features, apply_category_mapping, fit_category_mapping
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge, ElasticNet
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, median_absolute_error, r2_score
from sklearn.inspection import permutation_importance

TARGET = 'target_surgery_duration_min'
CAT = ['sexe', 'interv_type', 'anesth_type', 'anesth_loco_reg', 'praticien', 'nom_chir',
       'cim_diag_pr', 'cim_diag_family', 'ccam_1', 'ccam_1_family']
NUM = ['age_years', 'intervention_month_sin', 'intervention_month_cos',
       'intervention_weekday_sin', 'intervention_weekday_cos', 'intervention_is_weekend',
       'num_secondary_diagnoses', 'num_ccam_codes', 'anesth_type_missing', 'anesth_loco_reg_missing']
FEATURES = NUM + CAT
SEED = 42
# Hypothese du projet confirmee par le professeur : procedure CCAM principale
# et famille connues avant chirurgie; ce ne sont pas des variables de fuite.
PREOPERATIVE_CCAM = ['ccam_1', 'ccam_1_family']
FIXED_FEATURES = [c for c in FEATURES if not c.startswith('intervention_')]


class MedianBaseline(RegressorMixin, BaseEstimator):
    """Mediane de groupe apprise uniquement sur train; repli global."""
    def __init__(self, columns=(), min_count=1):
        self.columns = columns
        self.min_count = min_count

    def fit(self, X, y):
        self.median_ = float(np.median(y))
        if self.columns:
            frame = X[list(self.columns)].copy()
            frame['_target'] = np.asarray(y)
            grouped = frame.groupby(list(self.columns), dropna=False)['_target']
            self.mapping_ = grouped.median().where(grouped.size().ge(self.min_count))
        return self

    def predict(self, X):
        if not self.columns:
            return np.full(len(X), self.median_)
        keys = X[self.columns[0]] if len(self.columns) == 1 else pd.MultiIndex.from_frame(X[list(self.columns)])
        return self.mapping_.reindex(keys).fillna(self.median_).to_numpy()


class HistoricalRidge(RegressorMixin, BaseEstimator):
    """Agregats calcules sur les mois de train strictement anterieurs."""
    def fit(self, X, y, event_dates):
        y = pd.Series(np.asarray(y), index=X.index)
        months = pd.to_datetime(event_dates).dt.to_period('M')
        encoded = X.copy()
        self.groups_ = [('ccam_1',), ('nom_chir',), ('ccam_1', 'nom_chir')]
        self.maps_ = []
        self.global_ = float(y.median())
        for i, cols in enumerate(self.groups_):
            encoded[f'history_{i}'] = 60.0  # prior fixe pour le premier mois sans historique
            for month in sorted(months.unique()):
                current = months.eq(month)
                previous = months.lt(month)
                if not previous.any():
                    continue
                baseline = MedianBaseline(cols).fit(X.loc[previous], y.loc[previous])
                encoded.loc[current, f'history_{i}'] = baseline.predict(X.loc[current])
            self.maps_.append(MedianBaseline(cols).fit(X, y))
        prep = preprocessing(columns=list(X.columns), scale=True)
        prep.transformers.append(('history', StandardScaler(), [f'history_{i}' for i in range(3)]))
        self.model_ = make_pipeline(prep, Ridge(alpha=10)).fit(encoded, y)
        return self

    def predict(self, X):
        encoded = X.copy()
        for i, baseline in enumerate(self.maps_):
            encoded[f'history_{i}'] = baseline.predict(X)
        return self.model_.predict(encoded)


def validate_split(df):
    if not df.index.is_unique:
        raise ValueError('Indices de lignes non uniques')
    if not df['split'].isin(['train', 'validation', 'test']).all():
        raise ValueError('Etiquette de partition inconnue')
    df = df.copy()
    df['split_event_date'] = pd.to_datetime(df['split_event_date'], errors='raise')
    parts = [df.loc[df.split.eq(s)].copy() for s in ('train', 'validation', 'test')]
    sets = []
    for part in parts:
        if part.empty or part.split_patient_id.isna().any() or part.split_event_date.isna().any():
            raise ValueError('Partition vide ou identifiant/date manquant')
        if not np.isfinite(part[TARGET]).all() or not part[TARGET].gt(0).all():
            raise ValueError('Cible invalide')
        sets.append(set(part.split_patient_id))
    if any(sets[i] & sets[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError('Patients partages entre partitions')
    if not (parts[0].split_event_date.max() < parts[1].split_event_date.min()
            and parts[1].split_event_date.max() < parts[2].split_event_date.min()):
        raise ValueError('Partitions non chronologiques')
    return parts


def prepared(frame, columns=FEATURES):
    X = frame[columns].copy()
    for col in [c for c in CAT if c in columns]:
        X[col] = X[col].fillna('__MISSING__').astype(str)
    for col in [c for c in NUM if c in columns]:
        X[col] = pd.to_numeric(X[col], errors='coerce').astype(float)
    return X


def preprocessing(columns=FEATURES, ordinal=False, scale=False, rare=10):
    nums = [c for c in NUM if c in columns]
    cats = [c for c in CAT if c in columns]
    encoder = (OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
               if ordinal else OneHotEncoder(handle_unknown='ignore', min_frequency=rare))
    numeric = make_pipeline(SimpleImputer(strategy='median'), StandardScaler()) if scale else SimpleImputer(strategy='median')
    return ColumnTransformer([('num', numeric, nums), ('cat', encoder, cats)], sparse_threshold=0 if ordinal else 0.3)


def metrics(y, pred):
    return dict(MAE_min=mean_absolute_error(y, pred), RMSE_min=np.sqrt(mean_squared_error(y, pred)),
                Median_AE_min=median_absolute_error(y, pred), R2=r2_score(y, pred))


def baseline_models():
    """References simples fixees avant toute comparaison ML."""
    specs = [('Global median', (), 1), ('Procedure median', ('ccam_1',), 1),
             ('Procedure family median', ('ccam_1_family',), 1),
             ('Surgeon median', ('nom_chir',), 1),
             ('Anesthesia type median', ('anesth_type',), 1),
             ('Procedure surgeon median', ('ccam_1', 'nom_chir'), 1),
             ('Procedure surgeon median min10', ('ccam_1', 'nom_chir'), 10),
             ('Intervention type median', ('interv_type',), 1),
             ('Intervention type surgeon median min10', ('interv_type', 'nom_chir'), 10)]
    return [(name, MedianBaseline(cols, minimum)) for name, cols, minimum in specs]


def run_baselines(data, out):
    """Evaluation des modeles de reference (baselines)"""
    out.mkdir(parents=True, exist_ok=True)
    train, validation, test = validate_split(pd.read_parquet(data))
    # Pas besoin d'age, de calendriers, de scaling ou d'encodage one-hot.
    columns = ['ccam_1', 'ccam_1_family', 'nom_chir', 'interv_type', 'anesth_type']
    frames = [p[columns].fillna('__MISSING__').astype(str) for p in (train, validation, test)]
    X, V, T = frames
    rows = []
    for name, model in baseline_models():
        start = time.perf_counter()
        model.fit(X, train[TARGET])
        training_s = time.perf_counter() - start
        val_mae = mean_absolute_error(validation[TARGET], model.predict(V))
        times = []
        for _ in range(3):
            start = time.perf_counter()
            pred = model.predict(T)
            times.append(time.perf_counter() - start)
        rows.append(dict(Model=name, **metrics(test[TARGET], pred), validation_MAE_min=val_mae,
                         training_s=training_s, inference_s=float(np.median(times))))
    result = pd.DataFrame(rows)
    # Choix uniquement sur validation; le test reste descriptif.
    chosen = result.loc[result.validation_MAE_min.idxmin(), 'Model']
    result['selected_on_validation'] = result.Model.eq(chosen)
    result = result.sort_values('MAE_min')
    result.to_csv(out / 'surgery_duration_baseline_comparison.csv', index=False)
    print(result.to_string(index=False))
    return result


def run_ccam_ablation(data, out, calendar=False):
    """Evaluation de la contribution des deux variables CCAM."""
    out.mkdir(parents=True, exist_ok=True)
    train, validation, test = validate_split(pd.read_parquet(data))
    validation, _ = calibration_split(validation)
    columns_used = FEATURES if calendar else FIXED_FEATURES
    X, V, T = map(prepared, (train, validation, test))
    y, vy, ty = [p[TARGET].astype(float) for p in (train, validation, test)]
    rows = []
    for name, columns in [('With preoperative CCAM', columns_used),
                          ('Without CCAM code and family', [c for c in columns_used if c not in PREOPERATIVE_CCAM])]:
        nums = [c for c in NUM if c in columns]
        cats = [c for c in CAT if c in columns]
        prep = preprocessing(columns=columns, ordinal=True)
        model = HistGradientBoostingRegressor(max_iter=200, max_leaf_nodes=15,
            categorical_features=list(range(len(nums), len(nums) + len(cats))),
            early_stopping=True, n_iter_no_change=30, random_state=SEED)
        start = time.perf_counter()
        encoded = prep.fit_transform(X[columns], y)
        model.fit(encoded, np.log1p(y), X_val=prep.transform(V[columns]), y_val=np.log1p(vy))
        training_s = time.perf_counter() - start
        pipeline = make_pipeline(prep, model)
        val_pred = np.expm1(pipeline.predict(V[columns]))
        times = []
        for _ in range(3):
            start = time.perf_counter()
            pred = np.expm1(pipeline.predict(T[columns]))
            times.append(time.perf_counter() - start)
        long_mask = ty.ge(120)
        rows.append(dict(Model=name, **metrics(ty, pred),
            validation_MAE_min=mean_absolute_error(vy, val_pred),
            long_surgery_MAE_min=mean_absolute_error(ty[long_mask], pred[long_mask]),
            training_s=training_s, inference_s=float(np.median(times))))
    result = pd.DataFrame(rows)
    result.to_csv(out / 'surgery_duration_ccam_ablation.csv', index=False)
    print(result.to_string(index=False))
    return result


def run(data, out, train_bounds=False, calendar=False):
    from catboost import CatBoostRegressor
    from xgboost import XGBRegressor
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(data)
    train, validation, test = validate_split(df)
    val, calibration = calibration_split(validation)
    columns_used = FEATURES if calendar else FIXED_FEATURES
    X, V, T = map(prepared, (train, val, test))
    y, vy, ty = [p[TARGET].astype(float) for p in (train, val, test)]
    audit = {'seed': SEED, 'dataset_sha256': hashlib.sha256(data.read_bytes()).hexdigest(),
             'test_row_sha256': hashlib.sha256(pd.util.hash_pandas_object(test, index=True).values.tobytes()).hexdigest(),
             'splits': {s: len(p) for s, p in zip(['train', 'selection', 'calibration', 'test'], [train, val, calibration, test])},
             'duration_percentiles': df[TARGET].describe(percentiles=[.01, .5, .9, .95, .99, .999]).to_dict(),
             'skewness': float(y.skew()), 'over_180_min': int(df[TARGET].gt(180).sum()),
             'under_15_min': int(df[TARGET].lt(15).sum()), 'outlier_policy': 'No additional filtering or clipping'}
    (out / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    experiments = []
    def add(name, model, columns=None, native=False, log=False, weights=False):
        columns = columns_used if columns is None else columns
        experiments.append((name, model, columns, native, log, weights))
    for name, baseline in baseline_models():
        add(name, baseline)
    for name, model in [('LinearRegression', LinearRegression()), ('Ridge', Ridge(alpha=10)),
                        ('Ridge alpha100', Ridge(alpha=100)), ('ElasticNet', ElasticNet(alpha=.03, l1_ratio=.2, max_iter=3000))]:
        add(name, make_pipeline(preprocessing(columns=columns_used, scale=True), model))
    for name, model in [('RandomForest fast', RandomForestRegressor(n_estimators=120, min_samples_leaf=3, n_jobs=4, random_state=SEED)),
                        ('ExtraTrees', ExtraTreesRegressor(n_estimators=160, min_samples_leaf=2, n_jobs=4, random_state=SEED)),
                        ('Previous RandomForest', RandomForestRegressor(n_estimators=300, n_jobs=4, random_state=SEED))]:
        add(name, make_pipeline(preprocessing(columns=columns_used, rare=None if name.startswith('Previous') else 10), model))
    for loss in ['squared_error', 'absolute_error']:
        add('HistGradientBoosting ' + loss, make_pipeline(preprocessing(columns=columns_used, ordinal=True), HistGradientBoostingRegressor(
            loss=loss, max_iter=200, max_leaf_nodes=15, categorical_features=list(range(sum(c in NUM for c in columns_used), len(columns_used))),
            early_stopping=True, scoring='neg_mean_absolute_error', n_iter_no_change=30, random_state=SEED)))
    add('HistGradientBoosting log1p', make_pipeline(preprocessing(columns=columns_used, ordinal=True), HistGradientBoostingRegressor(
        max_iter=200, max_leaf_nodes=15, categorical_features=list(range(sum(c in NUM for c in columns_used), len(columns_used))),
        early_stopping=True, n_iter_no_change=30, random_state=SEED)), log=True)
    add('Ridge log1p', TransformedTargetRegressor(regressor=make_pipeline(preprocessing(columns=columns_used, scale=True), Ridge(alpha=10)), func=np.log1p, inverse_func=np.expm1))
    add('Ridge historical medians', HistoricalRidge())  # classe historique sans calendrier egalement
    for name, objective, iterations in [('Previous XGBoost', 'reg:absoluteerror', 700), ('XGBoost fast', 'reg:absoluteerror', 400)]:
        add(name, make_pipeline(preprocessing(columns=columns_used, rare=None if name.startswith('Previous') else 10), XGBRegressor(objective=objective, n_estimators=iterations,
            max_depth=7 if name.startswith('Previous') else 5, learning_rate=.04 if name.startswith('Previous') else .06,
            subsample=.9, colsample_bytree=.9, reg_lambda=5, tree_method='hist', n_jobs=4, random_state=SEED)))
    def cb(loss='MAE', depth=6, iterations=500):
        return CatBoostRegressor(loss_function=loss, eval_metric='MAE', depth=depth, iterations=iterations,
                                 learning_rate=.06, l2_leaf_reg=8, random_seed=SEED, thread_count=4,
                                 verbose=False, allow_writing_files=False)
    add('CatBoost native MAE', cb(), native=True)
    add('CatBoost native MAE depth4', cb(depth=4), native=True)
    add('CatBoost native RMSE', cb('RMSE'), native=True)
    add('CatBoost native log1p', cb('RMSE'), native=True, log=True)
    conservative = [c for c in columns_used if c not in ['cim_diag_pr', 'cim_diag_family',
        'num_secondary_diagnoses', 'num_ccam_codes', 'anesth_type', 'anesth_loco_reg', 'anesth_type_missing', 'anesth_loco_reg_missing']]
    add('CatBoost confirmed CCAM features', cb(), columns=conservative, native=True)
    no_calendar = [c for c in columns_used if not c.startswith('intervention_')]
    if calendar:
        add('CatBoost no calendar', cb(), columns=no_calendar, native=True)
    previous = CatBoostRegressor(loss_function='RMSE', iterations=700, depth=7, learning_rate=.04,
        l2_leaf_reg=8, random_seed=SEED, thread_count=4, verbose=False, allow_writing_files=False)
    add('Previous weighted CatBoost', previous, native=True, weights=True)
    # LightGBM reste optionnel
    try:
        from lightgbm import LGBMRegressor
        add('LightGBM', make_pipeline(preprocessing(columns=columns_used), LGBMRegressor(objective='regression_l1', n_estimators=300,
            num_leaves=15, verbosity=-1, n_jobs=4, random_state=SEED)))
    except ImportError:
        (out / 'optional_models.txt').write_text('LightGBM absent; non teste.\n', encoding='utf-8')
    rows, fitted = [], {}
    for name, model, columns, native, log, weights in experiments:
        start = time.perf_counter()
        fit_y = np.log1p(y) if log else y
        kwargs = {}
        if isinstance(model, HistoricalRidge):
            kwargs['event_dates'] = train.split_event_date
        if native:
            kwargs['cat_features'] = [c for c in CAT if c in columns]
            if not weights:
                kwargs.update(eval_set=(V[columns], np.log1p(vy) if log else vy), early_stopping_rounds=50)
            else:
                kwargs['sample_weight'] = np.where(y >= y.quantile(.9), 3., 1.)
        if name.startswith('HistGradientBoosting') or name == 'XGBoost fast':
            prep, estimator = model.steps[0][1], model.steps[1][1]
            encoded = prep.fit_transform(X[columns], y)
            encoded_val = prep.transform(V[columns])
            if name.startswith('HistGradientBoosting'):
                estimator.fit(encoded, fit_y, X_val=encoded_val, y_val=np.log1p(vy) if log else vy)
            else:
                estimator.set_params(early_stopping_rounds=40, eval_metric='mae')
                estimator.fit(encoded, y, eval_set=[(encoded_val, vy)], verbose=False)
        else:
            model.fit(X[columns], fit_y, **kwargs)
        elapsed = time.perf_counter() - start
        pred = model.predict(V[columns])
        if log:
            pred = np.expm1(pred)
        row = dict(Model=name, **metrics(vy, pred), **tail_metrics(vy, pred, y.quantile(.9)), training_s=elapsed)
        rows.append(row)
        fitted[name] = (model, columns, log)
        print(name, 'validation MAE', round(row['MAE_min'], 3), 'fit seconds', round(elapsed, 3), flush=True)
        pd.DataFrame(rows).to_csv(out / 'validation_comparison.csv', index=False)
    validation_results = pd.DataFrame(rows).sort_values('MAE_min')
    best_mae = validation_results.MAE_min.min()
    # Tolerance explicite: <=0.2 minute; preferer le temps d'apprentissage.
    eligible = validation_results.loc[validation_results.MAE_min <= best_mae + .2]
    selected = eligible.sort_values('training_s').iloc[0].Model
    results, predictions = [], {}
    for row in rows:
        name = row['Model']
        model, columns, log = fitted[name]
        times = []
        for _ in range(3):
            start = time.perf_counter()
            pred = model.predict(T[columns])
            if log:
                pred = np.expm1(pred)
            times.append(time.perf_counter() - start)
        predictions[name] = pred
        results.append(dict(Model=name, **metrics(ty, pred), **tail_metrics(ty, pred, y.quantile(.9)), training_s=row['training_s'],
                            inference_s=float(np.median(times)), validation_MAE_min=row['MAE_min'], selected=name == selected))
    comparison = pd.DataFrame(results).sort_values('MAE_min')
    comparison.to_csv(out / 'surgery_duration_model_comparison.csv', index=False)
    model, columns, log = fitted[selected]
    mapping_path = data.with_suffix('.preprocessing.joblib')
    # Older local Parquets predate the separate preprocessing artifact. Their
    # categories were already normalized and grouped using train only, so the
    # categories present in train still define a safe raw-inference mapping.
    mapping = (joblib.load(mapping_path) if mapping_path.exists() else
               fit_category_mapping(X, [c for c in columns if c in CAT], min_count=1))
    saved = dict(model=model, features=columns, log_target=log, name=selected,
                 category_mapping=mapping, calendar=calendar, artifact_version=2)
    if train_bounds:
        saved['bounds'] = fit_bounds(X, y, prepared(calibration), calibration[TARGET], columns)
    joblib.dump(saved, out / 'surgery_duration_model.joblib')
    (out / 'selection.json').write_text(json.dumps({'selected': selected, 'rule': 'Validation MAE within 0.2 minutes of best, then fastest training',
        'fit_partition': 'train only; early validation for selection/early stopping; later validation for calibration; test for reporting',
        'calendar': calendar, 'calibration_rows': len(calibration), 'selection_rows': len(val),
        'raw_inference_available': mapping is not None, 'bounds_trained': train_bounds}, indent=2), encoding='utf-8')
    top = list(validation_results.head(3).Model)
    if selected not in top:
        top[-1] = selected
    bands, groups, worst = [], [], []
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for name in top:
        errors = np.abs(ty.to_numpy() - predictions[name])
        for label, mask in [('short <60', ty < 60), ('medium 60-120', (ty >= 60) & (ty < 120)), ('long >=120', ty >= 120)]:
            bands.append(dict(Model=name, band=label, n=int(mask.sum()), MAE_min=float(errors[mask].mean())))
        for column in ['interv_type', 'ccam_1']:
            detail = pd.DataFrame({'group': T[column], 'error': errors})
            summary = detail.groupby('group').error.agg(['size', 'mean']).reset_index()
            summary['Model'], summary['feature'] = name, column
            groups.append(summary)
        for pos in np.argsort(errors)[-10:][::-1]:
            worst.append(dict(Model=name, dataset_row_id=int(test.index[pos]), actual_min=float(ty.iloc[pos]),
                predicted_min=float(predictions[name][pos]), absolute_error_min=float(errors[pos]),
                procedure_group=T.ccam_1.iloc[pos],
                procedure_train_count=int(X.ccam_1.eq(T.ccam_1.iloc[pos]).sum())))
        axes[0].scatter(ty, predictions[name], s=5, alpha=.2, label=name)
        axes[1].hist(predictions[name] - ty, bins=50, alpha=.4, label=name)
    axes[0].plot([0, ty.max()], [0, ty.max()], 'k--')
    axes[0].set(xlabel='True duration (min)', ylabel='Predicted duration (min)')
    axes[1].set(xlabel='Prediction minus actual (min)', ylabel='Cases')
    axes[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out / 'prediction_errors.png', dpi=160)
    plt.close(fig)
    pd.DataFrame(bands).to_csv(out / 'duration_band_errors.csv', index=False)
    pd.concat(groups).to_csv(out / 'procedure_errors.csv', index=False)
    pd.DataFrame(worst).to_csv(out / 'worst_errors.csv', index=False)
    # Importance sur validation, aucune utilisation du test pour choisir les variables.
    tree_names = [n for n in validation_results.Model if any(k in n for k in ['CatBoost', 'XGBoost', 'Forest', 'ExtraTrees', 'HistGradient', 'LightGBM'])]
    importance_name = selected if selected in tree_names else tree_names[0]
    imodel, icols, ilog = fitted[importance_name]
    def scorer(estimator, features, target):
        prediction = estimator.predict(features)
        return -mean_absolute_error(target, np.expm1(prediction) if ilog else prediction)
    importance = permutation_importance(imodel, V[icols], vy, scoring=scorer, n_repeats=3, random_state=SEED)
    pd.DataFrame({'feature': icols, 'MAE_increase_min': importance.importances_mean,
                  'std': importance.importances_std, 'Model': importance_name}).sort_values('MAE_increase_min', ascending=False).to_csv(out / 'feature_importance.csv', index=False)
    output = pd.DataFrame({'dataset_row_id': test.index, 'duration_point_min': predictions[selected]})
    output.to_csv(out / 'selected_test_predictions.csv', index=False)
    scheduler = predict_schedule(test, out / 'surgery_duration_model.joblib')
    scheduler.insert(0, 'dataset_row_id', test.index)
    scheduler.to_csv(out / 'scheduler_predictions_test.csv', index=False)
    if train_bounds:
        pd.DataFrame([dict(bound=label, **upper_bound_metrics(ty, scheduler[f'duration_{label}_min']))
                      for label in ('p80', 'p95')]).to_csv(out / 'bounds_test_metrics.csv', index=False)
    print('SELECTED', selected, flush=True)


def calibration_split(validation):
    """Reserve la seconde moitie des dates; ecarte les patients deja vus."""
    dates = sorted(pd.to_datetime(validation.split_event_date).unique())
    if len(dates) < 2:
        raise ValueError('Au moins deux dates de validation requises pour calibrer')
    cutoff = dates[len(dates) // 2]
    selection = validation.loc[validation.split_event_date.lt(cutoff)].copy()
    calibration = validation.loc[validation.split_event_date.ge(cutoff)
        & ~validation.split_patient_id.isin(selection.split_patient_id)].copy()
    if selection.empty or calibration.empty:
        raise ValueError('Selection/calibration vide apres separation patient/temps')
    return selection, calibration


def tail_metrics(y, prediction, threshold):
    y, prediction = np.asarray(y), np.asarray(prediction)
    errors = prediction - y
    tail = y >= threshold
    return dict(tail_n=int(tail.sum()),
        tail_MAE_min=float(np.abs(errors[tail]).mean()) if tail.any() else np.nan,
        tail_mean_signed_error_min=float(errors[tail].mean()) if tail.any() else np.nan,
        tail_underprediction_rate=float((errors[tail] < 0).mean()) if tail.any() else np.nan,
        tail_P90_absolute_error_min=float(np.quantile(np.abs(errors[tail]), .9)) if tail.any() else np.nan,
        tail_underprediction_30plus_rate=float((errors[tail] <= -30).mean()) if tail.any() else np.nan)


def upper_bound_metrics(y, prediction):
    overrun = np.asarray(y) - np.asarray(prediction)
    return dict(coverage=float((overrun <= 0).mean()),
        overrun_30plus_rate=float((overrun >= 30).mean()),
        overrun_60plus_rate=float((overrun >= 60).mean()),
        mean_prediction_min=float(np.mean(prediction)))


def conformal_offset(y, prediction, coverage):
    scores = np.asarray(y) - np.asarray(prediction)
    if not len(scores) or not np.isfinite(scores).all() or not 0 < coverage < 1:
        raise ValueError('Calibration invalide')
    rank = int(np.ceil((len(scores) + 1) * coverage))
    if rank > len(scores):
        raise ValueError('Calibration trop petite pour la couverture demandee')
    return max(0., float(np.sort(scores)[rank - 1]))


def fit_bounds(X, y, calibration, cy, columns):
    from catboost import CatBoostRegressor
    bounds = {}
    for label, alpha in [('p80', .8), ('p95', .95)]:
        model = CatBoostRegressor(loss_function=f'Quantile:alpha={alpha}', iterations=700,
            depth=7, learning_rate=.04, l2_leaf_reg=8, random_seed=SEED,
            thread_count=4, verbose=False, allow_writing_files=False)
        model.fit(X[columns], y, cat_features=[c for c in CAT if c in columns])
        offset = conformal_offset(cy, model.predict(calibration[columns]), alpha)
        bounds[label] = dict(model=model, offset=offset, coverage=alpha)
    return bounds


def inference_features(frame, saved, raw=False):
    columns = saved['features']
    if raw:
        mapping = saved.get('category_mapping')
        if mapping is None:
            raise ValueError('Regenerer le dataset avec le notebook de preprocessing pour sauvegarder le mapping')
        frame = apply_category_mapping(engineer_features(frame, columns), mapping)
    return prepared(frame, columns)


def checked_prediction(prediction):
    prediction = np.asarray(prediction, dtype=float)
    if not np.isfinite(prediction).all() or (prediction <= 0).any():
        raise ValueError('Durees predites non finies ou non positives')
    return prediction


def predict_schedule(frame, artifact='results/surgery_duration_model.joblib', raw=False):
    """Predictions individuelles; P95 patient ne garantit pas P95 vacation."""
    saved = joblib.load(artifact)
    X = inference_features(frame, saved, raw)
    point = saved['model'].predict(X)
    if saved['log_target']:
        point = np.expm1(point)
    result = pd.DataFrame({'duration_point_min': checked_prediction(point)}, index=frame.index)
    previous = point
    for label in ('p80', 'p95'):
        if label in saved.get('bounds', {}):
            bound = saved['bounds'][label]
            prediction = np.maximum(bound['model'].predict(X) + bound['offset'], previous)
            result[f'duration_{label}_min'] = checked_prediction(prediction)
            previous = prediction
    if 'duration_p95_min' in result:
        result['uncertainty_width_min'] = result.duration_p95_min - result.duration_point_min
    return result


def predict_duration(frame, artifact='results/surgery_duration_model.joblib', raw=False):
    return predict_schedule(frame, artifact, raw).duration_point_min.rename('duree_operatoire')


def apply_predicted_durations(patients, preoperative_features, artifact='results/surgery_duration_model.joblib',
                              risk='point', raw=False, allow_calendar=False):
    """Durees fixes: modele sans calendrier par defaut, index uniques alignes."""
    if risk not in ('point', 'p80', 'p95'):
        raise ValueError('Risque attendu: point, p80 ou p95')
    if not patients.index.is_unique or not patients.index.equals(preoperative_features.index):
        raise ValueError('Aligner explicitement les lignes patients et variables preoperatoires')
    saved = joblib.load(artifact)
    if any(c.startswith('intervention_') for c in saved['features']) and not allow_calendar:
        raise ValueError('Modele calendrier: recalculer pour chaque date candidate ou utiliser un modele sans calendrier')
    predictions = predict_schedule(preoperative_features, artifact, raw)
    column = f'duration_{risk}_min'
    if column not in predictions:
        raise ValueError('Bornes absentes; entrainer avec --train-bounds')
    result = patients.copy()
    result['duree_operatoire'] = predictions[column]
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path('resources/model_surgery_duration_dataset.parquet'))
    parser.add_argument('--out', type=Path, default=Path('results'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--baselines-only', action='store_true', help='Evaluer uniquement les references medianes')
    mode.add_argument('--ccam-ablation', action='store_true', help='Comparer avec/sans les deux variables CCAM')
    parser.add_argument('--train-bounds', action='store_true', help='Entrainer et calibrer les bornes P80/P95')
    parser.add_argument('--calendar', action='store_true', help='Experimenter avec la date proposee; incompatible avec des durees fixes')
    args = parser.parse_args()
    # Classes picklees sous le nom importable du module, meme avec execution CLI.
    from surgery_duration import run as run_comparison, run_baselines, run_ccam_ablation
    if args.baselines_only:
        run_baselines(args.data, args.out)
    elif args.ccam_ablation:
        run_ccam_ablation(args.data, args.out, calendar=args.calendar)
    else:
        run_comparison(args.data, args.out, train_bounds=args.train_bounds, calendar=args.calendar)
