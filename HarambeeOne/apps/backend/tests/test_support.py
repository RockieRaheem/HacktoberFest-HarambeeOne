import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from harambeeone_api import support
from harambeeone_api.auth import AuthenticatedUser, get_current_user
from harambeeone_api.database import Base, get_session
from harambeeone_api.main import app
from harambeeone_api.models import (
    AcademicClass,
    AcademicPeriod,
    AcademicYear,
    Enrollment,
    FeeStructure,
    GuardianAccountLink,
    GuardianInvitation,
    GuardianLink,
    InstallmentRule,
    LedgerEntry,
    Payment,
    PaymentAllocation,
    Person,
    School,
    SchoolMembership,
    Student,
    StudentFeeAssignment,
    SupportCase,
    SupportPledge,
    SupportReferral,
)


@pytest.fixture
def support_workspace(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    user_id = uuid.uuid4()
    with Session(engine) as session:
        school = School(name="Trust Academy")
        other_school = School(name="Other School")
        session.add_all([school, other_school])
        session.flush()
        year = AcademicYear(
            school_id=school.id,
            name="2026 Academic Year",
            year=2026,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="open",
        )
        session.add(year)
        session.flush()
        period = AcademicPeriod(
            academic_year_id=year.id,
            school_id=school.id,
            name="Term 3",
            sequence=3,
            opening_date=date(2026, 9, 1),
            due_date=date(2026, 9, 20),
            closing_date=date(2026, 12, 5),
            status="open",
        )
        learner_person = Person(first_name="Amina", last_name="Kato")
        guardian_person = Person(first_name="Sarah", last_name="Kato")
        session.add_all([period, learner_person, guardian_person])
        session.flush()
        learner = Student(
            school_id=school.id,
            person_id=learner_person.id,
            admission_no="TA-001",
            gender="female",
        )
        session.add(learner)
        session.flush()
        guardian = GuardianLink(
            student_id=learner.id,
            person_id=guardian_person.id,
            relationship="mother",
            is_primary=True,
        )
        session.add_all(
            [
                guardian,
                SchoolMembership(school_id=school.id, auth_user_id=user_id, role="owner"),
                LedgerEntry(
                    school_id=school.id,
                    period_id=period.id,
                    student_id=learner.id,
                    entry_type="fee_charge",
                    amount=Decimal("500000"),
                    reference="BILL-001",
                    description="Term fees",
                ),
            ]
        )
        session.commit()
        ids = {
            "school": school.id,
            "other_school": other_school.id,
            "period": period.id,
            "student": learner.id,
            "guardian": guardian.id,
        }

    def session_override():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=user_id, email="owner@example.com"
    )
    monkeypatch.setattr(
        support,
        "_call_gemma",
        lambda **_kwargs: (
            "gemma-4-26b-a4b-it",
            {
                "summary": "The anonymous school balance is internally consistent.",
                "risk_level": "high",
                "observed_factors": ["Verified school balance remains unpaid"],
                "missing_information": [],
                "consistency_flags": [],
                "recommended_action": "Human owner should review and publish.",
                "safe_public_summary": (
                    "A verified learner account needs support to clear an outstanding "
                    "school obligation."
                ),
            },
        ),
    )
    try:
        yield engine, user_id, ids, TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_reviewed_campaign(client: TestClient, ids: dict) -> tuple[str, str]:
    created = client.post(
        "/api/v1/support/cases",
        json={
            "school_id": str(ids["school"]),
            "period_id": str(ids["period"]),
            "student_id": str(ids["student"]),
            "title": "Keep one learner in class",
            "public_summary": "An anonymous learner has a verified outstanding school balance.",
            "need_category": "fees",
            "target_amount": 300000,
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    consent = client.post(
        f"/api/v1/support/cases/{case_id}/consent",
        json={
            "guardian_link_id": str(ids["guardian"]),
            "method": "signed_form",
            "anonymous_publication": True,
            "gemma_processing": True,
            "cross_border_processing": True,
            "child_assent_status": "agreed",
        },
    )
    assert consent.status_code == 200, consent.text
    review = client.post(f"/api/v1/support/cases/{case_id}/ai-review", json={})
    assert review.status_code == 200, review.text
    published = client.post(f"/api/v1/support/cases/{case_id}/publish")
    assert published.status_code == 200, published.text
    return case_id, published.json()["public_code"]


def test_support_case_eligibility_reports_verified_balance(support_workspace) -> None:
    _engine, _user_id, ids, client = support_workspace
    response = client.get(
        "/api/v1/support/eligibility",
        params={
            "school_id": str(ids["school"]),
            "period_id": str(ids["period"]),
            "student_id": str(ids["student"]),
        },
    )
    assert response.status_code == 200, response.text
    assert Decimal(str(response.json()["general_outstanding"])) == Decimal("500000")
    assert response.json()["eligible"] is True


def test_guardian_referral_consent_is_scoped_and_withdrawable(support_workspace) -> None:
    engine, _user_id, ids, client = support_workspace
    guardian_user_id = uuid.uuid4()
    with Session(engine) as session:
        invitation = GuardianInvitation(
            school_id=ids["school"],
            guardian_link_id=ids["guardian"],
            token_hash="a" * 64,
            invited_email="guardian@example.com",
            status="accepted",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            created_by="owner@example.com",
            accepted_by_user_id=guardian_user_id,
            accepted_at=datetime.now(UTC),
        )
        session.add(invitation)
        session.flush()
        session.add(
            GuardianAccountLink(
                auth_user_id=guardian_user_id,
                school_id=ids["school"],
                guardian_link_id=ids["guardian"],
                invitation_id=invitation.id,
            )
        )
        referral = SupportReferral(
            school_id=ids["school"],
            period_id=ids["period"],
            student_id=ids["student"],
            guardian_link_id=ids["guardian"],
            outstanding_snapshot=Decimal("350000"),
            overdue_since=date(2026, 9, 20),
            days_overdue_snapshot=26,
            priority_band="watch",
            priority_reasons='["Verified overdue balance"]',
            created_by="owner@example.com",
        )
        session.add(referral)
        session.commit()
        referral_id = referral.id
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=guardian_user_id, email="guardian@example.com"
    )

    consent = client.post(
        f"/api/v1/support/guardian/referrals/{referral_id}/consent",
        json={
            "action": "grant",
            "privacy_notice_version": "2026-10-v1",
            "guardian_authority_confirmed": True,
            "age_verification_method": "school_record",
            "anonymous_publication": True,
            "gemma_processing": False,
            "cross_border_processing": False,
            "child_assent_status": "agreed",
        },
    )
    assert consent.status_code == 200, consent.text
    assert consent.json()["status"] == "consented"
    assert consent.json()["gemma_processing"] is False
    with Session(engine) as session:
        campaign = SupportCase(
            school_id=ids["school"],
            period_id=ids["period"],
            student_id=ids["student"],
            public_code="HSP-WITHDRAWAL",
            title="Anonymous support",
            public_summary="A private learner account has a verified school obligation.",
            need_category="fees",
            target_amount=Decimal("350000"),
            status="published",
            created_by="owner@example.com",
        )
        session.add(campaign)
        session.commit()
        campaign_id = campaign.id

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid.uuid4(), email="stranger@example.com"
    )
    forbidden = client.post(f"/api/v1/support/guardian/referrals/{referral_id}/withdraw")
    assert forbidden.status_code == 404

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=guardian_user_id, email="guardian@example.com"
    )
    withdrawn = client.post(f"/api/v1/support/guardian/referrals/{referral_id}/withdraw")
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"
    assert withdrawn.json()["anonymous_publication"] is False
    with Session(engine) as session:
        assert session.get(SupportCase, campaign_id).status == "withdrawn"


