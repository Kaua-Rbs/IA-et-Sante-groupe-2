"""Optimiseur de planning de bloc operatoire.

Sous-modules :
- ``optimizer`` : modele, fonction de cout et metaheuristiques (10 methodes) ;
- ``multiagent`` : systemes multi-agents Mesa (SMA et SMA x metaheuristiques) ;
- ``search_control`` : budget d'evaluations et echeance communs aux recherches.

Utilise par l'API KYST (optimisation de cohorte, actualisation des propositions)
et par ``hospital_sim.metaheuristics`` (simulation Mesa des salles).
"""
