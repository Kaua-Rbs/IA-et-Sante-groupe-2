# Slide « Avancement » — note d'accompagnement

Fichier source : `rapport/slide_avancement.tex` (une seule frame Beamer,
format 16:9). Cette note explique chaque élément de la slide et d'où viennent
les chiffres.

## Rôle de la slide

Montrer en une vue ce qui tourne déjà : dix méthodes implémentées et
comparées, un benchmark multi-graines, des tests, et un pont vers la
re-planification dynamique. Deux figures servent de preuve visuelle.

## Structure

Une frame, deux colonnes `0.47` / `0.5` de la largeur. À gauche le texte,
à droite deux figures empilées. Titre :
« Avancement : optimisation du planning de bloc operatoire ».

## Colonne gauche — bloc « Realise »

- **10 methodes : 5 d'origine, 3 hybrides, 2 SMA Mesa.** Les dix méthodes sont
  définies comme constantes `METHODE_*` dans `optimiseur/optimizer.py` et
  recensées dans `README.md` : recuit simulé, tabou, génétique, tabou×recuit,
  fourmis ; génétique×tabou, génétique×recuit, fourmis×tabou ; SMA simple et
  SMA×métaheuristiques (`optimiseur/multiagent.py`).
- **Affectation patients → vacations, cout a 3 termes, budget temps.** Le
  modèle `PlanningProblem` affecte chaque patient à une vacation compatible
  avec sa spécialité. Le coût additionne trois termes pondérés
  (`w_vacation` = 5, `w_lits` = 3, `w_balance` = 0,05), détaillés dans
  `rapport/RAPPORT.md` section 1. Le budget temps (`time_budget_s`) est le
  seul frein du benchmark.
- **Benchmark 20 graines sur 3 echelles : 7, 300, 582 patients.** Les trois
  échelles de `run_benchmark` : petite instance 7 patients / 4 vacations,
  grande synthétique 300 patients / 80 vacations, réelle 582 patients /
  280 vacations. 20 graines (0 à 19), mêmes graines pour toutes les méthodes.
- **130 tests ; les 10 methodes atteignent l'optimum exact en petite
  instance.** `python -m unittest discover -t . -s tests` (détail dans
  `TEST_PLAN.md`). Sur la petite instance, l'optimum est calculé par force
  brute (`4^7 = 16 384` combinaisons) et les dix méthodes l'atteignent sur
  les 20 graines (`RAPPORT.md` section 4).
- **Re-planification dynamique (`hospital_sim`), GUI Tkinter, CLI.** Le pont
  `optimiseur/coordination_bridge.py` branche l'optimiseur sur le coordinateur
  asynchrone de `hospital_sim/` (indisponibilité, urgence). L'interface est
  `optimiseur/app_gui.py` ; les entrées headless sont `run_demo.py`,
  `run_benchmark.py` et `run_coordination_demo.py`.

## Encadré « Resultats »

Deux constats tirés de `RAPPORT.md` :

- **Recuit simulé et tabou×recuit dominent** à budget égal sur la grande
  instance : écarts moyens 0,015 et 0,018 sur une référence de `-38847.195`,
  soit moins de 0,0001 % du coût. Le « < 0,02 » de la slide vient de là.
- **ACO et génétique décrochent sur les données réelles** : écarts moyens
  d'environ 3 369 et 2 973 sur l'instance réelle (582 patients), contre 10 à
  19 pour les méthodes locales. L'instance réelle a un couloir faisable
  étroit, où les méthodes à acceptation de dégradations passent et les
  constructions non.

## Colonne droite — les deux figures

Les images sont dans `rapport/figures/` et référencées par
`\graphicspath{{figures/}}`. Elles sont produites par `run_benchmark
--figures rapport/figures` via `optimiseur/plotting.py`.

### `petite_taux_optimum.png` (haut)

Généré par `plot_taux_succes` (`plotting.py:251`). Barres du pourcentage de
graines ayant atteint l'optimum exact, une barre par méthode, en petite
instance. Les dix barres sont à 100 % : c'est le test de correction, il ne
départage pas les méthodes mais prouve qu'aucune ne se trompe d'optimum.

Légende ajoutée : « Petite echelle : 10/10 methodes a l'optimum exact
(20 graines). »

### `grande_convergence.png` (bas)

Généré par `plot_convergence_mediane` (`plotting.py:211`). Courbe médiane de
la meilleure fitness en fonction du temps, avec bande interquartile sur les
20 graines, en grande instance (300 patients, 3 s de budget). Elle montre la
vitesse de convergence : qui atteint vite son plateau et qui reste loin de la
référence.

Légende ajoutée : « Grande echelle : convergence a budget egal (300 patients,
3 s). »

### Pourquoi ces deux-là

