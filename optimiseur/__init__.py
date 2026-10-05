"""Optimiseur de planning de bloc operatoire.

Sous-modules :
- ``optimizer`` : modele, fonction de cout et metaheuristiques (10 methodes) ;
- ``aleas`` : gestion des aleas (urgences, annulations, lits, retards) et plannings alternatifs / adaptation dynamique ;
- ``multiagent`` : systemes multi-agents Mesa (SMA et SMA x metaheuristiques) ;
- ``coordination_bridge`` : pont asynchrone vers ``hospital_sim`` ;
- ``benchmark`` : campagnes multi-graines (petite et grande echelle) ;
- ``plotting`` : graphiques matplotlib ;
- ``data_bridge`` : conversion du Parquet EDA vers le schema de l'optimiseur ;
- ``run_demo`` : demonstration en ligne de commande ;
- ``run_benchmark`` : campagnes comparatives en ligne de commande ;
- ``run_coordination_demo`` : re-planification dynamique avec hospital_sim ;
- ``app_gui`` : interface graphique Tkinter.

Lancement depuis la racine du depot :

    python -m optimiseur.run_demo --n-patients 30 --n-days 5 --out resultats
    python -m optimiseur.run_demo --toutes --budget 2
    python -m optimiseur.run_benchmark
    python -m optimiseur.run_coordination_demo
    python -m optimiseur.app_gui
"""
