import hashlib
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from harambeeone_api.auth import SchoolContext, require_permission
from harambeeone_api.database import get_session
from harambeeone_api.models import (
    AcademicClass,
    AcademicPeriod,
    AcademicYear,
    AuditEvent,
    Enrollment,
    FeeCategory,
    FeeStructure,
    FeeStructureItem,
    FeeStructureLearner,
    GuardianLink,
    InstallmentRule,
    LedgerEntry,
    Payment,
    PaymentAllocation,
    Person,
    Requirement,
    School,
    StellarAnchor,
    Stream,
    Student,
    StudentFeeAssignment,
    StudentRequirement,
)
from harambeeone_api.periods import resolve_period
from harambeeone_api.schemas import (
    ArrearAccount,
    ArrearsRegister,
    FeeCategoryCreate,
    FeePlanCreate,
    FeeStructureSummary,
    PaymentCreate,
    PaymentSummary,
    ReceiptDetail,
)

router = APIRouter(prefix="/api/v1", tags=["finance"])


@router.get("/fee-categories")
def list_fee_categories(
    school_id: uuid.UUID,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("fees:read")),
):
    context.assert_school(school_id)
    return session.scalars(
        select(FeeCategory)
        .where(FeeCategory.school_id == school_id, FeeCategory.is_active.is_(True))
        .order_by(FeeCategory.priority, FeeCategory.name)
    ).all()


@router.post("/fee-categories", status_code=status.HTTP_201_CREATED)
def create_fee_category(
    payload: FeeCategoryCreate,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("fees:write")),
):
    context.assert_school(payload.school_id)
    category = FeeCategory(**payload.model_dump(exclude={"code"}), code=payload.code.upper())
    session.add(category)
    try:
        session.flush()
        session.add(
            AuditEvent(
                school_id=context.school_id,
                entity_type="fee_category",
                entity_id=category.id,
                action="created",
                actor=context.actor,
                summary=f"Created fee category {category.name}",
            )
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Fee category code already exists") from error
    session.refresh(category)
    return category


@router.post("/fee-plans", status_code=status.HTTP_201_CREATED)
def create_fee_plan(
    payload: FeePlanCreate,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("fees:write")),
):
    context.assert_school(payload.school_id)
    period = resolve_period(
        session,
        school_id=context.school_id,
        period_id=payload.period_id,
        academic_year=payload.academic_year,
        term=payload.term,
        writable=True,
    )
    academic_class = session.get(AcademicClass, payload.class_id)
    if academic_class is None or academic_class.school_id != payload.school_id:
        raise HTTPException(status_code=422, detail="Class does not belong to school")
    stream = session.get(Stream, payload.stream_id) if payload.stream_id else None
    if stream is not None and stream.class_id != payload.class_id:
        raise HTTPException(status_code=422, detail="Stream does not belong to the selected class")
    if payload.student_ids:
        eligible_ids = set(
            session.scalars(
                select(Student.id)
                .join(Enrollment, Enrollment.student_id == Student.id)
                .where(
                    Student.school_id == payload.school_id,
                    Student.id.in_(payload.student_ids),
                    Student.status == "active",
                    Enrollment.period_id == period.id,
                    Enrollment.class_id == payload.class_id,
                )
            ).all()
        )
        if eligible_ids != set(payload.student_ids):
            raise HTTPException(
                status_code=422,
                detail="Every selected learner must be active in the plan class and period",
            )
    category_ids = {item.category_id for item in payload.items}
    valid_categories = set(
        session.scalars(
            select(FeeCategory.id).where(
                FeeCategory.school_id == payload.school_id, FeeCategory.id.in_(category_ids)
            )
        ).all()
    )
    if valid_categories != category_ids:
        raise HTTPException(status_code=422, detail="One or more fee categories are invalid")
    total = sum(item.amount for item in payload.items)
    plan = FeeStructure(
        school_id=payload.school_id,
        class_id=payload.class_id,
        stream_id=payload.stream_id,
        period_id=period.id,
        name=payload.name,
        academic_year=period.academic_year.year,
        term=period.sequence,
        currency=payload.currency,
        total_amount=total,
        target_type=payload.target_type,
        boarding_status=payload.boarding_status,
    )
    session.add(plan)
    try:
        session.flush()
        plan.items = [
            FeeStructureItem(category_id=item.category_id, amount=item.amount)
            for item in payload.items
        ]
        plan.installments = [
            InstallmentRule(
                name=item.name,
                amount=item.calculated_amount(total),
                calculation_type=item.calculation_type,
                percentage=item.percentage,
                due_date=item.due_date,
                sort_order=item.sort_order,
            )
            for item in payload.installments
        ]
        plan.selected_learners = [
            FeeStructureLearner(student_id=student_id) for student_id in payload.student_ids
        ]
        session.add(
            AuditEvent(
                school_id=context.school_id,
                entity_type="fee_structure",
                entity_id=plan.id,
                action="created",
                actor=context.actor,
                summary=f"Created {plan.name} totaling {plan.total_amount} {plan.currency}",
            )
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="This fee plan conflicts with existing configuration"
        ) from error
    return {"id": plan.id, "total_amount": plan.total_amount}


