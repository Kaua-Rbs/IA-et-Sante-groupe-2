"""Synthetic demo resources for frontend development: `just seed` (or `PYTHONPATH=.. uv run python -m api.seed`).

Capacities follow the project brief (45 conventional beds, 21 ambulatory places);
rooms, surgeons and vacations are invented. Contains no patient data.
"""

import datetime as dt

from sqlmodel import Session, select

from api.bootstrap import init_db
from api.db import engine
from api.resources.models import BedUnit, CareType, OperatingRoom, Specialty, Surgeon, Vacation

SPECIALTIES = ["Orthopédie", "Digestif", "Urologie", "ORL"]
HALF_DAYS = [dt.time(8, 0), dt.time(13, 30)]
WEEKS = 4


def seed(session: Session) -> bool:
    if session.exec(select(Specialty)).first() is not None:
        return False
    specialties = [Specialty(name=name) for name in SPECIALTIES]
    session.add_all(specialties)
    session.flush()
    rooms = [
        OperatingRoom(name=f"Salle {i}", default_specialty_id=s.id)
        for i, s in enumerate(specialties, start=1)
    ]
    session.add_all(rooms)
    session.add_all([
        BedUnit(name="Chirurgie conventionnelle", care_type=CareType.conventional, capacity=45),
        BedUnit(name="Ambulatoire", care_type=CareType.ambulatory, capacity=21),
    ])
    session.add_all([
        Surgeon(name=f"Dr {s.name[:3].upper()}-{n}", specialty_id=s.id)
        for s in specialties for n in (1, 2)
    ])
    session.flush()
    monday = dt.date.today() - dt.timedelta(days=dt.date.today().weekday())
    for day in (monday + dt.timedelta(days=d) for d in range(7 * WEEKS)):
        if day.weekday() >= 5:
            continue
        for room in rooms:
            for start in HALF_DAYS:
                session.add(Vacation(
                    room_id=room.id, specialty_id=room.default_specialty_id,
                    date=day, start_time=start, duration_min=240,
                ))
    session.commit()
    return True


if __name__ == "__main__":
    init_db()
    with Session(engine) as session:
        print("Demo resources created." if seed(session) else "Database already has resources.")
