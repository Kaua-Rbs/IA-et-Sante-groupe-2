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
3. [Backend FastAPI (`api/`)](#backend-fastapi-api)
4. [Frontend Svelte (`app/`)](#frontend-svelte-app)
5. [Infrastructure & Déploiement (`ansible/`)](#infrastructure--déploiement-ansible)
6. [Extensions et IDE recommandés](#extensions-et-ide-recommandés)
7. [Workflow Git & Bonnes pratiques](#workflow-git--bonnes-pratiques)

---

## Architecture du projet

La partie est structuré de la manière suivante :

```text
.
├── api/              # Backend FastAPI (gestion des dépendances via uv)
├── app/              # Frontend Svelte (version Node via mise, dépendances via pnpm)
├── ansible/          # Recettes d'automatisation et playbooks (gérés avec just et uv)
└── docs/             # Documentation détaillée (déploiement, architecture...)
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

## Backend FastAPI (`api/`)

Le backend repose sur [FastAPI](https://fastapi.tiangolo.com/) et est géré avec **`uv`**.

### 1. Initialiser l'environnement

Placez-vous dans le dossier `api/` et synchronisez les dépendances :
```bash
cd api
uv sync
```
`uv` créera automatiquement l'environnement virtuel `.venv` et installera les dépendances définies dans `pyproject.toml` et verrouillées dans `uv.lock`.

### 2. Lancer le serveur de développement

Pour lancer l'API avec rechargement automatique en cas de modification du code (*hot-reload*) :
```bash
uv run fastapi dev
```

L'API est alors accessible sur :
- **Serveur local :** `http://127.0.0.1:8000`
- **Documentation interactive Swagger UI :** `http://127.0.0.1:8000/docs`
- **Documentation alternative ReDoc :** `http://127.0.0.1:8000/redoc`

### 3. Gérer les dépendances Python

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
  L'application s'exécute avec Vite et est accessible sur `http://localhost:5173`.

- **Vérifier les types et composants Svelte :**
  ```bash
  pnpm check
  ```

- **Compiler l'application pour la production :**
  ```bash
  pnpm build
  ```

- **Prévisualiser le build de production localement :**
  ```bash
  pnpm preview
  ```

- **Exécuter les tests :**
  ```bash
  pnpm test
  ```

### 3. Gérer les dépendances JavaScript

```bash
# Ajouter une dépendance
pnpm add <nom-du-paquet>

# Ajouter une dépendance de développement
pnpm add -D <nom-du-paquet>
```

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
   - Assurez-vous que l'API fonctionne (`uv run fastapi dev`).
   - Assurez-vous que le frontend compile et passe les vérifications sans erreur (`pnpm check` et `pnpm build`).
   - Si vous touchez à Ansible, vérifiez avec `just lint`.

3. **Rédiger des messages de commit clairs :**
   - Utilisez de préférence le format *Conventional Commits* (ex. `feat: ajout de l'endpoint items`, `fix: correction du style d'en-tête`, `docs: mise à jour du guide de contribution`).

4. **Pousser votre branche et ouvrir une Pull Request** sur le dépôt distant.
