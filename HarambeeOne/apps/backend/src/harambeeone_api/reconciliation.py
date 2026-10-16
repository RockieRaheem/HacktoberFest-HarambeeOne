import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from harambeeone_api.auth import SchoolContext, require_permission
from harambeeone_api.database import get_session
from harambeeone_api.models import (
    AuditEvent,
    LedgerEntry,
    Payment,
    PaymentAllocation,
    Person,
    StatementImport,
    StatementTransaction,
    StellarAnchor,
    Student,
)
from harambeeone_api.periods import resolve_period
from harambeeone_api.schemas import ReconciliationConfirm, StatementImportCreate

router = APIRouter(prefix="/api/v1/reconciliation", tags=["reconciliation"])


@router.post("/imports", status_code=status.HTTP_201_CREATED)
def import_statement(
    payload: StatementImportCreate,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("reconciliation:write")),
):
    context.assert_school(payload.school_id)
    students = session.scalars(select(Student).where(Student.school_id == payload.school_id)).all()
    batch = StatementImport(
        school_id=payload.school_id, file_name=payload.file_name, row_count=len(payload.rows)
    )
    session.add(batch)
    session.flush()
    for row in payload.rows:
        haystack = f"{row.source_reference} {row.description}".casefold()
        matches = [student for student in students if student.admission_no.casefold() in haystack]
        suggestion = matches[0] if len(matches) == 1 else None
        session.add(
            StatementTransaction(
                import_id=batch.id,
                school_id=payload.school_id,
                transaction_date=row.transaction_date,
                source_reference=row.source_reference.strip(),
                description=row.description.strip(),
                amount=row.amount,
                status="suggested" if suggestion else "unmatched",
                suggested_student_id=suggestion.id if suggestion else None,
                confidence=1 if suggestion else None,
            )
        )
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="statement_import",
            entity_id=batch.id,
            action="created",
            actor=context.actor,
            summary=f"Imported {batch.row_count} statement transactions from {batch.file_name}",
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="A statement reference has already been imported"
        ) from error
    return {"id": batch.id, "row_count": batch.row_count}


@router.get("/transactions")
def list_transactions(
    school_id: uuid.UUID,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("reconciliation:read")),
):
    context.assert_school(school_id)
    suggestion = aliased(Student)
    person = aliased(Person)
    rows = session.execute(
        select(StatementTransaction, suggestion, person)
        .outerjoin(suggestion, suggestion.id == StatementTransaction.suggested_student_id)
        .outerjoin(person, person.id == suggestion.person_id)
        .where(StatementTransaction.school_id == school_id)
        .order_by(StatementTransaction.transaction_date.desc())
    ).all()
    return [
        {
            "id": item.id,
            "transaction_date": item.transaction_date,
            "source_reference": item.source_reference,
            "description": item.description,
            "amount": item.amount,
            "status": item.status,
            "suggested_student_id": item.suggested_student_id,
            "suggested_student_name": f"{person_row.first_name} {person_row.last_name}"
            if person_row
            else None,
            "confidence": item.confidence,
            "payment_id": item.payment_id,
        }
        for item, _, person_row in rows
    ]


@router.post("/transactions/{transaction_id}/confirm", status_code=status.HTTP_201_CREATED)
def confirm_transaction(
    transaction_id: uuid.UUID,
    payload: ReconciliationConfirm,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("reconciliation:write")),
):
    transaction = session.scalar(
        select(StatementTransaction).where(
            StatementTransaction.id == transaction_id,
            StatementTransaction.school_id == context.school_id,
        )
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="Statement transaction not found")
    if transaction.status == "reconciled":
        raise HTTPException(status_code=409, detail="Transaction is already reconciled")
    period = resolve_period(
        session,
        school_id=context.school_id,
        period_id=payload.period_id,
        writable=True,
    )
    student = session.get(Student, payload.student_id)
    if student is None or student.school_id != transaction.school_id:
        raise HTTPException(status_code=422, detail="Learner does not belong to this school")
    payment_id = uuid.uuid4()
    payment = Payment(
        id=payment_id,
        school_id=transaction.school_id,
        period_id=period.id,
        receipt_no=f"H1-{payment_id.hex[:12].upper()}",
        external_reference=transaction.source_reference,
        channel="bank",
        amount=transaction.amount,
        note=transaction.description or None,
    )
    allocation = PaymentAllocation(
        payment_id=payment_id, student_id=student.id, amount=transaction.amount
    )
    entry = LedgerEntry(
        school_id=context.school_id,
        period_id=period.id,
        student_id=student.id,
        entry_type="payment",
        amount=-transaction.amount,
        reference=transaction.source_reference,
        payment_id=payment_id,
    )
    commitment = hashlib.sha256(
        f"{payment_id}|{transaction.amount}|UGX|{transaction.source_reference}".encode()
    ).hexdigest()
    anchor = StellarAnchor(payment_id=payment_id, commitment_hash=commitment, status="pending")
    transaction.status = "reconciled"
    transaction.suggested_student_id = student.id
    transaction.payment_id = payment_id
    session.add_all([payment, allocation, entry, anchor])
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="statement_transaction",
            entity_id=transaction.id,
            action="reconciled",
            actor=context.actor,
            summary=f"Reconciled {transaction.source_reference} to learner {student.admission_no}",
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="This source transaction was already posted"
        ) from error
    return {"payment_id": payment_id, "receipt_no": payment.receipt_no}
