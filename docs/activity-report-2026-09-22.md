# Bilan d'activité — 22 septembre 2026

**Statut lors de la rédaction, avant les commits :** modifications locales sur `feat/coordination-core`, non encore commitées ni poussées vers le dépôt distant.

**Dépôt du projet :** [Kaua-Rbs/IA-et-Sante-groupe-2](https://github.com/Kaua-Rbs/IA-et-Sante-groupe-2).

Périmètre personnel : analyse et préparation des données, architecture du futur système multi-agents et préparation de l'intégration backend.

## Travail réalisé

- Analyse de l'intérêt d'une approche multi-agents pour réagir aux perturbations du planning. Distinction entre simulation hospitalière, coordination des propositions et calcul des métaheuristiques.
- Préparation d'un [guide d'entretien avec un médecin](doctor-discussion-guide.md) : anticipation des urgences, réserves de capacité, responsabilités dans un établissement français, définitions des durées et données manquantes. Les rôles logiciels restent abstraits et adaptables à l'organisation locale.
- Revue des sept articles disponibles, de la soutenance intermédiaire et du rapport en cours. Identification de points à préciser : calcul de l'occupation des lits, granularité des vacations, origine des réserves d'urgence, interprétation de l'ambulatoire et évaluation conjointe des prédictions et des plannings. Les documents des branches de rapport ont été consultés, sans modification.
- Inspection de la structure du classeur de vacations : présence d'un planning hebdomadaire avec cellules fusionnées. L'importeur reste à développer.
- Clarification du périmètre entre équipes : modèles ML suivis directement avec l'équipe concernée ; validation des plannings partagée déjà convenue ; granularité et interface de reprogrammation encore à définir par l'équipe de modélisation. Aucun nouveau transfert de données n'est requis à ce stade.
- Implémentation du [socle de coordination](coordination-core.md) sur la branche `feat/coordination-core` : interfaces pour état, événements, prédicteurs, solveur et validateur ; coordination asynchrone ; versions de l'état ; rejet des résultats obsolètes ; validation et acceptation explicite des propositions ; gestion des délais et erreurs.

## Résultat vérifié

Une démonstration synthétique reproduit deux indisponibilités successives de salles pendant un calcul. La proposition devenue obsolète est rejetée ; une nouvelle proposition est validée puis acceptée explicitement. Les 14 tests automatisés passent, notamment sur l'isolation des données, les mises à jour concurrentes, la validation, les délais et l'arrêt du calcul.

Les notebooks de préparation et les jeux de données existaient avant cette session et n'ont pas été modifiés. Aucun modèle réel, métaheuristique, serveur backend ou adaptateur Mesa n'a été ajouté. Le socle est une infrastructure de coordination, pas encore un système multi-agents complet.

## Prochaines étapes

- Faire valider les hypothèses métier à l'aide du guide d'entretien.
- Normaliser le classeur de vacations après clarification des champs nécessaires au modèle.
- Brancher le solveur et le validateur communs lorsque leurs interfaces seront stabilisées.
- Étendre progressivement les événements simulés et mesurer le temps de réaction ainsi que les changements apportés au planning.
