# TODO

## Deployment

### Modèles IA

- Code des modèles « consultation » (v3, 2026-10-20) mergé depuis `improvement/technical-audit` (`consultation_features.py` et `prediction_planning.py` déplacés dans `prediction/`)
- Fichiers `.joblib` récupérés dans `artifacts/ml-models/final-2026-10-20-v3/` (non versionnés) : empreintes vérifiées, chargés par l'API sous Python 3.13
  - Liste : `FINAL_MODEL_ARTIFACT_FILES.txt` ; empreintes SHA-256 : `experiments/results/final-consultation-2026-10-20-v3/manifest.json` et `experiments/results/final-artifact-verification-2026-10-20-v3/artifact_verification.json`
  - À placer dans `artifacts/ml-models/final-2026-10-20-v3/` : le rôle `kyst` déploie `room_consultation_selected_…` et `los_consultation_selected_…` sous les noms attendus par l'API (`kyst_model_files`)
  - Provenance : les manifestes ci-dessus suffisent (date, données, hash des sources)
- Versions compatibles : scikit-learn 1.9.1, xgboost 3.4.1, pandas 3.0.6, joblib 1.6.0 identiques entre `experiments/final_model_requirements.txt` et `interface/api/uv.lock` (entraînement sous Python 3.14 / Windows, image API en 3.13 : à confirmer au chargement)
- Tester en local dans l'interface : `AI_BACKEND=trained` dans `kyst.local.env`, avec `ROOM_MODEL_PATH` / `LOS_MODEL_PATH` pointant vers les fichiers v3, créer une demande, vérifier temps de salle / séjour / propositions
- Ambulatoire : séjour prédit arrondi à 1 jour (< 1,5) et réservation d'une seule journée ; le modèle prédit une moyenne, l'ancien seuil `<= 1` ne classait presque rien en ambulatoire. À mentionner dans le rapport
- Précision dégradée en consultation (anesthésie et praticien absents) : voir `docs/web-full-system-integration.md`, à mentionner dans le rapport
- Les bornes P80/P95 du temps de salle ne sont pas exposées (pas d'intervalle affiché pour le bloc en mode `trained`)
- Chiffres pour le rapport : `FINAL_MODEL_RESULTS_FOR_REPORT.md` (MAE salle 16,6 min, séjour 0,51 j ; couverture faible pour les séjours ≥ 7 j)

### Instance de démo

Objectif : une instance qui ressemble à la vraie vie d'un service, avec l'IA branchée et assez de données pour être crédible.

#### Fait

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

- Seed testé avec les modèles v3 (`AI_BACKEND=trained`, 2026-10-20) : ~20 s, ~720 patients, 30 % d'ambulatoire (surtout orthopédie et ORL), 30 à 36 lits conventionnels sur 45 et 5 à 9 places ambulatoires sur 21 sur les deux semaines à venir
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
