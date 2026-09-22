# Routes

## Liste des routes

### /account
- `POST /login` : Connexion
- `POST /register` : Inscription d'un nouvel utilisateur
- `GET /me` : Récupérer son propre profil
- `PUT /me/update` : Mettre à jour son propre profil (appelle /user/update)

### /configuration (Accès Admin)
- `GET /users` : Liste tous les utilisateurs (pour validation)
- `PUT /user/update/{id}` : Modification d'un utilisateur par l'admin
- `PATCH /user/approve/{id}` : Approuve un utilisateur en attente (appelle /update under the hood)
- `DELETE /user/delete/{id}` : Supprime un utilisateur
- `GET /structure` : Récupère la configuration globale de l'établissement (lits, etc.)
- `PUT /structure/update` : Met à jour la configuration de la structure
- `GET /operating_rooms` : Liste les salles d'opération
- `GET /operating_rooms/{status}/{date}` : Liste les salles libres ou non à une date
- `GET /operating_room/status/{date}`: Renvoie le statut en fonction de la date
- `POST /operating_room/add` : Ajoute une nouvelle salle d'opération
- `PUT /operating_room/update/{id}` : Modifie une salle d'opération
- `DELETE /operating_room/delete/{id}` : Supprime une salle

### /event (Planning & Interventions)
- `GET /list` : Liste des événements (avec filtres par date, chirurgien, salle)
- `POST /add` : Ajoute un événement générique
- `PUT /update/{id}` : Modifie un événement
- `DELETE /delete/{id}` : Supprime un événement
- `POST /intervention/predict` : Appelle le modèle d'IA pour obtenir une prédiction de durée
- `POST /intervention/feedback/{id}` : Soumet la durée réelle post-opération (pour améliorer/ré-entraîner l'IA)
- `POST /intervention/add` : Planifie une intervention chirurgicale spécifique
- `GET /hospital_stay/list` : Liste les séjours hospitaliers en cours
- `GET /hospital_stay/active` : Liste uniquement les patients actuellement admis (occupant un lit)
- `POST /hospital_stay/add` : Crée un nouveau séjour (admission)
- `PUT /hospital_stay/update/{id}` : Met à jour un séjour (ex: date de sortie)

### /people (Gestion des acteurs)
- `GET /patient/list` : Recherche / Liste des patients
- `GET /patient/{id}` : Détails d'un patient (historique et séjours)
- `POST /patient/add` : Ajout d'un patient
- `PUT /patient/update/{id}` : Mise à jour du dossier patient
- `DELETE /patient/delete/{id}` : Suppression d'un patient
- `GET /surgeon/list` : Liste des chirurgiens
- `GET /surgeon/{id}` : Détails d'un chirurgien et son emploi du temps
- `GET /surgeon/{id}/availability` : Trouve les créneaux libres pour un chirurgien
- `POST /surgeon/add` : Ajout d'un chirurgien (et liaison avec un user_id)
- `PUT /surgeon/update/{id}` : Mise à jour d'un chirurgien
- `DELETE /surgeon/delete/{id}` : Suppression d'un chirurgien

### /analytics (Statistiques & Tableaux de bord)
- `GET /analytics/occupancy` : Taux d'occupation global des lits et des places ambulatoires
- `GET /analytics/operating_rooms` : Taux d'utilisation des salles d'opération par période
- `GET /analytics/ai_accuracy` : Compare les durées prédites par l'IA aux durées réelles

### /data (Import / Export)

- `POST /data/import_dataset` : Upload d'un fichier CSV/Excel pour peupler la base de données (ex: historique)
- `GET /data/export_schedule` : Exporte le planning au format .ical
- `POST /data/import_schedule/{id}` : Importe le planning d'un chirurgien au format .ical