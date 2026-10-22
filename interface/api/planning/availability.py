"""Room closures and surgeon absences: the two rules every planning path applies.

- A room closure shortens the vacations it overlaps (minutes lost, union of windows).
- A surgeon absent during any part of a vacation cannot operate in it at all.
"""

import datetime as dt
from collections.abc import Iterable

from sqlmodel import Session, select

from api.resources.models import Unavailability, VacationBase


def load_unavailabilities(session: Session, start: dt.date, end: dt.date) -> list[Unavailability]:
    return list(session.exec(select(Unavailability).where(
        Unavailability.start_date <= end, Unavailability.end_date >= start,
    )).all())


def room_closures(vacation: VacationBase, unavailabilities: Iterable[Unavailability]) -> list[Unavailability]:
    """Closures of the vacation's room that overlap it."""
    return [u for u in unavailabilities
            if u.room_id is not None and u.room_id == getattr(vacation, "room_id", None)
            and u.overlap(vacation) is not None]


def surgeon_absences(
    vacation: VacationBase, unavailabilities: Iterable[Unavailability], surgeon_id: int | None,
) -> list[Unavailability]:
    """Absences of the operating surgeon that overlap the vacation, even partly."""
    if surgeon_id is None:
        return []
    return [u for u in unavailabilities
            if u.surgeon_id == surgeon_id and u.overlap(vacation) is not None]


def open_minutes(vacation: VacationBase, unavailabilities: Iterable[Unavailability]) -> int:
    """Vacation minutes left once room closures are removed (overlaps counted once)."""
    lost, reach = 0, None
    for start, end in sorted(u.overlap(vacation) for u in room_closures(vacation, unavailabilities)):
        if reach is not None and start < reach:
            start = reach
        if start < end:
            lost += end - start
        reach = end if reach is None else max(reach, end)
    return vacation.duration_min - lost


def describe(unavailability: Unavailability, names: dict[tuple[str, int], str]) -> str:
    """`names` maps ("room", id) and ("surgeon", id) to display names."""
    if unavailability.room_id is not None:
        what = f"{names.get(('room', unavailability.room_id), 'Salle')} fermée"
    else:
        what = f"{names.get(('surgeon', unavailability.surgeon_id), 'Chirurgien')} absent"
    reason = f" ({unavailability.reason})" if unavailability.reason else ""
    return f"{what} {unavailability.describe()}{reason}"
