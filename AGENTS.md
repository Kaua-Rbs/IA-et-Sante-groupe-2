# AGENTS.md

Optimiseur de planning de bloc operatoire : cinq methodes d'origine
(recuit simule, tabou, genetique, hybride tabou x recuit, colonie de fourmis)
plus **trois hybrides** (genetique x tabou, genetique x recuit, fourmis x
tabou) et **deux SMA Mesa** (agents simples, agents metaheuristiques),
auxquels s'ajoute un **systeme complet de gestion des aleas** (urgences,
annulations, indisponibilite de lits, retards bloc) combinant **generation
proactive de plannings alternatifs** (Date A / Date B, robustesse) et
**adaptation dynamique reactive** (replanning sous contrainte de stabilite).
Entree = deux DataFrames pandas, sortie = planning patient -> vacation +
historiques de convergence + plannings de repli et adaptations. S'ajoutent un
harnais de benchmark multi-graines, un rapport comparatif et un pont de
re-planification dynamique vers `hospital_sim/`.

## Setup

Le Python systeme est 3.14 et `ensurepip` / `python3-venv` sont absents : un
`.venv` classique echoue. Il a ete cree via `virtualenv` (deja installe en
`--user`). Pour reinstaller :

```bash
python3 -m virtualenv .venv          # PAS python3 -m venv
.venv/bin/pip install -r requirements.txt
```

Toujours utiliser `.venv/bin/python`. Versions verrouillees de fait :
pandas 3.0, numpy 2.5, matplotlib 3.11, pyarrow 25, mesa 3.5, scipy 1.18,
networkx 3.7 (wheels 3.14 OK). `networkx` est requis a l'import par mesa 3.5
mais non declare par mesa : il est donc liste explicitement dans
`requirements.txt`.

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

# Demo des 10 methodes avec budget temps par methode
.venv/bin/python -m optimiseur.run_demo --toutes --budget 1 --out resultats

# Benchmark multi-graines (petite + grande echelle), CSV + figures + meta JSON
.venv/bin/python -m optimiseur.run_benchmark --graines 20 --out resultats/benchmark --figures rapport/figures

# Variante donnees reelles (Parquet EDA) a la place de la grande synthetique
.venv/bin/python -m optimiseur.run_benchmark --donnees-reelles --graines 20 --budget-grande 4 \
    --horizon 40 --capacite-min 600 --out resultats/benchmark_reel --figures rapport/figures

# Re-planification dynamique via hospital_sim (indisponibilite + urgence)
.venv/bin/python -m optimiseur.run_coordination_demo

# Interface graphique (necessite tkinter) avec onglets Convergence, Comparaison,
# Planning, Lits, Tableau, Plannings alternatifs (Date A/B) et Aleas & Adaptation.
.venv/bin/python -m optimiseur.app_gui

# Suite de tests (stdlib unittest, ~20 s, sans affichage)
.venv/bin/python -m unittest discover -t . -s tests -v

# Executer les notebooks guides et rapports
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/guide_optimisation.ipynb
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/rapport_aleas_et_adaptation.ipynb
```

Tout se lance **depuis la racine du depot** (les packages `optimiseur/` et
`hospital_sim/` doivent etre importables).

La verification de reference combine la suite `tests/` (140 tests couvrant le modele,
les 10 methodes, le pont de donnees EDA, les visualisations, les 4 types d'aleas,
les plannings alternatifs, l'adaptation dynamique et les notebooks ; les 10
methodes doivent atteindre l'optimum exact sur la petite instance), `run_demo`
et `run_coordination_demo`. Le plan detaille est dans `TEST_PLAN.md`. Les tests
dependant du Parquet EDA reel, de tkinter ou de mesa se sautent d'eux-memes si la
ressource est absente. Le depot git a un remote GitHub (`origin`), avec des
branches par sujet ; il n'y a ni linter ni CI.

## Architecture

```text
optimiseur/               # package : tout le code
optimiseur/               # package : tout le code
  optimizer.py            # coeur : modele PlanningProblem + 8 metaheuristiques + hooks + budget
  aleas.py                # systeme d'aleas + plannings alternatifs + adaptation dynamique
  multiagent.py           # SMA Mesa (tableau noir + coordinateur)
  coordination_bridge.py  # pont async vers hospital_sim
  benchmark.py            # campagnes multi-graines + agregats
  plotting.py             # graphiques matplotlib (dont aleas et multi-graines)
  data_bridge.py          # Parquet EDA -> schema optimiseur
  run_demo.py             # CLI headless (demo complete + aleas)
  run_benchmark.py        # CLI benchmark (CSV + figures + meta JSON)
  run_coordination_demo.py# CLI re-planification dynamique
  app_gui.py              # interface Tkinter avec onglets dedies
