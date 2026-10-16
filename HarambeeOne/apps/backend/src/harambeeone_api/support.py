import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from harambeeone_api.auth import (
    AuthenticatedUser,
    SchoolContext,
    get_current_user,
    require_permission,
)
from harambeeone_api.database import get_session
from harambeeone_api.gemma import GEMMA_REVIEW_SCHEMA, call_gemma, gemma_status
from harambeeone_api.models import (
    AuditEvent,
    GuardianAccountLink,
    GuardianLink,
    LedgerEntry,
    Payment,
    PaymentAllocation,
    Person,
    School,
    StellarAnchor,
    Student,
    StudentRequirement,
    SupportAiReview,
    SupportAttestation,
    SupportCase,
    SupportConsent,
    SupportPledge,
    SupportReferral,
)
from harambeeone_api.periods import resolve_period
from harambeeone_api.schemas import (
    SupportAiReviewCreate,
    SupportAttestationCreate,
    SupportCaseCreate,
    SupportConsentCreate,
    SupportPledgeCreate,
    SupportPledgeVerify,
    SupportReferralConsent,
    SupportReferralCreate,
)

router = APIRouter(prefix="/api/v1/support", tags=["learner support"])

# Re-exported so existing tests can patch the Support workflow boundary.
_call_gemma = call_gemma

PRIVACY_NOTICE_VERSION = "2026-10-v1"
PRIVACY_NOTICE = (
    "The school will use the learner's private identity only to verify eligibility and post "
    "support to the school account. Donors see an anonymous campaign code, need category, "
    "target, verified totals and redacted outcomes—not the learner or guardian identity. "
    "Gemma and processing outside Uganda are optional. Consent may be withdrawn at any time."
)


def _guardian_referral(session: Session, referral_id: uuid.UUID, user_id: uuid.UUID):
    referral = session.scalar(
        select(SupportReferral)
        .join(
            GuardianAccountLink,
            GuardianAccountLink.guardian_link_id == SupportReferral.guardian_link_id,
        )
        .where(SupportReferral.id == referral_id, GuardianAccountLink.auth_user_id == user_id)
    )
    if referral is None:
        raise HTTPException(status_code=404, detail="Support referral not found")
    return referral


def _referral_payload(session: Session, referral: SupportReferral) -> dict:
    student = session.get(Student, referral.student_id)
    person = session.get(Person, student.person_id) if student else None
    school = session.get(School, referral.school_id)
    return {
        "id": referral.id,
        "school_id": referral.school_id,
        "school_name": school.name if school else "School",
        "student_id": referral.student_id,
        "learner_name": (f"{person.first_name} {person.last_name}" if person else "Linked learner"),
        "admission_no": student.admission_no if student else None,
        "outstanding_snapshot": referral.outstanding_snapshot,
        "overdue_since": referral.overdue_since,
        "days_overdue_snapshot": referral.days_overdue_snapshot,
        "priority_band": referral.priority_band,
        "priority_reasons": json.loads(referral.priority_reasons),
        "status": referral.status,
        "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        "privacy_notice": PRIVACY_NOTICE,
        "anonymous_publication": referral.anonymous_publication,
        "gemma_processing": referral.gemma_processing,
        "cross_border_processing": referral.cross_border_processing,
        "child_assent_status": referral.child_assent_status,
        "child_assent_reason": referral.child_assent_reason,
        "consented_at": referral.consented_at,
        "withdrawn_at": referral.withdrawn_at,
    }


def _money_total(session: Session, case_id: uuid.UUID, *statuses: str) -> Decimal:
    return session.scalar(
        select(func.coalesce(func.sum(SupportPledge.amount), 0)).where(
            SupportPledge.case_id == case_id,
            SupportPledge.status.in_(statuses),
        )
    ) or Decimal("0")


def _latest_review(session: Session, case_id: uuid.UUID) -> SupportAiReview | None:
    return session.scalar(
        select(SupportAiReview)
        .where(SupportAiReview.case_id == case_id, SupportAiReview.status == "completed")
        .order_by(SupportAiReview.created_at.desc())
        .limit(1)
    )


def _active_consent(session: Session, case_id: uuid.UUID) -> SupportConsent | None:
    return session.scalar(
        select(SupportConsent).where(
            SupportConsent.case_id == case_id, SupportConsent.status == "active"
        )
    )


def _assert_public_text(case: SupportCase, student: Student, person: Person, value: str) -> None:
    normalized = value.casefold()
    private_values = [
        student.admission_no,
        person.first_name,
        person.middle_name,
        person.last_name,
        student.learner_identification_number,
    ]
    for private_value in private_values:
        if (
            private_value
            and len(private_value.strip()) >= 3
            and private_value.casefold() in normalized
        ):
            raise HTTPException(
                status_code=422,
                detail="Public campaign text must not identify the learner",
            )


