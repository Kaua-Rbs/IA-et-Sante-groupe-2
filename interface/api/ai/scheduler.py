"""Individual date search: proposes the best compatible vacations for one request."""

import datetime as dt
from collections import defaultdict

from api.ai.contracts import Candidate, MovableCase, SchedulingInput, stay_days


class GreedyCapacityScheduler:
    """Greedy baseline: scores each compatible vacation independently.

    It neither reorders existing cases nor plans several patients together, and
    ignores weekends and holidays. Cohort optimization is a separate operation.
    An urgent request may use the emergency margin; when no vacation is free, it
    proposes to postpone the fewest confirmed future cases, for a human to decide.
    """

    name = "greedy-capacity"

    def propose(self, request: SchedulingInput, count: int) -> list[Candidate]:
        window_days = max(1, (request.latest_date - request.earliest_date).days)
        candidates: list[Candidate] = []
        for vacation in request.vacations:
            candidate = self._evaluate(request, vacation, window_days)
            if candidate is not None:
                candidates.append(candidate)
        candidates.sort(key=lambda c: (-c.score, c.admission_date, c.vacation_id))
        chosen = _prefer_distinct_dates(candidates, count)
        if request.urgent and len(chosen) < count:
            used_dates = {c.admission_date for c in chosen}
            displacements = [c for c in self._displacements(request)
                             if c.admission_date not in used_dates]
            chosen += _prefer_distinct_dates(displacements, count - len(chosen))
        return chosen

    def _compatible(self, request, vacation) -> bool:
        return (vacation.specialty_id == request.specialty_id
                and vacation.surgeon_id in (None, request.surgeon_id)
                and request.earliest_date <= vacation.date <= request.latest_date)

    def _usable(self, request, vacation) -> float:
        return vacation.duration_min * (1 - request.emergency_margin)

    def _evaluate(self, request, vacation, window_days) -> Candidate | None:
        if not self._compatible(request, vacation):
            return None
        if vacation.used_min + request.room_minutes > self._usable(request, vacation):
            return None

        admission = vacation.date
        bed = _best_unit(request, admission)
        if bed is None:
            return None
        best_unit, best_peak = bed

        fill = (vacation.used_min + request.room_minutes) / vacation.duration_min
        bed_load = best_peak / best_unit.capacity
        delay = (vacation.date - request.earliest_date).days / window_days
        score = 0.5 * fill + 0.3 * (1 - bed_load) + 0.2 * (1 - delay)
        margin = (
            "Urgence : la marge réservée aux urgences peut être utilisée."
            if request.urgent else
            f"Marge de {request.emergency_margin:.0%} de la vacation préservée pour les urgences."
        )
        reasons = (
            f"Vacation du {vacation.date:%d/%m/%Y} en {vacation.room_name} : remplissage "
            f"{fill:.0%} après ajout ({request.room_minutes:.0f} min prévues).",
            f"{best_unit.name} : au plus {best_peak}/{best_unit.capacity} lits occupés "
            f"pendant le séjour ({request.los_days} j).",
            margin,
        )
        return Candidate(vacation.id, best_unit.id, admission, _discharge(request, admission),
                         round(score, 4), reasons)

    def _displacements(self, request: SchedulingInput) -> list[Candidate]:
        """Least disruptive postponements: fewest cases, then earliest date, then fewest minutes.

        Cases of the vacation are postponed to free operating time, then cases
        holding a bed of the right type, if the stay still finds no bed."""
        in_vacation: dict[int, list[MovableCase]] = defaultdict(list)
        for case in request.movable_cases:
            in_vacation[case.vacation_id].append(case)
        options = []
        for vacation in request.vacations:
            if not self._compatible(request, vacation):
                continue
            deficit = vacation.used_min + request.room_minutes - self._usable(request, vacation)
            moved = _free_time(in_vacation[vacation.id], deficit)
            if moved is None:
                continue
            stay = stay_days(vacation.date, _discharge(request, vacation.date))
            bed = _free_bed(request, stay, moved)
            if bed is None:
                continue
            unit, peak, for_beds = bed
            moved = moved + for_beds
            if not moved:
                continue  # fits without postponing anyone: a regular candidate
            minutes = sum(case.minutes for case in moved)
            postponed = (f"{len(moved)} interventions programmées ({minutes} min) : elles "
                         "repassent à programmer et reçoivent" if len(moved) > 1 else
                         f"1 intervention programmée ({minutes} min) : elle repasse à "
                         "programmer et reçoit")
            beds = (f" Dont {len(for_beds)} pour libérer un lit." if for_beds else "")
            options.append(((len(moved), vacation.date, minutes, vacation.id), Candidate(
                vacation.id, unit.id, vacation.date, _discharge(request, vacation.date),
                round(-len(moved) - minutes / 10_000, 4),
                (
                    f"Urgence : aucune vacation n'a de place libre (temps et lit) dans la fenêtre. "
                    f"Vacation du {vacation.date:%d/%m/%Y} en {vacation.room_name}.",
                    f"Confirmer cette date reporte {postponed} de nouvelles dates.{beds}",
                    f"{unit.name} : au plus {peak}/{unit.capacity} lits occupés pendant le séjour "
                    f"({request.los_days} j), après report.",
                    "Les interventions du jour et des jours passés ne sont jamais déplacées.",
                ),
                tuple(sorted(case.id for case in moved)),
            )))
        options.sort(key=lambda option: option[0])
        return [candidate for _, candidate in options]


