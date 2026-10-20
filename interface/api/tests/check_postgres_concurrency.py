"""Standalone check for an empty, explicitly marked disposable PostgreSQL DB.

No table is dropped. Run inside the API image with an isolated PostgreSQL
container named kyst_disposable_test and server setting
app.kyst_disposable_test=on. This does not use the pytest database fixture.
"""

from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from threading import Barrier

from sqlalchemy import inspect, text
from sqlmodel import Session, select

from api.accounts.models import User
from api.bootstrap import init_db
from api.clinical.models import Patient, Prediction, SurgicalRequest
from api.db import engine
from api.planning.models import PlannedCase, Proposal
from api.planning.service import accept, check_still_feasible, lock_proposal_resources
from api.resources.models import BedUnit, CareType, OperatingRoom, Specialty, Surgeon, Vacation


def main():
    if engine.dialect.name != "postgresql":
        raise SystemExit("Requires a dedicated disposable PostgreSQL container")
    with engine.connect() as conn:
        database, marker = conn.execute(text(
            "SELECT current_database(), current_setting('app.kyst_disposable_test', true)"
        )).one()
    if database != "kyst_disposable_test" or marker != "on" or inspect(engine).get_table_names():
        raise SystemExit("Requires the marked, empty kyst_disposable_test database")
    init_db()
    day = dt.date.today() + dt.timedelta(days=1)
    with Session(engine) as session:
        user = User(username="concurrency-test", email="test@example.org", full_name="Synthetic tester",
                    hashed_password="unused", validated=True)
        specialty = Specialty(name="Synthetic test")
        session.add_all([user, specialty])
        session.flush()
        room = OperatingRoom(name="Synthetic room", default_specialty_id=specialty.id)
        unit = BedUnit(name="Synthetic ward", care_type=CareType.conventional, capacity=1)
        surgeon = Surgeon(name="Synthetic surgeon", specialty_id=specialty.id)
        session.add_all([room, unit, surgeon])
        session.flush()
        vacation = Vacation(room_id=room.id, specialty_id=specialty.id,
                            date=day, start_time=dt.time(8), duration_min=480)
        patients = [Patient(birth_year=1970, sex=1) for _ in range(2)]
        session.add_all([vacation, *patients])
        session.flush()
        requests = [SurgicalRequest(
            patient_id=patient.id, surgeon_id=surgeon.id, specialty_id=specialty.id,
            principal_diagnosis="TEST", ccam_codes=["TEST"], earliest_date=day,
            latest_date=day, created_by=user.id,
        ) for patient in patients]
        session.add_all(requests)
        session.flush()
        predictions = [Prediction(
            request_id=request.id, room_minutes=60, los_days=2,
            care_type=CareType.conventional, model_version="synthetic", source="synthetic",
        ) for request in requests]
        session.add_all(predictions)
        session.flush()
        proposals = [Proposal(
            request_id=request.id, prediction_id=prediction.id, rank=1,
            vacation_id=vacation.id, bed_unit_id=unit.id, admission_date=day,
            discharge_date=day + dt.timedelta(days=1), planned_minutes=60,
            score=0, reasons=["Synthetic concurrency check"], scheduler="synthetic",
        ) for request, prediction in zip(requests, predictions)]
        session.add_all(proposals)
        session.flush()
        proposal_ids = [proposal.id for proposal in proposals]
        user_id = user.id
        session.commit()
    ready = Barrier(2)

    def confirm(proposal_id):
        with Session(engine) as session:
            proposal = session.get(Proposal, proposal_id)
            user = session.get(User, user_id)
            ready.wait(timeout=5)
            lock_proposal_resources(session, proposal)
            if check_still_feasible(session, proposal):
                session.rollback()
                return "rejected"
            accept(session, proposal, user)
            return "accepted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(confirm, proposal_id) for proposal_id in proposal_ids]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(results) == ["accepted", "rejected"], results
    with Session(engine) as session:
        assert len(session.exec(select(PlannedCase)).all()) == 1
    print("PostgreSQL concurrent confirmations: accepted=1, rejected=1, bookings=1")


if __name__ == "__main__":
    main()