def _assert_review_identity(
    case: SupportCase, student: Student, person: Person, result: dict
) -> None:
    for key in ("summary", "recommended_action", "safe_public_summary"):
        _assert_public_text(case, student, person, str(result[key]))
    for key in ("observed_factors", "missing_information", "consistency_flags"):
        for item in result[key]:
            _assert_public_text(case, student, person, item)


def _private_case(session: Session, case_id: uuid.UUID, school_id: uuid.UUID) -> SupportCase:
    support_case = session.scalar(
        select(SupportCase).where(SupportCase.id == case_id, SupportCase.school_id == school_id)
    )
    if support_case is None:
        raise HTTPException(status_code=404, detail="Support case not found")
    return support_case


def _public_campaign(session: Session, public_code: str) -> SupportCase:
    support_case = session.scalar(
        select(SupportCase).where(
            SupportCase.public_code == public_code.upper(),
            SupportCase.status.in_(("published", "funded", "closed")),
        )
    )
    if support_case is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return support_case


def _public_payload(session: Session, support_case: SupportCase, *, detail: bool) -> dict:
    verified = _money_total(session, support_case.id, "verified")
    pending = _money_total(session, support_case.id, "pending")
    school = session.get(School, support_case.school_id)
    payload = {
        "public_code": support_case.public_code,
        "title": support_case.title,
        "public_summary": support_case.public_summary,
        "need_category": support_case.need_category,
        "target_amount": support_case.target_amount,
        "verified_amount": verified,
        "pending_amount": pending,
        "remaining_amount": max(support_case.target_amount - verified, Decimal("0")),
        "currency": support_case.currency,
        "status": support_case.status,
        "school": school.name if school else "Verified participating school",
        "published_at": support_case.published_at,
        "privacy": "Learner identity is held privately by the school and is never published.",
    }
    if not detail:
        return payload
    review = _latest_review(session, support_case.id)
    attestations = session.scalars(
        select(SupportAttestation)
        .where(
            SupportAttestation.case_id == support_case.id,
            SupportAttestation.is_public.is_(True),
        )
        .order_by(SupportAttestation.verified_at.desc())
    ).all()
    payload["ai_review"] = None
    if review:
        result = json.loads(review.result_json)
        payload["ai_review"] = {
            "model": review.model_name,
            "observed_factors": result.get("observed_factors", []),
            "consistency_flags": result.get("consistency_flags", []),
            "recommended_action": result.get("recommended_action"),
        }
    payload["attestations"] = [
        {
            "type": item.attestation_type,
            "statement": item.statement,
            "attendance_band": item.attendance_band,
            "evidence_hash": item.evidence_hash,
            "verified_at": item.verified_at,
        }
        for item in attestations
    ]
    return payload


@router.get("/gemma")
def get_gemma_status(
    _context: SchoolContext = Depends(require_permission("support:read")),
):
    return {
        **gemma_status(),
        "required_fields": list(GEMMA_REVIEW_SCHEMA["required"]),
    }


@router.get("/referral-candidates")
def list_referral_candidates(
    school_id: uuid.UUID,
    period_id: uuid.UUID,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:read")),
):
    from harambeeone_api.finance import list_arrears

    context.assert_school(school_id)
    arrears = list_arrears(school_id, period_id, None, session, context)
    referrals = {
        item.student_id: item
        for item in session.scalars(
            select(SupportReferral).where(
                SupportReferral.school_id == school_id,
                SupportReferral.period_id == period_id,
            )
        ).all()
    }
    rows = []
    for item in arrears.items:
        guardian_row = session.execute(
            select(GuardianLink, Person)
            .join(Person, Person.id == GuardianLink.person_id)
            .where(GuardianLink.student_id == item.student_id)
            .order_by(GuardianLink.is_primary.desc())
            .limit(1)
        ).one_or_none()
        guardian, guardian_person = guardian_row if guardian_row else (None, None)
        portal_linked = bool(
            guardian
            and session.scalar(
                select(GuardianAccountLink.id).where(
                    GuardianAccountLink.guardian_link_id == guardian.id
                )
            )
        )
        referral = referrals.get(item.student_id)
        band = (
            "urgent" if item.days_overdue >= 60 else "high" if item.days_overdue >= 30 else "watch"
        )
        rows.append(
            {
                **item.model_dump(),
                "priority_band": band,
                "priority_reasons": [
                    f"UGX {item.overdue_amount:,.0f} is overdue",
                    f"Oldest unpaid installment is {item.days_overdue} days overdue",
                ],
                "guardian_link_id": guardian.id if guardian else None,
                "guardian_email": guardian_person.email if guardian_person else None,
                "guardian_portal_linked": portal_linked,
                "referral_id": referral.id if referral else None,
                "referral_status": referral.status if referral else None,
            }
        )
    return {"privacy_notice_version": PRIVACY_NOTICE_VERSION, "items": rows}


