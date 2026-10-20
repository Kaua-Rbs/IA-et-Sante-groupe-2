# Dictionnaire des données — `donees bloc anonyme pour centrale 2026.xlsx`

Ce document décrit les 30 colonnes du classeur fourni par l'hôpital (14 649 lignes). Les définitions combinent les informations du détenteur des données et des vérifications faites directement sur le classeur. Les éléments marqués **Incertain** demandent encore un contexte local avant d'être exploités.

Le classeur n'est pas versionné : il se place dans `resources/` (voir le [README](../README.md#confidentialité)). Il est nettoyé et préparé par les [notebooks](../notebooks/README.md) ; les modèles qui en sont issus sont décrits dans [Modèles de prédiction](modeles-prediction.md), et le parcours patient correspondant dans [le parcours type](parcours-patient.md).

Certains en-têtes ont des problèmes d'encodage, comme `EntrÈe`, `AnnÈe`, `N∞`, `DurÈe` et `Sèjour`, pour `Entrée`, `Année`, `N°`, `Durée` et `Séjour`.

| # | Colonne d'origine | Signification probable | Format / unité | Fiabilité et remarques |
|---:|---|---|---|---|
| 1 | `No Cas` | Numéro de cas | Identifiant entier | Confirmé. Chaque valeur est unique : 14 649 numéros pour 14 649 lignes. À traiter comme un identifiant, pas comme une mesure. |
| 2 | `Date EntrÈe` | Date d'entrée du patient à l'hôpital | Date | Confirmé. |
| 3 | `Date Sortie` | Date de sortie du patient | Date | Confirmé. |
| 4 | `Date Naissance` | Date de naissance du patient | Date | Confirmé. Donnée personnelle sensible, même dans un jeu pseudonymisé ; à utiliser surtout pour calculer l'âge. |
| 5 | `Sexe` | Sexe enregistré : `1` homme, `2` femme | Catégorie codée | Confirmé. |
| 6 | `CIM Diag Pr.` | Diagnostic principal en CIM-10 (*Classification internationale des maladies, 10ᵉ révision*) | Code CIM-10 | Confirmé. |
| 7 | `Cim Assoc 1` | Premier diagnostic associé, en CIM-10 | Code CIM-10 | Confirmé. L'ordre des positions 1 à 5 n'est pas documenté, mais n'est pas nécessaire au projet. |
| 8 | `Cim Assoc 2` | Deuxième diagnostic associé | Code CIM-10 | Confirmé. |
| 9 | `Cim Assoc 3` | Troisième diagnostic associé | Code CIM-10 | Confirmé. |
| 10 | `Cim Assoc 4` | Quatrième diagnostic associé | Code CIM-10 | Confirmé. |
| 11 | `Cim Assoc 5` | Cinquième diagnostic associé | Code CIM-10 | Confirmé. |
| 12 | `CCAM 1` | Premier acte en CCAM (*Classification commune des actes médicaux*) | Code CCAM | Confirmé. L'ordre des positions 1 à 4 n'est pas documenté, mais n'est pas nécessaire au projet. |
| 13 | `CCAM 2` | Deuxième acte CCAM | Code CCAM | Confirmé. |
| 14 | `CCAM 3` | Troisième acte CCAM | Code CCAM | Confirmé. |
| 15 | `CCAM 4` | Quatrième acte CCAM | Code CCAM | Confirmé. |
| 16 | `GHM Code` | Code GHM (*Groupe homogène de malades*), classification médico-économique du séjour | Code alphanumérique | Confirmé. |
| 17 | `GHS N∞` | Numéro GHS (*Groupe homogène de séjours*), tarif associé au séjour | Code entier | Confirmé. `∞` est une erreur d'encodage pour `°`. À stocker comme catégorie, pas comme quantité. |
| 18 | `AnnÈe` | Année d'entrée à l'hôpital | Année sur quatre chiffres | Confirmé : identique à l'année de `Date EntrÈe` sur les 14 649 lignes. |
| 19 | `ID Patient` | Identifiant pseudonymisé du patient, qui relie ses différents séjours | Identifiant entier | Confirmé. 11 108 identifiants distincts ; 2 546 patients ont plusieurs séjours, jusqu'à 9. Confidentiel, à traiter comme une catégorie. |
| 20 | `Date Inter` | Date de l'intervention chirurgicale | Date | Le sens est confirmé ; la date est toujours comprise entre l'entrée et la sortie. **Incertain** : s'agit-il toujours de la première intervention quand un séjour en compte plusieurs ? |
| 21 | `Praticien` | Initiales d'un praticien | Code texte court | Confirmé. Le rôle exact n'est pas précisé et peut varier. |
| 22 | `Nom Chir` | Nom ou identifiant du chirurgien | Texte | Vérifié (colonne V du classeur). Donnée relative au personnel, même si les patients sont pseudonymisés. |
| 23 | `Heure entrée SSPI avant intervention (…)` | Heure d'entrée dans le SAS de pré-anesthésie avant l'intervention. Selon l'en-tête, une heure égale à l'entrée en salle signifie qu'il n'y a pas eu de passage par ce SAS | Heure | Confirmé. La SSPI désigne habituellement la salle de réveil après l'intervention ; ici, le champ décrit un SAS préopératoire. **Incertain** : une valeur nulle signifie-t-elle minuit, une donnée manquante ou l'absence d'événement ? |
| 24 | `Heure d'entrée en salle d'opération (calimed)` | Heure d'entrée en salle, issue du logiciel Calimed | Heure | Confirmé. |
| 25 | `Heure Incision ` | Heure de l'incision | Heure | Confirmé. L'en-tête finit par une espace. Une valeur nulle peut signifier une donnée non saisie plutôt que minuit : incertain. |
| 26 | `Heure de sortie de salle d'opération (calimed)` | Heure de sortie de salle, issue de Calimed | Heure | Confirmé. |
| 27 | `Anesth Type` | Type principal d'anesthésie | Catégorie texte | Confirmé. |
| 28 | `Anesth Loco_reg` | Anesthésie locorégionale ou bloc nerveux, en complément ou à la place du type principal | Catégorie texte | Confirmé. |
| 29 | `DurÈe Sèjour en jour (1 pour ambu)` | Durée du séjour en jours ; un séjour ambulatoire vaut `1` | Jours | Confirmé. Suit une convention administrative plutôt qu'une durée écoulée exacte. |
| 30 | `Interv Type` | Catégorie lisible d'intervention | Catégorie texte | Confirmé. |