La première prouve la correction (optimum exact), la seconde la performance à
budget réel. Mettre les deux évite de ne montrer qu'un axe.

## Compiler

Depuis `rapport/` :

```bash
pdflatex slide_avancement.tex
```

Paquets utilisés : `beamer`, `graphicx`, `booktabs`, `babel` (français),
`amsmath`. Le thème est celui de Beamer par défaut, donc pas de dépendance
externe. LaTeX n'est pas installé sur cette machine : la compilation reste à
faire côté poste avec TeX Live.

## Réutiliser dans la soutenance existante

La soutenance complète vit sur la branche `report/presentation`, dossier
`soutenance/`, avec le thème `beamerthememidcenturymodern` (LuaLaTeX requis).
Pour y insérer cette slide, copier le contenu de la frame dans un fichier
`soutenance/sections/9-avancement.tex`, retirer le préambule local
(le document maître le fournit), et inclure le fichier depuis
`Soutenance_intermediaire.tex` avec `\include{sections/9-avancement}`.

## Points à vérifier d'ici la soutenance

- Les chiffres de l'encadré viennent du benchmark local ; refaire tourner
  `run_benchmark` si les poids ou la capacité changent.
- Le « 5 d'origine / 3 hybrides / 2 SMA » doit rester synchronisé avec
  `TOUTES_METHODES` dans `optimizer.py`.
- La projection 16:9 doit correspondre au reste du support (le thème force
  `aspectratio=169`).

---

# Théorie derrière les méthodes

## Le problème

On affecte `P` patients à `V` vacations. Chaque patient ne peut aller que
dans les vacations de sa spécialité. Une solution est donc un vecteur de `P`
décisions, chacune dans un sous-ensemble de vacations. Le nombre de
combinaisons est `∏_i |options_i|` : sur la petite instance, 7 patients ×
4 vacations donnent `4^7 = 16 384` planings. Passer à 300 patients × 80
vacations fait exploser ce produit. C'est un problème d'affectation sous
contraintes, NP-difficile : aucune méthode exacte ne tient en temps utile à
l'échelle d'un hôpital. On cherche donc une bonne solution en un temps
borné, pas l'optimum garanti.

## La fonction objectif

Le coût pénalise trois tensions (`RAPPORT.md` section 1) :

```
coût = w_vacation · Σ max(0, charge_vacation − capacité_vacation)
     + w_lits     · Σ max(0, occupation_lits_jour − capacité_lits)
     + w_balance  · écart-type(charge des vacations)
```

Les deux premiers termes sont des **contraintes dures relâchées** : nuls si
la capacité n'est jamais dépassée. Le troisième est un objectif souple de
lissage, il ne s'annule jamais parfaitement. La fitness vaut `-coût`, donc
0 serait un planning à la fois faisable et parfaitement équilibré. Les
métaheuristiques ne lisent que cette valeur scalaire : elles ignorent la
structure interne du coût.

## Recuit simulé

Analogie avec le recuit métallurgique. On part d'une solution et on la
perturbe ; une perturbation qui améliore est acceptée, une qui dégrade est
acceptée avec la probabilité `exp(Δ/T)` (règle de Metropolis), où `Δ` est la
variation de fitness et `T` la température. La température décroît
géométriquement (`T ← α·T`, α proche de 1). Au début, `T` élevée autorise
des dégradations et l'exploration est large ; `T` basse fige la solution.

Théoriquement, un refroidissement logarithmique garantit la convergence vers
l'optimum global en probabilité, mais il est impraticable. Le refroidissement
géométrique du code (`α = 0,95`) est l'heuristique standard : rapide, sans
garantie. C'est l'acceptation de dégradations qui permet de traverser le
plateau et de ne pas se coincer dans un optimum local, d'où sa domination
sur les instances rugueuses.

## Recherche Tabou

À chaque itération, on évalue un échantillon de voisins et on se déplace vers
le meilleur, même s'il est moins bon que l'état courant. Le piège est le
cyclage : revenir sans cesse sur la même solution. On mémorise donc les
derniers mouvements dans une **liste taboue** (un `deque` de taille fixe dans
`optimizer.py:375`) et on les interdit pendant un temps. Le **critère
d'aspiration** lève l'interdiction si un mouvement tabou mène à un nouveau
meilleur global, pour ne pas rater une amélioration.

