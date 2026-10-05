# AGENTS.md

Optimiseur de planning de bloc operatoire : trois metaheuristiques d'origine
(recuit simule, tabou, genetique) plus un **hybride Tabou x Recuit**, une
**colonie de fourmis (ACO)**, ainsi qu'un **systeme complet de gestion des aleas**
(urgences, annulations, indisponibilite de lits, retards bloc) combinant
**generation proactive de plannings alternatifs** (Date A / Date B, robustesse) et
**adaptation dynamique reactive** (replanning sous contrainte de stabilite).
Entree = deux DataFrames pandas, sortie = planning patient -> vacation +
historiques de convergence + plannings de repli et adaptations.

## Setup

Le Python systeme est 3.14 et `ensurepip` / `python3-venv` sont absents : un
`.venv` classique echoue. Il a ete cree via `virtualenv` (deja installe en
`--user`). Pour reinstaller :

```bash
python3 -m virtualenv .venv          # PAS python3 -m venv
.venv/bin/pip install -r requirements.txt
```

Toujours utiliser `.venv/bin/python` (ou l'interpreteur Python 3.14 du systeme). Versions verrouillees de fait :
pandas 3.0, numpy 2.5, matplotlib 3.11, pyarrow 25 (wheels 3.14 OK).

Sous Windows / Python 3.14, definir la variable d'environnement `OPENBLAS_NUM_THREADS=1`
pour eviter les erreurs d'allocation memoire d'OpenBLAS.

`python3-tk` est installe au niveau systeme : `app_gui.py` fonctionne
directement avec `.venv/bin/python` (le venv partage la stdlib du systeme).
Si tkinter manque un jour : `sudo apt install python3-tk`.

## Commandes

```bash
# Demo complete (sans GUI) : genere les donnees, lance les 5 methodes,
# plannings alternatifs (Date A/B), simulation d'aleas et adaptation dynamique,
# ecrit CSV + graphiques PNG dans --out, et verifie l'optimum par force brute.
python -m optimiseur.run_demo --n-patients 30 --n-days 5 --out resultats

# Interface graphique (necessite tkinter) avec onglets Convergence, Comparaison,
# Planning, Lits, Tableau, Plannings alternatifs (Date A/B) et Aleas & Adaptation.
python -m optimiseur.app_gui

# Suite complete de tests (stdlib unittest, 57 tests, sans affichage)
python -m unittest discover -t . -s tests -v

# Executer les notebooks guides et rapports
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/guide_optimisation.ipynb
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/rapport_aleas_et_adaptation.ipynb
```

Tout se lance **depuis la racine du depot** (`IA-et-Sante-groupe-2`, le package `optimiseur/` doit
etre importable).

La verification de reference combine la suite `tests/` (57 tests, couvrant le modele,
les 5 metaheuristiques, le pont de donnees EDA, les visualisations, les 4 types d'aleas,
les plannings alternatifs, l'adaptation dynamique et les deux notebooks) et `run_demo`. Le plan detaille est dans `TEST_PLAN.md`.
Les tests dependant du Parquet EDA reel ou de tkinter se sautent d'eux-memes si la ressource est absente.

## Architecture

```text
optimiseur/               # package : tout le code
  optimizer.py            # coeur : modele PlanningProblem + 5 metaheuristiques
  aleas.py                # systeme d'aleas + plannings alternatifs + adaptation dynamique
  plotting.py             # graphiques matplotlib (convergence, planning, lits, aleas)
  data_bridge.py          # Parquet EDA -> schema optimiseur
  run_demo.py             # CLI headless de demonstration complete
  app_gui.py              # interface Tkinter avec onglets dedies
EDA_donees_bloc.ipynb     # source de verite du pretraitement (racine)
notebooks/
  guide_optimisation.ipynb             # guide pas a pas des metaheuristiques
  rapport_aleas_et_adaptation.ipynb    # rapport operationnel et guide aleas & adaptation
tests/                    # suite unittest (test_optimizer, test_aleas, test_plotting, ...)
TEST_PLAN.md              # plan de tests detaille
resources/                # gitignore : classeur reel + Parquet EDA
resultats/                # gitignore : sorties generees (CSV/PNG)
```

- `optimiseur/optimizer.py` — coeur : `generate_test_data`, `PlanningProblem`
  (fitness + voisinage), les 5 metaheuristiques, `optimize_planning`,
  `exact_bruteforce`. Accepte une capacite de lits scalaire ou vectorielle journaliere
  (`_lits_capacity_arr`) ainsi que des retards par vacation (`vacation_delays`).
- `optimiseur/aleas.py` — module d'aleas :
  - Classes d'aleas : `Urgence`, `Annulation`, `IndisponibiliteLits`, `RetardBloc`, `ScenarioAleas`.
  - Simulateur d'aleas reproductible : `generer_scenario_aleas`.
  - Generation de plannings alternatifs : `generer_plannings_alternatifs` (profils Nominal,
    Robuste_Buffer, Securite_Lits, Alternatif_Date_B) et `extraire_options_date_a_b`.
  - Adaptation dynamique : `adapter_planning` (warm-start, gel temporel du passe, respect des
    fenetres d'urgence, penalite de stabilite/moindre perturbation, rapport d'arbitrage).
- `optimiseur/plotting.py` — matplotlib : convergence, comparaison barres, planning obtenu,
  occupation des lits, ainsi que `plot_adaptation_dynamique`, `plot_comparaison_alternatives` et
  `plot_occupation_lits_aleas`.
- `optimiseur/run_demo.py` — CLI headless (backend `Agg`) integrant l'ensemble de la chaine
  (optimisation, verification force brute, plannings alternatifs et simulation d'aleas).
- `optimiseur/app_gui.py` — Tkinter (backend `TkAgg`), thread de calcul + `queue`.
  Comporte les onglets : Donnees, Convergence, Comparaison, Planning, Lits, Tableau,
  Plannings alternatifs (comparaison radar/barres et table Date A/B), Aleas & Adaptation
  (simulation interactive des 4 types d'aleas et restitution graphique + rapport texte).
- `optimiseur/data_bridge.py` — convertit le Parquet du notebook EDA au schema de l'optimiseur.
- `EDA_donees_bloc.ipynb` — **source de verite du pretraitement, ne pas modifier** ;
  produit `resources/donnees_bloc_pretraitees.parquet`.
- `notebooks/guide_optimisation.ipynb` — notebook pedagogique pas a pas.

Direction des imports :
- `app_gui` -> `aleas` + `plotting` + `optimizer` + `data_bridge`
- `run_demo` -> `aleas` + `plotting` + `optimizer`
- `plotting` -> `optimizer`
- `aleas` -> `optimizer`
Ne jamais importer l'inverse.

## Conventions critiques

- **Une `Solution` est un dict `patient_id -> INDICE positionnel de vacation`**
  (0..n-1), pas un `vacation_id`. `fitness`, `neighbor` et `exact_bruteforce`
  reposent sur cette convention ; `solution_to_dataframe` fait la conversion
  vers `vacation_id`.
- `fitness` renvoie `-cout` : **on maximise**, `0` = planning parfait sans aucune tension.
- Les noms de methodes sont centralises en constantes `METHODE_*` dans `optimizer.py`.
- `PlanningProblem` precalcule des tableaux numpy (`_pat_duree`, `_vac_day`,
  `_patient_options`...) : ne pas reintroduire d'acces `df.loc[pid]` dans la
  boucle chaude de `fitness`, c'est ce qui garantit les temps actuels.
- Le backend matplotlib doit etre choisi **avant** d'importer `pyplot`
  (`Agg` dans `run_demo`, `TkAgg` dans `app_gui`).

## Systeme d'aleas et aide a la decision (`optimiseur/aleas.py`)

### 1. Les quatre types d'aleas

| Type d'alea | Classe | Description & Impact operationnel |
|---|---|---|
| **Urgences** | `Urgence` | Patient imprévu arrivant au fil de l'eau. Attributs : `specialite`, `duree_operatoire`, `duree_sejour`, `jour_apparition`, `delai_max_jours` (0 = jour même), `priorite`. Doit être inséré dans une vacation compatible de sa fenêtre temporelle. |
| **Annulations** | `Annulation` | Patient programmé qui annule à partir de `jour_notification`. Libère immédiatement le créneau opératoire et les lits d'hospitalisation prévus. |
| **Indisponibilité lits** | `IndisponibiliteLits` | Réduction imprévue de capacité en lits sur $[j_{\text{debut}}, j_{\text{fin}}]$ (tensions RH, épidémie). Contraint le lissage et force la réaffectation de séjours chevauchants. |
| **Retard bloc** | `RetardBloc` | Dépassement d'intervention ou incident technique sur une vacation (`vacation_id`), réduisant la capacité utile disponible (`capacite_min - retard_min`). |

### 2. Approche 1 : Generation de plannings alternatifs (Proactive)

Fonction principale : `generer_plannings_alternatifs(problem, ...)`
- **Nominal** : planning optimisé à 100% de la capacité.
- **Robuste Bufferisé** : réserve de capacité bloc (buffer 15%) et lits pour absorber les imprévus sans décalage de patient.
- **Sécurité Lits** : priorité au lissage strict et à la sous-saturation des lits pour parer aux fermetures inopinées.
- **Alternatif Diversifié (Date B)** : solution de haute qualité maximisant la diversité d'affectation par rapport au nominal.
- Extraction des choix chirurgien : `extraire_options_date_a_b` génère la table de double proposition **Date A (optimale) / Date B (alternative)** pour chaque patient (répondant directement aux consignes du cours).

### 3. Approche 2 : Adaptation dynamique (Reactive)

Fonction principale : `adapter_planning(problem, solution_initiale, scenario, jour_courant, ...)`
- **Sanctuarisation du passé** : tout patient opéré ou programmé avant `jour_courant` est **gelé** (inviolabilité des actes passés).
- **Application immédiate des flux** : retrait des annulations et placement glouton initial des urgences.
- **Optimisation sous moindre perturbation** : recherche métaheuristique (recherche taboue ou recuit) pondérée par :
  $$\text{Score}(s) = \text{Fitness}_{\text{adaptee}}(s) - w_{\text{perturbation}} \cdot \sum \text{Déplacements} - w_{\text{changement\_jour}} \cdot \sum \text{Changements de jour}$$
- **Rapport d'arbitrage** : synthèse textuelle exhaustive et chiffrée des motifs de chaque déplacement et des urgences accueillies.

## Donnees

Schema attendu par `optimiseur/optimizer.py` :
- patients : `patient_id`, `specialite`, `duree_operatoire` (min), `duree_sejour` (jours)
- vacations : `vacation_id`, `jour`, `specialite`, `capacite_min` (min)

`optimiseur/data_bridge.py::prepare_inputs` construit ces tables depuis le Parquet EDA :
- `specialite` est un proxy derive de `ccam_1` (1re lettre), sinon `ghm_code`, sinon `interv_type`.
- `duree_operatoire` <- `room_duration_min`, `duree_sejour` <- `duree_sejour_corrigee`.
- Les identifiants personnels sont ecartes (confidentialite).

## Pieges

- Fichiers `*:Zone.Identifier` a la racine : metadonnees Windows telechargees, a ignorer.
- Sous Windows avec Python 3.14 : toujours positionner `$env:OPENBLAS_NUM_THREADS="1"` en PowerShell pour eviter les saturations de threads BLAS.
- Langue mixte : code, docstrings, README et noms de methodes en francais (sans accents dans le code), notebook EDA en anglais. Garder cette coherence.
- `resources/` est reference avec la coquille `donees` dans le notebook EDA (`donees bloc anonyme ...`) : ne pas "corriger" sans mettre a jour le notebook.
