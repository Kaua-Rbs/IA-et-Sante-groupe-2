# Entretien médical — urgences, organisation et modélisation du planning

Date de préparation : 22 septembre 2026. Statut : questions et hypothèses de travail à valider, aucune règle clinique arrêtée.

Objectif : préciser le fonctionnement réel avant de développer les deux modèles prédictifs (séjour et occupation de salle), les métaheuristiques et une éventuelle simulation multi-agents. Le premier terrain est un établissement français ; les responsabilités et règles devront pouvoir être adaptées à d'autres établissements et systèmes de santé.

Documents à parcourir ensemble : [parcours du patient](patient-workflow.md), [dictionnaire des données](../data_dictionary_donees_bloc.md), [présentation du projet](../README.md).

## 1. Questions prioritaires pour commencer l'entretien

1. Comment anticipez-vous aujourd'hui les urgences et les admissions non programmées ? Quelles prévisions utilisez-vous réellement pour réserver du temps de bloc et des lits ?
2. Qui propose, valide et modifie le programme ? Qui arbitre un conflit entre urgence, bloc, anesthésie et disponibilité des lits, notamment la nuit et le week-end ?
3. Quelles contraintes sont incontournables et quelles modifications restent possibles une fois le programme communiqué ?
4. Que représentent exactement les durées et catégories de notre base, et quelles informations sont connues au moment où l'on programme le patient ?
5. Quel premier cas d'usage serait utile : proposer une date, préparer une semaine, ou réparer le programme du jour ? Quel délai de réponse serait acceptable ?

## 2. Urgences : préciser ce qui est prévisible

### Point de départ

L'hypothèse à discuter est qu'une partie de la charge non programmée peut être anticipée statistiquement, tout en gardant une incertitude sur chaque arrivée. Il faut distinguer la prévision du volume de passages aux urgences, celle des hospitalisations et celle des interventions chirurgicales urgentes.

