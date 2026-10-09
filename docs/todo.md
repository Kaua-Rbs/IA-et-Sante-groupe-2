# TODO — KYST

## Intégration de l'IA (livrée par les autres parties du projet)

Aujourd'hui, l'API utilise des **fixtures** (`interface/api/ai/fixtures.py` et `fixtures.json`) : les valeurs sont plausibles mais ni ajustées ni calibrées. Les points de branchement sont les protocoles de `interface/api/ai/contracts.py`, sélectionnés par `AI_BACKEND` (voir `interface/kyst.env`) dans `interface/api/ai/providers.py`.

- [ ] Brancher le modèle de durée de séjour (`LOSPredictor`, jours calendaires inclusifs) à partir de `preprocessing_los.ipynb`
- [ ] Brancher le modèle de temps de salle (`RoomDurationPredictor`, minutes de l'entrée à la sortie de salle) à partir de `preprocessing_surgery_duration.ipynb`
- [ ] Brancher le classifieur ambulatoire / conventionnel (`CareTypeClassifier`)
- [ ] Remplacer `GreedyFixtureScheduler` par le solveur de l'équipe optimisation (tabou, recuit, génétique) derrière le protocole `Scheduler`
- [ ] Faire tourner les solveurs gourmands en CPU hors de la boucle d'événements (`ProcessPoolExecutor`)
- [ ] Décider où vit le code partagé : `hospital_sim` comme dépendance de l'API, ou package commun
- [ ] Brancher le `Coordinator` de `hospital_sim` : un seul worker, état reconstruit depuis la base au démarrage, aléas (urgence, annulation, dépassement, sortie retardée, salle indisponible) via une route `/events`
- [ ] Ré-entraînement et suivi à partir de `/cases/{id}/outcome` et `/analytics/predictions`

## API

- [ ] Migrations Alembic à la place de `create_all`
- [ ] Import de l'historique (xlsx → base) et export du planning (iCal / CSV)
- [ ] Modèles de vacations hebdomadaires par spécialité (génération en masse), en partant de l'historique ; justifier chaque aménagement
- [ ] Week-ends et jours fériés dans l'ordonnancement ; règle d'admission la veille pour certaines interventions
- [ ] Occupation des lits fondée sur la sortie réelle quand elle est connue (aujourd'hui, la sortie prévue)
- [ ] Droits plus fins : un médecin ne voit que ses demandes, une secrétaire celles de ses chirurgiens
- [ ] Journal d'audit des décisions et des accès aux données patient
- [ ] Ordre de passage dans une vacation et temps de remise en état entre deux interventions
- [ ] Ajouter l'image de l'API à `interface/ansible/roles/hestia/files/compose.yml`

## Front (`interface/app`, SvelteKit)

- [ ] Tests : parcours demande → propositions → confirmation (Playwright) et tests unitaires de `format.ts`
- [ ] Recherche de patients et de demandes paginée côté API (les listes sont limitées à 100)
- [ ] Vue « planning du jour » par salle : ordre de passage, patients, temps de remise en état
- [ ] Modèles de vacations hebdomadaires (génération en masse) depuis la page Bloc
- [ ] Indicateurs d'aide au lissage : week-ends, vacances, comparaison avec l'occupation historique
- [ ] Mode sombre (le design actuel n'a que des jetons clairs)
- [ ] Ajouter l'image du front au déploiement (`interface/ansible/roles/hestia/files/compose.yml`)

## Configuration et déploiement

- [ ] Générer le fichier d'environnement du serveur (`interface/ansible/roles/hestia/templates/ias.env.j2`) à partir des clés de `interface/kyst.env`, avec les secrets tirés d'Ansible Vault
- [ ] Construire `DATABASE_URL` à partir des variables `POSTGRES_*` en déploiement

## Ménage du dépôt

- [ ] Retirer `texput.log` du dépôt ; vérifier que `interface/ansible/hosts` peut rester versionné
- [ ] Mettre à jour le README principal (structure du dépôt, KYST)
