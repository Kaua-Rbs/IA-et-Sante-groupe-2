# TODO

## Deployment

### Modèles IA

- Code des modèles « consultation » (v3, 2026-10-20) mergé depuis `improvement/technical-audit` (`consultation_features.py` dans `prediction/`)
- Fichiers `.joblib` récupérés dans `artifacts/ml-models/final-2026-10-20-v3/` (non versionnés) : empreintes vérifiées, chargés par l'API sous Python 3.13
  - Liste et empreintes SHA-256 : `experiments/results/final-consultation-2026-10-20-v3/manifest.json` (`artifact_sha256`)
  - À placer dans `artifacts/ml-models/final-2026-10-20-v3/` : le rôle `kyst` déploie `room_consultation_selected_…` et `los_consultation_selected_…` sous les noms attendus par l'API (`kyst_model_files`)
  - Provenance : le manifeste ci-dessus suffit (date, données, hash des sources)
- Versions compatibles : scikit-learn 1.9.1, xgboost 3.4.1, pandas 3.0.6, joblib 1.6.0 identiques entre `experiments/final_model_requirements.txt` et `interface/api/uv.lock` (entraînement sous Python 3.14 / Windows, image API en 3.13 : à confirmer au chargement)
- Tester en local dans l'interface : `AI_BACKEND=trained` dans `kyst.local.env`, avec `ROOM_MODEL_PATH` / `LOS_MODEL_PATH` pointant vers les fichiers v3, créer une demande, vérifier temps de salle / séjour / propositions
- Ambulatoire : séjour prédit arrondi à 1 jour (< 1,5) et réservation d'une seule journée ; le modèle prédit une moyenne, l'ancien seuil `<= 1` ne classait presque rien en ambulatoire. À mentionner dans le rapport
- Précision dégradée en consultation (anesthésie et praticien absents) : voir `docs/models.md`, à mentionner dans le rapport
- Les bornes P80/P95 du temps de salle ne sont pas exposées (pas d'intervalle affiché pour le bloc en mode `trained`)
- Chiffres pour le rapport : `docs/models.md` (MAE salle 16,6 min, séjour 0,51 j ; couverture faible pour les séjours ≥ 7 j)

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
- `kyst_origin` laissé vide : vérifié le 2026-10-20, le proxy transmet `Host` (POST de formulaire depuis `https://kyst.tech` accepté, depuis une autre origine refusé en 403). À définir seulement si le proxy change
- pgAdmin désactivé par défaut (`kyst_pgadmin_enabled: false` : ni conteneur, ni règle de pare-feu sur 3001) ; pour déboguer : `just playbook-deploy-infra -e kyst_pgadmin_enabled=true`
- Passer `kyst_seed_demo: false` avant d'y mettre de vraies données

### Conformité (RGPD, marquage CE)

#### Fait

- Journalisation sur le serveur (rôle `journald`) : journal persistant, rétention 1 an (`journald_retention`, max 8 Go), scellement FSS dont la clé de vérification reste dans `credentials/<hôte>/journald/`
- Logs des conteneurs dans le journal (`log_driver = "journald"`) : ils ne sont plus perdus à chaque `--force-recreate` (déploiement, mise à jour automatique)
- Trace d'accès de l'API (`api/audit.py`) : une ligne JSON par appel (utilisateur, IP du navigateur, route et identifiants, statut), connexions réussies et échouées, versions des modèles au démarrage ; jamais de corps de requête ni de paramètres d'URL
- Le front transmet l'IP du navigateur (`handleFetch`) : la limite de 5 connexions par minute s'applique par navigateur et non plus au front entier
- PostgreSQL journalise connexions et déconnexions

#### Reste à faire

- Vérifier après déploiement : `journalctl -t kyst-api` rempli, `journalctl --verify --verify-key=…` OK, IP du navigateur (et non celle du proxy) dans `client` : sinon, vérifier que le proxy ajoute `X-Forwarded-For`
- Copier la clé `credentials/<hôte>/journald/verification_key` hors de la machine de contrôle
- Copie des journaux hors du serveur (`systemd-journal-remote` ou syslog distant)
- Hébergement de données de santé réelles : hébergeur certifié HDS obligatoire (le serveur actuel ne l'est pas : démo uniquement)
- Documents à produire pour le rapport : registre des traitements, AIPD, information des patients, durée de conservation des données patients (aucune purge automatique aujourd'hui)
- Statut réglementaire à argumenter : logiciel de planification (dispositif médical MDR ou non, risque AI Act), avec validation humaine de chaque date proposée

## Rendu final

- Diapo
  - Branche `report/presentation` : 16 commits pas encore dans `final_deployment`
  - Lien vers l'instance (`kyst.tech`) à vérifier le jour J
  - Captures d'écran de l'interface avec l'IA branchée
- Rapport
  - Chapitre sur l'intégration IA ↔ web : modèles, précision, limites (champs manquants en consultation) ; sources : `docs/models.md`, `docs/kyst-integration.md`
  - Résultats des modèles (MAE temps de salle, séjour) et des métaheuristiques
- Merge tout dans final_deployment
  - Branches avec des commits absents de `final_deployment` :
    - `origin/report/presentation` (16)
    - `origin/model/los-bridge` (4)
    - `origin/model/or-occupation` (1)
  - `meta_heuristics` et `feat/mesa-historical-simulation` sont contenues dans `feat/combine-mesa-metaheuristics`, dont le code est pour l'essentiel déjà intégré (≈ 120 lignes d'écart) ; leurs campagnes d'expérimentation (CLI `hospital_sim.experiment`, benchmarks, GUI) ont été retirées du produit final : ne pas les re-fusionner
  - Vérifier pour chacune si le contenu est déjà intégré autrement (rebase / squash) avant de merger
  - Relancer la CI et les tests (`tests/`, `interface/api/tests/`, `svelte-check`) après les merges
- Merge avec main

### Fait (ménage du 2026-10-20)

- Code hors produit supprimé : on ne garde que l'application, ce que l'API importe (`prediction/`, `optimiseur/{optimizer,multiagent,search_control}`, `hospital_sim/` sans les CLI d'expérimentation) et l'entraînement des modèles déployés (`experiments/train_consultation_models.py`, les trois notebooks de préparation)
  - Supprimés : expériences S1/S2 et campagne de planification, ponts `bridge_los` / `prediction_planning`, aléas, benchmarks, GUI Tkinter, démos CLI, tableau de bord Streamlit, notebooks `guide_optimisation` et `rapport_aleas_et_adaptation`, `api/ai/validate_web_models.py`, tests correspondants
  - Adaptateurs de démo et instances de référence de `hospital_sim` déplacés dans `tests/` (fixtures)
  - Restes du gabarit Ansible retirés (recette `playbook-update`, Vault, pysnmp)
- Documentation en français, reliée depuis `README.md` et `docs/README.md` ; un README par dossier ; règles Git dans `CONTRIBUTING.md`
- Racine rangée : rapports dans `docs/` (`models.md`, `data-dictionary.md`), plan de tests dans `tests/README.md`

### Reste à faire

- Supprimer les bases locales `interface/api/kyst.db` et `ias.db` (non versionnées, exclues de l'image Docker)
