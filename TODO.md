# TODO

## Deployment

### Modèles IA

- Récupérer les modèles entraînés `surgery_duration_model.joblib` et `los_regressor.joblib`
  - Introuvables : ni sur la machine, ni dans Git (toutes branches, historique, LFS)
  - Demander à l'équipe modèles (branches `model/los-bridge`, `model/or-occupation`) qui les a en local
  - Sinon les ré-entraîner (`python -m prediction.los_model`, `python -m prediction.surgery_duration`, depuis la racine) : il faut `resources/model_los_dataset.parquet` et `resources/model_surgery_duration_dataset.parquet` (générés par `preprocessing_los.ipynb` et `preprocessing_surgery_duration.ipynb` à partir du classeur source)
  - Vérifier les releases / artefacts CI GitHub (`gh` non installé)
  - Noter quelque part (hors Git) la provenance : date d'entraînement, données, commit, hash (l'API affiche `room-<sha256[:12]>` / `los-<sha256[:12]>`)
- Décider où ranger les modèles
  - Option A (en place) : copiés par Ansible depuis `artifacts/ml-models/` (`kyst_models_src`) vers `/home/podman/ias/models`, montés en lecture seule dans l'API ; le déploiement échoue s'ils manquent
  - Option B : `interface/api/ai/` → ajouter au `.gitignore`, faire pointer `ROOM_MODEL_PATH` / `LOS_MODEL_PATH` dessus, retirer la copie et le montage `./models` du rôle
  - ⚠️ Option B : le Dockerfile copie `interface/api/` → modèles (données confidentielles) dans l'image publiée sur ghcr.io. Vérifier si l'image est publique
