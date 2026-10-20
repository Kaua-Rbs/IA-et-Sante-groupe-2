# Modèles de prédiction

KYST s'appuie sur deux modèles, entraînés sur le classeur de l'hôpital (2019–2022) :

| Modèle | Cible | Unité | Fichier déployé |
| :--- | :--- | :--- | :--- |
| Temps de salle | De l'entrée à la sortie de salle, sans la remise en état | minutes | `room_consultation_selected_2026-10-20_v1.joblib` |
| Durée de séjour | De l'admission à la sortie, bornes incluses (ambulatoire = 1) | jours calendaires | `los_consultation_selected_2026-10-20_v1.joblib` |

Le type d'hébergement n'est pas un troisième modèle : un séjour prédit qui s'arrondit à un jour (moins de 1,5 jour) est classé **ambulatoire** et réserve une seule journée. Le modèle de séjour prédit une moyenne : l'ancien seuil `<= 1` ne classait presque aucun patient en ambulatoire.

Le code est dans [`prediction/`](../prediction/README.md), l'entraînement dans [`experiments/`](../experiments/README.md) ; le branchement dans l'application est décrit dans [l'intégration de l'IA dans KYST](integration-ia-kyst.md).

## Données et découpage

Les jeux d'entraînement sont produits par les [notebooks de préparation](../notebooks/README.md) à partir du classeur décrit dans le [dictionnaire des données](dictionnaire-donnees.md). Le découpage est **chronologique** et **disjoint par patient** : un même patient n'apparaît jamais dans deux partitions.

| Tâche | Entraînement (2019–2020) | Sélection (début 2021) | Calibration (fin 2021) | Test (2022) |
| :--- | ---: | ---: | ---: | ---: |
| Temps de salle | 7 079 | 1 678 | 1 400 | 3 043 |
| Durée de séjour | 7 124 | 1 684 | 1 402 | 3 059 |

Les modèles sont ajustés sur 2019–2020 uniquement. Le choix entre candidats se fait sur le début de 2021, la calibration des intervalles sur la fin de 2021, et 2022 ne sert qu'à mesurer. Les résultats de 2022 avaient toutefois déjà été consultés lors de travaux antérieurs : ce n'est pas un test externe en aveugle.

## Variables : ce qui est connu en consultation

Les modèles déployés n'utilisent que les sept variables disponibles dans le formulaire de KYST : âge, sexe, type d'intervention prévu, diagnostic principal CIM-10 et sa famille, acte CCAM principal et sa famille (`prediction/consultation_features.py`).

Sont exclus : anesthésie, praticien et chirurgien (inconnus du formulaire), diagnostics et actes secondaires, dates, durées réelles et identifiants. Les catégories rares sont regroupées à partir des seules données d'entraînement.

Une version antérieure utilisait aussi l'anesthésie et le praticien. Elle était plus précise sur les données historiques (14,3 min), mais tombait à 17,9 min dès que ces champs manquaient, c'est-à-dire dans KYST. D'où ces modèles « consultation », entraînés directement sur les champs réellement disponibles.

## Résultats sur le test 2022

### Temps de salle (3 043 interventions)

| Modèle | Erreur absolue moyenne (min) |
| :--- | ---: |
| Ancien modèle, toutes les variables (référence rétrospective) | 14,33 |
| Ancien modèle, champs absents de KYST masqués | 17,90 |
| Médiane par type d'intervention | 18,15 |
| **Gradient boosting « consultation » (déployé)** | **16,62** |

Le modèle déployé gagne 1,3 min (7 %) sur l'ancien modèle privé de ses champs, et 1,5 min (8 %) sur la médiane par type d'intervention. Les bornes unilatérales calibrées couvrent 79,8 % (P80) et 95,7 % (P95) des cas. Si le type d'intervention n'est pas renseigné, l'erreur monte à 20,7 min.

### Durée de séjour (3 059 séjours)

| Modèle | Erreur absolue moyenne (jours) |
| :--- | ---: |
| Modèle complet, toutes les variables (référence rétrospective) | 0,45 |
| Modèle complet, champs absents de KYST masqués | 0,65 |
| **Médiane par type d'intervention** | **0,49** |
| XGBoost « consultation » (déployé) | 0,51 |

Le XGBoost « consultation » fait mieux que le modèle complet privé de ses champs, mais **pas mieux que la médiane par type d'intervention**, ni en sélection (0,46 contre 0,43) ni en test. Son intervalle à 90 % couvre 89,2 % des séjours.

Les erreurs se calculent sur des jours calendaires inclusifs : pour planifier les lits après l'intervention, il faut retrancher les jours passés avant l'opération.

## Limites

- **Longues interventions** : sur les 397 interventions de 2 h ou plus, l'erreur moyenne est de 36 min et le modèle sous-estime dans 90 % des cas ; la borne P95 ne couvre que 74 % d'entre elles.
- **Longs séjours** : sur les 67 séjours de 7 jours ou plus, l'erreur moyenne est de 2,5 jours, avec 99 % de sous-estimations et une couverture de l'intervalle de 25 %. Une bonne couverture globale masque ce défaut : ces intervalles ne suffisent pas à planifier sans risque les lits pour les longs séjours.
- **Moment de saisie** : on ne sait pas si les codes CIM-10 et CCAM du classeur étaient connus dès la consultation ; les codes prévus peuvent différer des codes facturés. L'âge exact de l'entraînement diffère aussi de l'âge calculé par KYST à partir de l'année de naissance.
- **Intervalle de la salle** : les bornes P80/P95 existent dans le modèle mais ne sont pas encore affichées dans KYST.
- **Validation** : l'évaluation est rétrospective. Un usage clinique demanderait une cohorte prospective, avec des horodatages de saisie vérifiés.

## Entraîner les modèles

La commande et ses prérequis sont dans [experiments/README.md](../experiments/README.md). Le manifeste d'entraînement, [`manifest.json`](../experiments/results/final-consultation-2026-10-20-v3/manifest.json), garde les empreintes SHA-256 des données d'entrée, du code source et des six fichiers produits. Les métriques détaillées sont dans [`model_metrics.csv`](../experiments/results/final-consultation-2026-10-20-v3/model_metrics.csv) et [`report.json`](../experiments/results/final-consultation-2026-10-20-v3/report.json).

Les modèles ont été entraînés sous Python 3.14 avec scikit-learn 1.9.1, xgboost 3.4.1, pandas 3.0.6 et joblib 1.6.0 ([versions exactes](../experiments/final_model_requirements.txt)) ; l'API les charge avec les mêmes versions de bibliothèques, sous Python 3.13.
