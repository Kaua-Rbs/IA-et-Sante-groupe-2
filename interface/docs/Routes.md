# KYST — Routes de l'API

La documentation interactive est générée par FastAPI : `http://127.0.0.1:8000/docs` (Swagger) et `/redoc`. Cette page donne la vue d'ensemble.

Rôles : **admin** (tout), **planner** (cadre de bloc / gestion des lits), **doctor**, **secretary**, **user** (lecture des ressources et des indicateurs). Un admin passe tous les contrôles. « Staff » désigne doctor, secretary ou planner ; « Clinique » désigne doctor ou secretary.

## Compte — `/account`

| Méthode | Route | Accès | Description |
|---|---|---|---|
| POST | `/account/login` | public | Formulaire OAuth2 (`username` = nom d'utilisateur ou email, `password`). Renvoie `access_token` et `refresh_token`. Limite : 5 par minute. |
| POST | `/account/token/refresh` | public | Échange un refresh token contre une nouvelle paire (rotation) |
| POST | `/account/logout` | connecté | Révoque le refresh token fourni |
| POST | `/account/change-password` | connecté | Révoque tous les refresh tokens |
| POST | `/account/users/create` | public | Inscription ; le compte attend la validation d'un admin si `ACCOUNT_VALIDATION` |
| GET, PATCH | `/account/users/me` | connecté | Profil ; seul `full_name` est modifiable |
| GET | `/account/users/` | admin | Liste ; `?validated=false` pour les comptes en attente |
| GET, PATCH, DELETE | `/account/users/{id}` | admin | Le PATCH permet notamment `disabled` |
| POST | `/account/users/{id}/validate` | admin | Valide un compte |
| GET | `/account/groups/` | admin | Rôles disponibles |
| POST, DELETE | `/account/users/{id}/groups/{group_id}` | admin | Ajoute ou retire un rôle |

Le jeton d'accès contient `sub`, `full_name`, `admin`, `doctor` et `roles` ; le front lit ces champs pour adapter ses menus.

## Ressources

| Méthode | Route | Accès | Description |
|---|---|---|---|
| GET / POST | `/specialties` | connecté / planner | |
| PATCH, DELETE | `/specialties/{id}` | planner | |
| GET / POST | `/rooms` | connecté / planner | `?active=` |
| PATCH, DELETE | `/rooms/{id}` | planner | Préférer `active=false` à la suppression |
| GET / POST | `/bed-units` | connecté / planner | |
| PATCH, DELETE | `/bed-units/{id}` | planner | |
| GET / POST | `/surgeons` | connecté / planner | `?specialty_id=` |
| GET, PATCH, DELETE | `/surgeons/{id}` | connecté / planner | |
| GET / POST | `/vacations` | connecté / planner | `?start=&end=&room_id=&specialty_id=&surgeon_id=` ; 409 en cas de chevauchement |
| GET, PATCH, DELETE | `/vacations/{id}` | connecté / planner | |

## Patients et demandes

| Méthode | Route | Accès | Description |
|---|---|---|---|
| GET / POST | `/patients` | staff / clinique | `?external_ref=` |
| GET, PATCH, DELETE | `/patients/{id}` | staff / clinique | |
| GET / POST | `/requests` | staff / clinique | `?status=&surgeon_id=&patient_id=` |
| GET, PATCH | `/requests/{id}` | staff / clinique | Modifiable seulement au statut `pending` |
| POST | `/requests/{id}/cancel` | clinique | Annule une demande `pending` |
| GET / POST | `/requests/{id}/predictions` | staff / clinique | Historique, ou nouvelle prédiction (aperçu) |

## Planification

| Méthode | Route | Accès | Description |
|---|---|---|---|
| POST | `/requests/{id}/proposals` | clinique | Prédit, puis propose jusqu'à `PROPOSAL_COUNT` dates (A, B…) avec leurs raisons. Remplace les propositions ouvertes. Une liste vide signifie qu'aucun créneau n'a été trouvé dans la fenêtre. |
| GET | `/requests/{id}/proposals` | staff | `?status=` |
| POST | `/proposals/{id}/accept` | clinique | Décision humaine. La capacité est revérifiée ; 409 avec `reasons` si la proposition est devenue infaisable. Crée le `PlannedCase`. |
| POST | `/proposals/{id}/reject` | clinique | |
| GET | `/cases` | staff | `?start=&end=&vacation_id=&request_id=&status=` (les séjours qui chevauchent la période) |
| GET | `/cases/{id}` | staff | |
| POST | `/cases/{id}/cancel` | clinique | Libère la capacité ; la demande repasse `pending` |
| POST | `/cases/{id}/outcome` | staff | Durée réelle en salle et durée réelle du séjour ; alimente `/analytics/predictions` |

## Indicateurs — `/analytics`

Ces routes ne renvoient que des agrégats, jamais de ligne patient.

| Méthode | Route | Accès | Description |
|---|---|---|---|
| GET | `/analytics/occupancy` | connecté | Lits occupés par unité et par jour (`?start=&end=`, 14 jours par défaut) |
| GET | `/analytics/vacations` | connecté | Remplissage de chaque vacation |
| GET | `/analytics/predictions` | staff | Erreur des prédictions sur les cas terminés |

## Divers

| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | État, version, backend IA actif, marge d'urgence et nombre de dates proposées |
