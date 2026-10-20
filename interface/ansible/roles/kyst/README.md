# KYST

Déploie KYST (API et front) avec PostgreSQL et pgAdmin, dans le Podman rootless configuré par le rôle [`podman`](../podman/README.md) (dépendance déclarée dans `meta/main.yml`).

## Services

Le fichier [`files/compose.yml`](files/compose.yml) est copié dans `kyst_project_dir` (`/home/podman/ias`), avec un `.env` généré depuis [`templates/ias.env.j2`](templates/ias.env.j2). Ce `.env` sert uniquement à remplacer les `${...}` du compose : chaque service ne reçoit que les variables qu'il cite.

| Service | Conteneur | Port hôte | Accès |
| :--- | :--- | :--- | :--- |
| Front SvelteKit | `kyst-app` | 3000 | Ouvert uniquement depuis `kyst_allowed_source` (reverse proxy) |
| API FastAPI | `kyst-api` | aucun | Réseau interne : seul le front l'appelle (`http://api:8000`) |
| PostgreSQL 18 | `postgres` | 5432 | Fermé par le pare-feu (politique `INPUT DROP`), joignable depuis l'hôte et le réseau interne |
| pgAdmin | `pgadmin` | 3001 | Seulement avec `kyst_pgadmin_enabled: true`, ouvert uniquement depuis `kyst_allowed_source` |

## Images

L'API et le front ne sont plus construits sur le serveur : le rôle tire les images publiées par la CI sur ghcr.io à chaque release GitHub (`kyst_image_registry`, par défaut `ghcr.io/kaua-rbs/ia-et-sante-groupe-2`). `kyst_version` choisit le tag : `latest` (défaut, dernière release stable), une version exacte (`1.2.0`) ou `<majeure>.<mineure>` (`1.2`). Les prereleases n'ont que leur version exacte.

Le tag de l'API et du front est tiré à chaque déploiement, puis tous les conteneurs sont recréés. Les anciennes images sont supprimées par le timer `podman-image-prune` du rôle `podman`.

## Mise à jour automatique

Comme Watchtower, le serveur suit le tag `kyst_version` et applique les nouvelles images sans relancer le playbook. Le timer systemd `kyst-auto-update.timer` de l'utilisateur `podman` lance `kyst_project_dir/auto-update.sh` toutes les 15 minutes (`kyst_auto_update_schedule`, avec un délai aléatoire `kyst_auto_update_random_delay`). Le script :

1. télécharge l'image de chaque service de `kyst_auto_update_services` (par défaut `api` et `app`) ;
2. compare son identifiant à celui du conteneur en cours ;
3. recrée uniquement les services dont l'image a changé (`podman-compose up -d --force-recreate --no-deps`), ainsi que ceux dont le conteneur a disparu.

Une release GitHub suffit donc à mettre le serveur à jour : la CI pousse les images, le timer les applique au passage suivant. Avec une version exacte (`kyst_version: 1.2.0`), le tag ne bouge pas et rien n'est mis à jour. PostgreSQL et pgAdmin ne sont pas suivis : une nouvelle version majeure de PostgreSQL demande une migration des données.

`kyst_auto_update: false` arrête et désactive le timer. Sur le serveur, en tant que `podman` :

```bash
systemctl --user list-timers kyst-auto-update.timer   # prochain passage
journalctl --user -u kyst-auto-update                 # journal des mises à jour
systemctl --user start kyst-auto-update.service       # forcer une vérification
```

Le script ne touche ni à `compose.yml`, ni à `.env`, ni aux modèles : leurs changements passent toujours par le playbook.

L'URL publique du front (protection CSRF des formulaires) est lue au démarrage du conteneur, dans la variable `ORIGIN`. Avec `kyst_origin` vide (défaut), le front suppose `https://` et l'en-tête `Host` transmis par le proxy, ce qui convient derrière un proxy TLS. Sinon, définir `kyst_origin` (ex. `https://kyst.example.org`) : le front est recréé au déploiement suivant, sans changer d'image.

Les serveurs déployés avant ce changement gardent le clone des sources et les images construites localement. Pour repartir de zéro, [`scripts/reset-kyst.sh`](../../scripts/reset-kyst.sh) supprime tout ce que le rôle a créé (Podman reste installé), puis relancer le playbook.

## Déployer

1. Publier une release GitHub et attendre la fin de la CI, qui pousse les images.
2. Lancer le playbook, en précisant la version si ce n'est pas `latest` :

   ```bash
   just playbook-deploy-infra -e kyst_version=1.2.0
   ```

3. Se connecter avec `kyst_first_admin_email` (`admin@kyst.fr`) et le mot de passe généré dans `credentials/<hôte>/kyst/first_admin_password`.

Les prédictions viennent toujours des modèles entraînés (`AI_BACKEND=trained`). Ces fichiers ne sont pas versionnés : le rôle copie les fichiers listés dans `kyst_model_files` depuis `kyst_models_src` (par défaut `artifacts/ml-models/` à la racine du dépôt, sur la machine de contrôle) vers `kyst_project_dir/models`, sous les noms `surgery_duration_model.joblib` et `los_regressor.joblib` attendus par l'API, montés en lecture seule. Par défaut, ce sont les modèles « consultation » `room_consultation_selected_2026-10-20_v1.joblib` et `los_consultation_selected_2026-10-20_v1.joblib`, à placer dans `artifacts/ml-models/final-2026-10-20-v3/` (voir `FINAL_MODEL_IMPROVEMENTS.md`). Le déploiement échoue s'ils sont absents.

Avec `kyst_seed_demo: true` (défaut), le rôle crée, si la base n'a aucune ressource, un service fictif mais réaliste : 4 spécialités, 4 salles, 8 chirurgiens, 45 lits conventionnels, 21 places ambulatoires, des vacations de 3 semaines en arrière à 5 semaines en avant, et l'activité qui va avec. Cette activité comprend environ 250 interventions réalisées avec leurs durées réelles, les patients hospitalisés le jour du déploiement, un planning à venir de moins en moins rempli et 20 demandes en attente. Les prédictions et les dates passent par les modèles et l'ordonnanceur de l'API. Les dates sont calculées à partir du jour du déploiement. Après quelques semaines, le planning à venir se vide : pour repartir de données fraîches, vider la base, puis relancer le playbook. À désactiver avant d'y mettre de vraies données.

## Variables

Voir [`defaults/main.yml`](defaults/main.yml). Les secrets (mots de passe PostgreSQL, pgAdmin et du premier administrateur, `SECRET_KEY` de l'API) sont générés au premier déploiement et conservés sur la machine de contrôle dans `credentials/<hôte>/kyst/` (ignoré par Git). Supprimer un de ces fichiers génère une nouvelle valeur au déploiement suivant, avec deux limites : PostgreSQL garde le mot de passe d'une base déjà initialisée, et l'API ne recrée pas un administrateur qui existe déjà.