@router.get("/fee-structures", response_model=list[FeeStructureSummary])
def list_fee_structures(
    school_id: uuid.UUID,
    period_id: uuid.UUID | None = None,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("fees:read")),
):
    context.assert_school(school_id)
    period = resolve_period(session, school_id=school_id, period_id=period_id)
    items = session.scalars(
        select(FeeStructure)
        .where(
            FeeStructure.school_id == school_id,
            FeeStructure.period_id == period.id,
            FeeStructure.is_active.is_(True),
        )
        .options(
            selectinload(FeeStructure.selected_learners),
            selectinload(FeeStructure.installments),
        )
        .order_by(FeeStructure.name)
    ).all()
    return [
        FeeStructureSummary(
            id=item.id,
            class_id=item.class_id,
            stream_id=item.stream_id,
            name=item.name,
            academic_year=item.academic_year,
            term=item.term,
            currency=item.currency,
            total_amount=item.total_amount,
            target_type=item.target_type,
            boarding_status=item.boarding_status,
            status=item.status,
            selected_learner_count=len(item.selected_learners),
            installments=[
                {
                    "id": rule.id,
                    "name": rule.name,
                    "amount": rule.amount,
                    "calculation_type": rule.calculation_type,
                    "percentage": rule.percentage,
                    "due_date": rule.due_date,
                    "sort_order": rule.sort_order,
                }
                for rule in sorted(item.installments, key=lambda value: value.sort_order)
            ],
        )
        for item in items
    ]


@router.delete("/fee-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft_fee_plan(
    plan_id: uuid.UUID,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("fees:write")),
) -> Response:
    plan = session.scalar(
        select(FeeStructure).where(
            FeeStructure.id == plan_id,
            FeeStructure.school_id == context.school_id,
            FeeStructure.is_active.is_(True),
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Fee plan not found")
    resolve_period(session, school_id=context.school_id, period_id=plan.period_id, writable=True)
    assignment_count = session.scalar(
        select(func.count(StudentFeeAssignment.id)).where(
            StudentFeeAssignment.fee_structure_id == plan.id
        )
    )
    if plan.status != "draft" or assignment_count:
        raise HTTPException(status_code=409, detail="Published fee plans cannot be removed")
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="fee_structure",
            entity_id=plan.id,
            action="deleted",
            actor=context.actor,
            summary=f"Deleted draft fee plan {plan.name}",
        )
    )
    session.delete(plan)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/arrears", response_model=ArrearsRegister)
