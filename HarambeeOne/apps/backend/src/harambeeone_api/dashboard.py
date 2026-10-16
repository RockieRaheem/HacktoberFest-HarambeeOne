import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from harambeeone_api.auth import SchoolContext, require_permission
from harambeeone_api.database import get_session
from harambeeone_api.finance import record_payment
from harambeeone_api.models import (
    Enrollment,
    LedgerEntry,
    Payment,
    PaymentAllocation,
    Person,
    School,
    StatementTransaction,
    Student,
)
from harambeeone_api.periods import resolve_period
from harambeeone_api.schemas import PaymentCreate

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


class CashPayment(BaseModel):
    school_id: uuid.UUID = Field(alias="schoolId")
    learner_ref: str = Field(alias="learnerRef", min_length=3, max_length=50)
    payer_name: str = Field(alias="payerName", min_length=2, max_length=100)
    amount: int = Field(gt=0, le=100_000_000)
    note: str | None = Field(default=None, max_length=240)
    period_id: uuid.UUID | None = Field(default=None, alias="periodId")


@router.get("")
def overview(
    school_id: uuid.UUID,
    period_id: uuid.UUID | None = None,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("school:read")),
) -> dict:
    context.assert_school(school_id)
    period = resolve_period(session, school_id=school_id, period_id=period_id)
    summary = session.execute(
        select(
            School.id,
            School.name,
            select(func.count(Student.id))
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(
                Student.school_id == School.id,
                Student.status == "active",
                Enrollment.period_id == period.id,
            )
            .correlate(School)
            .scalar_subquery(),
            select(func.coalesce(func.sum(LedgerEntry.amount), 0))
            .where(
                LedgerEntry.school_id == School.id,
                LedgerEntry.period_id == period.id,
                LedgerEntry.entry_type != "payment",
            )
            .correlate(School)
            .scalar_subquery(),
            select(func.coalesce(func.sum(Payment.amount), 0))
            .where(
                Payment.school_id == School.id,
                Payment.period_id == period.id,
                Payment.status == "reconciled",
            )
            .correlate(School)
            .scalar_subquery(),
            select(func.count(StatementTransaction.id))
            .where(
                StatementTransaction.school_id == School.id,
                StatementTransaction.status != "reconciled",
            )
            .correlate(School)
            .scalar_subquery(),
            select(func.count(StatementTransaction.id))
            .where(
                StatementTransaction.school_id == School.id,
                StatementTransaction.status == "suggested",
            )
            .correlate(School)
            .scalar_subquery(),
        ).where(School.id == school_id)
    ).one_or_none()
    if summary is None:
        raise HTTPException(status_code=404, detail="No institution configured")
    school_id, school_name, active, billed, collected, unreconciled, suggested = summary
    rows = session.execute(
        select(Payment, PaymentAllocation, Student, Person)
        .select_from(Payment)
        .join(PaymentAllocation, PaymentAllocation.payment_id == Payment.id)
        .join(Student, Student.id == PaymentAllocation.student_id)
        .join(Person, Student.person_id == Person.id)
        .where(Payment.school_id == school_id, Payment.period_id == period.id)
        .order_by(Payment.received_at.desc())
        .limit(8)
    ).all()
    activity = [
        {
            "id": str(payment.id),
            "occurredAt": payment.received_at.isoformat(),
            "learner": f"{person.first_name} {person.last_name}",
            "learnerRef": student.admission_no,
            "description": f"{payment.channel.replace('_', ' ').title()} payment",
            "amount": float(allocation.amount),
            "currency": "UGX",
            "status": "RECONCILED",
        }
        for payment, allocation, student, person in rows
    ]
    return {
        "mode": "LIVE",
        "school": {"id": str(school_id), "name": school_name},
        "period": {
            "id": str(period.id),
            "label": f"{period.name} · {period.academic_year.name}",
        },
        "generatedAt": datetime.now(UTC).isoformat(),
        "metrics": {
            "billed": float(billed),
            "collected": float(collected),
            "outstanding": float(max(billed - collected, 0)),
            "activeLearners": active,
            "accountsInArrears": active if billed > collected else 0,
            "unreconciledCount": unreconciled,
            "suggestedMatches": suggested,
        },
        "weeklyCollections": [0, 0, 0, 0, 0, 0, float(collected)],
        "activity": activity,
        "attention": [],
    }


@router.post("/cash-payments")
def cash_payment(
    payload: CashPayment,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("payments:write")),
) -> dict:
    context.assert_school(payload.school_id)
    student = session.scalar(
        select(Student).where(
            Student.school_id == payload.school_id,
            Student.admission_no == payload.learner_ref.strip(),
        )
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Learner reference not found")
    reference = f"CASH-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
    result = record_payment(
        PaymentCreate(
            school_id=student.school_id,
            student_id=student.id,
            external_reference=reference,
            payer_name=payload.payer_name,
            note=payload.note,
            channel="cash",
            amount=payload.amount,
            period_id=payload.period_id,
        ),
        session,
        context,
    )
    return {"receiptNo": result.receipt_no, "paymentId": str(result.id)}
