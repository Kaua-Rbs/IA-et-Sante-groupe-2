# Documentation

Point d'entrée de la documentation du projet. Pour la présentation générale et le démarrage, voir le [README principal](../README.md).

## Comprendre le problème et les données

| Document | Contenu |
| :--- | :--- |
| [Parcours type d'un patient](patient-workflow.md) | Diagramme du parcours chirurgical, de la consultation à la sortie, et ce que les données en observent |
| [Dictionnaire des données](data-dictionary.md) | Les 30 colonnes du classeur de l'hôpital, leurs relations et leurs incertitudes |
| [Guide d'entretien médical](doctor-discussion-guide.md) | Questions préparées pour valider les hypothèses métier (urgences, responsabilités, durées) |
| [Glossaire](glossaire.md) | Termes hospitaliers, médicaux, techniques et réglementaires employés dans le projet |

## L'IA du projet

| Document | Contenu |
| :--- | :--- |
| [Modèles de prédiction](models.md) | Temps de salle et durée de séjour : variables, découpage, résultats, limites |
| [Intégration de l'IA dans KYST](kyst-integration.md) | Comment modèles, métaheuristiques et simulation sont branchés dans l'application ; configuration |
| [Socle de coordination](coordination-core.md) | Le coordinateur asynchrone de la simulation : interfaces, cycle de vie, échecs |
| [optimiseur/](../optimiseur/README.md) | Les dix métaheuristiques d'affectation aux vacations |
| [hospital_sim/](../hospital_sim/README.md) | La simulation Mesa des salles |

## L'application KYST

| Document | Contenu |
| :--- | :--- |
| [Fonctionnalités](../interface/docs/Features.md) | Ce que fait KYST, pour qui, et l'état de chaque fonctionnalité |
| [interface/](../interface/README.md) | Organisation de l'application et liens vers sa documentation technique (données, routes, front, déploiement) |

## Reproduire et vérifier

| Document | Contenu |
| :--- | :--- |
| [notebooks/](../notebooks/README.md) | Analyse exploratoire et préparation des jeux d'entraînement |
| [experiments/](../experiments/README.md) | Entraînement des modèles déployés |
| [tests/](../tests/README.md) | Les trois suites de tests et ce qu'elles couvrent |
| [Contribuer](../CONTRIBUTING.md) | Branches, commits, revues, règles de confidentialité |

## Rendu

| Document | Contenu |
| :--- | :--- |
| [report/](../report/README.md) | Rapport LaTeX et sa compilation |
| [soutenance/](../soutenance/README.md) | Présentation Beamer |
