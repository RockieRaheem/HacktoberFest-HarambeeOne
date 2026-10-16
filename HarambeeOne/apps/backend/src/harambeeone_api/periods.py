import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from harambeeone_api.auth import SchoolContext, require_permission
from harambeeone_api.database import get_session
from harambeeone_api.models import (
    AcademicPeriod,
    AcademicYear,
    AuditEvent,
    BillingAdjustment,
    BillingPublication,
    Enrollment,
    FeeStructure,
    LedgerEntry,
    Payment,
    Requirement,
    School,
)
from harambeeone_api.schemas import (
    AcademicPeriodTransition,
    AcademicPeriodUpdate,
    AcademicYearCreate,
)

router = APIRouter(prefix="/api/v1", tags=["academic periods"])
PeriodReadContext = Annotated[SchoolContext, Depends(require_permission("periods:read"))]
PeriodManageContext = Annotated[SchoolContext, Depends(require_permission("periods:manage"))]


def _activity_count(session: Session, period_id: uuid.UUID) -> int:
    models = (
        Enrollment,
        FeeStructure,
        Requirement,
        BillingAdjustment,
        BillingPublication,
        LedgerEntry,
        Payment,
    )
    return sum(
        session.scalar(select(func.count()).select_from(model).where(model.period_id == period_id))
        or 0
        for model in models
    )


def _period_payload(session: Session, period: AcademicPeriod) -> dict:
    return {
        "id": period.id,
        "academic_year_id": period.academic_year_id,
        "academic_year": period.academic_year.year,
        "academic_year_name": period.academic_year.name,
        "name": period.name,
        "sequence": period.sequence,
        "opening_date": period.opening_date,
        "closing_date": period.closing_date,
        "due_date": period.due_date,
        "status": period.status,
        "is_operational": period.status in {"open", "closing"},
        "activity_count": _activity_count(session, period.id),
    }


def resolve_period(
    session: Session,
    *,
    school_id: uuid.UUID,
    period_id: uuid.UUID | None = None,
    academic_year: int | None = None,
    term: int | None = None,
    writable: bool = False,
) -> AcademicPeriod:
    statement = (
        select(AcademicPeriod)
        .join(AcademicYear, AcademicYear.id == AcademicPeriod.academic_year_id)
        .where(AcademicPeriod.school_id == school_id)
        .options(selectinload(AcademicPeriod.academic_year))
    )
    if period_id is not None:
        statement = statement.where(AcademicPeriod.id == period_id)
    elif academic_year is not None and term is not None:
        statement = statement.where(
            AcademicYear.year == academic_year, AcademicPeriod.sequence == term
        )
    else:
        statement = statement.where(AcademicPeriod.status.in_(("open", "closing")))
    period = session.scalar(statement)
    if period is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Select or open an academic period before continuing",
        )
    if writable and period.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This academic period is closed and cannot be changed",
        )
    return period


def _refresh_year_status(year: AcademicYear) -> None:
    statuses = {period.status for period in year.periods}
    if "open" in statuses:
        year.status = "open"
    elif "closing" in statuses:
        year.status = "closing"
    elif statuses and statuses == {"closed"}:
        year.status = "closed"
    else:
        year.status = "draft"


@router.get("/academic-period-templates")
def calendar_templates(context: PeriodReadContext) -> dict:
    return {
        "country": "Uganda",
        "school_id": context.school_id,
        "default_period_names": ["Term 1", "Term 2", "Term 3"],
        "note": (
            "Dates are intentionally editable because the Ministry calendar "
            "and school schedules vary."
        ),
    }


@router.get("/academic-periods")
def list_periods(
    context: PeriodReadContext,
    session: Annotated[Session, Depends(get_session)],
    school_id: uuid.UUID | None = None,
) -> list[dict]:
    if school_id is not None:
        context.assert_school(school_id)
    periods = session.scalars(
        select(AcademicPeriod)
        .where(AcademicPeriod.school_id == context.school_id)
        .join(AcademicYear, AcademicYear.id == AcademicPeriod.academic_year_id)
        .options(selectinload(AcademicPeriod.academic_year))
        .order_by(AcademicYear.year.desc(), AcademicPeriod.sequence)
    ).all()
    return [_period_payload(session, period) for period in periods]


