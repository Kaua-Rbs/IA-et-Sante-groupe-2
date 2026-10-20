# prediction

Modèles de durée utilisés par KYST : temps d'occupation de la salle et durée de séjour. Leur entraînement, leurs résultats et leurs limites sont décrits dans [Modèles de prédiction](../docs/models.md).

| Module | Rôle |
| :--- | :--- |
| `duration_features.py` | Variables communes : normalisation, familles CIM-10 / CCAM, regroupement des catégories rares |
| `consultation_features.py` | Les sept variables connues en consultation, seules utilisées par les modèles déployés |
| `surgery_duration.py` | Temps de salle : comparaison de modèles, entraînement, bornes P80/P95, inférence |
| `los_model.py` | Durée de séjour (jours calendaires inclusifs) : entraînement et inférence |

L'API charge les modèles par `predict_schedule_loaded` et `predict_los_loaded` (voir `interface/api/ai/trained.py`). Le script qui produit les modèles déployés est [`experiments/train_consultation_models.py`](../experiments/README.md).

Les modules se lancent aussi seuls, depuis la racine du dépôt (les chemins `resources/` et `artifacts/` sont relatifs), pour entraîner les modèles à toutes variables :

```bash
python -m prediction.surgery_duration --data resources/model_surgery_duration_dataset.parquet
python -m prediction.los_model --data resources/model_los_dataset.parquet
```

Les modèles entraînés vont dans `artifacts/ml-models/` (non versionné). Les classes enregistrées dans les fichiers joblib sont déclarées sous le nom `prediction.surgery_duration` ; les modèles entraînés avant le rangement du dossier, sous l'ancien nom `surgery_duration`, restent lisibles.