@router.post("/referrals", status_code=status.HTTP_201_CREATED)
def create_support_referral(
    payload: SupportReferralCreate,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:write")),
):
    from harambeeone_api.finance import list_arrears

    context.assert_school(payload.school_id)
    resolve_period(session, school_id=context.school_id, period_id=payload.period_id, writable=True)
    account = next(
        (
            item
            for item in list_arrears(
                payload.school_id, payload.period_id, None, session, context
            ).items
            if item.student_id == payload.student_id
        ),
        None,
    )
    if account is None:
        raise HTTPException(status_code=422, detail="Learner has no overdue fee obligation")
    guardian = session.scalar(
        select(GuardianLink)
        .join(Student, Student.id == GuardianLink.student_id)
        .where(
            GuardianLink.id == payload.guardian_link_id,
            GuardianLink.student_id == payload.student_id,
            Student.school_id == context.school_id,
        )
    )
    if guardian is None:
        raise HTTPException(status_code=422, detail="Guardian does not belong to this learner")
    if not session.scalar(
        select(GuardianAccountLink.id).where(GuardianAccountLink.guardian_link_id == guardian.id)
    ):
        raise HTTPException(
            status_code=409,
            detail="Invite the guardian and wait for portal access before creating a referral",
        )
    band = (
        "urgent"
        if account.days_overdue >= 60
        else "high"
        if account.days_overdue >= 30
        else "watch"
    )
    referral = SupportReferral(
        school_id=context.school_id,
        period_id=payload.period_id,
        student_id=payload.student_id,
        guardian_link_id=guardian.id,
        outstanding_snapshot=account.overdue_amount,
        overdue_since=account.overdue_since,
        days_overdue_snapshot=account.days_overdue,
        priority_band=band,
        priority_reasons=json.dumps(
            [
                f"UGX {account.overdue_amount:,.0f} is overdue",
                f"Oldest unpaid installment is {account.days_overdue} days overdue",
            ]
        ),
        created_by=context.actor,
    )
    session.add(referral)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="This learner already has a referral for the period"
        ) from error
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="support_referral",
            entity_id=referral.id,
            action="created",
            actor=context.actor,
            summary="Created a private arrears-based guardian referral",
        )
    )
    session.commit()
    return _referral_payload(session, referral)


@router.get("/referrals")
def list_school_referrals(
    school_id: uuid.UUID,
    period_id: uuid.UUID,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:read")),
):
    context.assert_school(school_id)
    rows = session.scalars(
        select(SupportReferral)
        .where(
            SupportReferral.school_id == school_id,
            SupportReferral.period_id == period_id,
        )
        .order_by(SupportReferral.created_at.desc())
    ).all()
    return [_referral_payload(session, item) for item in rows]


