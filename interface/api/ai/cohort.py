"""Read-only cohort optimization against the web application's capacity snapshot.

The vacation optimizer assigns a cohort, while KYST's normal proposal flow
confirms one request at a time. This adapter checks the extra per-request rules
and never writes a proposed cohort plan into the clinical database.
"""

import datetime as dt
from dataclasses import dataclass
from math import ceil
from uuid import UUID

import pandas as pd

from api.ai.contracts import BedUnitLoad, VacationSlot
from api.resources.models import CareType
from optimiseur import optimizer as op


@dataclass(frozen=True)
class CohortCase:
    request_id: UUID
    specialty_id: int
    surgeon_id: int
    room_minutes: float
    los_days: int
    care_type: CareType
    earliest_date: dt.date
    latest_date: dt.date
    rejected_dates: tuple[dt.date, ...] = ()


@dataclass(frozen=True)
class CohortAssignment:
    request_id: UUID
    vacation_id: int
    bed_unit_id: int
    admission_date: dt.date
    discharge_date: dt.date
    planned_minutes: int


@dataclass(frozen=True)
class CohortPreview:
    method: str
    assignments: tuple[CohortAssignment, ...]
    unassigned: tuple[UUID, ...]
    evaluated_cases: int


def _stay(day: dt.date, length: int) -> tuple[dt.date, ...]:
    return tuple(day + dt.timedelta(days=offset) for offset in range(length))


def optimize_cohort(
    cases: tuple[CohortCase, ...],
    vacations: tuple[VacationSlot, ...],
    bed_units: tuple[BedUnitLoad, ...],
    *,
    method: str,
    emergency_margin: float,
    seed: int = 0,
    budget_seconds: float = 1.0,
) -> CohortPreview:
    if method not in op.TOUTES_METHODES:
        raise ValueError("Unknown optimization method")
    if not 0 <= emergency_margin < 1 or budget_seconds <= 0:
        raise ValueError("Invalid optimization settings")
    if len({case.request_id for case in cases}) != len(cases):
        raise ValueError("Duplicate request in cohort")
    if len({slot.id for slot in vacations}) != len(vacations):
        raise ValueError("Duplicate vacation in snapshot")
    if not vacations:
        return CohortPreview(method, (), tuple(sorted(
            (case.request_id for case in cases), key=str)), len(cases))

    remaining = {
        slot.id: max(0, int(slot.duration_min * (1 - emergency_margin)) - slot.used_min)
        for slot in vacations
    }
    allocated_beds: dict[tuple[int, dt.date], int] = {}
    assignments: list[CohortAssignment] = []
    unassigned: set[UUID] = set()

    # Optimize care types separately: an ambulatory place cannot cover an
    # inpatient stay. Vacation capacity is shared and updated between groups.
    for care_type in (CareType.conventional, CareType.ambulatory):
        group = sorted((case for case in cases if case.care_type == care_type),
                       key=lambda case: str(case.request_id))
        if not group:
            continue
        units = [unit for unit in bed_units if unit.care_type == care_type and unit.capacity > 0]
        available = sorted(vacations, key=lambda slot: (slot.date, slot.id))
        eligible: list[CohortCase] = []
        patient_options: list[list[int]] = []
        for case in group:
            options = [index for index, slot in enumerate(available)
                       if slot.specialty_id == case.specialty_id
                       and slot.surgeon_id in (None, case.surgeon_id)
                       and case.earliest_date <= slot.date <= case.latest_date
                       and slot.date not in case.rejected_dates
                       and ceil(case.room_minutes) <= remaining[slot.id]]
            if options and units:
                eligible.append(case)
                patient_options.append(options)
            else:
                unassigned.add(case.request_id)
        if not eligible:
            continue

        first_day = min(slot.date for slot in available)
        last_day = max(slot.date for slot in available)
        patients_df = pd.DataFrame([
            {"patient_id": index, "specialite": case.specialty_id,
             "duree_operatoire": ceil(case.room_minutes),
             # PlanningProblem's occupancy includes both endpoints.
             "duree_sejour": case.los_days - 1}
            for index, case in enumerate(eligible)
        ])
        vacations_df = pd.DataFrame([
            {"vacation_id": slot.id, "jour": (slot.date - first_day).days,
             "specialite": slot.specialty_id, "capacite_min": remaining[slot.id]}
            for slot in available
        ])
        free_beds = [
            sum(unit.capacity - unit.occupancy.get(day, 0)
                - allocated_beds.get((unit.id, day), 0) for unit in units)
            for day in _stay(first_day, (last_day - first_day).days + 1)
        ]
        result = op.optimize_planning(
            patients_df, vacations_df, lits_capacity=free_beds,
            patient_options=patient_options, methodes=[method], seed=seed,
            time_budget_s=budget_seconds,
        )[method]
        # Search fitness is a soft objective. Validate every real vacation and
        # bed unit before presenting a case as schedulable.
        chosen = sorted(result.meilleure_solution.items(),
                        key=lambda item: (available[item[1]].date,
                                          ceil(eligible[item[0]].room_minutes), item[0]))
        for patient_index, vacation_index in chosen:
            case, slot = eligible[patient_index], available[vacation_index]
            minutes = ceil(case.room_minutes)
            if vacation_index not in patient_options[patient_index] or minutes > remaining[slot.id]:
                unassigned.add(case.request_id)
                continue
            stay = _stay(slot.date, case.los_days)
            possible = [unit for unit in units if all(
                unit.occupancy.get(day, 0) + allocated_beds.get((unit.id, day), 0) < unit.capacity
                for day in stay)]
            if not possible:
                unassigned.add(case.request_id)
                continue
            unit = min(possible, key=lambda candidate: (
                max((candidate.occupancy.get(day, 0)
                     + allocated_beds.get((candidate.id, day), 0) + 1) / candidate.capacity
                    for day in stay), candidate.id))
            remaining[slot.id] -= minutes
            for day in stay:
                allocated_beds[(unit.id, day)] = allocated_beds.get((unit.id, day), 0) + 1
            assignments.append(CohortAssignment(case.request_id, slot.id, unit.id,
                                                slot.date, stay[-1], minutes))

    placed = {assignment.request_id for assignment in assignments}
    unassigned.update(case.request_id for case in cases if case.request_id not in placed)
    unassigned.difference_update(placed)
    return CohortPreview(method, tuple(assignments), tuple(sorted(unassigned, key=str)), len(cases))