hospital_sim/             # squelette de coordination async (stdlib)
  contracts.py coordinator.py demo.py
EDA_donees_bloc.ipynb     # source de verite du pretraitement (racine)
notebooks/
  guide_optimisation.ipynb             # guide pas a pas des metaheuristiques
  rapport_aleas_et_adaptation.ipynb    # rapport operationnel et guide aleas & adaptation
tests/                    # suite unittest (test_optimizer, test_aleas, test_plotting, ...)
TEST_PLAN.md              # plan de tests detaille
rapport/                  # rapport comparatif + figures (versionne)
resources/                # gitignore : classeur reel + Parquet EDA
resultats/                # gitignore : sorties generees (CSV/PNG)
```

- `optimiseur/optimizer.py` — coeur : `generate_test_data`, `PlanningProblem`
  (fitness + voisinage + violations), les 8 metaheuristiques, les hooks de
  reprise (`solution_initiale`, `population_initiale`, `pheromones_initiaux`,
  `etat`), `time_budget_s`, `optimize_planning(methodes=...)`,
  `exact_bruteforce`. Accepte une capacite de lits scalaire ou vectorielle
  journaliere (`_lits_capacity_arr`) ainsi que des retards par vacation
  (`vacation_delays`). Seules dependances calcul : pandas/numpy.
- `optimiseur/aleas.py` — module d'aleas :
  - Classes d'aleas : `Urgence`, `Annulation`, `IndisponibiliteLits`, `RetardBloc`, `ScenarioAleas`.
  - Simulateur d'aleas reproductible : `generer_scenario_aleas`.
  - Generation de plannings alternatifs : `generer_plannings_alternatifs` (profils Nominal,
    Robuste_Buffer, Securite_Lits, Alternatif_Date_B) et `extraire_options_date_a_b`.
  - Adaptation dynamique : `adapter_planning` (warm-start, gel temporel du passe, respect des
    fenetres d'urgence, penalite de stabilite/moindre perturbation, rapport d'arbitrage).
- `optimiseur/multiagent.py` — Mesa : `TableauNoir`, `Coordinateur`,
  `AgentChercheur` + agents simples/metaheuristiques, `systeme_multiagent` et
  `systeme_multiagent_hybride`. Import paresseux depuis `optimize_planning`
  (mesa n'est requis que pour les methodes SMA). RNG propre par agent
  (`random.Random`) pour le determinisme ; Mesa ne sert qu'au modele/registre.
- `optimiseur/coordination_bridge.py` — implemente les protocoles de
  `hospital_sim.contracts` (`EtatBlocAdapter`, `PlanificateurOptimiseur`,
  `ValidateurBloc`) ; `asyncio.to_thread` pour l'optimisation CPU.
- `optimiseur/benchmark.py` + `run_benchmark.py` — campagne a budget temps egal
  (`PLAFONDS_ITERATIONS` eleves pour que le budget soit le seul frein),
  tableau par graine, resume (medianes, ecarts, rangs, taux de reference).
- `optimiseur/plotting.py` — matplotlib ; importe les constantes `METHODE_*`
  depuis `.optimizer`. `COULEURS` (5 historiques) reste intact,
  `COULEURS_ETENDUES` couvre les 10 methodes ; inclut `plot_adaptation_dynamique`,
  `plot_comparaison_alternatives` et `plot_occupation_lits_aleas`.
- `optimiseur/run_demo.py` — CLI headless (backend `Agg`) ; defaut = 5
  methodes, `--toutes` = 10, `--budget` = budget par methode ; integre
  plannings alternatifs, simulation d'aleas et adaptation dynamique.
- `optimiseur/app_gui.py` — Tkinter (backend `TkAgg`), thread de calcul +
  `queue` pour rester reactif ; lance les 10 methodes. Comporte les onglets :
  Donnees, Convergence, Comparaison, Planning, Lits, Tableau, Plannings
  alternatifs (comparaison radar/barres et table Date A/B), Aleas & Adaptation
  (simulation interactive des 4 types d'aleas et restitution graphique +
  rapport texte). Bouton "Charger donnees reelles (EDA)" : lit le Parquet via
  `data_bridge.prepare_inputs` (le `.xlsx` n'est jamais lu directement, c'est
  le notebook EDA qui le transforme).
- `optimiseur/data_bridge.py` — convertit le Parquet du notebook EDA au schema
  de l'optimiseur.
- `hospital_sim/` — coordination asynchrone pure stdlib (issue de `main`) :
  snapshots versionnes, validation et acceptation explicites. Le pont vit cote
  `optimiseur/`, jamais l'inverse.
- `EDA_donees_bloc.ipynb` — **source de verite du pretraitement, ne pas
  modifier** ; produit `resources/donnees_bloc_pretraitees.parquet`.
- `notebooks/guide_optimisation.ipynb` — notebook pedagogique pas a pas (des
  donnees EDA aux 5 methodes historiques) ; executable meme sans le Parquet
  reel (repli synthetique). Il ajoute la racine du depot a `sys.path`, donc
  fonctionne lance depuis la racine ou depuis `notebooks/`.
- `notebooks/rapport_aleas_et_adaptation.ipynb` — rapport operationnel et guide
  aleas & adaptation.
- `rapport/RAPPORT.md` — rapport comparatif (protocole, resultats reels,
  discussion) alimente par `run_benchmark` ; figures versionnees.

Direction des imports : `app_gui`/`run_demo`/`run_benchmark`/
`run_coordination_demo` -> `plotting` + `optimizer` (+ `aleas` pour
`app_gui`/`run_demo`, + `benchmark` / `coordination_bridge`) ; `multiagent`,
`aleas` et `plotting` -> `optimizer` (imports relatifs `from . import ...`) ;
`coordination_bridge` -> `optimizer` + `hospital_sim`. Ne jamais importer
l'inverse.

## Conventions critiques

- **Une `Solution` est un dict `patient_id -> INDICE positionnel de vacation`**
  (0..n-1), pas un `vacation_id`. `fitness`, `neighbor` et `exact_bruteforce`
  reposent sur cette convention ; `solution_to_dataframe` fait la conversion
  vers `vacation_id`.
- `fitness` renvoie `-cout` : **on maximise**, `0` = planning parfait.
- Les noms de methodes sont centralises en constantes `METHODE_*` dans
  `optimizer.py`. Ajouter une methode oblige a mettre a jour : `optimize_planning`,
  `KWARGS_PAR_METHODE`, `TOUTES_METHODES`, `benchmark.PLAFONDS_ITERATIONS`,
  `plotting.COULEURS_ETENDUES`, `app_gui.METHODES` et le tableau du
  `optimiseur/README.md`.
- `optimize_planning(..., methodes=None)` reste **retrocompatible** : defaut =
  5 methodes historiques ; `methodes="toutes"` = 10 ; le SMA est importe
  paresseusement (mesa n'est charge que si demande).
- `PlanningProblem` precalcule des tableaux numpy (`_pat_duree`, `_vac_day`,
  `_patient_options`...) : ne pas reintroduire d'acces `df.loc[pid]` dans la
  boucle chaude de `fitness`, c'est ce qui garantit les temps actuels.
- Le backend matplotlib doit etre choisi **avant** d'importer `pyplot`
  (`Agg` dans `run_demo`/`run_benchmark`, `TkAgg` dans `app_gui`).

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
- Mesa 3.5 importe `networkx` sans le declarer : si `import mesa` echoue,
  verifier que `networkx` est installe.
- `Agent` Mesa possede une propriete `rng` en lecture seule : les agents du
  SMA stockent leur generateur dans `self.alea` (ne pas renommer en `rng`).
