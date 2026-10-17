# Intégration du moteur complet dans KYST

Branche de travail : `codex/web-full-system`, créée depuis `origin/main`.
Les calculs historiques et les artefacts de modèles restent locaux ; aucune
donnée patient n'est ajoutée au dépôt ou à l'image de l'API.

## État comparé

| Domaine | Application sur `main` | Dans le moteur de recherche/simulation | Intégration sur cette branche |
| --- | --- | --- | --- |
| Prédictions | Valeurs de démonstration par spécialité/type/âge | Modèles entraînés de durée de salle et de séjour, avec artefacts locaux | Adaptateurs `AI_BACKEND=trained` pour le parcours habituel de propositions A/B ; `fixtures` reste le défaut |
| Proposition A/B | Glouton par demande, avec contrôle de vacation et de lits | Métaheuristiques pour un **ensemble** de patients/vacations | Le choix individuel reste glouton ; un aperçu séparé optimise jusqu'à 50 demandes en attente avec les 10 méthodes disponibles |
| Capacité | Vacations, lits conventionnels et places ambulatoires persistés ; contrôle lors de la confirmation | Objectif global de vacations/lits, mais modèle de lits agrégé | L'aperçu respecte fenêtre, chirurgien, marge d'urgence et lits par unité après la recherche ; les propositions rejetées par ce contrôle sont signalées non placées |
| SMA/Mesa | Aucun appel depuis le site | Coordinateur, fermetures, replanification, simulations salle minute par minute et lits sur plusieurs jours | Aperçu Mesa **salles uniquement** sur les demandes en attente, avec durées d'exécution hypothétiques ; aucun changement de réservation |
| Aléas | Annulation manuelle et marge d'urgence | Fermetures et adaptation dynamique dans les moteurs | Fermeture aux nouvelles entrées de la salle 1, 10 h–12 h, testable en politique figée/réactive dans l'aperçu |
| Données réelles | Cas cliniques saisis dans KYST ; résultats observés enregistrables | Classeur historique, Parquet et cohortes 2022 pour évaluation | Aucun chargement des données historiques dans l'API web ; les artefacts de modèles sont fournis séparément |

## Utilisation

Le gestionnaire du bloc voit désormais deux panneaux sur la page **Planning** :

1. **Optimisation de la cohorte** : prévisualisation en lecture seule des
   demandes en attente sur une fenêtre de 60 jours au maximum. Les vacations
   déjà réservées, les lits occupés et les capacités disponibles sont lus en
   base. Le résultat affiche les affectations réalisables et les demandes
   non placées. Il ne remplace pas la confirmation humaine d'une proposition.
2. **Simulation Mesa : salles** : simulation hypothétique d'une journée, avec
   salles identiques, 08 h–17 h et 15 minutes de remise en état. Les durées
   réalisées sont les prédictions multipliées par un facteur explicite de 1 à 2.
   La simulation ne connaît pas les résultats futurs réels ; son résultat est
   agrégé et ne montre aucun identifiant d'épisode. Elle ne simule ni les lits,
   ni les spécialités, ni les vacations dans cet aperçu.

Par défaut, KYST reste en mode `fixtures`. Pour exécuter les modèles entraînés,
fournir les deux fichiers non versionnés et définir :

```text
AI_BACKEND=trained
ROOM_MODEL_PATH=/chemin/absolu/surgery_duration_model.joblib
LOS_MODEL_PATH=/chemin/absolu/los_regressor.joblib
```

Dans le conteneur, `KYST_MODEL_DIR` est monté en lecture seule sur `/srv/models`.
Ne placer aucun artefact ou jeu de données patient dans l'image Docker ni dans Git.
Un fichier manquant provoque une erreur explicite ; il n'est pas remplacé en
silence par les valeurs de démonstration.

## Limites à traiter avant un usage clinique

- Le formulaire de consultation fournit âge, sexe, diagnostic principal, CCAM
  et type d'intervention. Les artefacts existants ont aussi été entraînés avec
  anesthésie et noms de praticiens, absents du formulaire. L'adaptateur encode
  ces champs comme manquants. **La performance avec ces entrées partielles n'a
  pas été validée** ; réentraîner et évaluer les modèles sur les champs
  réellement disponibles à la consultation.
- L'optimiseur de vacations a une fonction de coût souple et des lits agrégés.
  L'adaptateur web impose les fenêtres, chirurgiens, unités réelles et capacités
  après recherche ; il peut laisser des demandes non placées. Il faut intégrer
  ces contraintes à la recherche elle-même puis comparer les méthodes sur des
  cohortes représentatives avant de produire des propositions opérationnelles.
- L'aperçu de cohorte n'écrit pas de propositions en base. La confirmation
  transactionnelle de plusieurs affectations, avec revalidation en cas de
  changement de capacité, reste à développer.
- La simulation Mesa du site utilise des durées hypothétiques et des salles
  interchangeables. Il faut relier le modèle de lits multi-jours aux unités,
  aux arrivées et aux événements de l'application avant de l'utiliser pour
  guider le planning réel. Les urgences, absences et annulations en temps réel
  demandent aussi une chaîne d'observation et de replanification persistante.

Les modèles restent séparés de l'optimiseur par les contrats de `api/ai/`.
Le plan initial est toujours calculé avec les prédictions ; les durées
réalisées restent dans l'exécution Mesa, hors des requêtes du solveur.
