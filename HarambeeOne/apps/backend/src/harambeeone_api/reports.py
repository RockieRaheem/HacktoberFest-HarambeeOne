import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from harambeeone_api.auth import SchoolContext, require_permission
from harambeeone_api.database import get_session
from harambeeone_api.models import (
    AcademicClass,
    Enrollment,
    LedgerEntry,
    Payment,
    PaymentAllocation,
    Person,
    Student,
)
from harambeeone_api.periods import resolve_period

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/collections")
def collections_report(
    school_id: uuid.UUID,
    start_date: date,
    end_date: date,
    period_id: uuid.UUID | None = None,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("reports:read")),
):
    context.assert_school(school_id)
    period = resolve_period(session, school_id=school_id, period_id=period_id)
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="End date must be on or after start date")
    start = datetime.combine(start_date, time.min, tzinfo=UTC)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)
    latest_class_id = (
        select(Enrollment.class_id)
        .where(Enrollment.student_id == Student.id, Enrollment.period_id == period.id)
        .order_by(Enrollment.academic_year.desc(), Enrollment.term.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = session.execute(
        select(Payment, PaymentAllocation, Student, Person, AcademicClass)
        .select_from(Payment)
        .join(PaymentAllocation, PaymentAllocation.payment_id == Payment.id)
        .join(Student, Student.id == PaymentAllocation.student_id)
        .join(Person, Person.id == Student.person_id)
        .outerjoin(AcademicClass, AcademicClass.id == latest_class_id)
        .where(
            Payment.school_id == school_id,
            Payment.period_id == period.id,
            Payment.received_at >= start,
            Payment.received_at < end,
        )
        .order_by(Payment.received_at.desc())
        .limit(5000)
    ).all()
    billed = session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.school_id == school_id,
            LedgerEntry.period_id == period.id,
            LedgerEntry.entry_type != "payment",
        )
    ) or Decimal("0")
    channels: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    classes: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    transactions = []
    for payment, allocation, student, person, academic_class in rows:
        channels[payment.channel] += allocation.amount
        classes[academic_class.name if academic_class else "Unplaced"] += allocation.amount
        transactions.append(
            {
                "id": payment.id,
                "receipt_no": payment.receipt_no,
                "received_at": payment.received_at,
                "student_name": f"{person.first_name} {person.last_name}",
                "admission_no": student.admission_no,
                "class_name": academic_class.name if academic_class else "Unplaced",
                "channel": payment.channel,
                "reference": payment.external_reference,
                "amount": allocation.amount,
            }
        )
    collected = sum((row["amount"] for row in transactions), Decimal("0"))
    return {
        "start_date": start_date,
        "end_date": end_date,
        "billed": billed,
        "collected": collected,
        "outstanding": max(billed - collected, Decimal("0")),
        "collection_rate": float(collected / billed * 100) if billed else 0,
        "transaction_count": len(transactions),
        "average_payment": collected / len(transactions) if transactions else 0,
        "by_channel": [
            {"label": key.replace("_", " ").title(), "amount": amount}
            for key, amount in sorted(channels.items())
        ],
        "by_class": [{"label": key, "amount": amount} for key, amount in sorted(classes.items())],
        "transactions": transactions,
    }
