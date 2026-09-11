# Data dictionary — `donees bloc anonyme pour centrale 2026.xlsx`

This document describes the 30 columns in the workbook. The definitions combine information supplied by the data owner with checks performed directly on the workbook. Items marked **Uncertain** still need local context before they should be used analytically.

Some headers contain character-encoding problems, such as `EntrÈe`, `AnnÈe`, `N∞`, `DurÈe`, and `Sèjour`. Their intended spellings are probably `Entrée`, `Année`, `N°`, `Durée`, and `Séjour`.

| # | Original column | Probable meaning | Format / unit | Confidence and notes |
|---:|---|---|---|---|
| 1 | `No Cas` | Case number. | Integer-like identifier | Confirmed. Every value is unique in this workbook: 14,649 case numbers for 14,649 rows. Treat it as an identifier rather than a numerical measurement. |
| 2 | `Date EntrÈe` | Date on which the patient entered the hospital. | Date | Confirmed. |
| 3 | `Date Sortie` | Date on which the patient left the hospital. | Date | Confirmed. |
| 4 | `Date Naissance` | Patient's date of birth. | Date | Confirmed. Sensitive personal data even in an otherwise anonymized dataset; use it mainly to derive age. |
| 5 | `Sexe` | Recorded patient sex: `1` means male and `2` means female. | Coded category (`1` or `2`) | Confirmed. |
| 6 | `CIM Diag Pr.` | Principal diagnosis coded using CIM-10 (*Classification internationale des maladies, 10e révision*). | Alphanumeric CIM-10 diagnosis code | Confirmed. |
| 7 | `Cim Assoc 1` | First associated or secondary diagnosis coded in CIM-10. | Alphanumeric CIM-10 diagnosis code | Confirmed. The precise prioritization of positions 1–5 is not documented, but is not needed for the current work. |
| 8 | `Cim Assoc 2` | Second associated or secondary diagnosis coded in CIM-10. | Alphanumeric CIM-10 diagnosis code | Confirmed. |
| 9 | `Cim Assoc 3` | Third associated or secondary diagnosis coded in CIM-10. | Alphanumeric CIM-10 diagnosis code | Confirmed. |
| 10 | `Cim Assoc 4` | Fourth associated or secondary diagnosis coded in CIM-10. | Alphanumeric CIM-10 diagnosis code | Confirmed. |
| 11 | `Cim Assoc 5` | Fifth associated or secondary diagnosis coded in CIM-10. | Alphanumeric CIM-10 diagnosis code | Confirmed. |
| 12 | `CCAM 1` | First procedure or medical act coded with CCAM (*Classification commune des actes médicaux*). | Alphanumeric CCAM code | Confirmed. The precise ordering rule for positions 1–4 is not documented, but is not needed for the current work. |
| 13 | `CCAM 2` | Second CCAM procedure or medical-act code. | Alphanumeric CCAM code | Confirmed. |
| 14 | `CCAM 3` | Third CCAM procedure or medical-act code. | Alphanumeric CCAM code | Confirmed. |
| 15 | `CCAM 4` | Fourth CCAM procedure or medical-act code. | Alphanumeric CCAM code | Confirmed. |
| 16 | `GHM Code` | GHM classification code. GHM means *Groupe homogène de malades*, the French case-mix grouping assigned to a hospital stay. | Alphanumeric category code | Confirmed. |
| 17 | `GHS N∞` | GHS number: the *Groupe homogène de séjours* tariff code associated with the stay. | Integer-like category code | Confirmed. The `∞` character is an encoding error for `°`, so the intended header is `GHS N°`. Store this as a category, not a quantity. |
| 18 | `AnnÈe` | Year of hospital entry. | Four-digit year | Confirmed by the workbook: it matches the year of `Date EntrÈe` in all 14,649 rows. |
| 19 | `ID Patient` | Anonymized or pseudonymized patient identifier used to link cases belonging to the same patient. | Integer-like identifier | Confirmed. There are 11,108 unique IDs among 14,649 rows; 2,546 patient IDs occur more than once, with a maximum of 9 cases for one ID. Treat it as confidential and categorical. |
| 20 | `Date Inter` | Date of the surgical intervention, possibly the first or principal intervention associated with the case. | Date | The intervention-date meaning is confirmed. **Uncertain:** whether it always represents the first intervention when a hospital case contains multiple interventions. The date falls between hospital entry and hospital exit in every row. |
| 21 | `Praticien` | Initials of a practitioner or other medic. | Short text code | Confirmed. The exact professional role is not specified and may vary. |
| 22 | `Nom Chir` | Name or identifier of the surgeon (`Chir` is short for *chirurgien*). | Text | Verified in the workbook as Excel column V (the 22nd column). This is personnel-related data even if patient data are anonymized. |
| 23 | `Heure entrée SSPI avant intervention (cela correspond à un SAS de pré-anesthésie). Si cette heure est la même que l'heure d'entrée en salle d'opération, cela signifie qu'il n'y as pas eu de passage en SSPI pré op` | Time at which the patient entered the pre-anesthesia holding area before the intervention. According to the header, equality with operating-room entry means there was no separate preoperative holding-area passage. | Clock time | Confirmed. Note that `SSPI` usually refers to a post-intervention monitoring room, while this dataset uses the field for a preoperative SAS; local terminology takes precedence. **Uncertain:** whether a zero represents midnight, missing data, or no recorded event. |
| 24 | `Heure d'entrée en salle d'opération (calimed)` | Time at which the patient entered the operating room, sourced from the Calimed system. | Clock time | Confirmed. |
| 25 | `Heure Incision ` | Time of surgical incision. | Clock time | Confirmed. The original header contains a trailing space. Zero values may mean missing/not recorded rather than midnight; this remains uncertain. |
| 26 | `Heure de sortie de salle d'opération (calimed)` | Time at which the patient left the operating room, sourced from Calimed. | Clock time | Confirmed. |
| 27 | `Anesth Type` | Main anesthesia type or technique. | Text category | Confirmed. |
| 28 | `Anesth Loco_reg` | Locoregional anesthesia technique, nerve block, or regional anesthesia used in addition to or instead of the main anesthesia type. | Text category | Confirmed. |
| 29 | `DurÈe Sèjour en jour (1 pour ambu)` | Length of hospital stay in days; ambulatory stays are recorded as `1`. | Number of days | Confirmed. This follows the dataset's stay-duration convention rather than necessarily representing exact elapsed time. |
| 30 | `Interv Type` | Human-readable intervention or procedure category. | Text category | Confirmed. Its derivation is not relevant to the intended analysis. |

## Important relationships between columns

- `No Cas` uniquely identifies each row/case, while `ID Patient` can connect multiple cases belonging to the same patient. Repeated patient IDs are present in the workbook.
- `Date EntrÈe`, `Date Sortie`, and `DurÈe Sèjour en jour (1 pour ambu)` describe the stay, but the duration may follow an inclusive administrative convention rather than simple date subtraction.
- `CIM Diag Pr.` and `Cim Assoc 1`–`5` describe diagnoses; `CCAM 1`–`4` describe performed acts; `GHM Code` and `GHS N∞` describe case grouping and reimbursement-related classification.
- The operating-room timestamps can be used to estimate preoperative waiting time, room occupancy, and entry-to-incision time after missing values and zero-time conventions have been clarified.
- `Interv Type` is likely a convenient local grouping for analysis, whereas the CCAM fields retain more detailed standardized procedure codes.

## Remaining uncertainties

Only the following points remain unclear enough to affect interpretation:

1. Does `Date Inter` always represent the first intervention, the principal intervention, or simply the intervention associated with the row?
2. What exact medical role is represented by the initials in `Praticien`?
3. Do zero values in the time fields mean midnight, missing data, or no recorded event?
4. Can interventions cross midnight, and are all clock times associated with `Date Inter`?
