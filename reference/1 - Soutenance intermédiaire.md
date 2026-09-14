---
title: "Soutenance intermédiaire du Fil rouge — Blocs opératoires"
duration: "20 min"
---

# Plan — Soutenance intermédiaire du Fil rouge Blocs opératoires (20 min)

---

## 1. Introduction (2 min)

- Présenter clairement le sujet : **optimisation conjointe des blocs opératoires et des lits**
- Expliquer l'objectif global : **mieux planifier pour améliorer l'efficacité hospitalière**

> **Attendu** : compréhension simple et claire du problème

---

## 2. Contexte et enjeux (3 min)

- **Fonctionnement général** :
  - Planification des interventions
  - Hospitalisation avant/après opération
- **Contraintes** :
  - Nombre limité de blocs et de lits
  - Durées variables des opérations
  - Urgences
- **Enjeux** :
  - Réduire les temps d'attente
  - Éviter les conflits (pas de lit disponible, bloc occupé…)

> **Attendu** : identification des contraintes réelles et des enjeux

---

## 3. Analyse de la BDD (3 min)

- **Présenter les données** :
  - Patients, interventions, durées, lits
- **Montrer** :
  - Qualité des données (manquantes, incohérences)
  - Premières statistiques (durée moyenne, taux d'occupation)
- **Lien avec le problème** : ces données serviront à construire le modèle

> **Attendu** : capacité à exploiter et comprendre les données

---

## 4. État de l'art (2 min)

- **Méthodes existantes** :
  - Programmation linéaire
  - Heuristiques / métaheuristiques
- **Limites** :
  - Souvent blocs et lits traités séparément

> **Attendu** : compréhension des approches existantes

---

## 5. Positionnement (2 min)

- **Expliquer le choix** : optimisation conjointe blocs + lits
- **Montrer l'intérêt** :
  - Meilleure coordination
  - Moins de conflits

> **Attendu** : justification claire de l'approche d'optimisation

---

## 6. Modélisation (4–5 min)

- **Variables** :
  - Affectation patient → bloc → lit
- **Contraintes** :
  - Capacité blocs/lits
  - Respect des durées
- **Fonction objectif** :
  - Minimiser retards ou conflits
- **Lien avec la BDD** : les paramètres viennent des données

> **Attendu** : modèle cohérent, même simplifié

---

## 7. Approches proposées (3 min)

- **Métaheuristiques** :
  - **Recuit simulé** (exploration progressive)
  - **Tabou** (éviter de revenir en arrière)
  - **Algorithme génétique** (évolution de solutions)
- **Pourquoi ces choix** : problème complexe (NP-difficile)

> **Attendu** : compréhension et justification des méthodes

---

## 8. Suite du travail (1–2 min)

- Implémentation des algorithmes
- Tests sur la BDD
- Comparaison des performances

> **Attendu** : plan clair et réaliste

---

## ❓ Questions (10 min)

