# Evaluation du modele de duree de salle

## Portee de cette branche et protocole courant

Cette branche, basee sur main, contient uniquement le modele OR et ses interfaces DataFrame. Le moteur optimiseur et le modele LOS restent sur leurs branches respectives. Les verifications historiques avec les cinq metaheuristiques ont ete effectuees dans le checkout optimiseur; elles ne sont pas une verification de cette branche autonome.

Le code courant selectionne sur la premiere partie chronologique de validation et reserve une partie ulterieure, disjointe en patients, pour calibrer les bornes optionnelles P80/P95. Les variables calendrier sont exclues par defaut. Selection: MAE validation a moins de 0.2 minute du meilleur, puis temps d apprentissage minimum. Le test sert au rapport, pas a la selection. Les erreurs de queue sont rapportees pour chaque candidat.

Les tableaux ci-dessous documentent une execution historique utilisant toute la validation et des variables calendrier. Ils ne constituent pas les resultats du protocole courant; consulter les CSV et selection.json generes localement pour celui-ci. Les hypotheses de disponibilite preoperatoire doivent etre validees pour les champs cliniques utilises.

La preparation reutilisable se trouve dans duration_features.py. L inference raw=True requiert le mapping de categories appris sur train, lu depuis le fichier .preprocessing.joblib associe au dataset. Le notebook utilise maintenant les fonctions partagees et exporte ce mapping apres le Parquet. Regenerer les anciens datasets pour obtenir le mapping; les artefacts historiques sans mapping restent utilisables avec les variables deja preparees.

## Comparaison des baselines avant ML

Executer `.venv/Scripts/python.exe surgery_duration.py --baselines-only` pour evaluer neuf references sans importer CatBoost/XGBoost ni entrainer un modele avance. Resultats complets : `results/surgery_duration_baseline_comparison.csv` (MAE, RMSE, mediane AE, R2, temps apprentissage/inference et choix sur validation).

Les medianes sont apprises uniquement sur train. Tout groupe inconnu ou insuffisamment represente dans les variantes min10 utilise la mediane globale train. Le seuil 10 est fixe, pas choisi sur test. Les partitions patient/temps initiales sont preservees.

| Baseline | MAE validation min | MAE test min |
|---|---:|---:|
| Globale | 29.225 | 29.108 |
| Procedure | 20.331 | 19.589 |
| Famille procedure | 20.043 | 19.122 |
| Chirurgien | 23.932 | 25.476 |
| Type anesthesie | 24.787 | 24.685 |
| Procedure + chirurgien | 18.444 | 18.175 |
| Procedure + chirurgien, min10 | 19.706 | 19.954 |
| Type intervention | 18.786 | 18.148 |
| Type intervention + chirurgien, min10 | **17.785** | 18.328 |

La derniere baseline est la reference retenue sur validation; la meilleure valeur descriptive sur test est celle du type intervention seul. Toutes s entrainent en moins de 0.01 seconde lors de cette execution. Les variantes sont aussi placees avant les modeles ML dans la prochaine comparaison complete. Six tests ciblant notamment les groupes inconnus/rares et la separation patient/temps passent.

## Pipeline initial

Entree : `resources/model_surgery_duration_dataset.parquet`, produit par `preprocessing_surgery_duration.ipynb` depuis le Parquet EDA. Cible : `target_surgery_duration_min` = occupation de salle entree-sortie, non duree incision-fermeture. Les valeurs manquantes, endpoints nuls et durees hors ]0, 1440] sont exclus en amont; aucune exclusion supplementaire dans cette comparaison.

Train : 7 079 interventions, 5 709 patients, 2019-2020. Validation : 3 189 interventions, 2 675 patients, 2021. Test : 3 043 interventions, 2 602 patients, 2022. Aucun patient commun, aucun identifiant/date manquant; partitions conservees exactement. Les interventions ulterieures des patients deja vus sont exclues par le preprocessing initial. Cela mesure la generalisation aux nouveaux patients, pas tous les patients futurs.