@router.get("/guardian/referrals")
def list_guardian_referrals(
    user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rows = session.scalars(
        select(SupportReferral)
        .join(
            GuardianAccountLink,
            GuardianAccountLink.guardian_link_id == SupportReferral.guardian_link_id,
        )
        .where(GuardianAccountLink.auth_user_id == user.id)
        .order_by(SupportReferral.created_at.desc())
    ).all()
    return [_referral_payload(session, item) for item in rows]


@router.post("/guardian/referrals/{referral_id}/consent")
def decide_referral_consent(
    referral_id: uuid.UUID,
    payload: SupportReferralConsent,
    user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    referral = _guardian_referral(session, referral_id, user.id)
    if referral.status not in {"awaiting_consent", "declined"}:
        raise HTTPException(status_code=409, detail="This consent decision can no longer change")
    now = datetime.now(UTC)
    referral.privacy_notice_version = payload.privacy_notice_version
    referral.guardian_authority_confirmed = payload.guardian_authority_confirmed
    referral.age_verification_method = payload.age_verification_method
    referral.anonymous_publication = payload.anonymous_publication
    referral.gemma_processing = payload.gemma_processing
    referral.cross_border_processing = payload.cross_border_processing
    referral.child_assent_status = payload.child_assent_status
    referral.child_assent_reason = (payload.child_assent_reason or "").strip() or None
    referral.consented_by_user_id = user.id
    referral.consented_at = now
    referral.withdrawn_at = None
    referral.status = "consented" if payload.action == "grant" else "declined"
    session.add(
        AuditEvent(
            school_id=referral.school_id,
            entity_type="support_referral",
            entity_id=referral.id,
            action=referral.status,
            actor=user.email or str(user.id),
            summary=f"Guardian {referral.status} private support participation",
        )
    )
    session.commit()
    return _referral_payload(session, referral)


@router.post("/guardian/referrals/{referral_id}/withdraw")
def withdraw_referral_consent(
    referral_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    referral = _guardian_referral(session, referral_id, user.id)
    if referral.status == "withdrawn":
        return _referral_payload(session, referral)
    referral.status = "withdrawn"
    referral.withdrawn_at = datetime.now(UTC)
    referral.anonymous_publication = False
    referral.gemma_processing = False
    referral.cross_border_processing = False
    open_cases = session.scalars(
        select(SupportCase).where(
            SupportCase.student_id == referral.student_id,
            SupportCase.period_id == referral.period_id,
            SupportCase.status.in_(("draft", "review", "published")),
        )
    ).all()
    for support_case in open_cases:
        support_case.status = "withdrawn"
    session.add(
        AuditEvent(
            school_id=referral.school_id,
            entity_type="support_referral",
            entity_id=referral.id,
            action="withdrawn",
            actor=user.email or str(user.id),
            summary="Guardian withdrew support participation consent",
        )
    )
    session.commit()
    return _referral_payload(session, referral)


@router.get("/public/campaigns")
def list_public_campaigns(session: Session = Depends(get_session)):
    cases = session.scalars(
        select(SupportCase)
        .where(SupportCase.status.in_(("published", "funded", "closed")))
        .order_by(SupportCase.published_at.desc())
    ).all()
    return [_public_payload(session, item, detail=False) for item in cases]


@router.get("/public/campaigns/{public_code}")
def get_public_campaign(public_code: str, session: Session = Depends(get_session)):
    return _public_payload(session, _public_campaign(session, public_code), detail=True)


@router.post("/public/campaigns/{public_code}/pledges", status_code=status.HTTP_201_CREATED)
def create_public_pledge(
    public_code: str,
    payload: SupportPledgeCreate,
    session: Session = Depends(get_session),
):
    support_case = session.scalar(
        select(SupportCase)
        .where(SupportCase.public_code == public_code.upper(), SupportCase.status == "published")
        .with_for_update()
    )
    if support_case is None:
        raise HTTPException(status_code=404, detail="Open campaign not found")
    reserved = _money_total(session, support_case.id, "pending", "verified")
    available = max(support_case.target_amount - reserved, Decimal("0"))
    if payload.amount > available:
        raise HTTPException(
            status_code=422,
            detail=f"Pledge exceeds the remaining campaign amount of UGX {available:,.0f}",
        )
    pledge = SupportPledge(
        case_id=support_case.id,
        school_id=support_case.school_id,
        public_reference=f"HSP-{uuid.uuid4().hex[:16].upper()}",
        external_reference=payload.external_reference.strip(),
        donor_display_name=(payload.donor_display_name or "").strip() or None,
        amount=payload.amount,
        currency=support_case.currency,
    )
    session.add(pledge)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="This contribution reference already exists"
        ) from error
    return {
        "public_reference": pledge.public_reference,
        "status": pledge.status,
        "amount": pledge.amount,
        "currency": pledge.currency,
        "message": "Contribution is pending independent settlement verification by the school.",
    }


@router.get("/public/campaigns/{public_code}/pledges/{public_reference}")
def track_public_pledge(
    public_code: str,
    public_reference: str,
    session: Session = Depends(get_session),
):
    support_case = _public_campaign(session, public_code)
    pledge = session.scalar(
        select(SupportPledge).where(
            SupportPledge.case_id == support_case.id,
            SupportPledge.public_reference == public_reference.upper(),
        )
    )
    if pledge is None:
        raise HTTPException(status_code=404, detail="Contribution reference not found")
    payment = session.get(Payment, pledge.payment_id) if pledge.payment_id else None
    return {
        "public_reference": pledge.public_reference,
        "campaign_code": support_case.public_code,
        "amount": pledge.amount,
        "currency": pledge.currency,
        "status": pledge.status,
        "created_at": pledge.created_at,
        "verified_at": pledge.verified_at,
        "allocation": (
            {
                "status": "posted_to_verified_learner_obligation",
                "receipt_no": payment.receipt_no,
            }
            if payment
            else None
        ),
    }


@router.get("/cases")
def list_support_cases(
    school_id: uuid.UUID,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:read")),
):
    context.assert_school(school_id)
    rows = session.execute(
        select(SupportCase, Student, Person)
        .join(Student, Student.id == SupportCase.student_id)
        .join(Person, Person.id == Student.person_id)
        .where(SupportCase.school_id == school_id)
        .order_by(SupportCase.created_at.desc())
    ).all()
    return [
        {
            "id": item.id,
            "public_code": item.public_code,
            "student_id": student.id,
            "student_name": f"{person.first_name} {person.last_name}",
            "admission_no": student.admission_no,
            "title": item.title,
            "need_category": item.need_category,
            "target_amount": item.target_amount,
            "verified_amount": _money_total(session, item.id, "verified"),
            "pending_amount": _money_total(session, item.id, "pending"),
            "currency": item.currency,
            "risk_level": item.risk_level,
            "status": item.status,
            "has_consent": _active_consent(session, item.id) is not None,
            "has_ai_review": _latest_review(session, item.id) is not None,
            "created_at": item.created_at,
        }
        for item, student, person in rows
    ]


@router.get("/eligibility")
def support_case_eligibility(
    school_id: uuid.UUID,
    student_id: uuid.UUID,
    period_id: uuid.UUID | None = None,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:read")),
) -> dict:
    context.assert_school(school_id)
    period = resolve_period(
        session,
        school_id=context.school_id,
        period_id=period_id,
    )
    student = session.scalar(
        select(Student).where(
            Student.id == student_id,
            Student.school_id == context.school_id,
        )
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    outstanding = session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.school_id == context.school_id,
            LedgerEntry.period_id == period.id,
            LedgerEntry.student_id == student.id,
        )
    ) or Decimal("0")
    outstanding = max(outstanding, Decimal("0"))
    return {
        "student_id": student.id,
        "period_id": period.id,
        "general_outstanding": outstanding,
        "eligible": outstanding > 0,
    }


@router.get("/cases/{case_id}")
def get_support_case(
    case_id: uuid.UUID,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:read")),
):
    support_case = _private_case(session, case_id, context.school_id)
    student = session.get(Student, support_case.student_id)
    person = session.get(Person, student.person_id) if student else None
    if student is None or person is None:
        raise HTTPException(status_code=409, detail="Learner record is incomplete")
    guardian_rows = session.execute(
        select(GuardianLink, Person)
        .join(Person, Person.id == GuardianLink.person_id)
        .where(GuardianLink.student_id == student.id)
        .order_by(GuardianLink.is_primary.desc(), Person.first_name)
    ).all()
    consent = _active_consent(session, case_id)
    review = _latest_review(session, case_id)
    return {
        "id": support_case.id,
        "public_code": support_case.public_code,
        "student": {
            "id": student.id,
            "name": f"{person.first_name} {person.last_name}",
            "admission_no": student.admission_no,
        },
        "title": support_case.title,
        "public_summary": support_case.public_summary,
        "need_category": support_case.need_category,
        "target_amount": support_case.target_amount,
        "verified_amount": _money_total(session, case_id, "verified"),
        "pending_amount": _money_total(session, case_id, "pending"),
        "currency": support_case.currency,
        "risk_level": support_case.risk_level,
        "risk_reasons": json.loads(support_case.risk_reasons),
        "status": support_case.status,
        "guardians": [
            {
                "id": guardian.id,
                "name": f"{guardian_person.first_name} {guardian_person.last_name}",
                "relationship": guardian.relationship,
                "is_primary": guardian.is_primary,
            }
            for guardian, guardian_person in guardian_rows
        ],
        "consent": (
            {
                "method": consent.method,
                "gemma_processing": consent.gemma_processing,
                "cross_border_processing": consent.cross_border_processing,
                "child_assent_status": consent.child_assent_status,
                "recorded_at": consent.recorded_at,
            }
            if consent
            else None
        ),
        "ai_review": json.loads(review.result_json) if review else None,
    }


@router.post("/cases", status_code=status.HTTP_201_CREATED)
def create_support_case(
    payload: SupportCaseCreate,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:write")),
):
    context.assert_school(payload.school_id)
    period = resolve_period(
        session,
        school_id=context.school_id,
        period_id=payload.period_id,
        writable=True,
    )
    student = session.scalar(
        select(Student).where(
            Student.id == payload.student_id, Student.school_id == context.school_id
        )
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    person = session.get(Person, student.person_id)
    if person is None:
        raise HTTPException(status_code=409, detail="Learner identity record is incomplete")
    assignment = None
    if payload.requirement_assignment_id:
        assignment = session.scalar(
            select(StudentRequirement).where(
                StudentRequirement.id == payload.requirement_assignment_id,
                StudentRequirement.student_id == student.id,
            )
        )
        if assignment is None:
            raise HTTPException(status_code=422, detail="Requirement does not belong to learner")
        paid = session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
                PaymentAllocation.requirement_assignment_id == assignment.id
            )
        ) or Decimal("0")
        outstanding = max(assignment.expected_amount - paid, Decimal("0"))
    else:
        outstanding = session.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.school_id == context.school_id,
                LedgerEntry.period_id == period.id,
                LedgerEntry.student_id == student.id,
            )
        ) or Decimal("0")
        outstanding = max(outstanding, Decimal("0"))
    if outstanding <= 0:
        raise HTTPException(
            status_code=409, detail="Learner has no verified outstanding obligation"
        )
    if payload.target_amount > outstanding:
        raise HTTPException(
            status_code=422,
            detail=f"Campaign target exceeds the verified balance of UGX {outstanding:,.0f}",
        )
    duplicate_filters = [
        SupportCase.student_id == student.id,
        SupportCase.period_id == period.id,
        SupportCase.status.notin_(("closed", "withdrawn")),
    ]
    if assignment:
        duplicate_filters.append(SupportCase.requirement_assignment_id == assignment.id)
    else:
        duplicate_filters.append(SupportCase.requirement_assignment_id.is_(None))
    if session.scalar(select(SupportCase.id).where(*duplicate_filters)):
        raise HTTPException(
            status_code=409, detail="An active campaign already covers this obligation"
        )
    placeholder = SupportCase(
        school_id=context.school_id,
        period_id=period.id,
        student_id=student.id,
        requirement_assignment_id=assignment.id if assignment else None,
        public_code=f"HS-{uuid.uuid4().hex[:10].upper()}",
        title=payload.title.strip(),
        public_summary=payload.public_summary.strip(),
        need_category=payload.need_category,
        target_amount=payload.target_amount,
        risk_level="high" if datetime.now(UTC).date() > period.due_date else "review",
        risk_reasons=json.dumps(
            [
                f"UGX {outstanding:,.0f} remains outstanding in the selected period",
                (
                    f"The school due date passed on {period.due_date.isoformat()}"
                    if datetime.now(UTC).date() > period.due_date
                    else f"The school due date is {period.due_date.isoformat()}"
                ),
            ]
        ),
        created_by=context.actor,
    )
    _assert_public_text(placeholder, student, person, placeholder.title)
    _assert_public_text(placeholder, student, person, placeholder.public_summary)
    session.add(placeholder)
    session.flush()
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="support_case",
            entity_id=placeholder.id,
            action="created",
            actor=context.actor,
            summary=f"Created anonymous support case {placeholder.public_code}",
        )
    )
    session.commit()
    return {"id": placeholder.id, "public_code": placeholder.public_code, "status": "draft"}