@router.get("/academic-periods/operational")
def operational_period(
    context: PeriodReadContext,
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    period = resolve_period(session, school_id=context.school_id)
    return _period_payload(session, period)


@router.post("/academic-years", status_code=status.HTTP_201_CREATED)
def create_academic_year(
    payload: AcademicYearCreate,
    context: PeriodManageContext,
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    context.assert_school(payload.school_id)
    if session.get(School, context.school_id) is None:
        raise HTTPException(status_code=404, detail="School not found")
    year = AcademicYear(
        id=uuid.uuid4(),
        school_id=context.school_id,
        name=payload.name,
        year=payload.year,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="draft",
    )
    year.periods = [
        AcademicPeriod(
            id=uuid.uuid4(),
            school_id=context.school_id,
            name=item.name,
            sequence=item.sequence,
            opening_date=item.opening_date,
            closing_date=item.closing_date,
            due_date=item.due_date,
            status="draft",
        )
        for item in payload.periods
    ]
    session.add(year)
    session.flush()
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="academic_year",
            entity_id=year.id,
            action="created",
            actor=context.actor,
            summary=f"Created {year.name} with {len(year.periods)} academic periods",
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="This academic year or one of its periods already exists"
        ) from error
    session.refresh(year)
    return {
        "id": year.id,
        "name": year.name,
        "year": year.year,
        "status": year.status,
        "periods": [_period_payload(session, period) for period in year.periods],
    }


@router.put("/academic-periods/{period_id}")
def update_period(
    period_id: uuid.UUID,
    payload: AcademicPeriodUpdate,
    context: PeriodManageContext,
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    period = resolve_period(session, school_id=context.school_id, period_id=period_id)
    if period.status == "closed":
        raise HTTPException(status_code=409, detail="Reopen this period before correcting it")
    year = period.academic_year
    if payload.opening_date < year.start_date or payload.closing_date > year.end_date:
        raise HTTPException(
            status_code=422, detail="The period must remain within its academic year"
        )
    sibling = session.scalar(
        select(AcademicPeriod.id).where(
            AcademicPeriod.academic_year_id == year.id,
            AcademicPeriod.id != period.id,
            AcademicPeriod.opening_date <= payload.closing_date,
            AcademicPeriod.closing_date >= payload.opening_date,
        )
    )
    if sibling is not None:
        raise HTTPException(status_code=422, detail="Academic periods cannot overlap")
    period.name = payload.name
    period.opening_date = payload.opening_date
    period.closing_date = payload.closing_date
    period.due_date = payload.due_date
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="academic_period",
            entity_id=period.id,
            action="corrected",
            actor=context.actor,
            summary=f"Corrected dates and name for {period.name}",
        )
    )
    session.commit()
    return _period_payload(session, period)


@router.post("/academic-periods/{period_id}/transition")
def transition_period(
    period_id: uuid.UUID,
    payload: AcademicPeriodTransition,
    context: PeriodManageContext,
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    period = resolve_period(session, school_id=context.school_id, period_id=period_id)
    allowed = {
        "draft": {"open"},
        "open": {"closing"},
        "closing": {"closed"},
        "closed": {"open"},
    }
    if payload.status not in allowed[period.status]:
        raise HTTPException(
            status_code=409,
            detail=f"A {period.status} period cannot transition directly to {payload.status}",
        )
    if period.status == "closed":
        if context.role != "owner":
            raise HTTPException(
                status_code=403, detail="Only the institution owner can reopen a period"
            )
        if not payload.reason or not payload.reason.strip():
            raise HTTPException(status_code=422, detail="A reason is required to reopen a period")
    if payload.status == "open":
        other = session.scalar(
            select(AcademicPeriod.id).where(
                AcademicPeriod.school_id == context.school_id,
                AcademicPeriod.id != period.id,
                AcademicPeriod.status.in_(("open", "closing")),
            )
        )
        if other is not None:
            raise HTTPException(
                status_code=409,
                detail="Close the current operational period before opening another",
            )
    previous = period.status
    period.status = payload.status
    _refresh_year_status(period.academic_year)
    detail = f" ({payload.reason.strip()})" if payload.reason else ""
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="academic_period",
            entity_id=period.id,
            action="reopened" if previous == "closed" else payload.status,
            actor=context.actor,
            summary=f"Changed {period.name} from {previous} to {payload.status}{detail}",
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Another operational period is already open"
        ) from error
    return _period_payload(session, period)


@router.delete("/academic-periods/{period_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_period(
    period_id: uuid.UUID,
    context: PeriodManageContext,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    period = resolve_period(session, school_id=context.school_id, period_id=period_id)
    if period.status != "draft":
        raise HTTPException(status_code=409, detail="Only a draft period can be deleted")
    if _activity_count(session, period.id):
        raise HTTPException(
            status_code=409,
            detail="A period containing financial or enrollment activity cannot be deleted",
        )
    session.add(
        AuditEvent(
            school_id=context.school_id,
            entity_type="academic_period",
            entity_id=period.id,
            action="deleted",
            actor=context.actor,
            summary=f"Deleted unused draft period {period.name}",
        )
    )
    session.delete(period)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
