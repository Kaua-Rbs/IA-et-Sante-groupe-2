# experiments

Entraînement des modèles « consultation » déployés dans KYST. Les modèles, leurs résultats et leurs limites sont présentés dans [Modèles de prédiction](../docs/models.md).

| Fichier | Rôle |
| :--- | :--- |
| `train_consultation_models.py` | Entraîne, sélectionne et calibre les modèles de temps de salle et de durée de séjour, puis les évalue sur 2022 |
| `final_model_requirements.txt` | Versions exactes des bibliothèques utilisées pour l'entraînement |
| `results/final-consultation-2026-10-20-v3/` | Sortie de l'entraînement des modèles déployés : manifeste (empreintes SHA-256), métriques, rapport. Aucune ligne patient |

## Prérequis

Le script lit, dans le dossier passé à `--source` (en général la racine du dépôt) :

- `resources/model_surgery_duration_dataset.parquet` et `resources/model_los_dataset.parquet`, produits par les [notebooks de préparation](../notebooks/README.md) ;
- `results/surgery_duration_model.joblib`, l'ancien modèle de temps de salle à toutes variables, produit par `python -m prediction.surgery_duration` (voir [prediction/](../prediction/README.md)). Il sert seulement de point de comparaison.

Utiliser un environnement séparé, avec les versions de `final_model_requirements.txt`, pour que les fichiers produits se chargent dans l'API.

## Lancer l'entraînement

Depuis la racine du dépôt, avec des dossiers de sortie neufs (le script refuse d'écraser un résultat) :

```bash
python -m experiments.train_consultation_models \
  --source . \
  --output experiments/results/<nouvelle-campagne> \
  --artifacts artifacts/ml-models/<nouvelle-campagne>
```

Le dossier `--artifacts` reçoit six fichiers : les modèles retenus (`*_consultation_selected_*.joblib`), les références médianes (`*_consultation_baseline_*.joblib`) et une reproduction du modèle de séjour à toutes variables, avec ses métadonnées. `artifacts/` n'est pas versionné : les modèles sont des données privées du projet.

## Déployer les modèles

Le rôle Ansible [`kyst`](../interface/ansible/roles/kyst/README.md) copie les deux modèles retenus de `artifacts/ml-models/final-2026-10-20-v3/` vers le serveur. Pour un essai local, voir [la configuration de l'intégration](../docs/kyst-integration.md#configuration).