@router.post("/cases/{case_id}/consent")
def record_support_consent(
    case_id: uuid.UUID,
    payload: SupportConsentCreate,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:write")),
):
    support_case = _private_case(session, case_id, context.school_id)
    if support_case.status not in {"draft", "review"}:
        raise HTTPException(status_code=409, detail="Consent cannot change after publication")
    if not payload.anonymous_publication:
        raise HTTPException(
            status_code=422, detail="Harambee Support only permits anonymous campaigns"
        )
    guardian = session.scalar(
        select(GuardianLink).where(
            GuardianLink.id == payload.guardian_link_id,
            GuardianLink.student_id == support_case.student_id,
        )
    )
    if guardian is None:
        raise HTTPException(status_code=422, detail="Guardian does not belong to this learner")
    consent = session.scalar(select(SupportConsent).where(SupportConsent.case_id == case_id))
    if consent is None:
        consent = SupportConsent(
            case_id=case_id,
            school_id=context.school_id,
            guardian_link_id=guardian.id,
            recorded_by=context.actor,
        )
        session.add(consent)
    consent.guardian_link_id = guardian.id
    consent.method = payload.method
    consent.scope_version = payload.scope_version
    consent.anonymous_publication = True
    consent.gemma_processing = payload.gemma_processing
    consent.cross_border_processing = payload.cross_border_processing
    consent.child_assent_status = payload.child_assent_status
    consent.status = "active"
    consent.withdrawn_at = None
    support_case.status = "review"
    session.flush()
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="support_consent",
            entity_id=consent.id,
            action="recorded",
            actor=context.actor,
            summary=f"Recorded scoped guardian consent for {support_case.public_code}",
        )
    )
    session.commit()
    return {"status": consent.status, "child_assent_status": consent.child_assent_status}