20 variables : age; sexe; type intervention; type anesthesie et anesthesie loco-regionale; praticien et chirurgien; cycles mois/jour de semaine et weekend; nombres de diagnostics secondaires et actes CCAM; indicateurs anesthesie manquante; CIM principal/famille et CCAM principal/famille. Annee exclue. Categories normalisees, manquants explicites et raretes (<10 occurrences) regroupees sur train uniquement. Imputation numerique mediane et encodage ajustes sur train.

Modeles precedents : RF 300 arbres one-hot; XGBoost MAE 700 iterations profondeur 7; CatBoost RMSE 700 iterations profondeur 7, poids 3 pour les cas >=P90 train. Deux autres CatBoost P80/P95 sont entraines a chaque execution. Aucun GridSearchCV, aucune recherche exhaustive, aucun early stopping initial. La selection precedente favorise les longues operations plutot que le MAE moyen. Les metrics initiales sont MAE, RMSE, R2 et erreurs de queue, sans temps ni mediane AE.

## Methode de comparaison

Graine 42. Tous les modeles utilisent le meme train/validation/test. Selection : MAE validation a moins de 0.2 minute du meilleur, puis apprentissage le plus rapide. Test utilise uniquement pour le rapport, jamais pour ajuster les parametres. CatBoost et XGBoost rapide utilisent early stopping sur validation; HistGradientBoosting utilise aussi la validation externe. Les configurations precedentes gardent leurs iterations fixes. Les temps sont des mesures murales locales, une seule execution, dependantes de la charge machine; inference = mediane de trois predictions du lot test complet, preprocessing inclus. Les petites differences temporelles ne permettent donc pas de tirer des conclusions precises sur les performances.

Baselines : mediane globale, procedure, chirurgien, procedure-chirurgien et type intervention; groupes inconnus -> mediane globale train. Ridge/ElasticNet : one-hot et numeriques standardises; forets et XGBoost : one-hot; HistGradientBoosting : categories natives via codes ordinaux, categories inconnues -1; CatBoost : categories natives. LightGBM absent du venv, non teste; aucune installation supplementaire.

Les medianes historiques de Ridge utilisent, pour chaque mois de train, uniquement les mois strictement anterieurs; premier mois sans historique = prior fixe de 60 minutes. Validation/test utilisent uniquement les tables apprises sur train. Pas de moyenne incluant la cible de la ligne. Les categories restent celles deja regroupees par le preprocessing initial; les agregats ne sont donc pas ceux des codes bruts rares.

## Resultats test

