# Interface — application KYST

KYST (*Keep Your Surgeries Timely*) propose des dates d'intervention compatibles avec le bloc et les lits, à partir des durées prédites par les modèles du projet. Ce dossier contient l'application complète.

```text
interface/
├── api/          # API FastAPI : données, droits, prédictions, ordonnancement
├── app/          # Front SvelteKit : pages vues dans le navigateur
├── ansible/      # Déploiement sur le serveur (Podman, PostgreSQL, journalisation)
├── docs/         # Documentation fonctionnelle et technique
├── kyst.env      # Référence de toutes les variables d'environnement (sans secret)
└── justfile      # Lancement en production sur une machine (just prod)
```

Le navigateur ne parle qu'au front ; seul le serveur du front appelle l'API, qui détient les données et appelle les moteurs de recherche du dépôt ([`prediction/`](../prediction/README.md), [`optimiseur/`](../optimiseur/README.md), [`hospital_sim/`](../hospital_sim/README.md)).

## Documentation

| Document | Contenu |
| :--- | :--- |
| [Fonctionnalités](docs/Features.md) | Ce que fait KYST, pour qui, état de chaque fonctionnalité |
| [Guide de contribution](CONTRIBUTING.md) | Outils, variables d'environnement, lancement en local et en production |
| [Modèle de données](docs/BDD.md) | Tables, cycle de vie d'une demande, calcul de la capacité |
| [Routes de l'API](docs/Routes.md) | Vue d'ensemble des routes et des droits |
| [Front](docs/Frontend.md) | Organisation du code SvelteKit, pages, session, mise en page |
| [Intégration de l'IA](../docs/integration-ia-kyst.md) | Modèles, cohorte, simulations Mesa, configuration |
| [Déploiement](ansible/README.md) | Playbooks et rôles Ansible |

## Démarrage rapide

Après avoir installé les outils (voir le [guide de contribution](CONTRIBUTING.md#installation-de-la-boîte-à-outils-toolchain)) :

```bash
cd api && just install && just seed && just dev   # http://127.0.0.1:8000/docs
cd app && pnpm install && pnpm dev                # http://localhost:5173
```

Se connecter avec `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` de [`kyst.env`](kyst.env).