@router.post("/cases/{case_id}/ai-review")
def review_support_case(
    case_id: uuid.UUID,
    payload: SupportAiReviewCreate,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:write")),
):
    support_case = _private_case(session, case_id, context.school_id)
    consent = _active_consent(session, case_id)
    if consent is None or not consent.gemma_processing or not consent.cross_border_processing:
        raise HTTPException(
            status_code=409,
            detail="Guardian consent for Gemma and cross-border processing is required",
        )
    facts = {
        "campaign_code": support_case.public_code,
        "need_category": support_case.need_category,
        "target_amount": str(support_case.target_amount),
        "currency": support_case.currency,
        "rule_based_risk": support_case.risk_level,
        "rule_based_reasons": json.loads(support_case.risk_reasons),
        "draft_public_summary": support_case.public_summary,
    }
    input_material = (
        json.dumps(facts, sort_keys=True)
        + hashlib.sha256((payload.evidence_image_base64 or "").encode()).hexdigest()
    )
    model_name, result = _call_gemma(
        case_payload=facts,
        evidence_image_base64=payload.evidence_image_base64,
        evidence_mime_type=payload.evidence_mime_type,
    )
    student = session.get(Student, support_case.student_id)
    person = session.get(Person, student.person_id) if student else None
    if student is None or person is None:
        raise HTTPException(status_code=409, detail="Learner record is incomplete")
    _assert_review_identity(support_case, student, person, result)
    safe_summary = str(result["safe_public_summary"]).strip()
    support_case.public_summary = safe_summary
    support_case.risk_level = result["risk_level"]
    review = SupportAiReview(
        case_id=support_case.id,
        school_id=context.school_id,
        model_name=model_name,
        input_hash=hashlib.sha256(input_material.encode()).hexdigest(),
        result_json=json.dumps(result),
        created_by=context.actor,
    )
    session.add(review)
    session.flush()
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="support_ai_review",
            entity_id=review.id,
            action="created",
            actor=context.actor,
            summary=f"Gemma reviewed anonymous support case {support_case.public_code}",
        )
    )
    session.commit()
    return {"id": review.id, "model": model_name, **result}


