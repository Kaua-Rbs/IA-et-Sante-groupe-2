# Glossaire

Termes techniques employés dans l'interface KYST et dans les diapositives de soutenance (`soutenance/05 - final`). Les termes sont regroupés par thème, puis classés par ordre alphabétique. Les renvois vers un autre terme sont en *italique*.

## Organisation hospitalière

| Terme | Définition |
| --- | --- |
| **ANAP** | Agence nationale de la performance sanitaire et médico-sociale. Elle publie des outils d'analyse du bloc opératoire et vise 85 % d'occupation des salles. |
| **ARS** | Agence régionale de santé. Elle délivre les autorisations d'activité chirurgicale. |
| **Cadre de bloc** | Responsable de l'organisation du bloc opératoire (ouverture des vacations, arbitrages). Rôle « Cadre bloc / lits » dans KYST. |
| **Flux poussé** | Organisation actuelle : le chirurgien fixe une date d'après son agenda, puis le bloc, les lits et les équipes s'adaptent. Produit des pics et des creux d'activité. |
| **Flux tiré** | Organisation proposée par KYST : on part de la capacité du bloc et des lits pour calculer des dates compatibles, puis le chirurgien choisit. |
| **HAS** | Haute Autorité de santé. Source des chiffres nationaux sur l'ambulatoire et la reprogrammation. |
| **IQSS** | Indicateurs de qualité et de sécurité des soins, publiés par la HAS. |
| **Vacation** | Plage horaire d'une salle d'opération attribuée à une spécialité (et souvent à un chirurgien) un jour donné, par exemple 08 h – 12 h. C'est l'unité d'affectation du planning. |

## Codes et données médicales

| Terme | Définition |
| --- | --- |
| **CCAM** | Classification commune des actes médicaux. Code de l'acte chirurgical prévu (KYST accepte 1 à 4 codes par demande). |
| **CIM-10** | Classification internationale des maladies, 10ᵉ révision. Code du *diagnostic principal* saisi dans la demande. |
| **Diagnostic principal** | Pathologie qui motive l'intervention, codée en CIM-10. |
| **EDA** | *Exploratory Data Analysis* : analyse exploratoire des données (volumes, anomalies, distributions) avant modélisation. |

## Interface KYST