def test_school_creates_referral_only_from_live_arrears(support_workspace) -> None:
    engine, _user_id, ids, client = support_workspace
    guardian_user_id = uuid.uuid4()
    with Session(engine) as session:
        academic_class = AcademicClass(
            school_id=ids["school"], name="Primary Seven", level="primary", sort_order=7
        )
        session.add(academic_class)
        session.flush()
        structure = FeeStructure(
            school_id=ids["school"],
            class_id=academic_class.id,
            period_id=ids["period"],
            name="Term fees",
            academic_year=2026,
            term=3,
            total_amount=Decimal("500000"),
            status="published",
        )
        session.add(structure)
        session.flush()
        session.add_all(
            [
                InstallmentRule(
                    fee_structure_id=structure.id,
                    name="Opening installment",
                    amount=Decimal("500000"),
                    due_date=date(2026, 9, 20),
                    sort_order=1,
                ),
                StudentFeeAssignment(
                    student_id=ids["student"],
                    fee_structure_id=structure.id,
                    amount=Decimal("500000"),
                ),
                Enrollment(
                    student_id=ids["student"],
                    class_id=academic_class.id,
                    period_id=ids["period"],
                    academic_year=2026,
                    term=3,
                ),
            ]
        )
        invitation = GuardianInvitation(
            school_id=ids["school"],
            guardian_link_id=ids["guardian"],
            token_hash="b" * 64,
            invited_email="guardian@example.com",
            status="accepted",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            created_by="owner@example.com",
            accepted_by_user_id=guardian_user_id,
            accepted_at=datetime.now(UTC),
        )
        session.add(invitation)
        session.flush()
        session.add(
            GuardianAccountLink(
                auth_user_id=guardian_user_id,
                school_id=ids["school"],
                guardian_link_id=ids["guardian"],
                invitation_id=invitation.id,
            )
        )
        session.commit()

    candidates = client.get(
        "/api/v1/support/referral-candidates",
        params={"school_id": str(ids["school"]), "period_id": str(ids["period"])},
    )
    assert candidates.status_code == 200, candidates.text
    candidate = candidates.json()["items"][0]
    assert candidate["student_id"] == str(ids["student"])
    assert candidate["guardian_portal_linked"] is True
    payload = {
        "school_id": str(ids["school"]),
        "period_id": str(ids["period"]),
        "student_id": str(ids["student"]),
        "guardian_link_id": str(ids["guardian"]),
    }
    created = client.post("/api/v1/support/referrals", json=payload)
    duplicate = client.post("/api/v1/support/referrals", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "awaiting_consent"
    assert duplicate.status_code == 409


def test_gemma_status_is_school_authenticated_and_keyless(support_workspace) -> None:
    _engine, _user_id, _ids, client = support_workspace
    response = client.get("/api/v1/support/gemma")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "gemma-4-26b-a4b-it"
    assert body["decision_authority"] == "human"
    assert "GEMINI" not in response.text
    assert "api_key" not in response.text.casefold()


def test_owner_may_publish_without_gemma_when_consent_declines_it(support_workspace) -> None:
    _engine, _user_id, ids, client = support_workspace
    created = client.post(
        "/api/v1/support/cases",
        json={
            "school_id": str(ids["school"]),
            "period_id": str(ids["period"]),
            "student_id": str(ids["student"]),
            "title": "Keep one learner in class",
            "public_summary": "An anonymous learner has a verified outstanding school balance.",
            "need_category": "fees",
            "target_amount": 300000,
        },
    )
    case_id = created.json()["id"]
    consent = client.post(
        f"/api/v1/support/cases/{case_id}/consent",
        json={
            "guardian_link_id": str(ids["guardian"]),
            "method": "signed_form",
            "anonymous_publication": True,
            "gemma_processing": True,
            "cross_border_processing": False,
            "child_assent_status": "agreed",
        },
    )
    assert consent.status_code == 422
    consent = client.post(
        f"/api/v1/support/cases/{case_id}/consent",
        json={
            "guardian_link_id": str(ids["guardian"]),
            "method": "signed_form",
            "anonymous_publication": True,
            "gemma_processing": False,
            "cross_border_processing": False,
            "child_assent_status": "agreed",
        },
    )
    assert consent.status_code == 200, consent.text
    blocked = client.post(f"/api/v1/support/cases/{case_id}/ai-review", json={})
    assert blocked.status_code == 409
    published = client.post(f"/api/v1/support/cases/{case_id}/publish")
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"


def test_support_campaign_posts_verified_contribution_end_to_end(support_workspace) -> None:
    engine, _user_id, ids, client = support_workspace
    case_id, code = create_reviewed_campaign(client, ids)
    public = client.get(f"/api/v1/support/public/campaigns/{code}")
    assert public.status_code == 200
    assert "Amina" not in public.text and "TA-001" not in public.text
    pledge = client.post(
        f"/api/v1/support/public/campaigns/{code}/pledges",
        json={
            "external_reference": "MM-9001",
            "donor_display_name": "Community donor",
            "amount": 300000,
        },
    )
    assert pledge.status_code == 201, pledge.text
    reference = pledge.json()["public_reference"]
    with Session(engine) as session:
        pledge_id = session.scalar(
            select(SupportPledge.id).where(SupportPledge.public_reference == reference)
        )
    verified = client.post(f"/api/v1/support/pledges/{pledge_id}/verify", json={"action": "verify"})
    assert verified.status_code == 200, verified.text
    proof = client.post(
        f"/api/v1/support/cases/{case_id}/attestations",
        json={
            "attestation_type": "enrolment",
            "statement": "The supported learner remains enrolled in the current school period.",
            "attendance_band": "90_plus",
            "is_public": True,
        },
    )
    assert proof.status_code == 201, proof.text
    tracked = client.get(f"/api/v1/support/public/campaigns/{code}/pledges/{reference}")
    assert tracked.json()["allocation"]["status"] == "posted_to_verified_learner_obligation"
    final_public = client.get(f"/api/v1/support/public/campaigns/{code}").json()
    assert Decimal(str(final_public["verified_amount"])) == Decimal("300000.00")
    assert Decimal(str(final_public["pending_amount"])) == Decimal("0.00")
    assert final_public["status"] == "funded"
    assert final_public["attestations"][0]["attendance_band"] == "90_plus"
    with Session(engine) as session:
        assert session.scalar(select(func.count(Payment.id))) == 1
        assert session.scalar(select(func.count(PaymentAllocation.id))) == 1
        support_case = session.get(SupportCase, uuid.UUID(case_id))
        balance = session.scalar(
            select(func.sum(LedgerEntry.amount)).where(
                LedgerEntry.student_id == ids["student"],
                LedgerEntry.period_id == ids["period"],
            )
        )
        assert support_case.status == "funded"
        assert balance == Decimal("200000.00")


def test_support_rejects_identity_overfunding_duplicates_and_cross_tenant(
    support_workspace,
) -> None:
    engine, _user_id, ids, client = support_workspace
    identity = client.post(
        "/api/v1/support/cases",
        json={
            "school_id": str(ids["school"]),
            "period_id": str(ids["period"]),
            "student_id": str(ids["student"]),
            "title": "Support Amina today",
            "public_summary": "This learner needs help with an outstanding school balance.",
            "need_category": "fees",
            "target_amount": 100000,
        },
    )
    assert identity.status_code == 422
    too_large = client.post(
        "/api/v1/support/cases",
        json={
            "school_id": str(ids["school"]),
            "period_id": str(ids["period"]),
            "student_id": str(ids["student"]),
            "title": "Anonymous learner support",
            "public_summary": "A verified learner obligation requires timely community support.",
            "need_category": "fees",
            "target_amount": 600000,
        },
    )
    assert too_large.status_code == 422
    cross_tenant = client.get(f"/api/v1/support/cases?school_id={ids['other_school']}")
    assert cross_tenant.status_code == 403
    _case_id, code = create_reviewed_campaign(client, ids)
    first = client.post(
        f"/api/v1/support/public/campaigns/{code}/pledges",
        json={"external_reference": "DUP-100", "amount": 100000},
    )
    second = client.post(
        f"/api/v1/support/public/campaigns/{code}/pledges",
        json={"external_reference": "DUP-100", "amount": 100000},
    )
    assert first.status_code == 201 and second.status_code == 409
    with Session(engine) as session:
        assert session.scalar(select(func.count(SupportPledge.id))) == 1


def test_failed_settlement_leaves_no_partial_financial_records(support_workspace) -> None:
    engine, _user_id, ids, client = support_workspace
    _case_id, code = create_reviewed_campaign(client, ids)
    pledge = client.post(
        f"/api/v1/support/public/campaigns/{code}/pledges",
        json={"external_reference": "ROLLBACK-1", "amount": 200000},
    ).json()
    with Session(engine) as session:
        pledge_id = session.scalar(
            select(SupportPledge.id).where(
                SupportPledge.public_reference == pledge["public_reference"]
            )
        )
        period = session.get(AcademicPeriod, ids["period"])
        period.status = "closed"
        session.commit()
    failed = client.post(f"/api/v1/support/pledges/{pledge_id}/verify", json={"action": "verify"})
    assert failed.status_code == 409
    with Session(engine) as session:
        assert session.scalar(select(func.count(Payment.id))) == 0
        assert session.get(SupportPledge, pledge_id).status == "pending"
