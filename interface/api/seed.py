"""Synthetic starting data for a running surgical service: `just seed` (or `PYTHONPATH=.. uv run python -m api.seed`).

Capacities follow the project brief (45 conventional beds, 21 ambulatory places);
rooms, surgeons, patients and activity are invented. Contains no patient data.

Activity is built around today so the dashboard looks like a service in use:
three weeks of completed cases with observed durations (prediction accuracy),
patients currently in the wards, four weeks of bookings that thin out with
distance, and pending requests with open date proposals. Every prediction and
date goes through the configured predictors and scheduler (`AI_BACKEND`).
"""

import datetime as dt
import random
from math import ceil
from dataclasses import dataclass

from sqlmodel import Session, select

from api.accounts.models import User
from api.ai.contracts import BedUnitLoad, SchedulingInput, Scheduler, VacationSlot
from api.ai.providers import Predictors, get_predictors, get_scheduler
from api.bootstrap import init_db
from api.clinical import service as clinical
from api.clinical.models import Patient, RequestStatus, SurgicalRequest
from api.config import settings
from api.db import engine
from api.planning import service as planning
from api.planning.capacity import bed_occupancy, used_minutes
from api.planning.models import CaseStatus, PlannedCase, Proposal, ProposalStatus
from api.resources.models import BedUnit, CareType, OperatingRoom, Specialty, Surgeon, Vacation

HALF_DAYS = [dt.time(8, 0), dt.time(13, 30)]
PAST_WEEKS = 3
FUTURE_WEEKS = 5
# Share of the usable vacation time already booked, by week from today
FUTURE_FILL = [0.9, 0.75, 0.5, 0.25, 0.0]
PENDING_WITH_PROPOSALS = 16
PENDING_NEW = 4
CANCELLATION_RATE = 0.04


@dataclass(frozen=True)
class Procedure:
    label: str
    diagnosis: str  # CIM-10
    ccam: tuple[str, ...]
    weight: int
    age: tuple[int, int]  # mean, standard deviation
    female_share: float


CATALOG: dict[str, list[Procedure]] = {
    "Orthopédie": [
        Procedure("Prothèse totale de hanche", "M16.1", ("NEKA020",), 3, (71, 9), 0.6),
        Procedure("Prothèse totale de genou", "M17.1", ("NFKA007",), 3, (72, 8), 0.65),
        Procedure("Méniscectomie arthroscopique", "S83.2", ("NFFC004",), 3, (45, 12), 0.35),
        Procedure("Canal carpien", "G56.0", ("AHPA009",), 4, (55, 13), 0.7),
        Procedure("Hallux valgus", "M20.1", ("NDPA009",), 2, (54, 12), 0.85),
    ],
    "Digestif": [
        Procedure("Cholécystectomie", "K80.2", ("HMFC004",), 4, (52, 15), 0.65),
        Procedure("Cure de hernie inguinale", "K40.9", ("LMMA006",), 4, (58, 15), 0.15),
        Procedure("Appendicectomie", "K35.8", ("HHFA016",), 2, (30, 14), 0.5),
        Procedure("Colectomie", "C18.7", ("HHFA024",), 1, (68, 10), 0.45),
        Procedure("Sleeve gastrectomie", "E66.0", ("HFFC018",), 1, (42, 10), 0.75),
    ],
    "Urologie": [
        Procedure("Résection transurétrale de prostate", "N40", ("JGFE023",), 3, (70, 8), 0.0),
        Procedure("Résection transurétrale de vessie", "C67.9", ("JDFE002",), 3, (72, 9), 0.25),
        Procedure("Urétéroscopie", "N20.1", ("JCGE003",), 3, (50, 14), 0.4),
        Procedure("Néphrectomie", "C64", ("JAFC019",), 1, (63, 11), 0.35),
        Procedure("Circoncision", "N47", ("JHFA009",), 2, (30, 18), 0.0),
    ],
    "ORL": [
        Procedure("Amygdalectomie", "J35.0", ("FAFA014",), 4, (18, 10), 0.5),
        Procedure("Septoplastie", "J34.2", ("GAMA007",), 3, (38, 12), 0.35),
        Procedure("Aérateurs transtympaniques", "H65.3", ("CASA001",), 3, (12, 12), 0.45),
        Procedure("Thyroïdectomie totale", "E04.2", ("KCFA005",), 2, (52, 13), 0.8),
    ],
}

SURGEONS = {
    "Orthopédie": ["Dr Martin", "Dr Lefèvre"],
    "Digestif": ["Dr Bernard", "Dr Moreau"],
    "Urologie": ["Dr Petit", "Dr Roux"],
    "ORL": ["Dr Garnier", "Dr Fontaine"],
}


