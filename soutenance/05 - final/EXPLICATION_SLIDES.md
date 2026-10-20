# Explication des slides — Soutenance finale

Ce document décrit les slides de contenu du deck `Soutenance_finale.tex`.
Les rappels « Où nous en sommes » s'intercalent après chaque partie ; ils ne
sont pas numérotés. Les annexes sont après la slide de remerciements.

## 1. Titre

Annonce le sujet : optimiser ensemble le bloc, les lits et l'ambulatoire.
Le sous-titre situe l'angle : du planning contraint à la décision explicable.
Auteur : IA & Santé — Groupe 2 ; soutenance 2026.

## 2. Le fil rouge

Donne la structure en cinq temps : contextualiser, problématiser, modéliser,
analyser, montrer l'application. Overlay : l'objectif apparaît ensuite —
décider plus tôt, avec des dates justifiées, sans décider à la place du
praticien.

## 3. Le bloc opératoire, une ressource rare qui ne se stocke pas

Trois chiffres : 64,4 % de chirurgie ambulatoire en 2023, 70 % visés pour
2022, 80 % de cap affiché. Le bloc « Enjeux » ajoute la cible ANAP de 85 %
d'occupation des salles et les 90 % d'établissements qui font tourner
l'ambulatoire dans un bloc commun.

## 4. Du flux poussé au flux tiré

Deux organisations. Flux poussé : le chirurgien choisit une date, le bloc et
les lits s'adaptent. Overlay : le diagramme est remplacé par le flux tiré —
les contraintes calculent des dates A/B, le chirurgien choisit. Message : le
planning propose, le praticien arbitre ; un lit engage plusieurs jours.

## 5. Ce que fait l'application, et ce qu'elle ne fait pas

Montre le parcours : saisie de la demande, prédiction, deux dates,
confirmation. La zone de droite contient pour l'instant une image grise de
remplacement, au même format que la maquette. Overlay : les étapes 3–4 puis
la règle de non-substitution — l'outil rend les conséquences visibles, il ne
programme pas seul.

## 6. Du terrain au problème

Pose l'instance : 582 patients, 280 vacations sur 40 jours, trois ressources,
quatre aléas principaux. Overlay : `280^582` affectations, puis le problème
NP-difficile. Message : les compatibilités réduisent l'espace sans le rendre
traitable ; dix méthodes sont comparées avec le même budget de temps.

## 7. Les contraintes du terrain

Trois contraintes d'exécution : gel du passé, urgences dans leur fenêtre
clinique, moindre perturbation. À droite, le cadre CE/RGPD : qualification
MDR, minimisation, audit. Overlay : le gel, la traçabilité et l'explicabilité
pèsent sur le voisinage, le score et l'interface.

## 8. Le modèle : affecter chaque patient à une vacation

Formalise l'affectation binaire `x_i,v`, avec une vacation par patient.
Contraintes dures : capacité de vacation, capacité de lits, fenêtre des
urgences. Objectif pondéré : dépassement de vacation (5), dépassement de lits
(3), écart-type de vacation (0,05). Overlay : les contraintes et la
vérification `violations(solution) = (0, 0)` apparaissent ; on maximise la
fitness.

## 9. Pipeline ML : trois cibles, aucune fuite

Montre le pipeline : 14 434 cas, 30 colonnes, 73 exclusions, split temporel
2019–2021 → 2022, trois cibles. Les pièges sont traités explicitement :
valeurs manquantes, heures nulles, catégories rares, aucune fuite. Overlay :
les sorties et la propagation de l'incertitude dans les scénarios.

## 10. Trois métaheuristiques

NP-difficile : on cherche une bonne solution en temps borné. Recuit =
explorer et accepter de remonter ; Tabou = intensifier avec mémoire ;
génétique = croiser une population. Overlay : les hybrides enchaînent
exploration globale et intensification locale.

## 11. Hybrides : exploration globale, intensification locale

Quatre hybrides : Tabou×Recuit, Génétique×Tabou, Génétique×Recuit,
Fourmis×Tabou. Principe : une méthode globale explore, une méthode locale
intensifie. Overlay : Génétique×Tabou divise l'écart du génétique par ~10^4 ;
Fourmis×Tabou divise l'écart ACO par ~1,7.

## 12. Validation exacte, puis changement d'échelle

Valide d'abord sur une petite instance : 7 patients, 4 vacations, 16 384
combinaisons ; les 10 méthodes atteignent l'optimum sur 20 graines. Puis
change d'échelle avec la convergence à 300 patients. Les deux graphiques
occupent maintenant une hauteur nettement plus grande. Overlay : un planning
optimal pour les durées prévues devient inadapté après un aléa.

## 13. Aléas : les quatre cas principaux, pas les seuls

Quatre aléas principaux : urgence, annulation, indisponibilité de lits,
retard bloc. Ils restent visibles sur les deux overlays. La stat HAS 2026
rappelle qu'environ 10 % des interventions programmées sont annulées, la
plupart reprogrammées. Overlay : les cartes « Statique » et « Dynamique »
s'ajoutent sous la liste.

## 14. Dynamique / proactif : préparer des dates de repli

