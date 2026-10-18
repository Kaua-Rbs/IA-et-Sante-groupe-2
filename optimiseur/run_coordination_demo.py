"""
run_coordination_demo.py
------------------------
Demonstration de re-planification dynamique : un planning de bloc est
recalcule lorsqu'un evenement hospitalier survient, en passant par le
squelette de coordination asynchrone ``hospital_sim``.

Scenario :
1. une vacation devient indisponible (``RESOURCE_UNAVAILABLE``) ;
2. une urgence se presente (``EMERGENCY_ARRIVAL``).

Usage (depuis la racine du depot) :
    python -m optimiseur.run_coordination_demo
    python -m optimiseur.run_coordination_demo --n-patients 40 --n-days 6 --budget 2
"""

from __future__ import annotations

import argparse
import asyncio

from hospital_sim.contracts import EventKind, HospitalEvent, Snapshot
from hospital_sim.coordinator import Coordinator

from . import optimizer as op
from .coordination_bridge import (
    EtatBloc,
    EtatBlocAdapter,
    PlanificateurOptimiseur,
    ValidateurBloc,
    probleme_depuis_etat,
    solution_vers_affectation,
)


def _resume(coordinator: Coordinator) -> None:
    planning = coordinator.snapshot.accepted_schedule
    if planning is None:
        print("   aucune solution acceptee")
        return
    print(
        f"   planning accepte : {len(planning.affectation)} patients, "
        f"fitness = {planning.fitness:.3f} (methode : {planning.methode})"
    )


# Plafonds d'iteration eleves pour que le budget temps soit le seul frein.
_BUDGET_KWARGS = {
    op.METHODE_RECUIT: {"n_iter": 10**6},
    op.METHODE_TABOU: {"n_iter": 10**6},
    op.METHODE_GENETIQUE: {"n_gen": 10**6},
    op.METHODE_HYBRIDE: {"n_iter": 10**6},
    op.METHODE_FOURMIS: {"n_iter": 10**6},
    op.METHODE_GEN_TABOU: {"n_gen": 10**6},
    op.METHODE_GEN_RECUIT: {"n_gen": 10**6},
    op.METHODE_FOURMIS_TABOU: {"n_iter": 10**6},
    op.METHODE_SMA: {"n_steps": 10**6},
    op.METHODE_SMA_HYBRIDE: {"n_steps": 10**6},
}


def _specialite_la_plus_souple(patients, vacations) -> str:
    """Specialite dont le ratio demande/capacite est le plus faible : retirer
    une de ses vacations laisse l'instance faisable."""
    demande = patients.groupby("specialite")["duree_operatoire"].sum()
    capacite = vacations.groupby("specialite")["capacite_min"].sum()
    return str((demande / capacite).sort_values().index[0])


async def scenario(args) -> None:
    patients, vacations = op.generate_test_data(
        n_patients=args.n_patients, n_days=args.n_days, seed=args.seed
    )
    etat = EtatBloc(patients, vacations, lits_capacity=args.lits_capacity)
    problem = probleme_depuis_etat(etat)

    spec_cible = _specialite_la_plus_souple(patients, vacations)
    vac_cible = int(vacations.loc[vacations["specialite"] == spec_cible, "vacation_id"].iloc[0])

    print(f"1) Instance initiale : {problem.n_patients} patients, {problem.n_vacations} vacations")
    print(f"   vacation cible de l'incident : {vac_cible} ({spec_cible})")

    coordinator = Coordinator(
        initial=Snapshot(0.0, 0, etat, None),
        state_adapter=EtatBlocAdapter(),
        scheduler=PlanificateurOptimiseur(
            methode=args.methode,
            budget_s=args.budget,
            seed=args.seed,
            kwargs_methode=_BUDGET_KWARGS.get(args.methode, {}),
        ),
        validator=ValidateurBloc(),
        timeout_seconds=args.budget + 5.0,
    )

    async with coordinator:
        print("2) Evenement : vacation indisponible")
        coordinator.submit(
            HospitalEvent(
                event_id="evt-1",
                simulation_time=1.0,
                kind=EventKind.RESOURCE_UNAVAILABLE,
                payload={"vacation_id": vac_cible},
            )
        )
        await coordinator.wait_idle()
        print(f"   resultat : {coordinator.outcomes[-1].status}")
        version = coordinator.snapshot.version
        resultat = coordinator.accept(version)
        print(f"   acceptation : {resultat.feasible}")
        _resume(coordinator)

        print("3) Evenement : arrivee en urgence")
        coordinator.submit(
            HospitalEvent(
                event_id="evt-2",
                simulation_time=2.0,
                kind=EventKind.EMERGENCY_ARRIVAL,
                payload={
                    "specialite": spec_cible,
                    "duree_operatoire": 90,
                    "duree_sejour": 2,
                },
            )
        )
        await coordinator.wait_idle()
        print(f"   resultat : {coordinator.outcomes[-1].status}")
        version = coordinator.snapshot.version
        resultat = coordinator.accept(version)
        print(f"   acceptation : {resultat.feasible}")
        _resume(coordinator)

        print(f"4) Metriques du coordinateur : {coordinator.metrics}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demonstration de re-planification dynamique (optimiseur + hospital_sim)"
    )
    parser.add_argument("--n-patients", type=int, default=25)
    parser.add_argument("--n-days", type=int, default=4)
    parser.add_argument("--lits-capacity", type=int, default=42)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--methode", type=str, default=op.METHODE_SMA_HYBRIDE)
    parser.add_argument("--budget", type=float, default=1.0)
    args = parser.parse_args()
    asyncio.run(scenario(args))


if __name__ == "__main__":
    main()
