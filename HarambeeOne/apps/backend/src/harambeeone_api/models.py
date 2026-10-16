import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as orm_relationship

from harambeeone_api.database import Base


class School(Base):
    __tablename__ = "schools"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))
    emis_code: Mapped[str | None] = mapped_column(String(40), unique=True)
    district: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    classes: Mapped[list["AcademicClass"]] = orm_relationship(back_populates="school")
    programmes: Mapped[list["SchoolProgramme"]] = orm_relationship(
        back_populates="school",
        cascade="all, delete-orphan",
        order_by="SchoolProgramme.sort_order",
    )
    memberships: Mapped[list["SchoolMembership"]] = orm_relationship(
        back_populates="school", cascade="all, delete-orphan"
    )


class AcademicYear(Base):
    __tablename__ = "academic_years"
    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uq_academic_years_school_name"),
        UniqueConstraint("school_id", "year", name="uq_academic_years_school_year"),
        CheckConstraint("start_date <= end_date", name="ck_academic_years_date_order"),
        CheckConstraint(
            "status in ('draft', 'open', 'closing', 'closed')",
            name="ck_academic_years_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    year: Mapped[int]
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    periods: Mapped[list["AcademicPeriod"]] = orm_relationship(
        back_populates="academic_year",
        cascade="all, delete-orphan",
        order_by="AcademicPeriod.sequence",
    )


class AcademicPeriod(Base):
    __tablename__ = "academic_periods"
    __table_args__ = (
        UniqueConstraint("academic_year_id", "sequence", name="uq_periods_year_sequence"),
        UniqueConstraint("academic_year_id", "name", name="uq_periods_year_name"),
        CheckConstraint("sequence > 0", name="ck_periods_positive_sequence"),
        CheckConstraint(
            "opening_date <= due_date and due_date <= closing_date",
            name="ck_periods_date_order",
        ),
        CheckConstraint(
            "status in ('draft', 'open', 'closing', 'closed')",
            name="ck_periods_status",
        ),
        Index(
            "uq_academic_periods_one_operational_per_school",
            "school_id",
            unique=True,
            postgresql_where=text("status in ('open', 'closing')"),
            sqlite_where=text("status in ('open', 'closing')"),
        ),
        Index("ix_academic_periods_school_dates", "school_id", "opening_date", "closing_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_years.id", ondelete="CASCADE"), index=True
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    sequence: Mapped[int]
    opening_date: Mapped[date] = mapped_column(Date)
    closing_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    academic_year: Mapped[AcademicYear] = orm_relationship(back_populates="periods")


class SchoolMembership(Base):
    __tablename__ = "school_memberships"
    __table_args__ = (UniqueConstraint("auth_user_id", name="uq_school_memberships_auth_user"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    auth_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(32), default="bursar")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    school: Mapped[School] = orm_relationship(back_populates="memberships")


class SchoolProgramme(Base):
    __tablename__ = "school_programmes"
    __table_args__ = (UniqueConstraint("school_id", "programme_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    programme_code: Mapped[str] = mapped_column(String(32))
    display_name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int]
    school: Mapped[School] = orm_relationship(back_populates="programmes")


class AcademicClass(Base):
    __tablename__ = "academic_classes"
    __table_args__ = (
        UniqueConstraint("school_id", "name"),
        UniqueConstraint(
            "school_id",
            "canonical_code",
            name="uq_academic_classes_school_canonical_code",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(40))
    level: Mapped[str] = mapped_column(String(20))
    canonical_code: Mapped[str | None] = mapped_column(String(32))
    sort_order: Mapped[int]
    school: Mapped[School] = orm_relationship(back_populates="classes")
    streams: Mapped[list["Stream"]] = orm_relationship(
        back_populates="academic_class", cascade="all, delete-orphan"
    )


class Stream(Base):
    __tablename__ = "streams"
    __table_args__ = (UniqueConstraint("class_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_classes.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(40))
    academic_class: Mapped[AcademicClass] = orm_relationship(back_populates="streams")


class Person(Base):
    __tablename__ = "people"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(80))
    middle_name: Mapped[str | None] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(254))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("school_id", "admission_no"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id"))
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("people.id"), unique=True)
    admission_no: Mapped[str] = mapped_column(String(40))
    learner_identification_number: Mapped[str | None] = mapped_column(String(40), unique=True)
    gender: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20), default="active")
    boarding_status: Mapped[str] = mapped_column(String(20), default="day")
    nationality: Mapped[str] = mapped_column(String(60), default="Ugandan")
    previous_school: Mapped[str | None] = mapped_column(String(160))
    special_needs: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    person: Mapped[Person] = orm_relationship()
    enrollments: Mapped[list["Enrollment"]] = orm_relationship(back_populates="student")
    guardians: Mapped[list["GuardianLink"]] = orm_relationship(back_populates="student")
    fee_assignments: Mapped[list["StudentFeeAssignment"]] = orm_relationship()
    ledger_entries: Mapped[list["LedgerEntry"]] = orm_relationship()


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "academic_year", "term"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_classes.id"))
    stream_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("streams.id"))
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_periods.id", ondelete="RESTRICT"), index=True
    )
    academic_year: Mapped[int]
    term: Mapped[int]
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    student: Mapped[Student] = orm_relationship(back_populates="enrollments")
    academic_class: Mapped[AcademicClass] = orm_relationship()
    stream: Mapped[Stream | None] = orm_relationship()


class GuardianLink(Base):
    __tablename__ = "guardian_links"
    __table_args__ = (UniqueConstraint("student_id", "person_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("people.id"))
    relationship: Mapped[str] = mapped_column(String(30))
    is_primary: Mapped[bool] = mapped_column(default=False)
    can_receive_statements: Mapped[bool] = mapped_column(default=True)
    student: Mapped[Student] = orm_relationship(back_populates="guardians")
    person: Mapped[Person] = orm_relationship()


class PortalProfile(Base):
    __tablename__ = "portal_profiles"
    __table_args__ = (
        CheckConstraint(
            "preferred_workspace is null or preferred_workspace in ('school','guardian','donor')",
            name="ck_portal_profiles_workspace",
        ),
    )

    auth_user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    preferred_workspace: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GuardianInvitation(Base):
    __tablename__ = "guardian_invitations"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','accepted','revoked','expired')",
            name="ck_guardian_invitations_status",
        ),
        Index("ix_guardian_invitations_school_status", "school_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), index=True
    )
    guardian_link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guardian_links.id", ondelete="RESTRICT"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_email: Mapped[str] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str] = mapped_column(String(120))
    accepted_by_user_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuardianAccountLink(Base):
    __tablename__ = "guardian_account_links"
    __table_args__ = (
        UniqueConstraint("guardian_link_id", name="uq_guardian_account_links_guardian"),
        UniqueConstraint(
            "auth_user_id", "guardian_link_id", name="uq_guardian_account_links_user_guardian"
        ),
        Index("ix_guardian_account_links_user_school", "auth_user_id", "school_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    auth_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), index=True
    )
    guardian_link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guardian_links.id", ondelete="RESTRICT"), index=True
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guardian_invitations.id", ondelete="RESTRICT"), unique=True
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DonorProfile(Base):
    __tablename__ = "donor_profiles"

    auth_user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    show_public_name: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SupportReferral(Base):
    __tablename__ = "support_referrals"
    __table_args__ = (
        UniqueConstraint("student_id", "period_id", name="uq_support_referrals_student_period"),
        CheckConstraint(
            "status in ('awaiting_consent','consented','declined','withdrawn','case_submitted')",
            name="ck_support_referrals_status",
        ),
        CheckConstraint(
            "child_assent_status in "
            "('pending','agreed','declined','not_applicable','unable_to_express')",
            name="ck_support_referrals_assent",
        ),
        Index("ix_support_referrals_school_status", "school_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id", ondelete="RESTRICT"))
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_periods.id", ondelete="RESTRICT")
    )
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    guardian_link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guardian_links.id", ondelete="RESTRICT")
    )
    outstanding_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    overdue_since: Mapped[date] = mapped_column(Date)
    days_overdue_snapshot: Mapped[int]
    priority_band: Mapped[str] = mapped_column(String(16))
    priority_reasons: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="awaiting_consent")
    privacy_notice_version: Mapped[str | None] = mapped_column(String(24))
    guardian_authority_confirmed: Mapped[bool] = mapped_column(default=False)
    age_verification_method: Mapped[str | None] = mapped_column(String(32))
    anonymous_publication: Mapped[bool] = mapped_column(default=False)
    gemma_processing: Mapped[bool] = mapped_column(default=False)
    cross_border_processing: Mapped[bool] = mapped_column(default=False)
    child_assent_status: Mapped[str] = mapped_column(String(24), default="pending")
    child_assent_reason: Mapped[str | None] = mapped_column(String(240))
    consented_by_user_id: Mapped[uuid.UUID | None]
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FeeStructure(Base):
    __tablename__ = "fee_structures"
    __table_args__ = (
        CheckConstraint(
            "target_type in ('cohort', 'selected')", name="ck_fee_structures_target_type"
        ),
        CheckConstraint(
            "boarding_status is null or boarding_status in ('day', 'boarding', 'half_boarding')",
            name="ck_fee_structures_boarding_status",
        ),
        CheckConstraint("status in ('draft', 'published')", name="ck_fee_structures_status"),
        Index("ix_fee_structures_period_target", "period_id", "class_id", "stream_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id"))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_classes.id"))
    stream_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("streams.id"))
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_periods.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    academic_year: Mapped[int]
    term: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), default="UGX")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    target_type: Mapped[str] = mapped_column(String(16), default="cohort")
    boarding_status: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list["FeeStructureItem"]] = orm_relationship(cascade="all, delete-orphan")
    installments: Mapped[list["InstallmentRule"]] = orm_relationship(cascade="all, delete-orphan")
    selected_learners: Mapped[list["FeeStructureLearner"]] = orm_relationship(
        cascade="all, delete-orphan"
    )