@router.post("/cases/{case_id}/publish")
def publish_support_case(
    case_id: uuid.UUID,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:approve")),
):
    support_case = _private_case(session, case_id, context.school_id)
    if support_case.status in {"published", "funded", "closed"}:
        return {"public_code": support_case.public_code, "status": support_case.status}
    consent = _active_consent(session, case_id)
    if consent is None or not consent.anonymous_publication:
        raise HTTPException(
            status_code=409, detail="Active anonymous publication consent is required"
        )
    if consent.child_assent_status == "declined":
        raise HTTPException(status_code=409, detail="The learner declined publication")
    referral = session.scalar(
        select(SupportReferral).where(
            SupportReferral.student_id == support_case.student_id,
            SupportReferral.period_id == support_case.period_id,
        )
    )
    if referral and (
        referral.status != "consented"
        or not referral.anonymous_publication
        or referral.child_assent_status == "declined"
    ):
        raise HTTPException(
            status_code=409,
            detail="Active guardian portal consent and an acceptable learner view are required",
        )
    if consent.gemma_processing and _latest_review(session, case_id) is None:
        raise HTTPException(status_code=409, detail="Complete the Gemma review before publication")
    support_case.status = "published"
    support_case.approved_by = context.actor
    support_case.published_at = datetime.now(UTC)
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="support_case",
            entity_id=support_case.id,
            action="published",
            actor=context.actor,
            summary=f"Published anonymous support campaign {support_case.public_code}",
        )
    )
    session.commit()
    return {"public_code": support_case.public_code, "status": support_case.status}


@router.get("/cases/{case_id}/pledges")
def list_case_pledges(
    case_id: uuid.UUID,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:read")),
):
    _private_case(session, case_id, context.school_id)
    rows = session.scalars(
        select(SupportPledge)
        .where(SupportPledge.case_id == case_id)
        .order_by(SupportPledge.created_at.desc())
    ).all()
    return [
        {
            "id": item.id,
            "public_reference": item.public_reference,
            "external_reference": item.external_reference,
            "donor_display_name": item.donor_display_name or "Anonymous donor",
            "amount": item.amount,
            "currency": item.currency,
            "status": item.status,
            "created_at": item.created_at,
            "verified_at": item.verified_at,
        }
        for item in rows
    ]


