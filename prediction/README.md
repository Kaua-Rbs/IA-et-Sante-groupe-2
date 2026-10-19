# prediction

Modèles de durée utilisés par KYST et par la simulation.

| Module | Rôle |
| :--- | :--- |
| `duration_features.py` | Variables communes (normalisation, familles CIM-10 / CCAM, regroupement des catégories rares) |
| `surgery_duration.py` | Temps d'occupation de salle : comparaison de modèles, entraînement, bornes P80/P95, inférence |
| `los_model.py` | Durée de séjour (jours calendaires inclusifs) : entraînement et inférence |
| `bridge_los.py` | Relie les prédictions aux patients de la simulation (`optimiseur`) |

Les commandes se lancent depuis la racine du dépôt (les chemins `resources/` et `artifacts/` sont relatifs) :

```bash
python -m prediction.surgery_duration --data resources/model_surgery_duration_dataset.parquet
python -m prediction.los_model --data resources/model_los_dataset.parquet
```

Les modèles entraînés sont écrits dans `artifacts/ml-models/` (non versionné). Les artefacts entraînés avant ce rangement restent lisibles : `surgery_duration.py` déclare l'ancien nom de module `surgery_duration`.