class Seeder:
    def __init__(self, session: Session, author: User, specialties: list[Specialty],
                 surgeons: list[Surgeon], predictors: Predictors, scheduler: Scheduler,
                 rng: random.Random):
        self.session = session
        self.specialty_names = {s.id: s.name for s in specialties}
        self.surgeons = {s.id: s for s in surgeons}
        self.author = author
        self.predictors = predictors
        self.scheduler = scheduler
        self.rng = rng
        self.today = dt.date.today()
        self.refs: set[str] = set()
        self.counts = {"patients": 0, "done": 0, "in_ward": 0, "booked": 0, "pending": 0}

    def _moment(self, day: dt.date) -> dt.datetime:
        return dt.datetime.combine(day, dt.time(self.rng.randint(8, 17), self.rng.randint(0, 59)))

    def _patient(self, procedure: Procedure) -> Patient:
        age = max(1, min(95, round(self.rng.gauss(*procedure.age))))
        ref = f"P{self.rng.randrange(10**7):07d}"
        while ref in self.refs:
            ref = f"P{self.rng.randrange(10**7):07d}"
        self.refs.add(ref)
        patient = Patient(external_ref=ref, birth_year=self.today.year - age,
                          sex=2 if self.rng.random() < procedure.female_share else 1)
        self.session.add(patient)
        self.counts["patients"] += 1
        return patient

    def _request(self, surgeon: Surgeon, earliest: dt.date, latest: dt.date | None,
                 created: dt.date) -> SurgicalRequest:
        procedures = CATALOG[self.specialty_names[surgeon.specialty_id]]
        procedure = self.rng.choices(procedures, [p.weight for p in procedures])[0]
        patient = self._patient(procedure)
        request = SurgicalRequest(
            patient_id=patient.id, surgeon_id=surgeon.id, specialty_id=surgeon.specialty_id,
            principal_diagnosis=procedure.diagnosis, ccam_codes=list(procedure.ccam),
            intervention_type=procedure.label, earliest_date=earliest, latest_date=latest,
            created_by=self.author.id, created_at=self._moment(created),
        )
        self.session.add(request)
        self.session.flush()
        return request

    def _slot(self, vacation: Vacation, room: OperatingRoom) -> VacationSlot:
        used = used_minutes(self.session, [vacation.id]).get(vacation.id, 0)
        return VacationSlot(vacation.id, vacation.date, room.name, vacation.specialty_id,
                            vacation.surgeon_id, vacation.duration_min, used)

    def book(self, vacation: Vacation, room: OperatingRoom, surgeon: Surgeon) -> PlannedCase | None:
        """Request, prediction and accepted proposal for one case in this vacation."""
        lead = self.rng.randint(10, 45)
        created = vacation.date - dt.timedelta(days=lead)
        request = self._request(surgeon, vacation.date - dt.timedelta(days=self.rng.randint(0, 5)),
                                vacation.date + dt.timedelta(days=self.rng.randint(7, 30)), created)
        prediction = clinical.build_prediction(self.session, request, self.predictors)
        prediction.created_at = request.created_at
        horizon = vacation.date + dt.timedelta(days=prediction.los_days)
        occupancy = bed_occupancy(self.session, vacation.date, horizon)
        units = self.session.exec(select(BedUnit)).all()
        candidates = self.scheduler.propose(SchedulingInput(
            specialty_id=request.specialty_id, surgeon_id=request.surgeon_id,
            room_minutes=prediction.room_minutes, los_days=prediction.los_days,
            care_type=prediction.care_type, earliest_date=vacation.date,
            latest_date=vacation.date, vacations=(self._slot(vacation, room),),
            bed_units=tuple(BedUnitLoad(u.id, u.name, u.care_type, u.capacity,
                                        dict(occupancy.get(u.id, {}))) for u in units),
            emergency_margin=settings.EMERGENCY_MARGIN,
        ), 1)
        if not candidates:
            # Vacation or beds full: this request was never made
            self.session.rollback()
            self.counts["patients"] -= 1
            return None
        best = candidates[0]
        self.session.add(prediction)
        decided = request.created_at + dt.timedelta(minutes=self.rng.randint(2, 30))
        proposal = Proposal(
            request_id=request.id, prediction_id=prediction.id, rank=1,
            vacation_id=best.vacation_id, bed_unit_id=best.bed_unit_id,
            admission_date=best.admission_date, discharge_date=best.discharge_date,
            planned_minutes=ceil(prediction.room_minutes), score=best.score,
            reasons=list(best.reasons), scheduler=self.scheduler.name,
            status=ProposalStatus.accepted, created_at=request.created_at,
            decided_by=self.author.id, decided_at=decided,
        )
        self.session.add(proposal)
        self.session.flush()
        case = PlannedCase(
            request_id=request.id, proposal_id=proposal.id, vacation_id=best.vacation_id,
            bed_unit_id=best.bed_unit_id, admission_date=best.admission_date,
            discharge_date=best.discharge_date, planned_minutes=proposal.planned_minutes,
            created_at=decided,
        )
        request.status = RequestStatus.scheduled
        if self.rng.random() < CANCELLATION_RATE:
            case.status = CaseStatus.cancelled
            request.status = RequestStatus.cancelled
        elif case.discharge_date < self.today:
            case.status = CaseStatus.done
            request.status = RequestStatus.done
            case.actual_room_minutes = max(15, round(
                prediction.room_minutes * self.rng.lognormvariate(0, 0.2)))
            if prediction.los_days == 1:
                case.actual_los_days = 1 if self.rng.random() < 0.93 else 2
            else:
                case.actual_los_days = max(1, prediction.los_days + self.rng.choice((-1, 0, 0, 0, 1, 2)))
            self.counts["done"] += 1
        elif case.admission_date <= self.today:
            self.counts["in_ward"] += 1
        else:
            self.counts["booked"] += 1
        self.session.add_all([case, request])
        self.session.commit()
        return case

    def fill(self, vacation: Vacation, room: OperatingRoom, target: float) -> None:
        surgeon = self.surgeons[vacation.surgeon_id]
        usable = vacation.duration_min * (1 - settings.EMERGENCY_MARGIN)
        misses = 0
        while misses < 3 and used_minutes(self.session, [vacation.id]).get(vacation.id, 0) < target * usable:
            if self.book(vacation, room, surgeon) is None:
                misses += 1

    def pending(self) -> None:
        surgeons = list(self.surgeons.values())
        for i in range(PENDING_WITH_PROPOSALS + PENDING_NEW):
            surgeon = self.rng.choice(surgeons)
            earliest = self.today + dt.timedelta(days=self.rng.randint(3, 12))
            request = self._request(surgeon, earliest, earliest + dt.timedelta(days=30),
                                    self.today - dt.timedelta(days=self.rng.randint(0, 4)))
            self.session.commit()
            if i < PENDING_WITH_PROPOSALS:
                planning.propose(self.session, request, self.predictors, self.scheduler)
            self.counts["pending"] += 1

    def run(self, vacations: list[Vacation], rooms: dict[int, OperatingRoom]) -> None:
        for vacation in sorted(vacations, key=lambda v: (v.date, v.start_time, v.room_id)):
            weeks_ahead = (vacation.date - self.today).days // 7
            if vacation.date < self.today:
                target = self.rng.uniform(0.75, 0.95)
            elif weeks_ahead < len(FUTURE_FILL):
                target = FUTURE_FILL[weeks_ahead] * self.rng.uniform(0.8, 1.1)
            else:
                target = 0
            if target > 0:
                self.fill(vacation, rooms[vacation.room_id], target)
        self.pending()


