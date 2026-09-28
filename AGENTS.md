# AGENTS.md

Optimiseur de planning de bloc operatoire : trois metaheuristiques d'origine
(recuit simule, tabou, genetique) plus un **hybride Tabou x Recuit** et une
**colonie de fourmis (ACO)**. Entree = deux DataFrames pandas, sortie = planning
patient -> vacation + historiques de convergence.

## Setup

Le Python systeme est 3.14 et `ensurepip` / `python3-venv` sont absents : un
`.venv` classique echoue. Il a ete cree via `virtualenv` (deja installe en
`--user`). Pour reinstaller :

```bash
python3 -m virtualenv .venv          # PAS python3 -m venv
.venv/bin/pip install -r requirements.txt
```

Toujours utiliser `.venv/bin/python`. Versions verrouillees de fait :
pandas 3.0, numpy 2.5, matplotlib 3.11, pyarrow 25 (wheels 3.14 OK).

`python3-tk` est installe au niveau systeme : `app_gui.py` fonctionne
directement avec `.venv/bin/python` (le venv partage la stdlib du systeme).
Si tkinter manque un jour : `sudo apt install python3-tk`.

## Commandes

```bash
# Demo complete (sans GUI) : genere les donnees, lance les 5 methodes,
# ecrit CSV + 4 PNG dans --out, et verifie l'optimum par force brute.
.venv/bin/python -m optimiseur.run_demo --n-patients 30 --n-days 5 --out resultats

# Interface graphique (necessite tkinter)
.venv/bin/python -m optimiseur.app_gui

# Suite de tests (stdlib unittest, ~10 s, sans affichage)
.venv/bin/python -m unittest discover -t . -s tests -v

# Executer le notebook guide
.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/guide_optimisation.ipynb
```

Tout se lance **depuis la racine du depot** (le package `optimiseur/` doit
etre importable).

