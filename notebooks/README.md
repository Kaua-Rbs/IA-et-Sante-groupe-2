# notebooks

Analyse exploratoire du classeur de l'hôpital et préparation des jeux qui servent à [entraîner les modèles](../experiments/README.md). Les colonnes du classeur sont décrites dans le [dictionnaire des données](../docs/data-dictionary.md).

| Ordre | Notebook | Lit | Produit (dans `resources/`, non versionné) |
| ---: | :--- | :--- | :--- |
| 1 | `EDA_donees_bloc.ipynb` | `donees bloc anonyme pour centrale 2026.xlsx` | `donnees_bloc_pretraitees.parquet` : table nettoyée, durées et âges dérivés |
| 2 | `preprocessing_surgery_duration.ipynb` | `donnees_bloc_pretraitees.parquet` | `model_surgery_duration_dataset.parquet` : jeu du modèle de temps de salle |
| 3 | `preprocessing_los.ipynb` | `donnees_bloc_pretraitees.parquet` | `model_los_dataset.parquet` : jeu du modèle de durée de séjour |

L'analyse exploratoire couvre le schéma, les valeurs manquantes et les doublons, les âges et durées dérivés, l'activité par mois et par jour, les catégories cliniques fréquentes, les horaires du bloc et les durées par type d'intervention.

Les deux jeux de modélisation ne gardent que les informations disponibles au moment de la planification, pour éviter toute fuite de données. Ils contiennent un découpage chronologique, disjoint par patient, en entraînement, validation et test. Les colonnes `split_*` sont des métadonnées d'audit : elles ne doivent jamais servir de variables. Les catégories restent en texte ; leur encodage se fait dans le pipeline de chaque modèle, sur l'entraînement seul.

## Lancer

Après avoir installé [`requirements.txt`](../requirements.txt) et placé le classeur dans `resources/` :

```bash
jupyter lab
```

Exécuter les notebooks dans l'ordre, de haut en bas. Ils se lancent depuis la racine du dépôt ou depuis `notebooks/` : les chemins vers `resources/` sont résolus à partir de la racine.

Aucun notebook n'affiche de ligne individuelle : les identifiants de patients, de séjours et de praticiens sont exclus des aperçus et des graphiques. Vider les sorties inutiles avant de commiter.