def seed_author(session: Session) -> User:
    """Requests record who created them: the first administrator, or any account."""
    author = None
    if settings.FIRST_ADMIN_EMAIL:
        author = session.exec(select(User).where(User.email == settings.FIRST_ADMIN_EMAIL)).first()
    author = author or session.exec(select(User)).first()
    if author is None:
        raise SystemExit("No user account: set FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD first")
    return author


def seed(session: Session) -> dict[str, int] | None:
    if session.exec(select(Specialty)).first() is not None:
        return None
    author = seed_author(session)
    specialties = [Specialty(name=name) for name in CATALOG]
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
    surgeons = {
        s.id: [Surgeon(name=name, specialty_id=s.id) for name in SURGEONS[s.name]]
        for s in specialties
    }
    session.add_all([surgeon for pair in surgeons.values() for surgeon in pair])
    session.flush()

    # Each room's half-days alternate between the two surgeons of its specialty
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    vacations = []
    for day in (monday + dt.timedelta(days=d) for d in range(-7 * PAST_WEEKS, 7 * FUTURE_WEEKS)):
        if day.weekday() >= 5:
            continue
        for room in rooms:
            pair = surgeons[room.default_specialty_id]
            for half, start in enumerate(HALF_DAYS):
                vacations.append(Vacation(
                    room_id=room.id, specialty_id=room.default_specialty_id,
                    surgeon_id=pair[(day.toordinal() + half) % 2].id,
                    date=day, start_time=start, duration_min=240,
                ))
    session.add_all(vacations)
    session.commit()

    seeder = Seeder(session, author, specialties,
                    [surgeon for pair in surgeons.values() for surgeon in pair],
                    get_predictors(), get_scheduler(), random.Random(2026))
    seeder.run(vacations, {room.id: room for room in rooms})
    return seeder.counts


if __name__ == "__main__":
    init_db()
    with Session(engine) as session:
        counts = seed(session)
        if counts is None:
            print("Database already has resources.")
        else:
            print("Demo resources created.")
            print(", ".join(f"{key}: {value}" for key, value in counts.items()))
