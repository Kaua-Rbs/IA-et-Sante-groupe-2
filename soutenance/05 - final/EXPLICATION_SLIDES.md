# Explication des slides — Soutenance finale

Ce document décrit chaque frame du deck `Soutenance_finale.tex`. Les numéros
sont ceux des frames ; le PDF contient 52 pages parce que certaines frames ont
plusieurs étapes d'overlay.

## 1. Titre

Annonce le sujet : optimiser ensemble le bloc, les lits et l'ambulatoire.
Le sous-titre situe l'angle : du planning contraint à la décision explicable.
Auteur : IA & Santé — Groupe 2 ; soutenance 2026.

## 2. Le fil rouge en cinq temps

Donne la structure en cinq temps : contextualiser, problématiser, modéliser,
analyser, montrer l'application. Les photos rappellent les trois ressources.
Overlay : l'objectif apparaît ensuite — décider plus tôt, avec des dates
justifiées, sans retirer la décision au praticien.

## 3. Le bloc opératoire, une ressource rare et non stockable

Trois chiffres HAS : 64,4 % de chirurgie ambulatoire en 2023, 70 % visés pour
2022, 80 % de cap affiché. La photo montre le bloc comme un lieu de ressources
couplées. Overlay : les enjeux — coût des ressources mobilisées sans patient,
traçabilité ARS, bénéfices de l'ambulatoire.

## 4. Du flux poussé au flux tiré

Deux organisations opposées. Flux poussé : le chirurgien choisit une date, le
bloc et les lits s'adaptent. Overlay : le diagramme est remplacé par le flux
tiré — les contraintes calculent des dates A/B, le chirurgien choisit. Message :
le planning propose, le praticien arbitre ; un lit engage plusieurs jours.

## 5. Ce que fait l'application, et ce qu'elle ne fait pas

Montre le parcours : saisie de la demande, prédiction, deux dates, confirmation.
La maquette illustre Mme D. : 95 min, 2 jours, date A le 12 mars, date B le
26 mars. Overlay : les étapes 3–4 puis la règle de non-substitution — l'outil
rend les conséquences visibles, il ne programme pas seul.

## 6. Du terrain au problème scientifique

Pose l'instance : 582 patients, 280 vacations sur 40 jours, trois ressources,
quatre aléas. Overlay : `280^582` affectations, puis le nœud NP-difficile.
Message : les compatibilités réduisent l'espace sans le rendre traitable ; dix
méthodes sont comparées avec le même budget de temps.

## 7. Les contraintes qui rendent le problème réel

Trois contraintes d'exécution : gel du passé, urgences dans leur fenêtre
clinique, moindre perturbation. À droite, le cadre CE/RGPD : qualification MDR,
minimisation, audit. Overlay : le gel, la traçabilité et l'explicabilité pèsent
sur le voisinage, le score et l'interface.

## 8. Le modèle : une affectation, trois tensions

Formalise l'affectation binaire `x_i,v`, avec une vacation par patient.
Contraintes dures : capacité de vacation, capacité de lits, fenêtre des
urgences. Objectif pondéré : `Δ_vac` (5), `Δ_lits` (3), `σ_vac` (0,05).
Overlay : les contraintes et la vérification `violations(solution) = (0, 0)`
apparaissent ; on maximise la fitness.

## 9. Pipeline ML : trois cibles, aucune fuite

Montre le pipeline : 14 434 cas, 30 colonnes, 73 exclusions, split temporel
2019–2021 → 2022, trois cibles. Les pièges sont traités explicitement : valeurs
manquantes, heures nulles, catégories rares, aucune fuite. Overlay : les sorties
et la propagation de l'incertitude dans les scénarios.

## 10. Trois métaheuristiques, trois gestes

NP-difficile : on cherche une bonne solution en temps borné. Recuit = explorer
et accepter de remonter ; Tabou = intensifier avec mémoire ; génétique = croiser
une population. Overlay : les hybrides combinent ces trois gestes.

## 11. Hybrides : combiner exploration et intensification

Quatre hybrides : Tabou×Recuit, Génétique×Tabou, Génétique×Recuit,
Fourmis×Tabou. Principe : une méthode globale explore, une méthode locale
intensifie. Overlay : Génétique×Tabou divise l'écart du génétique par ~10^4 ;
Fourmis×Tabou divise l'écart ACO par ~1,7.

## 12. Validation exacte, puis changement d'échelle

Valide d'abord sur une instance jouet : 7 patients, 4 vacations, 16 384
combinaisons ; les 10 méthodes atteignent l'optimum sur 20 graines. Puis change
d'échelle avec la convergence à 300 patients. Overlay : un planning optimal pour
les durées prévues devient inadapté après un aléa.

## 13. Aléas : du planning statique à l'approche dynamique

Quatre aléas : urgence, annulation, indisponibilité de lits, retard bloc. Le
tableau donne description et impact. Overlay : le tableau est remplacé par la
distinction statique / dynamique. Statique = un plan nominal pour les durées
prévues. Dynamique = maintien du plan dans le temps via des dates de repli
proactives puis une replanification réactive. Message : l'application fait les
deux, elle part du statique et le maintient en dynamique.