Il n'y a **ni linter, ni CI, ni git** dans ce depot. La verification de
reference combine la suite `tests/` (44 tests, dont : les 5 methodes doivent
atteindre l'optimum exact sur la petite instance) et `run_demo`. Le plan
detaille est dans `TEST_PLAN.md`. Les tests dependant du Parquet EDA reel ou de
tkinter se sautent d'eux-memes si la ressource est absente.

## Architecture

```text
optimiseur/               # package : tout le code
  optimizer.py            # coeur : modele + metaheuristiques
  plotting.py             # graphiques matplotlib
  data_bridge.py          # Parquet EDA -> schema optimiseur
  run_demo.py             # CLI headless
  app_gui.py              # interface Tkinter
EDA_donees_bloc.ipynb     # source de verite du pretraitement (racine)
notebooks/
  guide_optimisation.ipynb
tests/                    # suite unittest + helpers
TEST_PLAN.md              # plan de tests detaille
resources/                # gitignore : classeur reel + Parquet EDA
resultats/                # gitignore : sorties generees (CSV/PNG)
```

- `optimiseur/optimizer.py` — coeur : `generate_test_data`, `PlanningProblem`
  (fitness + voisinage), les 5 metaheuristiques, `optimize_planning`,
  `exact_bruteforce`. Seule dependance calcul : pandas/numpy.
- `optimiseur/plotting.py` — matplotlib ; importe les constantes `METHODE_*`
  depuis `.optimizer`.
- `optimiseur/run_demo.py` — CLI headless (backend `Agg`).
- `optimiseur/app_gui.py` — Tkinter (backend `TkAgg`), thread de calcul +
  `queue` pour rester reactif. Bouton "Charger donnees reelles (EDA)" : lit le
  Parquet via `data_bridge.prepare_inputs` (le `.xlsx` n'est jamais lu
  directement, c'est le notebook EDA qui le transforme).
- `optimiseur/data_bridge.py` — convertit le Parquet du notebook EDA au schema
  de l'optimiseur.
- `EDA_donees_bloc.ipynb` — **source de verite du pretraitement, ne pas
  modifier** ; produit `resources/donnees_bloc_pretraitees.parquet`.
- `notebooks/guide_optimisation.ipynb` — notebook pedagogique pas a pas (des
  donnees EDA aux 5 methodes) ; executable meme sans le Parquet reel (repli
  synthetique). Il ajoute la racine du depot a `sys.path`, donc fonctionne
  lance depuis la racine ou depuis `notebooks/`.

Direction des imports : `app_gui` -> `plotting` + `optimizer` + `data_bridge`,
`run_demo` -> `plotting` + `optimizer` ; `plotting` -> `optimizer` (imports
relatifs `from . import ...`). Ne jamais importer l'inverse.

## Conventions critiques

- **Une `Solution` est un dict `patient_id -> INDICE positionnel de vacation`**
  (0..n-1), pas un `vacation_id`. `fitness`, `neighbor` et `exact_bruteforce`
  reposent sur cette convention ; `solution_to_dataframe` fait la conversion
  vers `vacation_id`.
- `fitness` renvoie `-cout` : **on maximise**, `0` = planning parfait.
- Les noms de methodes sont centralises en constantes `METHODE_*` dans
  `optimizer.py`. Ajouter une methode oblige a mettre a jour : `optimize_planning`,
  `plotting.COULEURS`, `app_gui.METHODES` et le tableau du `optimiseur/README.md`.
- Le backend matplotlib doit etre choisi **avant** d'importer `pyplot`
  (`Agg` dans `run_demo`, `TkAgg` dans `app_gui`).
- `PlanningProblem` precalcule des tableaux numpy (`_pat_duree`, `_vac_day`,
  `_patient_options`...) : ne pas reintroduire d'acces `df.loc[pid]` dans la
  boucle chaude de `fitness`, c'est ce qui garantit les temps actuels.

## Donnees

Schema attendu par `optimiseur/optimizer.py` :

- patients : `patient_id`, `specialite`, `duree_operatoire` (min),
  `duree_sejour` (jours)
- vacations : `vacation_id`, `jour`, `specialite`, `capacite_min` (min)

`optimiseur/data_bridge.py::prepare_inputs` construit ces tables depuis le Parquet EDA :

- `specialite` est un **proxy** derive de `ccam_1` (1re lettre), sinon
  `ghm_code`, sinon `interv_type` — a valider cliniquement.
- `duree_operatoire` <- `room_duration_min`, `duree_sejour` <-
  `duree_sejour_corrigee` ; seules les `horizon_jours` dernieres dates sont
  retenues puis reindexees en jours `0..n-1`.
- Les identifiants (`no_cas`, `id_patient`, `praticien`, `nom_chir`) sont
  ecartes (confidentialite).

Le classeur source et le Parquet vivent dans `resources/` (ignore par git,
confidentialite) : `resources/donees bloc anonyme pour centrale 2026.xlsx` et
`resources/donnees_bloc_pretraitees.parquet` sont **presents localement**.
Executer `EDA_donees_bloc.ipynb` depuis la racine du depot pour regenerer le
Parquet ; les notebooks basculent sur des donnees synthetiques seulement si le
Parquet est absent. `run_demo` ecrit dans `resultats/` (ignore par git).

## Pieges

- Fichiers `*:Zone.Identifier` a la racine : metadonnees Windows telechargees,
  sans interet, a ignorer / ne pas suivre.
- Langue mixte : code, docstrings, README et noms de methodes en francais
  (sans accents dans le code), notebook EDA en anglais. Garder cette coherence.
- `resources/` est reference avec la coquille `donees` dans le notebook EDA
  (`donees bloc anonyme ...`) : ne pas "corriger" sans mettre a jour le notebook.
- Skills OpenCode dans `.opencode/skill/` (auto-charges) : `codebase-design`,
  `improve-codebase-architecture`, `code-review`, `domain-modeling`,
  `diagnosing-bugs`, `writing-for-agents`, `grilling` (issus de
  github.com/mattpocock/skills). Les relire avant de restructurer du code.
