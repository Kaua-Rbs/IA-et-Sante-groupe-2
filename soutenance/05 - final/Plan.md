## Contextualiser: (3 slides / 3 min)

- enjeux (économiques, réglementaire, santé publique --> concept mobilisateur)
- intérêt de la méthode (flux poussé/flux tiré)
- que fait l'application concretement (aide à la planification, ne substitue pas le praticien)

## Problématique: (2 slides / 2 min)

- transition entre le contexte et la modélisation scientifique / notre approche globale (problème NP difficile)
- contraintes d'implémentation + CE/RGPD
	- Gel du passé : tout acte antérieur au jour courant est sanctuarisé.
	- Insertion prioritaire des urgences dans leur fenêtre clinique.
	– Moindre perturbation : on minimise les déplacements de patients futurs.
	- RGPD/CE

## Modélisation / approche: (5-10 slides / 5-10min)

- Fonction objectif à minimiser (insister sur les 3 termes) (donner les notations)
- Pipeline ML (données imparfaites / réelles à traiter)
- 3 métaheuristiques (presentation Générale + hybridation)
- approche statique complémentée par une approche dynamique (couplage SMA)
- approche dynamique: gestion des aléas (choix toujours laisse au praticien)

## Analyse des résultats: (3 slides / 3min)
- benchmarks:
	- métaheuristiques + hybridation (convergence, fitness)
	- ML
	- SMA


## Présentation de l'application (7 slides / 7min)

- Overview (interface conviviale, architecture (serveur existant de l'hopital, solution simple et sécurisée))
- Tests en direct (3 scenarios / 3min)
	- planning déjà établi, rajout d'un patient
	- aléas: fermeture de salle, déplacement d'un patient, chirurgien en arrêt de travail...
	- prise de personnes en urgence
- Déploiement (et vous aurez ça chez vous)
	- technologies standards, connues
	- application web pour les pc, application mobile possible
- Validation du cahier des charges (RGPD, non-substitution du praticien)