class FeeStructureLearner(Base):
    __tablename__ = "fee_structure_learners"
    __table_args__ = (UniqueConstraint("fee_structure_id", "student_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fee_structure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fee_structures.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )


class FeeCategory(Base):
    __tablename__ = "fee_categories"
    __table_args__ = (UniqueConstraint("school_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(12))
    category_type: Mapped[str] = mapped_column(String(30), default="other")
    is_required: Mapped[bool] = mapped_column(default=True)
    is_recurring: Mapped[bool] = mapped_column(default=True)
    priority: Mapped[int] = mapped_column(default=1)
    is_active: Mapped[bool] = mapped_column(default=True)


class FeeStructureItem(Base):
    __tablename__ = "fee_structure_items"
    __table_args__ = (UniqueConstraint("fee_structure_id", "category_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fee_structure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fee_structures.id", ondelete="CASCADE")
    )
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fee_categories.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    category: Mapped[FeeCategory] = orm_relationship()


class InstallmentRule(Base):
    __tablename__ = "installment_rules"
    __table_args__ = (UniqueConstraint("fee_structure_id", "sort_order"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fee_structure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fee_structures.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    calculation_type: Mapped[str] = mapped_column(String(16), default="fixed")
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    due_date: Mapped[date]
    sort_order: Mapped[int]


class StudentFeeAssignment(Base):
    __tablename__ = "student_fee_assignments"
    __table_args__ = (UniqueConstraint("student_id", "fee_structure_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    fee_structure_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fee_structures.id"))
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("billing_publications.id", ondelete="RESTRICT"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    fee_structure: Mapped[FeeStructure] = orm_relationship()


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("school_id", "code", "academic_year", "term"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_periods.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(20))
    requirement_type: Mapped[str] = mapped_column(String(24))
    description: Mapped[str | None] = mapped_column(Text)
    academic_year: Mapped[int]
    term: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1"))
    unit: Mapped[str] = mapped_column(String(30), default="item")
    due_date: Mapped[date | None] = mapped_column(Date)
    stream_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("streams.id"))
    boarding_status: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    is_mandatory: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    classes: Mapped[list["RequirementClass"]] = orm_relationship(
        cascade="all, delete-orphan", back_populates="requirement"
    )
    assignments: Mapped[list["StudentRequirement"]] = orm_relationship(
        cascade="all, delete-orphan", back_populates="requirement"
    )
    selected_learners: Mapped[list["RequirementLearner"]] = orm_relationship(
        cascade="all, delete-orphan"
    )


class RequirementClass(Base):
    __tablename__ = "requirement_classes"
    __table_args__ = (UniqueConstraint("requirement_id", "class_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_classes.id", ondelete="RESTRICT")
    )
    requirement: Mapped[Requirement] = orm_relationship(back_populates="classes")
    academic_class: Mapped[AcademicClass] = orm_relationship()


class RequirementLearner(Base):
    __tablename__ = "requirement_learners"
    __table_args__ = (UniqueConstraint("requirement_id", "student_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )


class StudentRequirement(Base):
    __tablename__ = "student_requirements"
    __table_args__ = (UniqueConstraint("requirement_id", "student_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("billing_publications.id", ondelete="RESTRICT"), index=True
    )
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    expected_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    fulfilled_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    is_waived: Mapped[bool] = mapped_column(default=False)
    waiver_reason: Mapped[str | None] = mapped_column(String(240))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfilment_note: Mapped[str | None] = mapped_column(String(240))
    requirement: Mapped[Requirement] = orm_relationship(back_populates="assignments")
    student: Mapped[Student] = orm_relationship()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("school_id", "external_reference"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id"))
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_periods.id", ondelete="RESTRICT"), index=True
    )
    receipt_no: Mapped[str] = mapped_column(String(32), unique=True)
    external_reference: Mapped[str] = mapped_column(String(100))
    payer_name: Mapped[str | None] = mapped_column(String(160))
    note: Mapped[str | None] = mapped_column(String(240))
    channel: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="UGX")
    status: Mapped[str] = mapped_column(String(24), default="reconciled")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    requirement_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_requirements.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class BillingPublication(Base):
    __tablename__ = "billing_publications"
    __table_args__ = (
        UniqueConstraint(
            "school_id", "period_id", "idempotency_key", name="uq_billing_publication_key"
        ),
        CheckConstraint("status in ('posted')", name="ck_billing_publications_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), index=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_periods.id", ondelete="RESTRICT"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(80))
    preview_token: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="posted")
    learner_count: Mapped[int]
    charge_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    credit_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    net_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BillingAdjustment(Base):
    __tablename__ = "billing_adjustments"
    __table_args__ = (
        CheckConstraint(
            "adjustment_type in ('addition', 'discount', 'sponsorship_credit', 'waiver')",
            name="ck_billing_adjustments_type",
        ),
        CheckConstraint("amount > 0", name="ck_billing_adjustments_amount"),
        CheckConstraint("status in ('draft', 'published')", name="ck_billing_adjustments_status"),
        Index("ix_billing_adjustments_period_student", "period_id", "student_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), index=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_periods.id", ondelete="RESTRICT"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fee_categories.id", ondelete="RESTRICT")
    )
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("billing_publications.id", ondelete="RESTRICT"), index=True
    )
    adjustment_type: Mapped[str] = mapped_column(String(24))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    description: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint("fee_assignment_id"),
        UniqueConstraint("requirement_assignment_id"),
        UniqueConstraint("billing_adjustment_id"),
        Index("ix_ledger_entries_period_student", "period_id", "student_id"),
        Index("ix_ledger_entries_student_created", "student_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), index=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_periods.id", ondelete="RESTRICT"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    entry_type: Mapped[str] = mapped_column(String(24))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="UGX")
    reference: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(240))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("billing_publications.id", ondelete="RESTRICT"), index=True
    )
    fee_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_fee_assignments.id", ondelete="RESTRICT")
    )
    requirement_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_requirements.id", ondelete="RESTRICT")
    )
    billing_adjustment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("billing_adjustments.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StellarAnchor(Base):
    __tablename__ = "stellar_anchors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), unique=True)
    commitment_hash: Mapped[str] = mapped_column(String(64), unique=True)
    network: Mapped[str] = mapped_column(String(20), default="testnet")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    transaction_hash: Mapped[str | None] = mapped_column(String(64))
    ledger_number: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StatementImport(Base):
    __tablename__ = "statement_imports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id"))
    file_name: Mapped[str] = mapped_column(String(160))
    row_count: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="review")
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StatementTransaction(Base):
    __tablename__ = "statement_transactions"
    __table_args__ = (UniqueConstraint("school_id", "source_reference"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    import_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("statement_imports.id", ondelete="CASCADE")
    )
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id"))
    transaction_date: Mapped[date]
    source_reference: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(240))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(20), default="unmatched")
    suggested_student_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("students.id"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"), unique=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id"))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(120), default="system")
    summary: Mapped[str] = mapped_column(String(240))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Sponsor(Base):
    __tablename__ = "sponsors"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))
    sponsor_type: Mapped[str] = mapped_column(String(30))
    country: Mapped[str] = mapped_column(String(80), default="Uganda")
    verification_status: Mapped[str] = mapped_column(String(20), default="verified")