def _free_time(cases: list[MovableCase], deficit: float) -> list[MovableCase] | None:
    """Fewest cases whose minutes cover the deficit; None if they cannot."""
    moved, freed = [], 0
    # Largest cases first: the fewest patients postponed
    for case in sorted(cases, key=lambda c: (-c.minutes, c.id)):
        if freed >= deficit:
            break
        moved.append(case)
        freed += case.minutes
    if freed < deficit:
        return None
    # Drop cases that are no longer needed once larger ones are moved
    for case in sorted(moved, key=lambda c: (c.minutes, c.id)):
        if len(moved) > 1 and freed - case.minutes >= deficit:
            moved.remove(case)
            freed -= case.minutes
    return moved


def _free_bed(request: SchedulingInput, stay: list[dt.date], moved: list[MovableCase]):
    """Unit for the stay once `moved` leave, postponing more bed holders if needed.

    Returns (unit, peak, extra cases) for the unit needing the fewest extra cases."""
    best = None
    for unit in request.bed_units:
        if unit.care_type != request.care_type:
            continue
        load = {day: unit.occupancy.get(day, 0) for day in stay}
        for case in moved:
            if case.bed_unit_id == unit.id:
                for day in stay_days(case.admission_date, case.discharge_date):
                    if day in load:
                        load[day] -= 1
        need = {day: load[day] + 1 - unit.capacity for day in stay}
        holders = [c for c in request.movable_cases
                   if c.bed_unit_id == unit.id and c not in moved
                   and c.admission_date <= stay[-1] and c.discharge_date >= stay[0]]
        def gain(case: MovableCase) -> int:
            """Saturated days of the stay this holder's departure relieves."""
            return sum(1 for d in stay_days(case.admission_date, case.discharge_date)
                       if need.get(d, 0) > 0)

        extra = []
        while any(n > 0 for n in need.values()):
            # The holder whose stay covers the most saturated days
            holders.sort(key=lambda c: (-gain(c), c.minutes, c.id))
            if not holders or gain(holders[0]) == 0:
                break
            case = holders.pop(0)
            extra.append(case)
            for day in stay_days(case.admission_date, case.discharge_date):
                if day in need:
                    need[day] -= 1
                    load[day] -= 1
        if any(n > 0 for n in need.values()):
            continue
        peak = max(load.values()) + 1
        key = (len(extra), peak / unit.capacity, unit.id)
        if best is None or key < best[0]:
            best = (key, unit, peak, extra)
    return None if best is None else best[1:]


def _discharge(request: SchedulingInput, admission: dt.date) -> dt.date:
    return admission + dt.timedelta(days=request.los_days - 1)


def _best_unit(request: SchedulingInput, admission: dt.date):
    """Bed unit of the right care type with the lowest relative peak over the stay."""
    stay = stay_days(admission, _discharge(request, admission))
    options = []
    for unit in request.bed_units:
        if unit.care_type != request.care_type:
            continue
        peak = max(unit.occupancy.get(day, 0) for day in stay) + 1
        if peak <= unit.capacity:
            options.append((peak / unit.capacity, unit.id, unit, peak))
    if not options:
        return None
    _, _, unit, peak = min(options)
    return unit, peak


def _prefer_distinct_dates(candidates: list[Candidate], count: int) -> list[Candidate]:
    """Best candidates first, but offer different dates before a second slot on the same day."""
    chosen: list[Candidate] = []
    seen_dates: set[dt.date] = set()
    for candidate in candidates:
        if candidate.admission_date not in seen_dates:
            chosen.append(candidate)
            seen_dates.add(candidate.admission_date)
        if len(chosen) == count:
            return chosen
    for candidate in candidates:
        if candidate not in chosen:
            chosen.append(candidate)
        if len(chosen) == count:
            break
    return chosen