`neighbor` propose deux familles de mouvements (`optimizer.py:192`) :
réaffecter un patient, ou échanger deux patients de même spécialité. La
liste mémorise ces mouvements, pas les solutions. Le tabou alterne
intensification (exploiter un bon voisinage) et diversification (interdire
pour sortir d'un bassin).

## Algorithme génétique

Une population de solutions évolue par générations :

- **Sélection** proportionnelle à la fitness, après décalage pour la rendre
  positive (roulette). Les meilleurs se reproduisent plus souvent.
- **Croisement** à un point de coupe : l'enfant prend les gènes du parent 1
  avant la coupe, du parent 2 après. Ici un « gène » est l'affectation d'un
  patient.
- **Mutation** : chaque gène change de vacation avec probabilité `p_mut`,
  ce qui maintient la diversité et empêche la convergence prématurée.
- **Élitisme** : le meilleur individu est recopié tel quel dans la
  génération suivante, pour ne pas perdre le meilleur trouvé.

Le théorème des schémas explique pourquoi ça marche : les briques de
solutions performantes se propagent de génération en génération. Sur un
paysage plat, la pression de sélection reste faible, d'où la lenteur
observée du génétique seul.

## Colonie de fourmis (ACO)

Modèle de **stigmergie** : les fourmis communiquent indirectement en
déposant des phéromones. Chaque fourmi construit une solution complète en
choisissant, patient par patient, une vacation avec une probabilité

```
p(patient → vacation) ∝ tau^α · eta^β
```

où `tau` est le niveau de phéromone de l'arête (patient, vacation) et `eta`
un heuristique glouton qui pénalise les vacations déjà chargées
(`optimizer.py:560`). Après chaque itération, les phéromones s'évaporent
(`tau ← (1−ρ)·tau`) et la meilleure fourmi renforce ses arêtes d'une
quantité proportionnelle à sa qualité. Évaporation = oubli, dépôt =
renforcement : les bonnes arêtes deviennent plus probables, mais
l'évaporation empêche la stagnation. Sur les grosses instances, chaque
construction est coûteuse, ce qui explique le décrochage à budget égal.

## Hybride d'origine : Tabou × Recuit

Combine les deux logiques (`optimizer.py:408`). On construit un voisinage, on
écarte les mouvements tabous sauf aspiration, puis on applique la règle de
Metropolis au candidat retenu : il est accepté s'il améliore, sinon avec la
probabilité `exp(Δ/T)`. Le tabou apporte le guidage vers de bons voisins, le
recuit la capacité à accepter des dégradations contrôlées. C'est l'hybride le
plus compétitif du projet.

## Hybrides construits : mémétiques et ACO×Tabou

Trois hybrides ajoutent une recherche locale à une méthode globale
(`optimizer.py:645-888`) :

- **Génétique × Tabou** et **Génétique × Recuit** sont des algorithmes
  **mémétiques** : après chaque génération, une courte recherche locale
  (tabou ou recuit) intensifie le meilleur individu. La stratégie est
  **lamarckienne** : le résultat amélioré remplace l'individu dans la
  population (`optimizer.py:710`). L'intensification corrige la faible
  pression de sélection du génétique.
- **Fourmis × Tabou** : à chaque itération ACO, la meilleure fourmi est
  affinée par une courte recherche tabou, et le dépôt de phéromones se fait
  depuis la solution améliorée (`optimizer.py:867`). Le tabou compense la
  myopie de la construction fourmi.

## SMA : tableau noir et coordination

Les SMA ne sont pas une métaheuristique de plus, mais une **architecture de
coopération** (`optimiseur/multiagent.py`). Les briques :

- **Tableau noir** : mémoire partagée qui ne retient que le meilleur planning
  publié, avec un numéro de version (`TableauNoir`, `multiagent.py:54`).
  Chaque agent y publie et peut y lire.
- **Agents** : chacun encapsule une stratégie (glouton, descente, aléatoire,
  ou recuit / tabou / génétique / fourmis / hybride) et travaille par
  **quanta** : peu d'itérations, puis il rend la main.
- **Coordinateur** : toutes les 5 étapes, il migre le meilleur commun vers
  les agents sous la moyenne. Si la version du tableau noir n'a pas bougé
  pendant 15 étapes, il **redémarre**   la moitié la plus faible des agents
  (`multiagent.py:84`). Migration = exploitation collective, redémarrage =
  diversification.

Le SMA simple combine des heuristiques simples ; le SMA hybride donne à
chaque agent une vraie métaheuristique. Le coût d'un pas de coordination
explique leurs résultats corrects mais non dominants à budget court.

## Vérification : l'optimum par force brute

La petite instance (7 patients, 4 vacations) est énumérable : `exact_bruteforce`
teste les `4^7 = 16 384` planings (`optimizer.py:1000`). C'est la seule
échelle où l'optimum est connu avec certitude. Les dix méthodes l'atteignent
(100 % des graines), ce qui valide leur correction : elles ne se contentent
pas d'un bon voisin, elles trouvent le vrai optimum quand l'espace est
petit. Aux échelles supérieures, aucune référence exacte n'existe ; on
compare les méthodes à la meilleure solution observée.