class FundingProgramme(Base):
    __tablename__ = "funding_programmes"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sponsor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sponsors.id"))
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id"))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), default="UGX")
    budget: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProgrammeAllocation(Base):
    __tablename__ = "programme_allocations"
    __table_args__ = (UniqueConstraint("programme_id", "student_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    programme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funding_programmes.id"))
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"))
    beneficiary_ref: Mapped[str] = mapped_column(String(32), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="UGX")
    status: Mapped[str] = mapped_column(String(20), default="allocated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupportCase(Base):
    __tablename__ = "support_cases"
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="ck_support_cases_target_amount"),
        CheckConstraint(
            "status in ('draft','review','published','funded','closed','withdrawn')",
            name="ck_support_cases_status",
        ),
        Index("ix_support_cases_school_status", "school_id", "status"),
        Index("ix_support_cases_student_period", "student_id", "period_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), index=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_periods.id", ondelete="RESTRICT"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )
    requirement_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_requirements.id", ondelete="RESTRICT"), index=True
    )
    public_code: Mapped[str] = mapped_column(String(24), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    public_summary: Mapped[str] = mapped_column(String(500))
    need_category: Mapped[str] = mapped_column(String(40))
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="UGX")
    risk_level: Mapped[str] = mapped_column(String(16), default="review")
    risk_reasons: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_by: Mapped[str] = mapped_column(String(120))
    approved_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportConsent(Base):
    __tablename__ = "support_consents"
    __table_args__ = (
        CheckConstraint("status in ('active','withdrawn')", name="ck_support_consents_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_cases.id", ondelete="RESTRICT"), unique=True, index=True
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), index=True
    )
    guardian_link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guardian_links.id", ondelete="RESTRICT")
    )
    method: Mapped[str] = mapped_column(String(24))
    scope_version: Mapped[str] = mapped_column(String(24), default="2026-10")
    anonymous_publication: Mapped[bool] = mapped_column(default=True)
    gemma_processing: Mapped[bool] = mapped_column(default=False)
    cross_border_processing: Mapped[bool] = mapped_column(default=False)
    child_assent_status: Mapped[str] = mapped_column(String(24), default="not_applicable")
    status: Mapped[str] = mapped_column(String(16), default="active")
    recorded_by: Mapped[str] = mapped_column(String(120))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportAiReview(Base):
    __tablename__ = "support_ai_reviews"
    __table_args__ = (Index("ix_support_ai_reviews_case_time", "case_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_cases.id", ondelete="RESTRICT"), index=True
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), index=True
    )
    model_name: Mapped[str] = mapped_column(String(80))
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="completed")
    result_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupportPledge(Base):
    __tablename__ = "support_pledges"
    __table_args__ = (
        UniqueConstraint("case_id", "external_reference"),
        CheckConstraint("amount > 0", name="ck_support_pledges_amount"),
        CheckConstraint(
            "status in ('pending','verified','rejected')", name="ck_support_pledges_status"
        ),
        Index("ix_support_pledges_case_status", "case_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_cases.id", ondelete="RESTRICT"), index=True
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), index=True
    )
    public_reference: Mapped[str] = mapped_column(String(32), unique=True)
    external_reference: Mapped[str] = mapped_column(String(100))
    donor_display_name: Mapped[str | None] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="UGX")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[str | None] = mapped_column(String(120))


class SupportAttestation(Base):
    __tablename__ = "support_attestations"
    __table_args__ = (
        CheckConstraint(
            "attestation_type in ('guardian_acknowledgement','fulfilment',"
            "'enrolment','independent_audit')",
            name="ck_support_attestations_type",
        ),
        Index("ix_support_attestations_case_time", "case_id", "verified_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_cases.id", ondelete="RESTRICT"), index=True
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), index=True
    )
    attestation_type: Mapped[str] = mapped_column(String(32))
    statement: Mapped[str] = mapped_column(String(500))
    attendance_band: Mapped[str | None] = mapped_column(String(24))
    evidence_hash: Mapped[str | None] = mapped_column(String(64))
    is_public: Mapped[bool] = mapped_column(default=True)
    verified_by: Mapped[str] = mapped_column(String(120))
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
