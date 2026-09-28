# Plan de tests

Objectif : verifier de bout en bout que le moteur d'optimisation, le pont de
donnees reelles, les graphiques, le CLI et les notebooks sont coherents et
reproductibles.

## Comment lancer

```bash
# toute la suite (depuis la racine du depot)
.venv/bin/python -m unittest discover -t . -s tests -v

# un seul module / une seule classe
.venv/bin/python -m unittest tests.test_optimizer -v
.venv/bin/python -m unittest tests.test_optimizer.TestFitness -v
```

Aucune dependance supplementaire : tout repose sur `unittest` (stdlib). La
suite force le backend matplotlib `Agg` (pas d'affichage requis). Les tests qui
ont besoin du Parquet EDA reel ou de tkinter sont **ignores** automatiquement
si la ressource est absente.

## Resultat attendu

`Ran 44 tests ... OK` en une dizaine de secondes. Toute regression doit se
traduire par un test en echec, pas par une inspection manuelle.

## Ce qui est couvert

### Environnement (`test_environment.py`)
- imports des dependances requises (numpy, pandas, matplotlib, seaborn,
  openpyxl, pyarrow, nbformat) et Python 3.14 ;
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

### Graphiques (`test_plotting.py`)
- `COULEURS` couvre exactement les 5 methodes ;
- chaque fonction renvoie une `Figure` et peut etre sauvegardee en PNG.

### Integration (`test_integration.py`)
- `optimiseur.run_demo` en sous-processus : code retour 0, 5 `[OPTIMUM ATTEINT]`,
  les 5 noms de methodes, et presence des 6 fichiers attendus ;
- `notebooks/guide_optimisation.ipynb` : notebook valide, sans cellule en erreur ;
- `EDA_donees_bloc.ipynb` : **non modifie** (aucune cellule executee, aucune
  sortie).

## Hors perimetre (verification manuelle)

- Rendu visuel de `optimiseur/app_gui.py` : lancer
  `.venv/bin/python -m optimiseur.app_gui` et verifier les 6 onglets (un test
  automatique construit la fenetre et lance une optimisation, mais pas la boucle
  d'evenements interactive).
- Qualite clinique du proxy `specialite` (CCAM/GHM) : validation metier requise.
- Pertinence des poids de la fonction de cout pour un usage reel.
- Execution complete de `EDA_donees_bloc.ipynb` sur le classeur source (lente) :
  la faire une fois via `jupyter nbconvert --execute` puis verifier le Parquet.

## Checklist de non-regression avant commit

1. `.venv/bin/python -m unittest discover -t . -s tests -v` -> OK.
2. `.venv/bin/python -m optimiseur.run_demo --n-patients 30 --n-days 5 --out resultats`
   -> 5 `[OPTIMUM ATTEINT]`.
3. Si le schema de donnees change : regenerer le Parquet EDA et relancer la
   suite (les tests reels se declenchent automatiquement).
