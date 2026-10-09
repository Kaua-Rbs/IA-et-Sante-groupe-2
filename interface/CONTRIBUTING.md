# Guide de contribution

Bienvenue sur le projet ! Ce document présente les prérequis, la configuration de l'environnement de développement et les flux de travail recommandés pour contribuer efficacement.

Le projet s'appuie sur une suite d'outils modernes pour garantir des environnements reproductibles, rapides et simples à prendre en main :
- **[`mise`](https://mise.jdx.dev/)** : gestionnaire universel de versions d'outils (Node.js, Python, pnpm, etc.) et de variables d'environnement.
- **[`just`](https://just.systems/)** : lanceur de tâches (*command runner*) moderne et lisible.
- **[`uv`](https://docs.astral.sh/uv/)** : gestionnaire de paquets et d'environnements virtuels Python ultra-rapide (écrit en Rust).
- **[`pnpm`](https://pnpm.io/)** : gestionnaire de paquets JavaScript performant et économe en espace disque.

---

## Sommaire

1. [Architecture du projet](#architecture-du-projet)
2. [Installation de la boîte à outils](#installation-de-la-boîte-à-outils-toolchain)
3. [Variables d'environnement (`kyst.env`)](#variables-denvironnement-kystenv)
4. [Backend FastAPI (`api/`)](#backend-fastapi-api)
5. [Frontend Svelte (`app/`)](#frontend-svelte-app)
6. [Mise en production (`just prod`)](#mise-en-production-just-prod)
7. [Infrastructure & Déploiement (`ansible/`)](#infrastructure--déploiement-ansible)
8. [Extensions et IDE recommandés](#extensions-et-ide-recommandés)
9. [Workflow Git & Bonnes pratiques](#workflow-git--bonnes-pratiques)

---

## Architecture du projet

L'interface KYST (*Keep Your Surgeries Timely*) est structurée de la manière suivante :

```text
interface/
├── kyst.env          # Référence de toutes les variables d'environnement (versionnée, sans secret)
├── kyst.local.env    # Vos valeurs locales et secrets (non versionné, facultatif)
├── justfile          # Mise en production (API + front) et outils communs
├── api/              # Backend FastAPI : package Python `api` (dépendances via uv, recettes just)
├── app/              # Frontend SvelteKit (version Node via mise, dépendances via pnpm)
├── ansible/          # Recettes d'automatisation et playbooks (gérés avec just et uv)
└── docs/             # Modèle de données, routes, front, fonctionnalités
```

---

## Installation de la boîte à outils (Toolchain)

Pour développer sur ce projet de manière fluide, installez les outils de base suivants sur votre machine (Linux / macOS / WSL).

### 1. `mise` (Gestionnaire d'environnements et de versions)

`mise` s'assure que tout le monde utilise les mêmes versions d'outils sans conflit avec les versions globales de votre système.

Installez `mise` :
```bash
curl https://mise.run | sh
```

Activez `mise` dans votre shell (ajoutez la ligne suivante à votre fichier de configuration `~/.bashrc`, `~/.zshrc` ou équivalent) :
```bash
# Pour Bash
eval "$(mise activate bash)"

# Pour Zsh
eval "$(mise activate zsh)"
```

### 2. `just`, `uv` et `pnpm`

Vous pouvez installer ces outils globalement via `mise` ou via votre gestionnaire de paquets système :

**Via `mise` (recommandé) :**
```bash
mise use -g just uv pnpm
```

**Ou via vos gestionnaires système :**
- **Debian / Ubuntu :**
  ```bash
  sudo apt install just
  curl -LsSf https://astral.sh/uv/install.sh | sh
  corepack enable && corepack prepare pnpm@latest --activate
  ```
- **Fedora :**
  ```bash
  sudo dnf install just
  curl -LsSf https://astral.sh/uv/install.sh | sh
  corepack enable && corepack prepare pnpm@latest --activate
  ```

### 3. Diagnostic et vérification de l'environnement (`mise doctor`)

Pour vérifier que `mise` est correctement configuré dans votre terminal, que les variables d'environnement (shims, `PATH`) sont bien injectées et qu'aucun conflit n'est détecté, exécutez la commande de diagnostic :
```bash
mise doctor
```
Elle fournit un bilan de santé complet de votre installation et signale les éventuels avertissements ou variables manquantes.

Vérifiez ensuite que les outils sont directement accessibles :
```bash
mise --version
just --version
uv --version
pnpm --version
```

---

## Variables d'environnement (`kyst.env`)

Toutes les variables (API, front, déploiement) sont décrites dans **`interface/kyst.env`**, avec leur rôle et une valeur de développement. C'est la seule référence : une nouvelle variable s'ajoute d'abord à ce fichier.

L'API (`api/config.py`) et le front (`app/vite.config.ts`, `pnpm start`) lisent, du plus prioritaire au moins prioritaire :

1. les variables d'environnement du processus ;
2. `interface/kyst.local.env`, non versionné, pour vos secrets et réglages personnels ;
3. `interface/kyst.env`, versionné.

`kyst.env` étant versionné, il ne contient **aucun secret réel**. Les valeurs `change-me` suffisent en local, mais l'API signale au démarrage une `SECRET_KEY` laissée à sa valeur par défaut. Pour vos propres valeurs, créez `kyst.local.env` avec uniquement les clés à remplacer :

```bash
# interface/kyst.local.env
SECRET_KEY=<sortie de : openssl rand -hex 32>
FIRST_ADMIN_PASSWORD=<votre mot de passe>
```

---

## Backend FastAPI (`api/`)

Le backend repose sur [FastAPI](https://fastapi.tiangolo.com/) et est géré avec **`uv`**. Le dossier `api/` est lui-même le package Python `api` : ses modules s'importent en `api.<module>` depuis `interface/`. Les recettes `just` du dossier encapsulent les commandes.

### 1. Initialiser l'environnement

```bash
cd api
just install        # ou : uv sync
```
`uv` crée l'environnement virtuel `.venv` et installe les dépendances définies dans `pyproject.toml` et verrouillées dans `uv.lock`.

### 2. Lancer le serveur de développement

```bash
just dev            # ou : uv run fastapi dev main.py
```

L'API est alors accessible sur :
- **Serveur local :** `http://127.0.0.1:8000`
- **Documentation interactive Swagger UI :** `http://127.0.0.1:8000/docs`
- **Documentation alternative ReDoc :** `http://127.0.0.1:8000/redoc`

Au démarrage, l'API crée les tables, les rôles et le premier administrateur (`FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` de `kyst.env`). Pour obtenir des ressources de démonstration synthétiques (spécialités, salles, lits, vacations sur 4 semaines) :
```bash
just seed           # ou : PYTHONPATH=.. uv run python -m api.seed
```

Lancer les tests :
```bash
just test           # ou : uv run pytest
```

### 3. Organisation du code

```text
api/
├── main.py           # Application FastAPI, routeurs, /health
├── config.py         # Lecture de kyst.env / kyst.local.env
├── db.py, crud.py    # Session SQLModel et aides CRUD
├── bootstrap.py      # Tables, rôles, premier administrateur
├── seed.py           # Données de démonstration
├── accounts/         # Comptes, rôles, jetons JWT
├── resources/        # Spécialités, salles, vacations, unités de lits, chirurgiens
├── clinical/         # Patients pseudonymisés, demandes d'intervention, prédictions
├── planning/         # Propositions de dates, interventions programmées, capacité
├── analytics/        # Indicateurs agrégés
├── ai/               # Protocoles des modèles et du solveur ; fixtures en attendant
└── tests/
```

Les prédictions et l'ordonnancement passent par les protocoles de `ai/contracts.py`, implémentés pour l'instant par des fixtures (`AI_BACKEND=fixtures`). Le modèle de données est décrit dans [docs/BDD.md](docs/BDD.md), les routes dans [docs/Routes.md](docs/Routes.md), et le travail restant dans [docs/todo.md](../docs/todo.md).

### 4. Gérer les dépendances Python

Avec `uv`, l'ajout et la mise à jour de dépendances sont immédiats :
```bash
# Ajouter une dépendance
uv add <nom-du-paquet>

# Ajouter une dépendance de développement
uv add --dev <nom-du-paquet>

# Mettre à jour les dépendances
uv lock --upgrade
```

---

## Frontend Svelte (`app/`)

Le frontend est une application Svelte située dans le dossier `app/`. La version de Node.js est déclarée dans `app/mise.toml` et les dépendances sont gérées avec **`pnpm`**.

### 1. Installer Node.js et les dépendances

Placez-vous dans le répertoire `app/` :
```bash
cd app
```

Activez et installez la version de Node.js requise via `mise` :
```bash
mise install
```

Installez les dépendances du projet avec `pnpm` :
```bash
pnpm install
```

### 2. Commandes de développement

- **Démarrer le serveur de développement :**
  ```bash
  pnpm dev
  ```
  L'application s'exécute avec Vite et est accessible sur `http://localhost:5173`. Elle lit `kyst.env` / `kyst.local.env` et appelle l'API à l'adresse `KYST_API_URL` (`http://127.0.0.1:8000` par défaut).

- **Vérifier les types et composants Svelte :**
  ```bash
  pnpm check
  ```

- **Compiler l'application pour la production :**
  ```bash
  pnpm build
  ```

- **Lancer le build de production avec le serveur Node** (variables lues dans `kyst.env` et `kyst.local.env`) :
  ```bash
  pnpm start
  ```

L'organisation du code, les pages et la gestion de session sont décrites dans [docs/Frontend.md](docs/Frontend.md).

### 3. Gérer les dépendances JavaScript

```bash
# Ajouter une dépendance
pnpm add <nom-du-paquet>

# Ajouter une dépendance de développement
pnpm add -D <nom-du-paquet>
```

---

## Mise en production (`just prod`)

Le `justfile` de `interface/` lance KYST en production sur une machine : l'API (`fastapi run`, un seul worker, sans rechargement) et le front (serveur Node d'adapter-node). Les deux lisent `kyst.env`, `kyst.local.env` et l'environnement.

1. Sur le serveur, créez `interface/kyst.local.env` avec les vraies valeurs, au minimum :
   ```bash
   SECRET_KEY=<sortie de : openssl rand -hex 32>
   FIRST_ADMIN_PASSWORD=<mot de passe du premier administrateur>
   POSTGRES_PASSWORD=<...>
   PGADMIN_DEFAULT_PASSWORD=<...>
   DATABASE_URL=postgresql+psycopg://kyst:<POSTGRES_PASSWORD>@localhost:5432/kyst
   ORIGIN=https://kyst.exemple.fr
   ```
2. Depuis `interface/` :
   ```bash
   just prod
   ```
   La recette enchaîne `preflight` (refuse de démarrer si un secret vaut encore `change-me` ou si `SECRET_KEY` fait moins de 32 caractères, et signale SQLite ou une `ORIGIN` en localhost), `install`, `build` puis `serve`. Ctrl+C arrête l'API et le front ; si l'un des deux s'arrête, l'autre aussi.

Recettes utiles :

| Recette | Rôle |
| :--- | :--- |
| `just prod` | Vérifie, installe, construit et lance tout |
| `just serve` | Relance l'API et le front déjà construits (après un redémarrage, sans rebuild) |
| `just preflight` | Vérifie seulement la configuration |
| `just build` | Reconstruit le front, à refaire après tout changement de code ou d'`ORIGIN` |
| `just check` | Tests de l'API et vérification du front |

Points d'attention :
- **HTTPS** : en production, les cookies de session sont `Secure`. Servez le site en HTTPS derrière un proxy (Caddy, nginx...) qui redirige vers `PORT`. Seul `localhost` fonctionne en HTTP.
- **`ORIGIN`** est figée au build, car elle sert à la protection CSRF des formulaires. Changer `ORIGIN` impose donc `just build`.
- **L'API écoute sur `API_HOST`** (`127.0.0.1` par défaut) : seul le front, sur la même machine, l'appelle. N'ouvrez que le port du front.
- **Un seul worker** pour l'API : l'état de coordination du planning vivra dans ce processus (voir [docs/todo.md](../docs/todo.md)).

---

## Infrastructure & Déploiement (`ansible/`)

Le répertoire `ansible/` contient la configuration pour le déploiement et la gestion des serveurs. Les tâches courantes sont encapsulées dans un fichier `justfile` exécuté avec **`just`**.

### 1. Préparer l'environnement virtuel

Depuis le dossier `ansible/`, lancez la commande suivante :
```bash
cd ansible
just venv
```
Cette recette crée le venv et installe automatiquement les dépendances Ansible avec `uv sync --locked`.

### 2. Recettes `just` utiles

Vous pouvez inspecter toutes les commandes disponibles en exécutant simplement :
```bash
just
```

Recettes principales :
- `just lint` : lance `ruff check` et `ansible-lint` pour vérifier la conformité du code et détecter les erreurs.
- `just todo` : recherche tous les commentaires `TODO` ou `noqa` (ignorant les règles de lint).
- `just playbook-create-ansible-user` : initialise le compte utilisateur `ansible` sur l'hôte cible.
- `just playbook-deploy-infra` : exécute le playbook principal de déploiement de l'infrastructure.

Pour plus de détails sur la procédure complète de déploiement, consultez [docs/Deploiement.md](./docs/Deploiement.md).

---

## Extensions et IDE recommandés

Pour une expérience de développement optimale avec Visual Studio Code ou Cursor :

- **Ansible :** [`Ansible` (Red Hat)][ansible-vscode-extension]
- **Python / FastAPI :** [`Python` (Microsoft)][python-vscode-extension] et [`Ruff` (Astral)][ruff-vscode-extension]
- **Just :** [`Just` (skellock)][just-vscode-extension]
- **Svelte :** [`Svelte for VS Code`][svelte-vscode-extension]
- **JavaScript / Formatage :** [`ESLint`][eslint-vscode-extension] et [`Prettier`][prettier-vscode-extension]

[ansible-vscode-extension]: https://marketplace.visualstudio.com/items?itemName=redhat.ansible
[python-vscode-extension]: https://marketplace.visualstudio.com/items?itemName=ms-python.python
[ruff-vscode-extension]: https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff
[just-vscode-extension]: https://marketplace.visualstudio.com/items?itemName=skellock.just
[svelte-vscode-extension]: https://marketplace.visualstudio.com/items?itemName=svelte.svelte-vscode
[eslint-vscode-extension]: https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint
[prettier-vscode-extension]: https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode

---

## Workflow Git & Bonnes pratiques

1. **Créer une branche dédiée pour chaque fonctionnalité ou correctif :**
   ```bash
   git checkout -b feat/nom-de-la-fonctionnalite
   # ou
   git checkout -b fix/nom-du-bug
   ```

2. **Vérifier le code localement :**
   - Assurez-vous que l'API démarre et que ses tests passent (`just dev`, `just test` dans `api/`).
   - Assurez-vous que le frontend compile et passe les vérifications sans erreur (`pnpm check` et `pnpm build`).
   - Si vous touchez à Ansible, vérifiez avec `just lint`.

3. **Rédiger des messages de commit clairs :**
   - Utilisez de préférence le format *Conventional Commits* (ex. `feat: ajout de l'endpoint items`, `fix: correction du style d'en-tête`, `docs: mise à jour du guide de contribution`).

4. **Pousser votre branche et ouvrir une Pull Request** sur le dépôt distant.