@router.post("/pledges/{pledge_id}/verify")
def verify_support_pledge(
    pledge_id: uuid.UUID,
    payload: SupportPledgeVerify,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:write")),
):
    pledge = session.scalar(
        select(SupportPledge)
        .where(SupportPledge.id == pledge_id, SupportPledge.school_id == context.school_id)
        .with_for_update()
    )
    if pledge is None:
        raise HTTPException(status_code=404, detail="Contribution not found")
    if pledge.status != "pending":
        raise HTTPException(status_code=409, detail="Contribution has already been decided")
    support_case = session.scalar(
        select(SupportCase).where(SupportCase.id == pledge.case_id).with_for_update()
    )
    if support_case is None:
        raise HTTPException(status_code=404, detail="Support case not found")
    if payload.action == "reject":
        pledge.status = "rejected"
        session.add(
            AuditEvent(
                school_id=context.school_id,
                entity_type="support_pledge",
                entity_id=pledge.id,
                action="rejected",
                actor=context.actor,
                summary=f"Rejected {pledge.public_reference}: {payload.reason}",
            )
        )
        session.commit()
        return {"public_reference": pledge.public_reference, "status": pledge.status}
    period = resolve_period(
        session,
        school_id=context.school_id,
        period_id=support_case.period_id,
        writable=True,
    )
    verified_before = _money_total(session, support_case.id, "verified")
    if verified_before + pledge.amount > support_case.target_amount:
        raise HTTPException(status_code=409, detail="Verification would overfund the campaign")
    student = session.get(Student, support_case.student_id)
    if student is None or student.school_id != context.school_id:
        raise HTTPException(status_code=404, detail="Learner not found")
    if support_case.requirement_assignment_id:
        assignment = session.get(StudentRequirement, support_case.requirement_assignment_id)
        if assignment is None:
            raise HTTPException(status_code=409, detail="Covered requirement no longer exists")
        already_paid = session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
                PaymentAllocation.requirement_assignment_id == assignment.id
            )
        ) or Decimal("0")
        live_outstanding = max(assignment.expected_amount - already_paid, Decimal("0"))
    else:
        live_outstanding = session.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.school_id == context.school_id,
                LedgerEntry.period_id == period.id,
                LedgerEntry.student_id == student.id,
            )
        ) or Decimal("0")
        live_outstanding = max(live_outstanding, Decimal("0"))
    if pledge.amount > live_outstanding:
        raise HTTPException(
            status_code=409,
            detail="Contribution exceeds the learner's current verified obligation",
        )
    payment_id = uuid.uuid4()
    financial_reference = (
        "HSP-"
        + hashlib.sha256(f"{support_case.id}:{pledge.external_reference}".encode())
        .hexdigest()[:24]
        .upper()
    )
    payment = Payment(
        id=payment_id,
        school_id=context.school_id,
        period_id=period.id,
        receipt_no=f"H1S-{payment_id.hex[:11].upper()}",
        external_reference=financial_reference,
        payer_name=pledge.donor_display_name or "Anonymous donor",
        note=f"Verified support contribution {pledge.public_reference}",
        channel="sponsor",
        amount=pledge.amount,
    )
    session.add(payment)
    session.flush()
    allocation = PaymentAllocation(
        id=uuid.uuid4(),
        payment_id=payment.id,
        student_id=student.id,
        requirement_assignment_id=support_case.requirement_assignment_id,
        amount=pledge.amount,
    )
    ledger = LedgerEntry(
        id=uuid.uuid4(),
        school_id=context.school_id,
        period_id=period.id,
        student_id=student.id,
        entry_type="payment",
        amount=-pledge.amount,
        reference=financial_reference,
        description=f"Anonymous learner support {support_case.public_code}",
        payment_id=payment.id,
    )
    commitment = hashlib.sha256(
        f"{payment.id}|{pledge.amount}|{pledge.currency}|{financial_reference}".encode()
    ).hexdigest()
    anchor = StellarAnchor(
        id=uuid.uuid4(),
        payment_id=payment.id,
        commitment_hash=commitment,
        status="pending",
    )
    pledge.status = "verified"
    pledge.payment_id = payment.id
    pledge.verified_at = datetime.now(UTC)
    pledge.verified_by = context.actor
    if verified_before + pledge.amount == support_case.target_amount:
        support_case.status = "funded"
    session.add_all([allocation, ledger, anchor])
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="support_pledge",
            entity_id=pledge.id,
            action="verified",
            actor=context.actor,
            summary=f"Verified and allocated {pledge.public_reference}",
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Contribution could not be posted twice"
        ) from error
    return {
        "public_reference": pledge.public_reference,
        "status": pledge.status,
        "receipt_no": payment.receipt_no,
        "campaign_status": support_case.status,
    }


@router.post("/cases/{case_id}/attestations", status_code=status.HTTP_201_CREATED)
def create_support_attestation(
    case_id: uuid.UUID,
    payload: SupportAttestationCreate,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("support:write")),
):
    support_case = _private_case(session, case_id, context.school_id)
    if support_case.status not in {"published", "funded", "closed"}:
        raise HTTPException(status_code=409, detail="Publish the campaign before adding proof")
    if payload.attestation_type == "enrolment" and not payload.attendance_band:
        raise HTTPException(
            status_code=422, detail="Attendance band is required for enrolment proof"
        )
    student = session.get(Student, support_case.student_id)
    person = session.get(Person, student.person_id) if student else None
    if student is None or person is None:
        raise HTTPException(status_code=409, detail="Learner record is incomplete")
    if payload.is_public:
        _assert_public_text(support_case, student, person, payload.statement)
    attestation = SupportAttestation(
        case_id=support_case.id,
        school_id=context.school_id,
        attestation_type=payload.attestation_type,
        statement=payload.statement.strip(),
        attendance_band=payload.attendance_band,
        evidence_hash=payload.evidence_hash.lower() if payload.evidence_hash else None,
        is_public=payload.is_public,
        verified_by=context.actor,
    )
    session.add(attestation)
    session.flush()
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="support_attestation",
            entity_id=attestation.id,
            action="created",
            actor=context.actor,
            summary=f"Recorded {payload.attestation_type} proof for {support_case.public_code}",
        )
    )
    session.commit()
    return {"id": attestation.id, "verified_at": attestation.verified_at}
