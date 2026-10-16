import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from harambeeone_api.auth import AuthenticatedUser, get_current_user
from harambeeone_api.database import Base, get_session
from harambeeone_api.main import app
from harambeeone_api.models import (
    AcademicClass,
    Enrollment,
    FeeStructure,
    GuardianLink,
    InstallmentRule,
    LedgerEntry,
    Payment,
    PaymentAllocation,
    Person,
    Requirement,
    School,
    SchoolMembership,
    StellarAnchor,
    Student,
    StudentFeeAssignment,
)


@pytest.fixture
def period_workspace():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    user_id = uuid.uuid4()
    with Session(engine) as session:
        school = School(name="Calendar School")
        other = School(name="Other School")
        session.add_all([school, other])
        session.flush()
        session.add(SchoolMembership(school_id=school.id, auth_user_id=user_id, role="owner"))
        session.commit()
        school_id, other_id = school.id, other.id

    def session_override():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    def user_override():
        return AuthenticatedUser(id=user_id, email="owner@example.com")

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = user_override
    try:
        yield engine, user_id, school_id, other_id, TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_year(client: TestClient, school_id: uuid.UUID, year: int = 2027) -> list[dict]:
    response = client.post(
        "/api/v1/academic-years",
        json={
            "school_id": str(school_id),
            "name": f"{year} Academic Year",
            "year": year,
            "start_date": f"{year}-01-10",
            "end_date": f"{year}-12-05",
            "periods": [
                {
                    "name": "Term 1",
                    "sequence": 1,
                    "opening_date": f"{year}-01-10",
                    "due_date": f"{year}-02-10",
                    "closing_date": f"{year}-04-20",
                },
                {
                    "name": "Term 2",
                    "sequence": 2,
                    "opening_date": f"{year}-05-15",
                    "due_date": f"{year}-06-15",
                    "closing_date": f"{year}-08-20",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["periods"]


def transition(client: TestClient, period_id: str, target: str, reason: str | None = None):
    return client.post(
        f"/api/v1/academic-periods/{period_id}/transition",
        json={"status": target, "reason": reason},
    )


def test_calendar_is_tenant_scoped_and_rejects_overlapping_dates(period_workspace) -> None:
    _engine, _user_id, school_id, other_id, client = period_workspace
    forbidden = client.post(
        "/api/v1/academic-years",
        json={
            "school_id": str(other_id),
            "name": "2027",
            "year": 2027,
            "start_date": "2027-01-01",
            "end_date": "2027-12-31",
            "periods": [
                {
                    "name": "Term 1",
                    "sequence": 1,
                    "opening_date": "2027-01-01",
                    "due_date": "2027-02-01",
                    "closing_date": "2027-04-01",
                }
            ],
        },
    )
    assert forbidden.status_code == 403

    invalid = client.post(
        "/api/v1/academic-years",
        json={
            "school_id": str(school_id),
            "name": "2027",
            "year": 2027,
            "start_date": "2027-01-01",
            "end_date": "2027-12-31",
            "periods": [
                {
                    "name": "First",
                    "sequence": 1,
                    "opening_date": "2027-01-01",
                    "due_date": "2027-02-01",
                    "closing_date": "2027-05-01",
                },
                {
                    "name": "Second",
                    "sequence": 2,
                    "opening_date": "2027-04-01",
                    "due_date": "2027-05-01",
                    "closing_date": "2027-08-01",
                },
            ],
        },
    )
    assert invalid.status_code == 422


def test_only_one_period_can_be_operational(period_workspace) -> None:
    _engine, _user_id, school_id, _other_id, client = period_workspace
    first, second = create_year(client, school_id)
    assert transition(client, first["id"], "open").status_code == 200
    duplicate = transition(client, second["id"], "open")
    assert duplicate.status_code == 409
    assert "current operational period" in duplicate.json()["detail"]


def test_closed_period_rejects_payments_and_requires_owner_reason_to_reopen(
    period_workspace,
) -> None:
    engine, user_id, school_id, _other_id, client = period_workspace
    period = create_year(client, school_id)[0]
    assert transition(client, period["id"], "open").status_code == 200
    assert transition(client, period["id"], "closing").status_code == 200
    assert transition(client, period["id"], "closed").status_code == 200
    with Session(engine) as session:
        person = Person(first_name="Closed", last_name="Learner")
        session.add(person)
        session.flush()
        student = Student(
            school_id=school_id,
            person_id=person.id,
            admission_no="CLOSED-001",
            gender="female",
        )
        session.add(student)
        session.commit()
        student_id = student.id
    payment = client.post(
        "/api/v1/payments",
        json={
            "school_id": str(school_id),
            "period_id": period["id"],
            "student_id": str(student_id),
            "external_reference": "CLOSED-PAYMENT",
            "channel": "cash",
            "amount": 1000,
        },
    )
    assert payment.status_code == 409
    assert "closed" in payment.json()["detail"]
    assert transition(client, period["id"], "open").status_code == 422
    with Session(engine) as session:
        membership = session.scalar(
            select(SchoolMembership).where(SchoolMembership.auth_user_id == user_id)
        )
        assert membership is not None
        membership.role = "bursar"
        session.commit()
    assert transition(client, period["id"], "open", "Correction").status_code == 403


def test_period_with_enrollment_activity_cannot_be_deleted(period_workspace) -> None:
    engine, _user_id, school_id, _other_id, client = period_workspace
    period = create_year(client, school_id)[0]
    with Session(engine) as session:
        academic_class = AcademicClass(
            school_id=school_id,
            name="Primary One",
            level="primary",
            sort_order=1,
        )
        person = Person(first_name="Term", last_name="Learner")
        session.add_all([academic_class, person])
        session.flush()
        student = Student(
            school_id=school_id,
            person_id=person.id,
            admission_no="TERM-001",
            gender="male",
        )
        session.add(student)
        session.flush()
        session.add(
            Enrollment(
                student_id=student.id,
                class_id=academic_class.id,
                period_id=uuid.UUID(period["id"]),
                academic_year=2027,
                term=1,
            )
        )
        session.commit()
    response = client.delete(f"/api/v1/academic-periods/{period['id']}")
    assert response.status_code == 409
    assert "activity" in response.json()["detail"]


def test_selected_period_filters_core_bursar_registers(period_workspace) -> None:
    engine, _user_id, school_id, _other_id, client = period_workspace
    first, second = create_year(client, school_id)
    first_id, second_id = uuid.UUID(first["id"]), uuid.UUID(second["id"])
    with Session(engine) as session:
        first_class = AcademicClass(
            school_id=school_id, name="Primary One", level="primary", sort_order=1
        )
        second_class = AcademicClass(
            school_id=school_id, name="Primary Two", level="primary", sort_order=2
        )
        learner = Person(first_name="Period", last_name="Learner")
        guardian = Person(first_name="Period", last_name="Guardian", phone="0700000000")
        session.add_all([first_class, second_class, learner, guardian])
        session.flush()
        student = Student(
            school_id=school_id,
            person_id=learner.id,
            admission_no="PERIOD-001",
            gender="female",
        )
        session.add(student)
        session.flush()
        session.add(
            GuardianLink(
                student_id=student.id,
                person_id=guardian.id,
                relationship="guardian",
                is_primary=True,
            )
        )
        session.add_all(
            [
                Enrollment(
                    student_id=student.id,
                    class_id=first_class.id,
                    period_id=first_id,
                    academic_year=2027,
                    term=1,
                ),
                Enrollment(
                    student_id=student.id,
                    class_id=second_class.id,
                    period_id=second_id,
                    academic_year=2027,
                    term=2,
                ),
            ]
        )
        first_fee = FeeStructure(
            school_id=school_id,
            class_id=first_class.id,
            period_id=first_id,
            name="First term fees",
            academic_year=2027,
            term=1,
            total_amount=Decimal("1000"),
        )
        second_fee = FeeStructure(
            school_id=school_id,
            class_id=second_class.id,
            period_id=second_id,
            name="Second term fees",
            academic_year=2027,
            term=2,
            total_amount=Decimal("2000"),
        )
        session.add_all([first_fee, second_fee])
        session.flush()
        session.add_all(
            [
                InstallmentRule(
                    fee_structure_id=first_fee.id,
                    name="Term 1 due",
                    amount=first_fee.total_amount,
                    due_date=date(2027, 2, 10),
                    sort_order=1,
                ),
                InstallmentRule(
                    fee_structure_id=second_fee.id,
                    name="Term 2 due",
                    amount=second_fee.total_amount,
                    due_date=date(2027, 6, 15),
                    sort_order=1,
                ),
                StudentFeeAssignment(
                    id=(first_assignment_id := uuid.uuid4()),
                    student_id=student.id,
                    fee_structure_id=first_fee.id,
                    amount=first_fee.total_amount,
                ),
                StudentFeeAssignment(
                    id=(second_assignment_id := uuid.uuid4()),
                    student_id=student.id,
                    fee_structure_id=second_fee.id,
                    amount=second_fee.total_amount,
                ),
                LedgerEntry(
                    school_id=school_id,
                    period_id=first_id,
                    student_id=student.id,
                    entry_type="fee_charge",
                    amount=first_fee.total_amount,
                    reference=f"FEE:{first_assignment_id}",
                    fee_assignment_id=first_assignment_id,
                ),
                LedgerEntry(
                    school_id=school_id,
                    period_id=second_id,
                    student_id=student.id,
                    entry_type="fee_charge",
                    amount=second_fee.total_amount,
                    reference=f"FEE:{second_assignment_id}",
                    fee_assignment_id=second_assignment_id,
                ),
                Requirement(
                    school_id=school_id,
                    period_id=first_id,
                    name="First term item",
                    code="FIRST",
                    requirement_type="bring_item",
                    academic_year=2027,
                    term=1,
                    amount=Decimal("0"),
                    quantity=Decimal("1"),
                ),
                Requirement(
                    school_id=school_id,
                    period_id=second_id,
                    name="Second term item",
                    code="SECOND",
                    requirement_type="bring_item",
                    academic_year=2027,
                    term=2,
                    amount=Decimal("0"),
                    quantity=Decimal("1"),
                ),
            ]
        )
        for index, (period_id, amount) in enumerate(
            ((first_id, Decimal("400")), (second_id, Decimal("700"))), start=1
        ):
            payment = Payment(
                school_id=school_id,
                period_id=period_id,
                receipt_no=f"PERIOD-R-{index}",
                external_reference=f"PERIOD-P-{index}",
                channel="cash",
                amount=amount,
            )
            session.add(payment)
            session.flush()
            session.add_all(
                [
                    PaymentAllocation(payment_id=payment.id, student_id=student.id, amount=amount),
                    StellarAnchor(
                        payment_id=payment.id,
                        commitment_hash=f"{index:064x}",
                        status="pending",
                    ),
                ]
            )
        session.commit()

    first_query = f"school_id={school_id}&period_id={first_id}"
    second_query = f"school_id={school_id}&period_id={second_id}"
    first_fees = client.get(f"/api/v1/fee-structures?{first_query}").json()
    second_fees = client.get(f"/api/v1/fee-structures?{second_query}").json()
    assert first_fees[0]["name"] == "First term fees"
    assert second_fees[0]["name"] == "Second term fees"
    assert client.get(f"/api/v1/requirements?{first_query}").json()[0]["code"] == "FIRST"
    assert client.get(f"/api/v1/requirements?{second_query}").json()[0]["code"] == "SECOND"
    assert (
        client.get(f"/api/v1/students?{first_query}").json()["items"][0]["class_name"]
        == "Primary One"
    )
    assert (
        client.get(f"/api/v1/students?{second_query}").json()["items"][0]["class_name"]
        == "Primary Two"
    )
    assert client.get(f"/api/v1/payments?{first_query}").json()[0]["amount"] == "400.00"
    assert client.get(f"/api/v1/payments?{second_query}").json()[0]["amount"] == "700.00"
    first_dashboard = client.get(f"/api/v1/dashboard?{first_query}").json()
    second_dashboard = client.get(f"/api/v1/dashboard?{second_query}").json()
    assert first_dashboard["metrics"]["billed"] == 1000.0
    assert second_dashboard["metrics"]["billed"] == 2000.0
    report_dates = "&start_date=2020-01-01&end_date=2100-12-31"
    first_report = client.get(f"/api/v1/reports/collections?{first_query}{report_dates}").json()
    second_report = client.get(f"/api/v1/reports/collections?{second_query}{report_dates}").json()
    assert first_report["collected"] == 400.0
    assert second_report["collected"] == 700.0
    first_arrears = client.get(
        f"/api/v1/arrears?{first_query}&as_of=2027-12-31"
    ).json()
    second_arrears = client.get(
        f"/api/v1/arrears?{second_query}&as_of=2027-12-31"
    ).json()
    assert Decimal(str(first_arrears["total_overdue"])) == Decimal("600")
    assert Decimal(str(second_arrears["total_overdue"])) == Decimal("1300")
