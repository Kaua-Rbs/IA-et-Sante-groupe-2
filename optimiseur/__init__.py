"""Optimiseur de planning de bloc operatoire.

Sous-modules :
- ``optimizer`` : modele, fonction de cout et metaheuristiques ;
- ``plotting`` : graphiques matplotlib ;
- ``data_bridge`` : conversion du Parquet EDA vers le schema de l'optimiseur ;
- ``run_demo`` : demonstration en ligne de commande ;
- ``app_gui`` : interface graphique Tkinter.

Lancement depuis la racine du depot :

    python -m optimiseur.run_demo --n-patients 30 --n-days 5 --out resultats
    python -m optimiseur.app_gui
"""