- Tester les modèles en local avant de déployer : `AI_BACKEND=trained` dans `kyst.local.env`, créer une demande, vérifier temps de salle / séjour / propositions
- Vérifier la compatibilité des versions (scikit-learn, etc.) entre l'environnement d'entraînement et `interface/api/uv.lock` : un `.joblib` se charge mal d'une version à l'autre
- Faire échouer l'API au démarrage si les modèles manquent (aujourd'hui `get_predictors` est paresseux : l'erreur n'apparaît qu'à la première prédiction)
- Précision dégradée en consultation (anesthésie et praticien absents) : voir `docs/web-full-system-integration.md`, à mentionner dans le rapport
- Les bornes P80/P95 du temps de salle ne sont pas exposées (pas d'intervalle affiché pour le bloc en mode `trained`)

### Instance de démo

Objectif : une instance qui ressemble à la vraie vie d'un service, avec l'IA branchée et assez de données pour être crédible.

#### Fait (non commité)

- Prod = toujours `AI_BACKEND=trained` (en dur dans `compose.yml`) ; seul `kyst_seed_demo` change entre instances
- Rôle Ansible : copie des modèles depuis `kyst_models_src` vers `/home/podman/ias/models` ; variables `kyst_ai_backend` / `kyst_model_dir` supprimées
- UI : plus aucune mention « démo » (tableau de bord, fiche demande, page d'accueil) ; la fiche demande affiche « Prédiction IA »
- Seed réaliste (`interface/api/seed.py`), testé en local en fixtures (~3 s, tests API OK) :
  - 4 spécialités, 4 salles, 8 chirurgiens (noms courants), 45 lits conventionnels, 21 places ambulatoires
  - Vacations de J-21 à J+35, attribuées aux chirurgiens en alternance
  - ~250 interventions réalisées avec durées réelles (alimente la précision des prédictions), patients hospitalisés le jour J, planning à venir dégressif (~77 % → 0 % à 4 semaines), 20 demandes en attente dont 16 avec dates A/B, ~3 % d'annulations, ~580 patients pseudonymes
  - Actes réalistes par spécialité (CIM-10 + CCAM, âge et sexe plausibles) ; prédictions et dates passent par les vrais prédicteurs et l'ordonnanceur
- Doc du seed mise à jour (README du rôle `kyst`, `interface/docs/Features.md`)

#### Reste à faire

- Commiter : UI + rôle Ansible + seed + docs (attention : `.gitignore` et le déplacement `reference/` → `docs/reference/` sont aussi dans l'arbre de travail)
- Tester le seed avec les modèles entraînés (`AI_BACKEND=trained`) : durée d'exécution, part de l'ambulatoire (en fixtures, seul l'ORL est ambulatoire → ~6 places sur 21), occupation des lits (en fixtures : 14 à 39 lits sur 45)
- Vérifier les codes CCAM du catalogue du seed (écrits de mémoire), idéalement avec les codes les plus fréquents du classeur pour que les modèles les reconnaissent
- Les demandes du seed sont attribuées au premier administrateur (« créée par Administrateur ») : créer des comptes fictifs (chirurgiens, secrétariat, cadre) pour la démo ?
- Les données vieillissent (datées autour du jour du seed) : vider la base et relancer le playbook juste avant la soutenance
- Publier une release GitHub pour que la CI pousse les images, puis `just playbook-deploy-infra`
- Vérifier après déploiement : connexion admin (`credentials/<hôte>/kyst/first_admin_password`), tableau de bord rempli, une demande → dates A/B → confirmation
- Définir `kyst_origin` (URL publique, ex. `https://kyst.tech`) si le proxy ne transmet pas `Host`
- pgAdmin exposé sur 3001 derrière le proxy : le retirer en prod
- Passer `kyst_seed_demo: false` avant d'y mettre de vraies données
- `interface/docs/Features.md` : les autres statuts « Démonstration » (prédictions, propositions) ne sont plus vrais en prod

## Rendu final

- Diapo
  - Branche `report/presentation` : 16 commits pas encore dans `final_deployment`
  - Lien vers l'instance (`kyst.tech`) à vérifier le jour J
  - Captures d'écran de l'interface avec l'IA branchée
- Rapport
  - Chapitre sur l'intégration IA ↔ web : modèles, précision, limites (champs manquants en consultation)
  - Résultats des modèles (MAE temps de salle, séjour) et des métaheuristiques
- Merge tout dans final_deployment
  - Branches avec des commits absents de `final_deployment` :
    - `origin/report/presentation` (16)
    - `origin/feat/combine-mesa-metaheuristics` (15)
    - `origin/meta_heuristics` (9)
    - `origin/feat/mesa-historical-simulation` (7)
    - `origin/model/los-bridge` (4)
    - `origin/codex/web-full-system` (3)
    - `origin/model/or-occupation` (1)
  - Vérifier pour chacune si le contenu est déjà intégré autrement (rebase / squash) avant de merger
  - Relancer la CI et les tests (`tests/`, `interface/api/tests/`, `svelte-check`) après les merges
- Rajouter des README dans tout les dossiers
  - En priorité : `interface/`, `interface/api/`, `interface/app/`, `hospital_sim/`, `docs/`, `notebooks/`, `soutenance/`
  - Déjà présents : racine, `optimiseur/`, `report/`, `interface/ansible/` et ses rôles `kyst` / `podman`
- Organiser la documentation, la traduire en français
  - En anglais : `README.md` (racine), `docs/coordination-core.md`, `docs/web-integration-summary.md`
  - `docs/todo.md` est obsolète (parle de fixtures, du rôle `hestia` qui n'existe plus) : le fusionner avec ce fichier ou le supprimer
  - README racine : section « Current state » à mettre à jour (KYST, déploiement, optimiseur, simulation)
- Organiser les dossiers
  - modèles dans `prediction/` ; imports, Dockerfile, tests et README mis à jour
  - Notebooks de la racine rangés dans `notebooks/` (fait, non commité) ; leurs chemins `resources/` passent par `REPO`, ils se lancent depuis la racine ou depuis `notebooks/`
  - Supprimer les `kyst.db` / `__pycache__` locaux (non versionnés, mais à ne pas embarquer)
- Merge avec mains
