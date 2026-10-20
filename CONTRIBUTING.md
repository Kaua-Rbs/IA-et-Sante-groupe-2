# Contribuer au projet

Ce guide fixe les règles communes de l'équipe : branches, commits, revues et confidentialité. Pour l'environnement de développement de l'application (outils, API, front, déploiement), voir le [guide de contribution de KYST](interface/CONTRIBUTING.md).

## Branches

Le code exécutable, les analyses et les sources du rapport vivent sur `main`. On ne commite pas directement sur `main` : chaque changement passe par une branche courte et une pull request relue.

Une branche correspond à une tâche bien délimitée, nommée `<domaine>/<sujet>` :

```text
eda/timing-quality
model/length-of-stay
optim/tabu-search
report/data-analysis
fix/missing-timestamps
```

Partir d'un `main` à jour, garder la branche ciblée et la supprimer après la fusion. Si elle vit plus de quelques jours, la synchroniser régulièrement avec `main` pour détecter tôt les conflits.

## Commits

Un commit correspond à un changement logique, relisible seul. Il ne mélange pas refactorisation, analyse, documentation et mise en forme, et laisse le dépôt dans un état utilisable.

Avant de commiter :

- relire le diff indexé avec `git diff --staged` ;
- utiliser `git add -p` quand un fichier contient plusieurs changements sans rapport ;
- exclure les fichiers temporaires, les artefacts générés, les secrets et les données confidentielles ;
- lancer les vérifications concernées (voir [les tests](tests/README.md)).

Les messages suivent [Conventional Commits](https://www.conventionalcommits.org/fr/) :

```text
<type>(<portée>): <description courte à l'impératif>
```

| Type | Usage |
| :--- | :--- |
| `feat` | Nouvelle fonctionnalité, analyse, modèle ou méthode d'optimisation |
| `fix` | Correction d'un comportement ou d'un traitement de données |
| `docs` | Documentation ou rapport uniquement |
| `refactor` | Restructuration sans changement de comportement |
| `test` | Ajout ou mise à jour de tests |
| `perf` | Amélioration des performances |
| `chore` | Outillage, dépendances, configuration du dépôt |

```text
feat(eda): add operating-room duration analysis
fix(data): handle procedures crossing midnight
docs(report): describe the tabu-search formulation
```

Expliquer dans le corps du commit la motivation ou les compromis quand ils ne sont pas évidents. Signaler une rupture de compatibilité par `!` et un pied de page `BREAKING CHANGE:`.

## Pull requests et revue

Une pull request reste assez petite pour être relue confortablement. Elle contient :

- le problème et la solution retenue ;
- les données, modèles, notebooks ou sections du rapport concernés ;
- de quoi reproduire ou valider le résultat ;
- les métriques, figures ou captures quand le comportement change ;
- les hypothèses, limites, implications pour la confidentialité et suites éventuelles.

Au moins un membre de l'équipe approuve avant la fusion. La revue vérifie la justesse, la reproductibilité, la lisibilité, la confidentialité et la cohérence avec les objectifs du projet. On résout les discussions plutôt que de les ignorer, et on préfère la fusion par squash quand la branche contient des commits de correction sans intérêt pour l'historique.

## Notebooks, données et rapport

- Garder les notebooks exécutables de haut en bas et documenter leurs entrées.
- Retirer les cellules de débogage et les sorties inutiles avant de commiter.
- N'afficher ni ne commiter aucune ligne de patient, de séjour, de praticien ou de chirurgien.
- Déplacer dans un module Python la logique réutilisable dès qu'elle devient trop lourde pour un notebook.
- Ne pas commiter `resources/`, `artifacts/`, les environnements locaux, les caches, les PDF générés ni les fichiers auxiliaires LaTeX.
- Donner des noms explicites aux figures générées et noter le code et les paramètres qui les produisent.
- Le rapport est découpé en un fichier par chapitre (voir [report/README.md](report/README.md)) pour limiter les conflits.
