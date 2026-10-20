"""Independent calendar-loop validation of complete vacation assignments.

Solutions use positional indices, as in optimizer.py. ``duree_sejour`` is a
postoperative day OFFSET: 0 occupies the operation day only; k occupies k+1
calendar days. Supply explicit residual bed capacity for every modeled day.
No optimizer occupancy routine is imported or called here.
"""
from dataclasses import dataclass
from math import isfinite, sqrt
from numbers import Integral, Real
from collections.abc import Mapping


@dataclass(frozen=True)
class Validation:
    valid: bool
    feasible: bool
    errors: tuple[str, ...]
    or_overload_minutes: float = 0.0
    bed_overload_days: float = 0.0
    tail_bed_overload_days: float = 0.0
    balance_minutes: float = 0.0
    occupancy: tuple[int, ...] = ()
    session_loads: tuple[float, ...] = ()
    assigned_cases: int = 0
    missing_cases: int = 0


def _nonnegative(value, *, integer=False):
    return (not isinstance(value, bool) and isinstance(value, Real)
            and isfinite(value) and value >= 0 and (not integer or value == int(value)))


def checked_inputs(patients, sessions, bed_capacities, patient_options=None):
    """Validate raw tables and return options, capacities and required horizon.

    Extra explicitly supplied bed days are accepted and checked; scalar capacity
    and implicit tail extension are deliberately unsupported in this opt-in API.
    Capacity is residual supply after any pre-existing admissions/reservations.
    """
    for table, columns in ((patients, ("patient_id", "specialite", "duree_operatoire", "duree_sejour")),
                           (sessions, ("vacation_id", "specialite", "jour", "capacite_min"))):
        if any(column not in table for column in columns):
            raise ValueError("Missing required planning columns")
        if not table[columns[0]].is_unique or table[columns[0]].isna().any():
            raise ValueError("Planning identifiers must be unique and present")
        if table["specialite"].isna().any():
            raise ValueError("Specialty must be present")
    for column, table, integer in (("duree_operatoire", patients, False),
                                   ("duree_sejour", patients, True),
                                   ("jour", sessions, True), ("capacite_min", sessions, False)):
        if not all(_nonnegative(x, integer=integer) for x in table[column]):
            raise ValueError(f"Invalid nonnegative {'integer ' if integer else ''}{column}")
    n, m = len(patients), len(sessions)
    if patient_options is not None and len(patient_options) != n:
        raise ValueError("One options list is required per patient")
    options = []
    for i in range(n):
        compatible = [j for j in range(m)
                      if sessions.iloc[j].specialite == patients.iloc[i].specialite]
        allowed = compatible if patient_options is None else list(patient_options[i])
        if (not allowed or any(isinstance(j, bool) or not isinstance(j, Integral)
                               or j not in compatible for j in allowed)):
            raise ValueError("Every patient needs nonempty specialty-compatible integer options")
        options.append(tuple(sorted(set(int(j) for j in allowed))))
    operating_days = int(sessions.jour.max()) + 1 if m else 1
    required_days = max([operating_days] + [
        max(int(sessions.iloc[j].jour) for j in options[i])
        + int(patients.iloc[i].duree_sejour) + 1 for i in range(n)])
    try:
        beds = tuple(bed_capacities)
    except TypeError as exc:
        raise ValueError("Supply an explicit bed-capacity vector, including tail days") from exc
    if len(beds) < required_days or not all(_nonnegative(x, integer=True) for x in beds):
        raise ValueError(f"Bed capacities must be nonnegative integers covering at least {required_days} days")
    return options, tuple(int(x) for x in beds), operating_days


def validate_full_stay(patients, sessions, bed_capacities, solution, patient_options=None):
    """Return diagnostics; malformed inputs/assignments can never be feasible.

    Capacity overflows are reported for valid complete assignments. For invalid
    assignments overflow fields are unavailable (zero placeholders); consult
    ``valid`` and ``errors`` before interpreting them.
    """
    try:
        options, beds, operating_days = checked_inputs(patients, sessions, bed_capacities, patient_options)
    except (ValueError, TypeError, AttributeError) as exc:
        return Validation(False, False, (str(exc),))
    n = len(patients)
    if not isinstance(solution, Mapping):
        return Validation(False, False, ("Assignment must be a mapping",), missing_cases=n)
    errors = []
    if any(isinstance(i, bool) or not isinstance(i, Integral) for i in solution):
        errors.append("Patient indices must be integers, not booleans")
    missing = len(set(range(n)) - set(solution))
    if missing or set(solution) != set(range(n)):
        errors.append("Assignment must cover every patient exactly once, without extras")
    for i, j in solution.items():
        if (isinstance(i, bool) or not isinstance(i, Integral) or not 0 <= i < n
                or isinstance(j, bool) or not isinstance(j, Integral) or j not in options[i]):
            errors.append("Invalid or disallowed session assignment")
    if errors:
        return Validation(False, False, tuple(sorted(set(errors))), assigned_cases=n - missing,
                          missing_cases=missing)
    # Deliberately use direct calendar iteration rather than difference arrays.
    occupancy = [0] * len(beds)
    loads = [0.0] * len(sessions)
    for i, j in solution.items():
        patient, session = patients.iloc[i], sessions.iloc[j]
        loads[j] += float(patient.duree_operatoire)
        for day in range(int(session.jour), int(session.jour) + int(patient.duree_sejour) + 1):
            occupancy[day] += 1
    room_over = sum(max(0.0, load - float(sessions.iloc[j].capacite_min)) for j, load in enumerate(loads))
    bed_over = [max(0, occupied - capacity) for occupied, capacity in zip(occupancy, beds)]
    mean = sum(loads) / len(loads) if loads else 0.0
    balance = sqrt(sum((load - mean) ** 2 for load in loads) / len(loads)) if loads else 0.0
    return Validation(True, room_over == 0 and sum(bed_over) == 0, (), room_over,
                      float(sum(bed_over)), float(sum(bed_over[operating_days:])), balance,
                      tuple(occupancy), tuple(loads), n, 0)
