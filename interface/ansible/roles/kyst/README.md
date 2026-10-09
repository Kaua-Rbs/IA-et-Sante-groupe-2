# KYST

Déploie KYST (API et front) avec PostgreSQL et pgAdmin, dans le Podman rootless configuré par le rôle [`podman`](../podman/README.md) (dépendance déclarée dans `meta/main.yml`).

## Services

Le fichier [`files/compose.yml`](files/compose.yml) est copié dans `kyst_project_dir` (`/home/podman/ias`), avec un `.env` généré depuis [`templates/ias.env.j2`](templates/ias.env.j2). Ce `.env` sert uniquement à remplacer les `${...}` du compose : chaque service ne reçoit que les variables qu'il cite.

| Service | Conteneur | Port hôte | Accès |
| :--- | :--- | :--- | :--- |
| Front SvelteKit | `kyst-app` | 3000 | Ouvert uniquement depuis `kyst_allowed_source` (reverse proxy) |
| API FastAPI | `kyst-api` | aucun | Réseau interne : seul le front l'appelle (`http://api:8000`) |
| PostgreSQL 18 | `postgres` | 5432 | Fermé par le pare-feu (politique `INPUT DROP`), joignable depuis l'hôte et le réseau interne |
| pgAdmin | `pgadmin` | 3001 | Ouvert uniquement depuis `kyst_allowed_source` |

## Images

L'API et le front sont construits sur le serveur. Le rôle clone le dépôt public (`kyst_repo_url`) à la version `kyst_repo_version` (branche, tag ou commit) dans `kyst_src_dir`, puis construit `localhost/kyst-api` et `localhost/kyst-app` avec les Dockerfiles de `interface/api` et `interface/app`. Seul le code **poussé** sur GitHub est déployé.

Chaque image porte le commit et l'URL publique dont elle est issue (labels `kyst.commit` et `kyst.origin`) : une image n'est reconstruite que si elle manque, ou si le commit cloné ou `kyst_origin` a changé. Les conteneurs ne sont recréés que si une image, `compose.yml` ou `.env` a changé, ou si un service est arrêté. Les anciennes images sont supprimées par le timer `podman-image-prune` du rôle `podman`.

L'URL publique du front est **figée dans l'image** (protection CSRF des formulaires) ; elle n'est pas lue au démarrage. Avec `kyst_origin` vide (défaut), le front suppose `https://` et l'en-tête `Host` transmis par le proxy, ce qui convient derrière un proxy TLS. Sinon, définir `kyst_origin` (ex. `https://kyst.example.org`) : les images sont reconstruites au déploiement suivant.

## Déployer

1. Pousser le code à déployer sur GitHub.
2. Lancer le playbook, en précisant la version si ce n'est pas `feat/fastapi` :

   ```bash
   just playbook-deploy-infra -e kyst_repo_version=main
   ```

   Le premier déploiement prend plusieurs minutes (téléchargement des images de base, `pnpm install`, build du front).

3. Se connecter avec `kyst_first_admin_email` (`admin@kyst.fr`) et le mot de passe généré dans `credentials/<hôte>/kyst/first_admin_password`.

Avec `kyst_seed_demo: true` (défaut), le rôle crée les ressources de démonstration (4 spécialités, 4 salles, 45 lits conventionnels, 21 places ambulatoires, 4 semaines de vacations) si la base n'en a aucune. À désactiver avant d'y mettre de vraies données.

## Variables

Voir [`defaults/main.yml`](defaults/main.yml). Les secrets (mots de passe PostgreSQL, pgAdmin et du premier administrateur, `SECRET_KEY` de l'API) sont générés au premier déploiement et conservés sur la machine de contrôle dans `credentials/<hôte>/kyst/` (ignoré par Git). Supprimer un de ces fichiers génère une nouvelle valeur au déploiement suivant, avec deux limites : PostgreSQL garde le mot de passe d'une base déjà initialisée, et l'API ne recrée pas un administrateur qui existe déjà.