def list_arrears(
    school_id: uuid.UUID,
    period_id: uuid.UUID | None = None,
    as_of: date | None = None,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("fees:read")),
):
    context.assert_school(school_id)
    period = resolve_period(session, school_id=school_id, period_id=period_id)
    cutoff = as_of or date.today()
    accounts: list[ArrearAccount] = []
    students = session.scalars(
        select(Student)
        .where(Student.school_id == school_id, Student.status == "active")
        .order_by(Student.admission_no)
        .options(
            joinedload(Student.person),
            selectinload(Student.enrollments).joinedload(Enrollment.academic_class),
            selectinload(Student.guardians).joinedload(GuardianLink.person),
            selectinload(Student.fee_assignments)
            .joinedload(StudentFeeAssignment.fee_structure)
            .selectinload(FeeStructure.installments),
        )
    ).all()
    paid_by_student = dict(
        session.execute(
            select(
                PaymentAllocation.student_id,
                func.coalesce(func.sum(PaymentAllocation.amount), 0),
            )
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .join(Student, Student.id == PaymentAllocation.student_id)
            .where(
                Student.school_id == school_id,
                Payment.period_id == period.id,
            )
            .group_by(PaymentAllocation.student_id)
        ).all()
    )
    eligible_period_ids = session.scalars(
        select(AcademicPeriod.id)
        .join(AcademicYear, AcademicYear.id == AcademicPeriod.academic_year_id)
        .where(
            AcademicPeriod.school_id == school_id,
            (AcademicYear.year < period.academic_year.year)
            | (
                (AcademicYear.year == period.academic_year.year)
                & (AcademicPeriod.sequence <= period.sequence)
            ),
        )
    ).all()
    ledger_balances = dict(
        session.execute(
            select(LedgerEntry.student_id, func.coalesce(func.sum(LedgerEntry.amount), 0))
            .where(
                LedgerEntry.school_id == school_id,
                LedgerEntry.period_id.in_(eligible_period_ids),
            )
            .group_by(LedgerEntry.student_id)
        ).all()
    )
    for student in students:
        assignments = [
            assignment
            for assignment in student.fee_assignments
            if assignment.fee_structure and assignment.fee_structure.period_id == period.id
        ]
        if not assignments:
            continue
        billed = sum((assignment.amount for assignment in assignments), Decimal("0"))
        paid = paid_by_student.get(student.id, Decimal("0"))
        due_events: list[tuple[date, Decimal]] = []
        for assignment in assignments:
            structure = assignment.fee_structure
            if structure is None or not structure.total_amount:
                continue
            for installment in sorted(
                structure.installments, key=lambda item: (item.due_date, item.sort_order)
            ):
                if installment.due_date <= cutoff:
                    due_events.append(
                        (
                            installment.due_date,
                            installment.amount * assignment.amount / structure.total_amount,
                        )
                    )
        overdue_amount, overdue_since = _overdue_position(due_events, paid, cutoff)
        balance = ledger_balances.get(student.id, billed - paid)
        overdue_amount = min(overdue_amount, max(balance, Decimal("0")))
        if overdue_amount <= 0 or overdue_since is None:
            continue
        person = student.person
        enrollment = next(
            (item for item in student.enrollments if item.period_id == period.id), None
        )
        academic_class = enrollment.academic_class if enrollment else None
        guardian_link = next(
            (item for item in student.guardians if item.is_primary),
            student.guardians[0] if student.guardians else None,
        )
        days_overdue = (cutoff - overdue_since).days
        guardian = guardian_link.person if guardian_link else None
        accounts.append(
            ArrearAccount(
                student_id=student.id,
                admission_no=student.admission_no,
                student_name=f"{person.first_name} {person.last_name}",
                class_name=academic_class.name if academic_class else "Unplaced",
                guardian_name=(f"{guardian.first_name} {guardian.last_name}" if guardian else None),
                guardian_phone=guardian.phone if guardian else None,
                billed=billed,
                paid=paid,
                balance=balance,
                overdue_amount=overdue_amount,
                overdue_since=overdue_since,
                days_overdue=days_overdue,
                severity="critical" if days_overdue >= 30 else "warning",
            )
        )
    accounts.sort(key=lambda item: (item.days_overdue, item.overdue_amount), reverse=True)
    return ArrearsRegister(
        as_of=cutoff,
        total_accounts=len(accounts),
        total_overdue=sum((item.overdue_amount for item in accounts), Decimal("0")),
        critical_accounts=sum(item.severity == "critical" for item in accounts),
        items=accounts,
    )


