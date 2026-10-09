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

L'API et le front ne sont pas construits sur le serveur. Le workflow [`images.yml`](../../../../.github/workflows/images.yml) lance les tests de l'API, puis publie `ghcr.io/<propriétaire>/kyst-api` et `kyst-app` :

- à chaque push sur `main` qui touche `interface/api` ou `interface/app` (tags `main`, `latest`, `sha-<commit>`) ;
- à la demande, sur n'importe quelle branche (onglet *Actions* > *Images* > *Run workflow*), avec le nom de la branche comme tag (ex. `feat-fastapi`).

Le rôle télécharge l'image du tag `kyst_image_tag` et ne recrée les conteneurs que si une image, `compose.yml` ou `.env` a changé, ou si un service est arrêté.

L'URL publique du front est **figée dans l'image** (protection CSRF des formulaires) ; elle n'est pas lue au démarrage. Sans valeur, le front suppose `https://` et l'en-tête `Host` transmis par le proxy, ce qui convient derrière un proxy TLS. Pour la fixer, définir la variable de dépôt GitHub `KYST_ORIGIN` (ex. `https://kyst.example.org`) puis relancer le workflow.

## Déployer

1. Publier les images (push sur `main`, ou lancement manuel du workflow).
2. Si les paquets GHCR sont privés (cas par défaut à leur création) : soit les rendre publics dans les réglages du paquet sur GitHub, soit renseigner `kyst_registry_user` et `kyst_registry_token` (jeton avec `read:packages`, chiffré avec `ansible-vault`).
3. Choisir le tag si besoin, puis lancer le playbook :

   ```bash
   just playbook-deploy-infra -e kyst_image_tag=feat-fastapi
   ```

4. Se connecter avec `kyst_first_admin_email` (`admin@kyst.fr`) et le mot de passe généré dans `credentials/<hôte>/kyst/first_admin_password`.

Avec `kyst_seed_demo: true` (défaut), le rôle crée les ressources de démonstration (4 spécialités, 4 salles, 45 lits conventionnels, 21 places ambulatoires, 4 semaines de vacations) si la base n'en a aucune. À désactiver avant d'y mettre de vraies données.

## Variables

Voir [`defaults/main.yml`](defaults/main.yml). Les secrets (mots de passe PostgreSQL, pgAdmin et du premier administrateur, `SECRET_KEY` de l'API) sont générés au premier déploiement et conservés sur la machine de contrôle dans `credentials/<hôte>/kyst/` (ignoré par Git). Supprimer un de ces fichiers génère une nouvelle valeur au déploiement suivant, avec deux limites : PostgreSQL garde le mot de passe d'une base déjà initialisée, et l'API ne recrée pas un administrateur qui existe déjà.
