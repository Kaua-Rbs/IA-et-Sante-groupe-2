# Plan de tests

Objectif : verifier de bout en bout que le moteur d'optimisation, le pont de
donnees reelles, les graphiques, le CLI et les notebooks sont coherents et
reproductibles.

## Comment lancer

```bash
# toute la suite (depuis la racine du depot)
venv/bin/python -m unittest discover -t . -s tests -v

# un seul module / une seule classe
venv/bin/python -m unittest tests.test_optimizer -v
venv/bin/python -m unittest tests.test_optimizer.TestFitness -v
```

Aucune dependance supplementaire : tout repose sur `unittest` (stdlib). La
suite force le backend matplotlib `Agg` (pas d'affichage requis). Les tests qui
ont besoin du Parquet EDA reel ou de tkinter sont **ignores** automatiquement
si la ressource est absente.

## Resultat attendu

La suite complete doit terminer avec OK (tests tkinter optionnels). Toute regression doit se
traduire par un test en echec, pas par une inspection manuelle.

## Ce qui est couvert

### Environnement (`test_environment.py`)
- imports des dependances requises (numpy, pandas, matplotlib, seaborn,
  openpyxl, pyarrow, nbformat) et Python >= 3.12 ;
- tkinter local : import, creation d'une fenetre (si `DISPLAY`), import de
  `app_gui`.

### Coeur (`test_optimizer.py`)
- `generate_test_data` : formes, colonnes, determinisme par graine, ids uniques ;
- `PlanningProblem` : dimensions, options de vacation non vides et compatibles
  avec la specialite, `random_solution` et `neighbor` produisent des solutions
  valides et des mouvements hashables ;
- `fitness` : formule verifiee a la main sur trois cas (depassement de
  capacite vacation, terme d'equilibrage, depassement de lits) et cas parfait
  a 0 ;
- `occupation_lits` : fenetre de sejour correcte et bornee a l'horizon ;
- `exact_bruteforce` : optimum recalcule independamment par enumeration ;
- **les 5 metaheuristiques atteignent l'optimum exact** sur la petite instance
  de validation (critere d'acceptation principal) ;
- `RunResult` : champs, historique (`HISTORY_COLUMNS`), temps monotone, meilleure
  fitness = max de l'historique, solution valide ;
- determinisme : meme graine -> meme meilleure fitness et meme solution ;
- `optimize_planning` : les 5 cles `METHODE_*`, surcharge des parametres ;
- `solution_to_dataframe` : conversion indice de vacation -> `vacation_id`,
  tri par jour.

### Pont de donnees (`test_data_bridge.py`)
- `derive_specialite` : depuis CCAM, colonne explicite prioritaire, repli,
  regroupement des modalites rares dans "Autre" ;
- `build_patients` : schema, remplissage des manquants, bornes minimales,
  erreur si colonne requise absente ;
- `build_vacations` : comptage jour x specialite, ids uniques ;
- `select_horizon` : dernieres dates, reindexation 0..n-1, patients sans date
  ignores ;
- `prepare_inputs` : pipeline complet sur un Parquet synthetique, et
  `FileNotFoundError` si absent ;
- **donnees reelles** (si le Parquet est present) : pipeline + optimisation des
  5 methodes, fitness finies.

### Aleas et adaptation dynamique (`test_aleas.py`)
- Structures d'aleas (`Urgence`, `Annulation`, `IndisponibiliteLits`, `RetardBloc`, `ScenarioAleas`) et methodes d'ajout ;
- `generer_scenario_aleas` : reproductibilite et coherence du scenario genere ;
- `generer_plannings_alternatifs` : presence des 4 profils (Nominal, Robuste_Buffer, Securite_Lits, Alternatif_Date_B), marges positives et taux de divergence ;
- `extraire_options_date_a_b` : tableau exhaustif Date A / Date B et recommandations cliniques ;
- `adapter_planning` :
  - **Gel temporel** : sanctuarisation des interventions des jours passes ($j < j_{\text{courant}}$) ;
  - **Annulations et Urgences** : retrait effectif des annulations et affectation stricte des urgences dans leur fenetre temporelle autorisee ;
  - **Moindre perturbation** : penalite de stabilite evitant les deplacements non indispensables ;
  - **Rapport** d'arbitrage lisible et chiffre.

### Graphiques (`test_plotting.py` et `test_aleas.py`)
- `COULEURS` couvre exactement les 5 methodes historiques et
  `COULEURS_ETENDUES` les 10 methodes ;
- chaque fonction renvoie une `Figure` et peut etre sauvegardee en PNG (y
  compris `plot_adaptation_dynamique`, `plot_comparaison_alternatives` et
  `plot_occupation_lits_aleas`) ainsi que les figures multi-graines (boxplot,
  convergence mediane, taux de succes, qualite/temps).

### Hybrides (`test_hybrides.py`)
- les 3 hybrides (genetique x tabou, genetique x recuit, fourmis x tabou)
  atteignent l'optimum exact sur la petite instance, avec historique coherent
  et determinisme par graine ;
- hooks de reprise : `solution_initiale` (recuit, tabou, tabou x recuit),
  `population_initiale` (genetique), `pheromones_initiaux` +
  `meilleure_solution_initiale` (fourmis), `etat` en sortie (population /
  pheromones) ;
- `time_budget_s` respecte sur les hybrides ;
- selecteur de methodes : defaut = 5 historiques, `"toutes"` = 10, liste
  explicite, erreur sur nom inconnu ;
- `PlanningProblem.violations` : depassements vacations/lits et cas faisable.

### Systemes multi-agents (`test_multiagent.py`, sautes si mesa absent)
- SMA et SMA x metaheuristiques atteignent l'optimum exact sur la petite
  instance et renvoient un `RunResult` valide (historique, solution) ;
- determinisme par graine des deux modeles ;
- tableau noir : publication initiale, conservation du meilleur ;
- coordinateur : migration des agents sous la moyenne, redemarrages sur
  stagnation ;
- budget temps respecte.

### Benchmark (`test_benchmark.py`)
- campagne petite echelle (2 graines, budget reduit, 2 methodes) : reference
  exacte, tableau long, colonnes et bornes du resume, taux de reference ;
- `resumer` avec reference imposee : ecarts moyens, taux, rang moyen ;
- `kwargs_plafonnes` couvre les 10 methodes.

### Pont de coordination (`test_coordination_bridge.py`)
- `EtatBlocAdapter` : les 5 types d'evenements (indisponibilite, annulation,
  urgence, sejour prolonge, depassement) modifient l'etat sans le muter, les
  payloads invalides et evenements non supportes levent `ValueError` ;
- conversions `affectation <-> solution` (aller-retour) et exclusion des
  vacations indisponibles ;
- `ValidateurBloc` : accepte un plan faisable, rejette version obsolete,
  patient manquant, vacation inconnue, depassement de capacite ;
- `PlanificateurOptimiseur.propose` (async) : proposition valide, `None` si
  deadline depassee, erreur si methode inconnue ;
- bout en bout avec `hospital_sim.Coordinator` : indisponibilite puis urgence,
  chaque proposition est validee et explicitement acceptee.

### Grandes instances (`test_grandes_instances.py`)
- instance synthetique 400 patients / 180 vacations : `fitness`, `violations`
  et `occupation_lits` comparés a un **oracle naif** (pandas + boucles,
  independant du code vectorise), validite des solutions aleatoires et de 200
  voisins, determinisme ;
- les 10 methodes sur 300 patients / 96 vacations : solutions valides, fitness
  finies et negatifs, historique coherent, hook `solution_initiale` qui ne
  degrade jamais le point de depart ;
- **donnees reelles** (si le Parquet est present) : concordance oracle sur
  582 patients / 280 vacations, `solution_to_dataframe` coherent, recuit et SMA
  valides.

### Integration (`test_integration.py`)
- `optimiseur.run_demo` en sous-processus : code retour 0, 5 `[OPTIMUM ATTEINT]`,
  les 5 noms de methodes, plannings alternatifs, adaptation dynamique et presence de tous les fichiers attendus ;
- `notebooks/guide_optimisation.ipynb` : notebook valide, sans cellule en erreur ;
- `EDA_donees_bloc.ipynb` : **non modifie** (aucune cellule executee, aucune
  sortie).

## Hors perimetre (verification manuelle)

- Rendu visuel de `optimiseur/app_gui.py` : lancer
  `venv/bin/python -m optimiseur.app_gui` et verifier les 6 onglets (un test
  automatique construit la fenetre et lance une optimisation, mais pas la boucle
  d'evenements interactive).
- Qualite clinique du proxy `specialite` (CCAM/GHM) : validation metier requise.
- Pertinence des poids de la fonction de cout pour un usage reel.
- Execution complete de `EDA_donees_bloc.ipynb` sur le classeur source (lente) :
  la faire une fois via `jupyter nbconvert --execute` puis verifier le Parquet.

## Checklist de non-regression avant commit

1. `venv/bin/python -m unittest discover -t . -s tests -v` -> OK.
2. `venv/bin/python -m optimiseur.run_demo --n-patients 30 --n-days 5 --out resultats`
   -> 5 `[OPTIMUM ATTEINT]`.
3. `.venv/bin/python -m optimiseur.run_demo --toutes --budget 1 --out resultats`
   -> 10 `[OPTIMUM ATTEINT]`.
4. `.venv/bin/python -m optimiseur.run_coordination_demo` -> 2 acceptations et
   `validation_rejections = 0` dans les metriques.
5. Campagne complete (longue, ~12 min) :
   `.venv/bin/python -m optimiseur.run_benchmark --graines 20 --out resultats/benchmark --figures rapport/figures`
   -> CSV + 6 figures et references coherentes.
6. Campagne donnees reelles (longue, ~14 min, Parquet EDA requis) :
   `.venv/bin/python -m optimiseur.run_benchmark --sans-petite --donnees-reelles --graines 20 --budget-grande 4 --horizon 40 --capacite-min 600 --out resultats/benchmark_reel --figures rapport/figures`
   -> CSV, 3 figures `reelle_*` et reference coherente.
7. Si le schema de donnees change : regenerer le Parquet EDA et relancer la
   suite (les tests reels se declenchent automatiquement).

## Couplage Mesa

Voir tests/test_metaheuristics_mesa.py : decodeur commun, ordre strict des
objectifs, reference exacte a 128 affectations, budgets des cinq methodes,
solutions initiales partagees, sorties de processus et absence de fuite des
durees observees. Le guide docs/metaheuristics-mesa-assembly.md donne les
commandes de verification sur donnees historiques et instances generees.

## Oracle duration mode

`tests/test_oracle_simulation.py` verifies explicit opt-in, unchanged default
predictions, rounded perfect-duration inputs without mutating outcomes, hidden
future closures, exact ongoing availability, execution/turnover consistency,
identical generated room sizing between modes, mode labels in exports, and an
exact small reference evaluated with oracle durations. Run both modes on the
same workbook dates and seeds when comparing operational results.