def _overdue_position(
    due_events: list[tuple[date, Decimal]], paid: Decimal, cutoff: date
) -> tuple[Decimal, date | None]:
    events = sorted((due_date, amount) for due_date, amount in due_events if due_date <= cutoff)
    expected = sum((amount for _, amount in events), Decimal("0"))
    overdue = max(expected - paid, Decimal("0"))
    if overdue <= 0:
        return Decimal("0"), None
    remaining_credit = paid
    for due_date, due_amount in events:
        if remaining_credit >= due_amount:
            remaining_credit -= due_amount
        else:
            return overdue, due_date
    return overdue, cutoff


@router.get("/payments", response_model=list[PaymentSummary])
def list_payments(
    school_id: uuid.UUID,
    period_id: uuid.UUID | None = None,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("payments:read")),
):
    context.assert_school(school_id)
    period = resolve_period(session, school_id=school_id, period_id=period_id)
    rows = session.execute(
        select(Payment, PaymentAllocation, Student, Person, StellarAnchor, Requirement)
        .select_from(Payment)
        .join(PaymentAllocation, PaymentAllocation.payment_id == Payment.id)
        .join(Student, Student.id == PaymentAllocation.student_id)
        .join(Person, Student.person_id == Person.id)
        .join(StellarAnchor, StellarAnchor.payment_id == Payment.id)
        .outerjoin(
            StudentRequirement,
            StudentRequirement.id == PaymentAllocation.requirement_assignment_id,
        )
        .outerjoin(Requirement, Requirement.id == StudentRequirement.requirement_id)
        .where(Payment.school_id == school_id, Payment.period_id == period.id)
        .order_by(Payment.received_at.desc())
        .limit(100)
    ).all()
    return [_summary(*row) for row in rows]


@router.post("/payments", response_model=PaymentSummary, status_code=status.HTTP_201_CREATED)
def record_payment(
    payload: PaymentCreate,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("payments:write")),
):
    context.assert_school(payload.school_id)
    period = resolve_period(
        session,
        school_id=context.school_id,
        period_id=payload.period_id,
        writable=True,
    )
    student = session.get(Student, payload.student_id)
    if student is None or student.school_id != payload.school_id:
        raise HTTPException(status_code=404, detail="Learner not found")
    person = session.get(Person, student.person_id)
    assignment = None
    requirement = None
    if payload.requirement_assignment_id:
        assignment = session.scalar(
            select(StudentRequirement)
            .where(StudentRequirement.id == payload.requirement_assignment_id)
            .options(joinedload(StudentRequirement.requirement))
        )
        if assignment is None or assignment.student_id != student.id:
            raise HTTPException(status_code=422, detail="Requirement does not belong to learner")
        requirement = assignment.requirement
        if requirement.period_id != period.id:
            raise HTTPException(status_code=422, detail="Requirement belongs to another period")
        if requirement.requirement_type not in {"payment", "school_item"}:
            raise HTTPException(status_code=422, detail="This requirement is not paid in cash")
        already_paid = session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
                PaymentAllocation.requirement_assignment_id == assignment.id
            )
        )
        outstanding = max(assignment.expected_amount - already_paid, Decimal("0"))
        if outstanding == 0:
            raise HTTPException(status_code=409, detail="This requirement is already fully paid")
        if payload.amount > outstanding:
            raise HTTPException(
                status_code=422,
                detail=f"Payment exceeds the requirement balance of UGX {outstanding:,.0f}",
            )
    payment_id = uuid.uuid4()
    payment = Payment(
        id=payment_id,
        school_id=payload.school_id,
        period_id=period.id,
        receipt_no=f"H1-{payment_id.hex[:12].upper()}",
        external_reference=payload.external_reference.strip(),
        payer_name=payload.payer_name.strip() if payload.payer_name else None,
        note=payload.note.strip() if payload.note else None,
        channel=payload.channel,
        amount=payload.amount,
    )
    session.add(payment)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="This payment reference has already been recorded"
        ) from error
    allocation = PaymentAllocation(
        id=uuid.uuid4(),
        payment_id=payment_id,
        student_id=student.id,
        requirement_assignment_id=assignment.id if assignment else None,
        amount=payload.amount,
    )
    if assignment and requirement and not requirement.is_mandatory:
        charge_reference = f"REQ:{assignment.id}"
        charged = session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.student_id == student.id,
                LedgerEntry.reference == charge_reference,
            )
        )
        if not charged:
            session.add(
                LedgerEntry(
                    id=uuid.uuid4(),
                    school_id=context.school_id,
                    period_id=period.id,
                    student_id=student.id,
                    entry_type="requirement_charge",
                    amount=assignment.expected_amount,
                    reference=charge_reference,
                    requirement_assignment_id=assignment.id,
                )
            )
    entry = LedgerEntry(
        id=uuid.uuid4(),
        school_id=context.school_id,
        period_id=period.id,
        student_id=student.id,
        entry_type="payment",
        amount=-payload.amount,
        reference=payload.external_reference.strip(),
        payment_id=payment_id,
    )
    commitment = hashlib.sha256(
        f"{payment_id}|{payload.amount}|UGX|{payload.external_reference.strip()}".encode()
    ).hexdigest()
    anchor = StellarAnchor(
        id=uuid.uuid4(), payment_id=payment_id, commitment_hash=commitment, status="pending"
    )
    session.add_all([allocation, entry, anchor])
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="payment",
            entity_id=payment.id,
            action="created",
            actor=context.actor,
            summary=f"Recorded {payment.amount} {payment.currency} via {payment.channel}",
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="This payment reference has already been recorded"
        ) from error
    return _summary(payment, allocation, student, person, anchor, requirement)