## 14. Dynamique / proactif : préparer des dates de repli

Quatre profils de repli : nominal, robuste avec marge, sécurité lits, Date B.
« Robuste avec marge » = 15 % de capacité laissée libre sur le bloc et les lits
pour absorber un aléa sans déplacer les patients. Le tableau montre trois
patients avec Date A, Date B et arbitrage. Overlay : le chirurgien voit la
date, l'occupation du bloc et des lits, et la raison de l'écart.

## 15. Dynamique / réactif : replanifier sans tout déplacer

Trois garde-fous : gel du passé, urgences, moindre perturbation. Le score ajoute
une pénalité aux déplacements et aux changements de jour. Le schéma SMA montre
trois agents, un tableau noir et un coordinateur. Overlay : couplage par quanta,
versionnement de la meilleure solution, migration si stagnation.

## 16. Métaheuristiques : le classement à budget de temps égal

Classement sur 300 patients, 80 vacations, 20 graines et 3 s par méthode.
Recuit simulé et Tabou×Recuit dominent ; génétique et ACO décrochent. Overlay :
les méthodes locales tiennent le haut, les hybrides corrigent les écarts ;
l'écart est mesuré à la meilleure solution observée, pas à un optimum prouvé.

## 17. ML : durée, séjour, ambulatoire

Table : 42 lits → médianes 246, modèle 251, oracle 260 ; 10 lits → 111, 108,
115. Métriques : MAE séjour 1,11 → 0,44 ; F1 ambulatoire 0,922 ; intervalle
±1,02 jour. Overlay : à 42 lits, +5 vs les médianes mais −9 vs l'oracle ; à
10 lits, la capacité sature. Le gain dépend des ressources.

## 18. SMA : ce que la coordination coûte

Plan figé : 255 interventions terminées, 2 911 min de dépassement. Réactif :
251, 2 716 min. Overlay : −195 min de dépassement mais −4 interventions ; rang
moyen 5,05 à 300 patients, 5,85 à 582. La coordination a un coût, elle n'est
pas systématiquement gagnante.

## 19. KYST : le flux tiré jusqu'à la réservation

Présente `kyst.tech` (Keep Your Surgeries Timely), l'application web qui
applique le flux tiré en consultation, du planning statique à l'adaptation
dynamique. Trois gestes : saisir, obtenir deux dates justifiées, confirmer. Le
QR code ouvre l'application. Overlay : planning statique initial, puis
dynamique (dates de repli, replanification réactive), disponible sur PC et
mobile.

## 20. Architecture : un socle standard, hébergé sur place

Chaîne navigateur → front SvelteKit → API FastAPI → PostgreSQL, avec modules IA.
Le navigateur ne parle qu'au front ; l'API garde les droits et les données.
Sécurité : Argon2, cookies HttpOnly/Secure, TLS, conteneurs rootless, données
pseudonymisées. Hébergement sur place avec Podman et Ansible.

## 21. Parcours 1/3 : le planning se construit

Montre les quatre étapes : demande, prédiction, dates A/B, confirmation. Le
calcul contraint entre dans le parcours clinique, pas dans un tableur séparé.
C'est un parcours fonctionnel, pas une capture live.

## 22. Parcours 2/3 : le bloc bouge

Tableau des aléas : salle fermée 10h–12h, patient à déplacer, chirurgien absent.
Pour chacun : ce que fait l'outil et ce que voit l'équipe. Overlay : le passé est
gelé ; une proposition invalide est rejetée et l'ancien plan reste actif.

## 23. Parcours 3/3 : l'urgence arrive

Timeline 08h–17h : fenêtre clinique de l'urgence, puis créneau retenu dans cette
fenêtre. L'outil insère l'urgence, décale le minimum de patients futurs,
recalcule et propose. Overlay : il ne décide pas seul ; le praticien valide le
décalage et son motif.

## 24. Déploiement : sur le serveur de l'établissement

Trois briques : application web PC/tablette/téléphone, SvelteKit/FastAPI/
PostgreSQL, conteneurs rootless + Ansible. Tout reste chez l'établissement.
Overlay : hébergement de données de santé, audit, sauvegardes, droits par rôle.
Ouverture : qualification CE et RGPD.

## 25. Conformité : CE, RGPD et non-substitution

Deux blocs remplacent le long tableau. CE/MDR : qualification au titre du
règlement (UE) 2017/745, marquage CE, dossier technique, gestion des risques,
matériovigilance. RGPD : minimisation, pseudonymisation, hébergement de données
de santé (HDS), base légale, droits des personnes, journal d'audit. Une ligne
indique ce qui est couvert et ce qui reste à compléter. Overlay : le praticien
confirme chaque programme ; CE et RGPD restent à instruire.

## 26. Références

Liste les sources : HAS IQSS 2026 et HAS 2012, MDR 2017/745, RGPD 2016/679,
puis les revues et travaux sur la planification de bloc et le
predict-then-optimize. Sert de caution méthodologique.

## 27. Remerciements

Clôture : merci de votre attention, questions. La slide est volontairement
sobre pour laisser place aux échanges.