Quatre profils de repli : nominal, robuste avec marge, sécurité lits, Date B.
« Robuste avec marge » = 15 % de capacité laissée libre sur le bloc et les
lits pour absorber un aléa sans déplacer les patients. Le tableau montre trois
patients avec Date A, Date B et arbitrage. Overlay : le chirurgien voit la
date, l'occupation du bloc et des lits, et la raison de l'écart.

## 15. Dynamique / réactif : replanifier sans tout déplacer

Trois garde-fous : gel du passé, urgences, moindre perturbation. Le score est
écrit sur deux lignes : fitness, puis pénalité de déplacements et de
changements de jour. Le schéma SMA montre trois agents, un tableau noir et un
coordinateur. Overlay : cycles courts, versionnement de la meilleure solution,
migration si stagnation.

## 16. Classement à budget de temps égal

Classement sur 300 patients, 80 vacations, 20 graines et 3 s par méthode.
Recuit simulé et Tabou×Recuit dominent ; génétique et ACO décrochent. Le
boxplot est agrandi. Overlay : les méthodes locales tiennent le haut, les
hybrides Génétique×Tabou et Fourmis×Tabou réduisent l'écart ; l'écart est
mesuré à la meilleure solution observée, pas à un optimum prouvé.

## 17. ML : durée, séjour, ambulatoire

Table : 42 lits → médianes 246, modèle 251, réel 260 ; 10 lits → 111, 108,
115. Métriques : MAE séjour 1,11 → 0,44 ; F1 ambulatoire 0,922 ; intervalle
±1,02 jour. Overlay : à 42 lits, +5 vs les médianes mais −9 vs le réel ; à
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

## 20. Architecture : tout tient sur le serveur de l'établissement

Version simple : navigateur → application web → modules IA. Le navigateur ne
parle qu'à l'application ; l'application garde les droits et les données. Les
modèles et le solveur se branchent derrière elle, sans changer l'interface.
L'architecture détaillée (front, API, base) est en annexe.

## 21. Parcours 1/3 : le planning se construit

Montre les quatre étapes : demande, prédiction, dates A/B, confirmation. Le
calcul contraint entre dans le parcours clinique, pas dans un tableur séparé.
Parcours fonctionnel, pas une capture live.

## 22. Parcours 2/3 : le bloc bouge

Tableau des aléas : salle fermée 10h–12h, patient à déplacer, chirurgien
absent. Pour chacun : ce que fait l'outil et ce que voit l'équipe. Une ligne
rappelle la correspondance avec les quatre aléas principaux. Overlay : le
passé est gelé ; une proposition invalide est rejetée et l'ancien plan reste
actif.

## 23. Parcours 3/3 : l'urgence arrive

Timeline 08h–17h : fenêtre clinique de l'urgence, puis créneau retenu dans
cette fenêtre. Les deux libellés sont attachés à leur segment. L'outil insère
l'urgence, décale le minimum de patients futurs, recalcule et propose.
Overlay : il ne décide pas seul ; le praticien valide le décalage et son
motif.

## 24. Déploiement : sur le serveur de l'établissement

Trois composants : application web PC/tablette/téléphone,
SvelteKit/FastAPI/PostgreSQL, conteneurs rootless + Ansible. Tout reste chez
l'établissement. Overlay : hébergement de données de santé, audit,
sauvegardes, droits par rôle. Ouverture : qualification CE et RGPD.

## 25. Conformité : CE, RGPD et non-substitution

Deux blocs : CE/MDR (qualification au titre du règlement (UE) 2017/745,
marquage CE, dossier technique, gestion des risques, matériovigilance) et
RGPD (minimisation, pseudonymisation, hébergement de données de santé, base
légale, droits des personnes, journal d'audit). La mention « À compléter » a
été retirée. Overlay : le praticien confirme chaque programme ; CE et RGPD
restent à instruire.

## 26. KYST : ce qui marche, ce qui reste à brancher

Trois colonnes : ce qui est en ligne (demande, dates A/B, réservation,
tableau de bord, comptes), ce qui reste à brancher (modèles ML, solveur
métaheuristique, coordinateur `hospital_sim`), et la suite (vacations
hebdomadaires, lissage week-ends et vacances, audit, CE/RGPD, tests E2E).
Message : l'interface ne change pas, les modèles et le solveur se branchent
derrière les mêmes contrats.

## 27. Références

Deux colonnes : HAS IQSS 2026, HAS Flash Sécurité Patient 2026, HAS 2012,
ANAP, MDR 2017/745 et RGPD ; puis les revues et travaux sur la planification
de bloc et le predict-then-optimize.

## 28. Remerciements

Clôture : merci de votre attention, questions. Peu de texte : la slide laisse
la place aux échanges.

## Rappels « Où nous en sommes »

Une frame réutilisée en cinq overlays, sans numéro. Elle affiche seulement la
barre de progression à cinq étapes, avec la partie courante en couleur. Elle
apparaît après chaque partie.

## Annexes

1. Architecture détaillée.
2. Variables, contraintes et objectif.
3. Les dix méthodes.
4. Benchmark 300 patients / 80 vacations.
5. Échelle réelle 582 patients / 280 vacations.
6. Quatre aléas et quatre profils de repli.
7. Adaptation réactive et arbitrage.
8. Simulations dynamiques.
9. Données EDA et nettoyage.
10. KYST : sécurité et confidentialité.
11. Chiffres et sources.