@router.get("/payments/{payment_id}/receipt", response_model=ReceiptDetail)
def get_payment_receipt(
    payment_id: uuid.UUID,
    session: Session = Depends(get_session),
    context: SchoolContext = Depends(require_permission("payments:read")),
):
    row = session.execute(
        select(
            Payment,
            PaymentAllocation,
            Student,
            Person,
            StellarAnchor,
            School,
            Requirement,
        )
        .join(PaymentAllocation, PaymentAllocation.payment_id == Payment.id)
        .join(Student, Student.id == PaymentAllocation.student_id)
        .join(Person, Student.person_id == Person.id)
        .join(StellarAnchor, StellarAnchor.payment_id == Payment.id)
        .join(School, School.id == Payment.school_id)
        .outerjoin(
            StudentRequirement,
            StudentRequirement.id == PaymentAllocation.requirement_assignment_id,
        )
        .outerjoin(Requirement, Requirement.id == StudentRequirement.requirement_id)
        .where(Payment.id == payment_id, Payment.school_id == context.school_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    payment, allocation, student, person, anchor, school, requirement = row
    billed = session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.student_id == student.id,
            LedgerEntry.amount > 0,
        )
    )
    paid = -session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.student_id == student.id, LedgerEntry.entry_type == "payment"
        )
    )
    summary = _summary(payment, allocation, student, person, anchor, requirement).model_dump()
    return ReceiptDetail(
        **summary,
        school_name=school.name,
        school_district=school.district,
        payer_name=payment.payer_name,
        note=payment.note,
        billed=billed,
        paid_to_date=paid,
        balance=billed - paid,
    )


def _summary(payment, allocation, student, person, anchor, requirement=None):
    return PaymentSummary(
        id=payment.id,
        receipt_no=payment.receipt_no,
        external_reference=payment.external_reference,
        student_name=f"{person.first_name} {person.last_name}",
        admission_no=student.admission_no,
        channel=payment.channel,
        amount=allocation.amount,
        currency=payment.currency,
        status=payment.status,
        purpose=requirement.name if requirement else "School fees / learner account",
        stellar_status=anchor.status,
        commitment_hash=anchor.commitment_hash,
        received_at=payment.received_at.isoformat(),
    )