| Terme | Définition |
| --- | --- |
| **KYST** | *Keep Your Surgeries Timely* : l'application web du projet, accessible sur `kyst.tech`. |
| **Date A / Date B** | Les deux dates proposées pour chaque demande : la date A est la meilleure trouvée, la date B une alternative de bonne qualité différente de A. Chacune est accompagnée de ses raisons (« Pourquoi cette date »). |
| **Remplissage** (d'une vacation) | Part des minutes de la vacation déjà occupée par des interventions programmées. |
| **Replanification** | Recalcul du planning après un aléa ou une modification de capacité. Seules les interventions non commencées peuvent bouger. |
| **Rôles** | Droits d'un compte : *Chirurgien*, *Secrétariat*, *Cadre bloc / lits*, *Administrateur*, *Lecture*. Un compte créé doit être validé par un administrateur. |
| **Statuts d'une intervention** | *Programmée* (date confirmée), *Réalisée* (durées réelles saisies), *Annulée* (créneau et lit libérés, demande à reprogrammer). |
| **Tendu / Saturé** | Niveaux d'alerte de l'occupation : *tendu* à partir de 90 % de la capacité (▲), *saturé* à 100 % (■). |
| **Conflit de lits** (jours-unité en conflit) | Jour où les séjours réservés dépassent la capacité d'une unité de lits, par exemple parce qu'un séjour réel a duré plus longtemps que prévu. |

## Apprentissage automatique (prédiction)

| Terme | Définition |
| --- | --- |
| **Cible** | Grandeur que le modèle apprend à prédire. Trois cibles ici : temps en salle, durée de séjour, ambulatoire oui/non. |
| **F1** (score) | Mesure de qualité d'une classification (ici ambulatoire oui/non), moyenne harmonique de la précision et du rappel. Vaut 1 pour un classement parfait (0,922 dans le projet). |
| **Fuite de données** (*data leakage*) | Utilisation, pendant l'entraînement, d'une information indisponible au moment de la prédiction réelle (date de sortie, durée observée…). Elle donne des scores trompeurs ; les colonnes concernées sont exclues. |
| **Imputation** | Remplacement d'une valeur manquante par une valeur estimée. Le projet garde les valeurs manquantes explicites plutôt que d'en inventer. |
| **Intervalle à 90 %** | Plage autour de la prédiction qui contient la valeur réelle dans 90 % des cas (± 1,02 jour pour le séjour). |
| **MAE** | *Mean Absolute Error* : erreur absolue moyenne entre prédiction et réalité, dans l'unité de la cible (minutes ou jours). Plus elle est faible, meilleur est le modèle. |
| **Médianes** (référence) | Méthode de comparaison naïve : prédire pour chaque acte la durée médiane observée dans l'historique. |
| **Mode consultation** | Version des modèles qui n'utilise que les informations disponibles en consultation (pas d'anesthésiste ni de praticien d'anesthésie connus), d'où une précision un peu dégradée. |
| **P80 / P95** | Quantiles : valeur que la durée réelle ne dépasse que dans 20 % (P80) ou 5 % (P95) des cas. |
| **Pipeline ML** | Chaîne de traitement : données brutes → nettoyage → découpage entraînement/test → entraînement des modèles. |
| **Split temporel par patient** | Découpage où l'on entraîne sur les années passées (2019 – 2021) et teste sur une année ultérieure (2022), sans qu'un même patient soit des deux côtés. Simule l'usage réel : prédire le futur. |
| **XGBoost / scikit-learn** | Bibliothèques Python d'apprentissage automatique utilisées pour entraîner les modèles. |

## Optimisation

| Terme | Définition |
| --- | --- |
| **Affectation** | Choix, pour chaque patient, d'une vacation. Variable de décision $x_{i,v}$ = 1 si le patient $i$ est placé dans la vacation $v$. |
| **Budget de temps** | Durée de calcul identique accordée à chaque méthode (3 ou 4 s) pour les comparer équitablement. |
| **Contrainte dure** | Règle qui ne peut jamais être violée : une vacation par patient, capacité de vacation, capacité de lits, fenêtre d'urgence, spécialité compatible. |
| **Convergence** | Évolution de la qualité de la meilleure solution au fil du calcul. |
| **Écart** | Distance relative entre la solution d'une méthode et la meilleure solution observée toutes méthodes confondues. 0 = aussi bon que la meilleure. |
| **Écart-type de charge** ($\sigma_{vac}$) | Mesure du déséquilibre entre vacations : faible si la charge est bien répartie. |
| **Fitness** | Score d'une solution, égal à moins le coût : on la maximise, 0 correspond à un planning faisable et parfaitement équilibré. |
| **Fonction objectif / coût** | Quantité à minimiser : 5 × dépassement des vacations + 3 × dépassement des lits + 0,05 × écart-type de charge. |
| **Graine** (*seed*) | Valeur initiale du générateur aléatoire. Relancer avec 20 graines différentes mesure la stabilité d'une méthode. |
| **Instance** | Jeu de données d'un problème (nombre de patients, de vacations, capacités). Petite instance : 7 patients, 4 vacations ; échelle réelle : 582 patients, 280 vacations. |
| **IQR** | *Interquartile range* : écart entre le 1ᵉʳ et le 3ᵉ quartile des résultats sur les graines. Mesure la dispersion. |
| **Métaheuristique** | Méthode générique qui cherche une bonne solution en temps limité, sans garantie d'optimalité, quand le problème est trop grand pour être résolu exactement. |
| **NP-difficile** | Classe de problèmes pour lesquels aucun algorithme connu ne trouve l'optimum en temps raisonnable sur de grandes instances (280⁵⁸² affectations possibles ici). |
| **Optimum / optimum local** | Meilleure solution possible / solution qu'aucune petite modification n'améliore, sans être forcément la meilleure. |
| **Rang moyen** | Position moyenne d'une méthode dans le classement sur toutes les graines (1 = toujours la meilleure). |
| **Voisinage / voisin** | Solutions obtenues par une petite modification de la solution courante (déplacer un patient, échanger deux patients). |

### Les méthodes comparées

| Terme | Définition |
| --- | --- |
| **Recuit simulé** | Explore en acceptant parfois une solution moins bonne, avec une probabilité qui décroît au cours du temps (critère de *Metropolis*). Évite de rester bloqué dans un optimum local. |
| **Recherche tabou** | Choisit à chaque étape le meilleur voisin, en interdisant temporairement les mouvements récents (liste tabou) pour éviter de tourner en rond. |
| **Algorithme génétique** | Fait évoluer une population de solutions par sélection, croisement et mutation. |
| **Colonie de fourmis** (ACO) | Construit des solutions pas à pas en suivant des « phéromones » renforcées sur les bons choix des itérations précédentes. |
| **Hybride** | Combinaison d'une méthode qui explore largement (génétique, fourmis) et d'une méthode qui améliore localement (tabou, recuit). Quatre hybrides : Tabou × Recuit, Génétique × Tabou, Génétique × Recuit, Fourmis × Tabou. |
| **Intensification / exploration** | Intensifier : améliorer finement autour d'une bonne solution. Explorer : visiter des régions variées de l'espace des solutions. |

## Planification dynamique et simulation

| Terme | Définition |
| --- | --- |
| **Planning statique (nominal)** | Plan optimisé une fois pour les durées prévues, sans tenir compte des aléas. |
| **Planning dynamique** | Plan maintenu dans le temps : dates de repli préparées à l'avance (proactif), puis replanification quand un aléa survient (réactif). |
| **Profils de repli** | Variantes du plan préparées à l'avance : *nominal* (100 % de la capacité), *robuste avec marge* (15 % de capacité libre), *sécurité lits* (lissage strict des lits), *date B*. |
| **Politique figée / réactive** | En simulation : *figée*, le plan initial est conservé et les cas attendent ; *réactive*, le coordinateur soumet un nouveau planning à chaque aléa. |
| **Gel du passé** | Règle de replanification : un acte commencé ou programmé avant le jour courant n'est jamais déplacé. |
| **Moindre perturbation** | Règle de replanification : déplacer le moins possible de patients déjà prévenus. |
| **Score d'adaptation** | Fitness pénalisée par le nombre de patients déplacés et de changements de jour : favorise un nouveau plan proche de l'ancien. |
| **Rapport d'arbitrage** | Liste des déplacements décidés (patient, ancienne date, nouvelle date, motif) et des urgences insérées. |
| **Dépassement** | Temps passé au-delà de la fin prévue d'une vacation ou de la journée (après 17 h), ou nombre de lits au-delà de la capacité. |
| **Mesa** | Bibliothèque Python de simulation multi-agents utilisée pour rejouer une journée de bloc et de lits. |
| **SMA** | Système multi-agents : plusieurs agents autonomes coopèrent pour construire le planning. *SMA × Méta* : chaque agent exécute une métaheuristique. |
| **Tableau noir** | Mémoire partagée où les agents déposent leur meilleure solution ; elle est versionnée et validée avant exécution. |
| **Coordinateur** | Agent qui lit le tableau noir, retient la meilleure solution et la soumet. Une proposition invalide est rejetée et l'ancien plan reste actif. |
| **Migration** | Échange de solutions entre agents quand la recherche stagne. |

## Architecture et déploiement

| Terme | Définition |
| --- | --- |
| **API** | Interface de programmation : le serveur (FastAPI) qui détient les données, vérifie les droits et appelle les modèles. Elle n'est pas exposée directement au navigateur. |
| **Ansible** | Outil qui automatise l'installation et la configuration du serveur. |
| **Argon2** | Algorithme de hachage des mots de passe, conçu pour résister aux attaques par force brute. |
| **Cookie HttpOnly / Secure** | Cookie inaccessible au JavaScript de la page (*HttpOnly*) et transmis uniquement en HTTPS (*Secure*) ; il contient les jetons de session. |
| **Conteneur rootless** | Application isolée dans un conteneur (Podman) qui tourne sans droits d'administrateur sur le serveur. |
| **CSRF** | *Cross-Site Request Forgery* : attaque où un autre site fait envoyer une requête à l'insu de l'utilisateur. Les formulaires de KYST sont protégés. |
| **FastAPI** | Framework Python utilisé pour l'API. |
| **Front** | Partie de l'application qui produit les pages vues dans le navigateur (SvelteKit). |
| **HTTPS / TLS** | Protocole web chiffré ; TLS est la couche de chiffrement. |
| **Jeton d'accès / refresh token** | Preuves de connexion à durée limitée ; le jeton d'accès est renouvelé automatiquement grâce au refresh token. |
| **Journal d'audit** (trace d'accès) | Enregistrement de chaque appel : qui, quand, depuis quelle adresse, sur quelle donnée. Permet de retrouver qui a décidé quoi. |
| **Podman** | Outil de gestion de conteneurs, alternative à Docker sans démon root. |
| **PostgreSQL** | Base de données relationnelle de KYST. |
| **Seed** (données de démonstration) | Jeu de données fictives réalistes injecté au déploiement de l'instance de démonstration. |
| **SvelteKit** | Framework web utilisé pour le front. |

## Réglementation

| Terme | Définition |
| --- | --- |
| **AI Act** | Règlement européen sur l'intelligence artificielle, qui classe les systèmes d'IA par niveau de risque. |
| **AIPD** | Analyse d'impact relative à la protection des données, obligatoire pour un traitement à grande échelle de données de santé. |
| **Base légale** | Fondement juridique qui autorise un traitement de données personnelles (RGPD, art. 6 et 9). |
| **HDS** | Hébergement de données de santé : certification obligatoire en France pour héberger des données de santé pour le compte d'un tiers. |
| **Marquage CE / MDR** | Conformité au règlement (UE) 2017/745 sur les dispositifs médicaux (*Medical Device Regulation*). Un logiciel d'aide à la décision peut en relever ; il faut alors un dossier technique, une gestion des risques et une matériovigilance. |
| **Matériovigilance** | Surveillance des incidents liés à un dispositif médical après sa mise sur le marché. |
| **Minimisation** | Principe du RGPD : ne collecter que les données nécessaires à la finalité. |
| **Non-substitution** | Principe de KYST : l'outil propose et justifie, le praticien décide. Aucune date n'est réservée sans confirmation humaine. |
| **RGPD** | Règlement général sur la protection des données (UE) 2016/679. |
