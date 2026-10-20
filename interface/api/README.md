# api — API FastAPI de KYST

L'API détient les données (SQLModel, SQLite en local, PostgreSQL en déploiement), vérifie les droits et appelle les moteurs de prédiction et d'ordonnancement. Elle n'est appelée que par le serveur du front.

| Dossier ou fichier | Rôle |
| :--- | :--- |
| `main.py`, `config.py` | Application, routeurs, `/health` ; lecture de [`kyst.env`](../kyst.env) |
| `accounts/` | Comptes, rôles, jetons JWT, limitation des tentatives de connexion |
| `resources/` | Spécialités, salles, vacations, unités de lits, chirurgiens |
| `clinical/` | Patients pseudonymisés, demandes d'intervention, prédictions |
| `planning/` | Propositions de dates, interventions programmées, capacité, file d'actualisation |
| `analytics/` | Indicateurs agrégés, sans ligne patient |
| `ai/` | Prédictions (`fixtures` ou modèles entraînés), optimisation de cohorte, aperçus Mesa |
| `audit.py` | Trace d'accès : une ligne JSON par appel, sans corps de requête |
| `bootstrap.py`, `seed.py` | Tables, rôles et premier administrateur ; service de démonstration synthétique |
| `tests/` | Tests `pytest` (base SQLite temporaire, prédictions `fixtures`) |

## Commandes

Depuis ce dossier :

| Recette | Rôle |
| :--- | :--- |
| `just install` | Crée `.venv` et installe les dépendances (`uv sync`) |
| `just dev` | Serveur de développement sur `http://127.0.0.1:8000` (documentation interactive sur `/docs`) |
| `just seed` | Crée le service de démonstration si la base n'a aucune ressource |
| `just test` | Lance les tests |

L'image Docker (`Dockerfile`) se construit depuis la racine du dépôt : elle embarque `prediction/`, `optimiseur/` et `hospital_sim/`, jamais de données ni de modèle.

Pour aller plus loin : [modèle de données](../docs/BDD.md), [routes](../docs/Routes.md), [intégration de l'IA](../../docs/integration-ia-kyst.md), [guide de contribution](../CONTRIBUTING.md#backend-fastapi-api).