| Modele | MAE min | RMSE min | Mediane AE min | R2 | Apprentissage s | Inference lot s |
|---|---:|---:|---:|---:|---:|---:|
| HistGradientBoosting log1p | 14.397 | 21.362 | 10.070 | 0.671 | 0.376 | 0.0390 |
| CatBoost no calendar | 14.416 | 21.300 | 10.218 | 0.672 | 32.864 | 0.0251 |
| HistGradientBoosting squared_error | 14.539 | 21.094 | 10.695 | 0.679 | 0.659 | 0.0421 |
| HistGradientBoosting absolute_error | 14.561 | 21.641 | 10.405 | 0.662 | 0.689 | 0.0457 |
| CatBoost native RMSE | 14.642 | 21.022 | 10.683 | 0.681 | 34.681 | 0.0283 |
| Previous XGBoost | 14.652 | 21.396 | 10.565 | 0.669 | 2.167 | 0.0692 |
| CatBoost native MAE depth4 | 14.681 | 21.732 | 10.419 | 0.659 | 22.118 | 0.0309 |
| CatBoost native log1p | 14.701 | 21.678 | 10.339 | 0.661 | 35.570 | 0.0280 |
| CatBoost native MAE | 14.733 | 21.562 | 10.692 | 0.664 | 34.788 | 0.0297 |
| XGBoost fast | 14.932 | 21.819 | 10.917 | 0.656 | 7.107 | 0.0473 |
| Ridge log1p | 15.026 | 21.927 | 10.964 | 0.653 | 0.154 | 0.0302 |
| Previous RandomForest | 15.250 | 21.858 | 11.253 | 0.655 | 44.315 | 0.1670 |
| Previous weighted CatBoost | 15.288 | 21.530 | 11.167 | 0.665 | 56.308 | 0.0269 |
| RandomForest fast | 15.483 | 22.119 | 11.390 | 0.647 | 9.797 | 0.0862 |
| Ridge alpha100 | 15.844 | 22.177 | 12.366 | 0.645 | 0.122 | 0.0278 |
| Ridge | 15.872 | 22.092 | 12.624 | 0.648 | 0.141 | 0.0245 |
| Ridge historical medians | 15.900 | 22.087 | 12.616 | 0.648 | 0.773 | 0.0352 |
| ElasticNet | 16.094 | 22.532 | 12.643 | 0.633 | 0.217 | 0.0264 |
| CatBoost conservative features | 16.443 | 24.320 | 11.713 | 0.573 | 16.129 | 0.0134 |
| ExtraTrees | 16.662 | 24.136 | 11.769 | 0.579 | 18.739 | 0.1023 |
| LinearRegression | 16.916 | 23.321 | 13.157 | 0.607 | 0.275 | 0.0232 |
| Intervention type median | 18.148 | 26.532 | 13.000 | 0.492 | 0.004 | 0.0014 |
| Procedure surgeon median | 18.175 | 26.424 | 12.500 | 0.496 | 0.006 | 0.0035 |
| Procedure median | 19.589 | 28.513 | 14.000 | 0.413 | 0.006 | 0.0013 |
| Surgeon median | 25.476 | 34.671 | 19.000 | 0.132 | 0.007 | 0.0014 |
| Global median | 29.108 | 37.786 | 25.000 | -0.031 | 0.002 | 0.0006 |

## Choix recommande

**HistGradientBoosting log1p** : MAE 14.397 min, RMSE 21.362, mediane AE 10.070, R2 0.671. Gain global median : 14.711 min (50.5%). Gain ancien CatBoost : 0.891 min (5.8%). Apprentissage 0.376 s contre 56.308 s; inference test 0.0390 s. CatBoost sans calendrier est tres proche mais beaucoup plus lent a entrainer; son inference est legerement plus rapide.

Le log1p aide HistGradientBoosting (14.539 -> 14.397 min sur test) et Ridge (15.872 -> 15.026); les predictions sont reconverties avec expm1 avant evaluation. La suppression du calendrier aide CatBoost (14.733 -> 14.416), mais pas assez pour justifier son temps. Les agregats historiques Ridge ne gagnent pas (15.872 -> 15.900); ExtraTrees (16.662), ElasticNet (16.094) et la ponderation des longues durees (15.288) ne sont pas retenus. Aucun clipping/filtering supplementaire teste ou applique.

## Qualite et erreurs

Durees : min 3, mediane 70, P90 128, P95 148, P99 189, P99.9 269.69, max 332 minutes; asymetrie train 1.164. 31 cas <15 minutes et 185 cas >180 minutes. Ces valeurs peuvent correspondre a des interventions courtes/longues valides ou des erreurs de saisie; les donnees seules ne permettent pas de conclure. Une revue clinique des endpoints est necessaire. Aucun doublon exact dans la table modele. Les endpoints 0 sont traites comme manquants en amont, ce qui pourrait aussi exclure une vraie heure de minuit.

Modele retenu : MAE courts <60 = 9.913 minutes (1 135 cas), moyens 60-120 = 13.576 (1 511), longs >=120 = 30.341 (397). Plus grande erreur absolue : 252.990 minutes. Sept des dix plus grosses erreurs impliquent __RARE__; la frequence du groupe rare ne mesure pas la frequence de chaque procedure brute. Les memes sept cas rares apparaissent parmi les dix pires des deux autres meilleurs modeles. Les CSV contiennent les dix erreurs les plus fortes par modele et les MAE par type intervention/CCAM. Pas de specialite clinique valide disponible : aucun proxy anatomique presente comme vraie specialite.