L'en-tête complet de la colonne 23 est : *Heure entrée SSPI avant intervention (cela correspond à un SAS de pré-anesthésie). Si cette heure est la même que l'heure d'entrée en salle d'opération, cela signifie qu'il n'y as pas eu de passage en SSPI pré op*.

## Relations entre colonnes

- `No Cas` identifie chaque ligne ; `ID Patient` relie plusieurs séjours d'un même patient.
- `Date EntrÈe`, `Date Sortie` et `DurÈe Sèjour en jour (1 pour ambu)` décrivent le séjour. La durée suit une convention inclusive : sortie − entrée + 1 jour. C'est la cible du [modèle de séjour](modeles-prediction.md).
- `CIM Diag Pr.` et `Cim Assoc 1` à `5` décrivent les diagnostics ; `CCAM 1` à `4` les actes réalisés ; `GHM Code` et `GHS N∞` le classement médico-économique du séjour.
- Les horodatages du bloc permettent d'estimer l'attente préopératoire, l'occupation de la salle (cible du [modèle de temps de salle](modeles-prediction.md), de l'entrée à la sortie) et le délai entre l'entrée et l'incision, une fois les conventions sur les valeurs nulles clarifiées.
- `Interv Type` est un regroupement local pratique ; les codes CCAM gardent le détail normalisé des actes.

## Incertitudes restantes

1. `Date Inter` désigne-t-elle toujours la première intervention, l'intervention principale, ou simplement celle de la ligne ?
2. Quel rôle médical représentent les initiales de `Praticien` ?
3. Une heure nulle signifie-t-elle minuit, une donnée manquante ou l'absence d'événement ?
4. Une intervention peut-elle passer minuit, et toutes les heures se rapportent-elles à `Date Inter` ?