Un précédent français est le besoin journalier minimal en lits (BJML), décrit dans la [circulaire DGOS du 7 novembre 2019](https://www.legifrance.gouv.fr/circulaire/id/44886), à partir des résumés de passage aux urgences. Cette référence documente une démarche d'anticipation de l'aval des urgences ; elle ne démontre ni son utilisation dans notre établissement ni une prévision de sa charge opératoire urgente.

### Questions au médecin

- Que recouvre « urgence » ici : passage par les urgences, admission directe, transfert, complication d'un patient hospitalisé, reprise chirurgicale, intervention ajoutée au programme ? Lesquels entrent dans le périmètre ?
- Distinguez-vous des urgences immédiates, différables et des interventions non programmées sans urgence immédiate ? Quelle classification locale utilisez-vous ?
- Qui attribue et réévalue la priorité ? Quel délai maximal est fixé et à partir de quel événement est-il mesuré : arrivée, diagnostic, décision opératoire ? Ne pas inventer ces délais dans le logiciel.
- Disposez-vous de prévisions par jour, heure, spécialité et type de lit ? Sur quel historique reposent-elles, à quelle fréquence sont-elles actualisées, et avec quelle incertitude ?
- Quelle part des arrivées non programmées conduit au bloc ? Quelle part consomme des lits partagés avec les patients programmés sans passer au bloc ?
- Comment les nuits, week-ends, vacances, saisons et épisodes inhabituels modifient-ils cette charge ? Les pics de demande et les absences de personnel peuvent-ils coïncider ?
- Réservez-vous une salle, une équipe, des créneaux ou une marge dans chaque vacation ? Comment dimensionnez-vous cette réserve ? Quand peut-elle être réaffectée si elle reste inutilisée ?
- Quand la réserve est dépassée, quelles actions sont possibles, dans quel ordre, et qui les autorise : réorganisation, report, ouverture supplémentaire, transfert ?

### Conséquences possibles pour le modèle — à confirmer

- Séparer les patients urgents déjà connus, qui entrent dans l'état courant, des arrivées futures incertaines, qui alimentent des scénarios.
- Prévoir une composante distincte de demande non programmée. Les deux modèles individuels de durée ne prédisent pas le nombre ni l'heure des futures arrivées ; cette composante pourrait commencer par des profils historiques, sans imposer un troisième modèle ML.
- Représenter chaque arrivée simulée par une heure, une spécialité, une priorité et un délai validés, un besoin éventuel de bloc, une durée et un parcours d'hébergement. Préserver les dépendances plausibles entre ces besoins.
- Commencer par des journées historiques comparables ou des scénarios validés avec le métier. Une loi d'arrivée, par exemple de Poisson, serait une hypothèse à tester, pas une propriété acquise des urgences.
- Distinguer la réserve de capacité, la demande prévue et la charge déjà réalisée pour éviter de compter deux fois les mêmes besoins. Réévaluer la demande restante après chaque arrivée.
- Tester séparément les fluctuations habituelles et quelques situations exceptionnelles. Préciser avec le médecin si ces dernières relèvent du prototype.

**Données à demander :** statut programmé/non programmé, origine, horodatages d'arrivée et de décision, priorité et ses changements, spécialité, passage au bloc, parcours de lits, reports, transferts et refus faute de capacité. Ces informations ne sont pas explicitement décrites dans le classeur actuel. Les seuls actes réalisés ne suffisent pas à reconstruire toute la demande ; ne pas déduire une urgence uniquement d'un horaire ou d'un diagnostic.

## 3. Organisation française et responsabilités abstraites

### Reconstituer l'organisation locale

Les termes « room manager » et « ward manager » utilisés dans la discussion technique désignent des fonctions possibles, pas des postes français établis ni une chaîne hiérarchique validée.

Demander le type d'établissement (public, privé, ESPIC), l'organigramme, la charte du bloc et les règles de programmation. Distinguer l'autorité médicale, l'encadrement soignant, la coordination opérationnelle et les arbitrages institutionnels. Leurs relations ne doivent pas être réduites d'emblée à une seule pyramide.

L'[ANAP cite notamment le conseil de bloc, le binôme de pilotage, la cellule de programmation et la charte de bloc](https://anap.my.site.com/s/article/blocs-operatoires-plateforme-guides) comme éléments d'organisation. Leur existence, leur composition et leurs pouvoirs doivent être confirmés sur le terrain.

| Responsabilité à représenter | Interlocuteurs ou instances possibles à identifier localement | Question à trancher |
|---|---|---|
| Indication et priorité cliniques | Chirurgien, médecin responsable, urgentiste selon le parcours | Qui fixe le besoin et le délai acceptable ? |
| Conditions anesthésiques | Médecin anesthésiste-réanimateur, équipe d'anesthésie | Qui confirme les conditions nécessaires et la disponibilité ? |
| Programmation et régulation du bloc | Cellule de programmation, cadre de bloc, coordonnateur ou régulateur | Qui propose, valide et ajuste le programme en cours de journée ? |
| Capacité d'hébergement | Cadre d'unité, gestionnaire de lits ou cellule de gestion des lits, responsable médical | Qui confirme qu'un lit est réellement utilisable et compatible ? |
| Règles et arbitrage des moyens | Conseil de bloc, responsables de service/pôle, encadrement, direction selon l'établissement | Qui fixe les règles et arbitre un conflit dépassant la régulation quotidienne ? |

Questions transversales : qui remplace ces acteurs en garde ou en astreinte ? Quelles décisions exigent plusieurs accords ? Qui peut refuser une proposition ? Qui informe le patient et les équipes ? Comment traite-t-on une absence de réponse ?

### Piste de conception portable

Définir des interfaces ou classes abstraites correspondant à des responsabilités, par exemple `ClinicalPrioritization`, `OperatingRoomCoordination`, `BedCapacityManagement` et `ScheduleApproval`. Les noms sont des propositions techniques, pas un organigramme cible.

Configurer ensuite, pour chaque établissement, les acteurs qui portent ces responsabilités, leur périmètre, leurs droits de proposition/validation, les accords nécessaires et les voies d'escalade. Un acteur peut cumuler plusieurs rôles ; un rôle peut être partagé ou changer selon la garde. Séparer les relations hiérarchiques des droits de décision et des échanges fonctionnels.

Une salle ou un lit peut rester une ressource sans devenir un agent autonome. Réserver les agents aux comportements ou décisions dont la simulation apporte quelque chose. Un agent logiciel ne reçoit pas automatiquement l'autorité du professionnel qu'il représente.

**Résultat attendu :** une matrice locale « décision → propose → valide → doit être consulté → est informé → arbitre en cas de conflit », avant de choisir une architecture multi-agents détaillée.

## 4. Autres sujets à clarifier dès maintenant

| Sujet | Questions à poser | Conséquence pour le projet |
|---|---|---|
| Périmètre du premier prototype | Quel site, quelles spécialités, quelles salles et quels lits ? Planification à plusieurs semaines ou ajustement du jour ? Admission et intervention sont-elles décidées ensemble ? | Fixer une première instance réaliste et un horizon de calcul. |
| Durée de salle | Notre cible va de l'entrée à la sortie de salle. Faut-il prévoir séparément nettoyage, remise en état, installation et contraintes d'enchaînement ? Comment comprendre les heures nulles et les passages de minuit ? | Ne pas confondre durée chirurgicale, occupation de salle et intervalle nécessaire entre deux patients. |
| Durée de séjour | La cible actuelle est un nombre inclusif de jours entre admission et sortie. Est-ce la convention utile ? Comment distinguer séjour préopératoire, postopératoire, ambulatoire et nuitées ? | Relier correctement prédiction, date d'admission et occupation des capacités. Un séjour d'un jour ne suffit pas à identifier l'ambulatoire. |
| Sortie et disponibilité d'un lit | Qu'est-ce qui retarde une sortie : état clinique, transport, aval, heure de visite, nettoyage ? Dispose-t-on d'une sortie prévue et d'une heure de remise à disposition ? | Une date administrative de sortie ne fournit pas une heure de libération du lit. |
| Patients déjà présents | Comment estimez-vous la durée restante lorsqu'un patient dépasse son séjour prévu ? | Une prédiction initiale de séjour total ne suffit pas à actualiser le besoin résiduel. |
| Ressources réellement disponibles | Quels lits sont ouverts et dotés en personnel ? Quelles compétences, équipes, matériels et compatibilités de salle sont indispensables ? Quel rôle pour la SSPI et les soins critiques ? | Distinguer capacité physique et capacité utilisable ; identifier les vrais goulots d'étranglement. |
| Informations connues à la programmation | Diagnostic, CCAM prévus, actes associés, anesthésie et intervenants sont-ils connus à cet instant ou renseignés après le séjour ? Que signifie `Praticien` ? | Valider chaque variable prédictive et éviter l'utilisation d'informations futures. |
| Unité d'observation | Une ligne décrit-elle un séjour, un acte ou une intervention principale ? Où sont les reprises et interventions multiples ? | Éviter doublons de lits et sous-comptage de la charge du bloc. |
| Reprogrammation acceptable | Quels patients et créneaux sont figés ? Quels préavis, préparations, contraintes de transport ou engagements limitent les déplacements ? Qui autorise un report ? | Définir les mouvements admissibles et le coût de perturbation du planning. |
| Objectifs et incertitude | Comment hiérarchiser délai clinique, attente, annulations, dépassements, stabilité du programme et occupation des lits ? Quelle marge est jugée utile et comment la valider ? | Séparer contraintes impératives et préférences ; ne pas optimiser uniquement le taux de remplissage. |
| Réactivité et état courant | Quel événement doit déclencher un recalcul ? Quel temps pour une première proposition ? À quelle fréquence les outils du bloc et des lits sont-ils actualisés ? | Définir le délai de bout en bout, y compris la disponibilité des données et la validation humaine. |
| Validation du prototype | À quelle pratique comparer les résultats ? Quels indicateurs et quelles situations rendraient une proposition inacceptable ? Qui relit les scénarios ? | Fixer les critères d'évaluation avant de comparer les algorithmes. |

Le champ nommé « SSPI avant intervention » dans la base désigne un SAS préopératoire. Il ne décrit pas à lui seul le passage en SSPI postopératoire : valider les deux parcours séparément avec le [diagramme existant](patient-workflow.md).

## 5. Trois situations à faire raconter au médecin

Pour chacune, demander les informations disponibles au départ, la chronologie réelle, les personnes intervenues, les options rejetées et la décision finale. Utiliser des exemples anonymisés, sans recopier de données identifiantes dans ce document.

1. Une urgence arrive alors que le programme est plein : comment trouve-t-on simultanément salle, équipe et capacité d'aval ?
2. Une intervention dépasse sa durée prévue et un lit attendu n'est pas libéré : qui est averti, quelles opérations restent possibles et qui arbitre ?
3. Un patient programmé annule alors qu'une capacité avait été réservée aux urgences : peut-on utiliser le créneau, pour qui et jusqu'à quelle heure ?

Ces récits serviront à construire des scénarios de référence pour une simulation, éventuellement avec Mesa, et à vérifier qu'une proposition calculée respecte les décisions réelles. Le choix de la bibliothèque reste ouvert.

## 6. Documents, interlocuteurs et décisions à obtenir

- Charte du bloc, organigramme fonctionnel, règles locales d'urgence et de reprogrammation.
- Calendriers des vacations, disponibilités des équipes et capacités ouvertes par type de lit ; sources des événements et fréquence d'actualisation.
- Historique de demande non programmée et prévisions déjà utilisées, en complément des interventions réalisées.
- Interlocuteurs à consulter ensuite : cadre de bloc, anesthésiste, gestionnaire de lits/cadre d'unité, urgentiste, responsable des données ou DIM selon les questions. Le médecin peut orienter vers les détenteurs de chaque information.
- Un périmètre initial, une liste de contraintes impératives, les droits de décision, un délai de réponse souhaité et des critères de réussite validés.

### Compte rendu à compléter pendant l'entretien

Date et fonctions des participants : …

| Point | Réponse / décision | Confirmé ou hypothèse ? | Document ou interlocuteur à consulter | Prochaine action |
|---|---|---|---|---|
| Prévision et réserve pour les urgences | À compléter | À compléter | À compléter | À compléter |
| Priorités et délais cliniques | À compléter | À compléter | À compléter | À compléter |
| Responsabilités et arbitrages | À compléter | À compléter | À compléter | À compléter |
| Définition des durées et disponibilité des données | À compléter | À compléter | À compléter | À compléter |
| Périmètre et validation du prototype | À compléter | À compléter | À compléter | À compléter |

Les références externes donnent des points de départ pour l'entretien, pas la preuve du fonctionnement de l'établissement. Les propositions de modélisation ci-dessus restent à confronter aux réponses et aux données disponibles.
