"""
run_demo.py
-----------
Demonstration complete, sans interface graphique : genere un jeu de
donnees de test, lance les metaheuristiques (recuit simule, tabou,
genetique, hybride tabou x recuit, fourmis/ACO), sauvegarde les
graphiques de comparaison, et verifie l'optimalite sur une petite
instance de reference.

Usage (depuis la racine du depot) :
    python -m optimiseur.run_demo
    python -m optimiseur.run_demo --n-patients 50 --n-days 6 --out dossier_resultats
"""

from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")  # rendu vers fichiers, sans fenetre

from . import optimizer as op
from . import plotting as pl
from . import aleas as al


def main():
    parser = argparse.ArgumentParser(description="Demo du moteur d'optimisation du bloc operatoire")
    parser.add_argument("--n-patients", type=int, default=30)
    parser.add_argument("--n-days", type=int, default=5)
    parser.add_argument("--lits-capacity", type=int, default=42)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="resultats")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    print(f"1) Generation du jeu de donnees de test ({args.n_patients} patients, {args.n_days} jours)...")
    patients_df, vacations_df = op.generate_test_data(
        n_patients=args.n_patients, n_days=args.n_days, seed=args.seed
    )
    patients_df.to_csv(os.path.join(args.out, "patients_test.csv"), index=False)
    vacations_df.to_csv(os.path.join(args.out, "vacations_test.csv"), index=False)
    problem = op.PlanningProblem(patients_df, vacations_df, lits_capacity=args.lits_capacity)

    print("2) Optimisation avec les metaheuristiques...")
    resultats = op.optimize_planning(patients_df, vacations_df, lits_capacity=args.lits_capacity, seed=args.seed)
    for nom, r in resultats.items():
        print(f"   - {nom:<15s} fitness finale = {r.meilleure_fitness:10.3f}   temps = {op.format_duree(r.duree_s):>9s}")

    print("3) Sauvegarde des graphiques de comparaison...")
    pl.plot_convergence(resultats).savefig(os.path.join(args.out, "convergence.png"), dpi=150)
    pl.plot_comparaison_barres(resultats).savefig(os.path.join(args.out, "comparaison.png"), dpi=150)

    meilleure_methode = max(resultats, key=lambda n: resultats[n].meilleure_fitness)
    meilleure_solution = resultats[meilleure_methode].meilleure_solution
    pl.plot_planning(problem, meilleure_solution, titre=f"Planning obtenu ({meilleure_methode})").savefig(
        os.path.join(args.out, "planning.png"), dpi=150
    )
    pl.plot_occupation_lits(problem, meilleure_solution).savefig(
        os.path.join(args.out, "occupation_lits.png"), dpi=150
    )

    planning_df = op.solution_to_dataframe(problem, meilleure_solution)
    planning_df.to_csv(os.path.join(args.out, f"planning_{meilleure_methode.replace(' ', '_')}.csv"), index=False)

    print(f"   -> meilleure methode sur ce jeu de donnees : {meilleure_methode}")

    print("4) Verification de l'optimalite sur une petite instance de reference...")
    pat_s, vac_s = op.small_validation_instance(seed=args.seed)
    prob_s = op.PlanningProblem(pat_s, vac_s)
    _, f_exact = op.exact_bruteforce(prob_s)
    res_s = op.optimize_planning(
        pat_s, vac_s,
        sa_kwargs=dict(n_iter=500),
        tabu_kwargs=dict(n_iter=100, neighborhood_size=10),
        ga_kwargs=dict(pop_size=20, n_gen=60),
        hybrid_kwargs=dict(n_iter=200, neighborhood_size=10),
        aco_kwargs=dict(n_ants=10, n_iter=80),
    )
    print(f"   optimum exact (force brute) = {f_exact:.6f}")
    for nom, r in res_s.items():
        ecart = r.meilleure_fitness - f_exact
        statut = "OPTIMUM ATTEINT" if abs(ecart) < 1e-9 else f"ecart = {ecart:.4f}"
        print(f"   - {nom:<15s} fitness = {r.meilleure_fitness:10.6f}   [{statut}]")

    print("5) Generation des plannings alternatifs (Nominal, Robuste bufferise, Date A/B)...")
    alts = al.generer_plannings_alternatifs(
        problem,
        solution_nominale=meilleure_solution,
        seed=args.seed,
    )
    pl.plot_comparaison_alternatives(alts).savefig(
        os.path.join(args.out, "plannings_alternatifs.png"), dpi=150
    )
    df_date_ab = al.extraire_options_date_a_b(
        problem,
        alts["Nominal"].solution,
        alts["Alternatif_Date_B"].solution,
    )
    df_date_ab.to_csv(os.path.join(args.out, "planning_alternatif_date_a_b.csv"), index=False)
    taux_diff = alts["Alternatif_Date_B"].taux_patients_differents * 100
    print(f"   -> Plannings alternatifs generes ({taux_diff:.1f}% des patients ont une Date B alternative)")

    print("6) Simulation d'aleas et adaptation dynamique du bloc...")
    jour_alea = 1 if args.n_days > 1 else 0
    scenario = al.generer_scenario_aleas(
        problem,
        meilleure_solution,
        jour_courant=jour_alea,
        n_urgences=2 if args.n_patients >= 15 else 1,
        n_annulations=1,
        proba_retard_bloc=0.5,
        max_retard_min=45.0,
        proba_baisse_lits=1.0,
        lits_perdus=max(2, args.lits_capacity // 10),
        seed=args.seed,
    )
    adap_res = al.adapter_planning(
        problem,
        meilleure_solution,
        scenario,
        jour_courant=jour_alea,
        seed=args.seed,
    )
    pl.plot_adaptation_dynamique(adap_res).savefig(
        os.path.join(args.out, "aleas_adaptation.png"), dpi=150
    )
    with open(os.path.join(args.out, "rapport_adaptation.txt"), "w", encoding="utf-8") as f:
        f.write(adap_res.rapport)

    print(f"   -> Adaptation dynamique terminee ({adap_res.perturbation_count} deplacement(s), {len(adap_res.urgences_affectees)} urgence(s) integree(s))")

    print(f"\nTermine. Resultats et graphiques dans le dossier : {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
