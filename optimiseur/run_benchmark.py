"""
run_benchmark.py
----------------
Campagne comparative en ligne de commande : petite echelle (optimum exact)
et grande echelle (meilleur connu), sur toutes les methodes (5 historiques,
3 hybrides, 2 SMA).

Usage (depuis la racine du depot) :
    python -m optimiseur.run_benchmark
    python -m optimiseur.run_benchmark --graines 20 --budget-petite 0.5 --budget-grande 3
    python -m optimiseur.run_benchmark --methodes "Recuit simule" Tabou --verbose
    python -m optimiseur.run_benchmark --donnees-reelles --horizon 40 --capacite-min 600 \
        --out resultats/benchmark_reel --figures rapport/figures

Sorties :
- CSV bruts et agreges dans ``--out`` (defaut resultats/benchmark) ;
- figures PNG dans ``--figures`` (defaut rapport/figures) ;
- metadonnees JSON (parametres + references) pour la reproductibilite.

Avec ``--donnees-reelles``, la campagne grande echelle est remplacee par une
campagne sur le Parquet EDA reel (``resources/donnees_bloc_pretraitees.parquet``,
produit par le notebook EDA) via ``data_bridge.prepare_inputs``.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # rendu vers fichiers, sans fenetre

from . import benchmark as bm
from . import optimizer as op
from . import plotting as pl


def _ecrire_csv(df, chemin: str) -> None:
    df.to_csv(chemin, index=False)
    print(f"   -> {chemin}")


def _afficher_resume(campagne: bm.Campagne) -> None:
    print(f"\n=== Synthese {campagne.nom} (reference {'exacte' if campagne.reference_exacte else 'meilleur connu'} = {campagne.reference:.3f}) ===")
    entete = f"{'methode':<25s} {'mediane':>12s} {'ecart_moy':>10s} {'taux_ref':>9s} {'rang_moy':>9s} {'duree_moy':>10s}"
    print(entete)
    print("-" * len(entete))
    for ligne in campagne.resume.itertuples():
        print(
            f"{ligne.methode:<25s} {ligne.mediane:12.3f} {ligne.ecart_moyen_ref:10.3f} "
            f"{100.0 * ligne.taux_reference:8.0f}% {ligne.rang_moyen:9.2f} {ligne.duree_moyenne_s:9.3f}s"
        )


def _figures_petite(campagne: bm.Campagne, dossier: str) -> None:
    pl.plot_taux_succes(
        campagne.taux_reference,
        titre="Petite instance : taux d'optimum exact par methode",
    ).savefig(os.path.join(dossier, "petite_taux_optimum.png"), dpi=150)
    pl.plot_boxplot_graines(
        campagne.resultats, titre="Petite instance : distribution de la fitness finale"
    ).savefig(os.path.join(dossier, "petite_boxplot.png"), dpi=150)
    pl.plot_convergence_mediane(
        campagne.resultats, titre="Petite instance : convergence mediane (20 graines)"
    ).savefig(os.path.join(dossier, "petite_convergence.png"), dpi=150)


def _figures_instance(campagne: bm.Campagne, dossier: str, prefixe: str, titre: str) -> None:
    pl.plot_boxplot_graines(
        campagne.resultats, titre=f"{titre} : distribution de la fitness finale"
    ).savefig(os.path.join(dossier, f"{prefixe}_boxplot.png"), dpi=150)
    pl.plot_convergence_mediane(
        campagne.resultats, titre=f"{titre} : convergence mediane"
    ).savefig(os.path.join(dossier, f"{prefixe}_convergence.png"), dpi=150)
    pl.plot_qualite_temps(
        campagne.resultats, titre=f"{titre} : qualite moyenne vs temps moyen"
    ).savefig(os.path.join(dossier, f"{prefixe}_qualite_temps.png"), dpi=150)


def _figures_grande(campagne: bm.Campagne, dossier: str) -> None:
    _figures_instance(campagne, dossier, "grande", "Grande instance synthetique")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark multi-graines des methodes d'optimisation du bloc operatoire"
    )
    parser.add_argument("--graines", type=int, default=20)
    parser.add_argument("--budget-petite", type=float, default=0.5)
    parser.add_argument("--budget-grande", type=float, default=3.0)
    parser.add_argument("--n-patients", type=int, default=300)
    parser.add_argument("--n-days", type=int, default=20)
    parser.add_argument("--lits-capacity", type=int, default=42)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="resultats/benchmark")
    parser.add_argument("--figures", type=str, default="rapport/figures")
    parser.add_argument("--methodes", nargs="*", default=None, choices=list(op.TOUTES_METHODES))
    parser.add_argument("--sans-petite", action="store_true")
    parser.add_argument("--sans-grande", action="store_true")
    parser.add_argument(
        "--donnees-reelles",
        action="store_true",
        help="remplace la campagne grande echelle par le Parquet EDA reel",
    )
    parser.add_argument("--parquet", type=str, default=None, help="chemin du Parquet EDA (optionnel)")
    parser.add_argument("--horizon", type=int, default=40, help="horizon en jours pour les donnees reelles")
    parser.add_argument(
        "--capacite-min", type=int, default=600, help="capacite d'une vacation en minutes (donnees reelles)"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.donnees_reelles and args.sans_grande:
        parser.error("--donnees-reelles et --sans-grande sont incompatibles")
    if args.donnees_reelles:
        from . import data_bridge as db

        chemin_parquet = args.parquet or str(db.DEFAULT_PARQUET)
        if not os.path.exists(chemin_parquet):
            parser.error(
                f"Parquet introuvable : {chemin_parquet}. Executez d'abord EDA_donees_bloc.ipynb."
            )

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.figures, exist_ok=True)

    methodes = args.methodes or list(op.TOUTES_METHODES)
    meta = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "methodes": methodes,
        "n_graines": args.graines,
        "budget_petite_s": args.budget_petite,
        "budget_grande_s": args.budget_grande,
        "grande_instance": {
            "n_patients": args.n_patients,
            "n_days": args.n_days,
            "seed": args.seed,
            "lits_capacity": args.lits_capacity,
        },
        "petite_instance": {"patients": 7, "vacations": 4, "seed": 1},
    }

    if not args.sans_petite:
        print(f"1) Campagne petite echelle : {len(methodes)} methodes x {args.graines} graines, "
              f"budget {args.budget_petite} s")
        petite = bm.campagne_petite_validation(
            n_graines=args.graines,
            budget_s=args.budget_petite,
            methodes=methodes,
            verbose=args.verbose,
        )
        _ecrire_csv(petite.tableau, os.path.join(args.out, "petite_graines.csv"))
        _ecrire_csv(petite.resume, os.path.join(args.out, "petite_resume.csv"))
        _afficher_resume(petite)
        _figures_petite(petite, args.figures)
        meta["petite_reference"] = petite.reference
        meta["petite_reference_exacte"] = petite.reference_exacte

    if args.donnees_reelles:
        from . import data_bridge as db

        patients_reels, vacations_reelles, contexte = db.prepare_inputs(
            args.parquet or db.DEFAULT_PARQUET,
            horizon_jours=args.horizon,
            capacite_min=args.capacite_min,
        )
        print(
            f"\n2) Campagne donnees reelles : {len(patients_reels)} patients, "
            f"{len(vacations_reelles)} vacations ({contexte['n_days']} jours), "
            f"{len(methodes)} methodes x {args.graines} graines, budget {args.budget_grande} s"
        )
        reelle = bm.campagne_sur_instance(
            patients_reels,
            vacations_reelles,
            nom="reelle",
            n_graines=args.graines,
            budget_s=args.budget_grande,
            lits_capacity=args.lits_capacity,
            methodes=methodes,
            verbose=args.verbose,
        )
        _ecrire_csv(reelle.tableau, os.path.join(args.out, "reelle_graines.csv"))
        _ecrire_csv(reelle.resume, os.path.join(args.out, "reelle_resume.csv"))
        _afficher_resume(reelle)
        _figures_instance(reelle, args.figures, "reelle", "Donnees reelles (Parquet EDA)")
        meta["reelle_instance"] = {
            "parquet": args.parquet or str(db.DEFAULT_PARQUET),
            "horizon_jours": args.horizon,
            "capacite_min": args.capacite_min,
            "n_patients": len(patients_reels),
            "n_vacations": len(vacations_reelles),
            "n_days": contexte["n_days"],
            "specialites": contexte["specialites"],
        }
        meta["reelle_reference_meilleur_connu"] = reelle.reference
        meta["reelle_reference_exacte"] = False
    elif not args.sans_grande:
        print(f"\n2) Campagne grande echelle : {len(methodes)} methodes x {args.graines} graines, "
              f"budget {args.budget_grande} s")
        grande = bm.campagne_grande_echelle(
            n_graines=args.graines,
            budget_s=args.budget_grande,
            n_patients=args.n_patients,
            n_days=args.n_days,
            seed_instance=args.seed,
            lits_capacity=args.lits_capacity,
            methodes=methodes,
            verbose=args.verbose,
        )
        _ecrire_csv(grande.tableau, os.path.join(args.out, "grande_graines.csv"))
        _ecrire_csv(grande.resume, os.path.join(args.out, "grande_resume.csv"))
        _afficher_resume(grande)
        _figures_grande(grande, args.figures)
        meta["grande_reference_meilleur_connu"] = grande.reference
        meta["grande_reference_exacte"] = grande.reference_exacte

    chemin_meta = os.path.join(args.out, "benchmark_meta.json")
    with open(chemin_meta, "w", encoding="utf-8") as fichier:
        json.dump(meta, fichier, ensure_ascii=False, indent=2)
    print(f"\nMetadonnees : {chemin_meta}")
    print("Termine.")


if __name__ == "__main__":
    main()