Importance permutation sur validation (augmentation MAE minutes, 3 repetitions) :

- cim_diag_pr: +4.235 min (ecart type 0.162).
- interv_type: +3.169 min (ecart type 0.235).
- praticien: +2.482 min (ecart type 0.056).
- cim_diag_family: +1.099 min (ecart type 0.043).
- anesth_type: +1.086 min (ecart type 0.006).
- nom_chir: +0.994 min (ecart type 0.028).
- ccam_1_family: +0.585 min (ecart type 0.100).
- num_ccam_codes: +0.505 min (ecart type 0.011).
- ccam_1: +0.177 min (ecart type 0.022).
- sexe: +0.160 min (ecart type 0.025).

Les variables correlees peuvent partager leur importance; ce ne sont pas des effets causaux.

## Limites et absence de fuite

La separation patient/temps, les imputations, encodages, regroupements et agregats ne montrent pas de fuite test. En revanche, la disponibilite avant chirurgie de CIM, CCAM, nombres de diagnostics/actes et anesthesie ne peut pas etre prouvee a partir de ce fichier retrospectif. Les mesures du modele complet supposent ces variables planifiees; une validation locale est indispensable avant utilisation operationnelle. Le CatBoost conservateur sans ces variables obtient 16.443 min : les gains dependent sensiblement des champs cliniques. Les heures reelles de salle/incision, LOS, discharge et GHM sont exclus. Pas de salle/session ou heure planifiee fiable dans la table : aucune variable de ce type inventee.

Le test est deja visible dans l ancien notebook : ce n est donc pas une evaluation prospective aveugle nouvelle. La comparaison fige les choix sur validation, mais une nouvelle cohorte temporelle independante serait necessaire pour confirmer les gains. Le jeu date de 2019-2022 et peut avoir derive. Pas de garantie de couverture conformale avec derive temporelle/reutilisation de validation.

## Integration et reproduction

Le benchmark sauvegarde le modele et les transformations dans results/surgery_duration_model.joblib. Avec --train-bounds, il entraine aussi les modeles quantiles P80/P95 et sauvegarde leurs offsets de calibration. Le notebook charge les artefacts par defaut; TRAIN_MODELS=True lance explicitement le benchmark et TRAIN_BOUNDS=True y ajoute les bornes.

predict_duration(frame) retourne une Series duree_operatoire. predict_schedule(frame) retourne le point et les bornes disponibles. apply_predicted_durations(patients, features, risk="point") retourne une copie avec la duree choisie; il verifie les index et les predictions finies positives. Les risques p80/p95 necessitent des bornes sauvegardees. L adaptateur ne depend pas d un import optimiseur. Les modeles calendrier sont refuses par defaut pour des durees fixes: ils exigent un recalcul par date candidate.

L integration executable avec optimize_planning est une etape ulterieure sur une branche d integration. Aucun fichier LOS, moteur optimiseur ou EDA source n est modifie ici. Les controles historiques mentionnes dans ce rapport ont ete effectues sur le checkout contenant l optimiseur, pas sur ce checkout autonome.

Depuis la racine sous Windows:

```powershell
.venv/Scripts/python.exe surgery_duration.py --train-bounds
.venv/Scripts/python.exe -m unittest tests.test_surgery_duration -v
```

Sous Linux utiliser .venv/bin/python. Toutes les dependances ML obligatoires sont dans requirements.txt; LightGBM est optionnel. Le jeu modele doit etre genere depuis les donnees locales autorisees. Les artefacts, predictions individuelles et mappings ne sont pas versionnes. La couverture mesuree ne garantit pas la couverture future sous derive temporelle; P95 patient ne garantit pas P95 vacation.