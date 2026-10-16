import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from harambeeone_api.academic_structure import PROGRAMME_NAMES, template_classes


class GuardianCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    relationship: str = Field(pattern="^(father|mother|guardian|other)$")
    phone: str = Field(min_length=7, max_length=32)
    email: EmailStr | None = None
    is_primary: bool = False


class StudentCreate(BaseModel):
    school_id: uuid.UUID
    period_id: uuid.UUID | None = None
    first_name: str = Field(min_length=1, max_length=80)
    middle_name: str | None = Field(default=None, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    date_of_birth: date | None = None
    gender: str = Field(pattern="^(male|female|other)$")
    learner_identification_number: str | None = Field(default=None, max_length=40)
    class_id: uuid.UUID | None = None
    stream_id: uuid.UUID | None = None
    fee_structure_id: uuid.UUID | None = None
    academic_year: int = Field(ge=2000, le=2100)
    term: int = Field(ge=1, le=3)
    boarding_status: str = Field(default="day", pattern="^(day|boarding|half_boarding)$")
    nationality: str = Field(default="Ugandan", max_length=60)
    previous_school: str | None = Field(default=None, max_length=160)
    special_needs: str | None = Field(default=None, max_length=1000)
    guardians: list[GuardianCreate] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def require_one_primary_guardian(self) -> "StudentCreate":
        primary_count = sum(guardian.is_primary for guardian in self.guardians)
        if primary_count != 1:
            raise ValueError("Exactly one guardian must be primary")
        if self.class_id is None and (
            self.stream_id is not None or self.fee_structure_id is not None
        ):
            raise ValueError("A stream or fee structure requires a class")
        return self


class StudentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    admission_no: str
    full_name: str
    gender: str
    status: str
    class_name: str
    stream_name: str | None
    primary_guardian: str
    guardian_phone: str


class StudentList(BaseModel):
    items: list[StudentSummary]
    total: int


class StudentStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|transferred|withdrawn|completed|archived)$")


class StudentProfileUpdate(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    middle_name: str | None = Field(default=None, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    date_of_birth: date | None = None
    gender: str = Field(pattern="^(male|female|other)$")
    learner_identification_number: str | None = Field(default=None, max_length=40)
    boarding_status: str = Field(pattern="^(day|boarding|half_boarding)$")
    nationality: str = Field(min_length=1, max_length=60)
    previous_school: str | None = Field(default=None, max_length=160)
    special_needs: str | None = Field(default=None, max_length=1000)
    guardian_id: uuid.UUID
    guardian_first_name: str = Field(min_length=1, max_length=80)
    guardian_last_name: str = Field(min_length=1, max_length=80)
    guardian_relationship: str = Field(pattern="^(father|mother|guardian|other)$")
    guardian_phone: str = Field(min_length=7, max_length=32)
    guardian_email: EmailStr | None = None


class StudentTransfer(BaseModel):
    class_id: uuid.UUID
    stream_id: uuid.UUID | None = None
    period_id: uuid.UUID | None = None
    academic_year: int = Field(ge=2000, le=2100)
    term: int = Field(ge=1, le=3)


class BulkStudentImport(BaseModel):
    students: list[StudentCreate] = Field(min_length=1, max_length=500)
    validate_only: bool = False


class StreamSummary(BaseModel):
    id: uuid.UUID
    name: str


class ClassWrite(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    level: str = Field(
        pattern="^(baby|nursery|primary|secondary|day_care|pre_primary|lower_secondary|upper_secondary|other)$"
    )
    canonical_code: str | None = Field(default=None, max_length=32, pattern="^[A-Z0-9_-]+$")
    sort_order: int = Field(ge=0, le=100)
    streams: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def normalize_and_validate_streams(self) -> "ClassWrite":
        self.name = self.name.strip()
        self.canonical_code = self.canonical_code.strip().upper() if self.canonical_code else None
        self.streams = [name.strip() for name in self.streams if name.strip()]
        if any(len(name) > 40 for name in self.streams):
            raise ValueError("Stream names cannot exceed 40 characters")
        if len({name.casefold() for name in self.streams}) != len(self.streams):
            raise ValueError("Stream names must be unique within a class")
        return self


class ClassSummary(BaseModel):
    id: uuid.UUID
    name: str
    level: str
    canonical_code: str | None
    sort_order: int
    student_count: int
    streams: list[StreamSummary]


class ProgrammeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    programme_code: str
    display_name: str
    sort_order: int


class SchoolSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    district: str | None
    emis_code: str | None
    programmes: list[ProgrammeSummary] = Field(default_factory=list)


class SchoolAccessSummary(SchoolSummary):
    role: str
    permissions: list[str]


class SchoolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    district: str | None = Field(default=None, max_length=80)
    emis_code: str | None = Field(default=None, max_length=40)
    programme_codes: list[str] = Field(min_length=1, max_length=5)
    canonical_codes: list[str] = Field(default_factory=list, max_length=20)
    default_streams: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def normalize_school_structure(self) -> "SchoolCreate":
        self.name = self.name.strip()
        self.district = self.district.strip() if self.district else None
        self.emis_code = self.emis_code.strip() if self.emis_code else None
        self.programme_codes = list(dict.fromkeys(self.programme_codes))
        invalid = set(self.programme_codes) - set(PROGRAMME_NAMES)
        if invalid:
            raise ValueError(f"Unknown education programme: {', '.join(sorted(invalid))}")
        self.canonical_codes = [code.strip().upper() for code in self.canonical_codes]
        valid_codes = {code for code, _name, _programme in template_classes(self.programme_codes)}
        invalid_codes = set(self.canonical_codes) - valid_codes
        if invalid_codes:
            raise ValueError(
                f"Classes do not belong to the selected programmes: "
                f"{', '.join(sorted(invalid_codes))}"
            )
        self.default_streams = [name.strip() for name in self.default_streams if name.strip()]
        if any(len(name) > 40 for name in self.default_streams):
            raise ValueError("Default stream names cannot exceed 40 characters")
        if len({name.casefold() for name in self.default_streams}) != len(self.default_streams):
            raise ValueError("Default stream names must be unique")
        return self


class SchoolOnboardingCreate(SchoolCreate):
    """The institution structure selected during authenticated account onboarding."""


class AcademicPeriodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    sequence: int = Field(ge=1, le=12)
    opening_date: date
    closing_date: date
    due_date: date

    @model_validator(mode="after")
    def validate_dates(self) -> "AcademicPeriodCreate":
        self.name = self.name.strip()
        if not self.opening_date <= self.due_date <= self.closing_date:
            raise ValueError("Opening date, due date, and closing date must be in order")
        return self


class AcademicYearCreate(BaseModel):
    school_id: uuid.UUID
    name: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=2000, le=2100)
    start_date: date
    end_date: date
    periods: list[AcademicPeriodCreate] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_calendar(self) -> "AcademicYearCreate":
        self.name = self.name.strip()
        if self.start_date > self.end_date:
            raise ValueError("Academic year start date must be before its end date")
        if len({period.sequence for period in self.periods}) != len(self.periods):
            raise ValueError("Period sequence numbers must be unique")
        if len({period.name.casefold() for period in self.periods}) != len(self.periods):
            raise ValueError("Period names must be unique")
        ordered = sorted(self.periods, key=lambda item: item.sequence)
        for index, period in enumerate(ordered):
            if period.opening_date < self.start_date or period.closing_date > self.end_date:
                raise ValueError("Every period must fall within the academic year")
            if index and period.opening_date <= ordered[index - 1].closing_date:
                raise ValueError("Academic periods cannot overlap")
        return self


class AcademicPeriodUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    opening_date: date
    closing_date: date
    due_date: date

    @model_validator(mode="after")
    def validate_dates(self) -> "AcademicPeriodUpdate":
        self.name = self.name.strip()
        if not self.opening_date <= self.due_date <= self.closing_date:
            raise ValueError("Opening date, due date, and closing date must be in order")
        return self


class AcademicPeriodTransition(BaseModel):
    status: str = Field(pattern="^(open|closing|closed)$")
    reason: str | None = Field(default=None, max_length=240)


class ClassTemplateApply(BaseModel):
    programme_codes: list[str] = Field(min_length=1, max_length=4)
    canonical_codes: list[str] = Field(default_factory=list, max_length=20)
    streams: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def normalize_template_selection(self) -> "ClassTemplateApply":
        self.programme_codes = list(dict.fromkeys(self.programme_codes))
        invalid = set(self.programme_codes) - (set(PROGRAMME_NAMES) - {"day_care"})
        if invalid:
            raise ValueError(f"Unknown class programme: {', '.join(sorted(invalid))}")
        self.canonical_codes = [code.strip().upper() for code in self.canonical_codes]
        self.streams = [name.strip() for name in self.streams if name.strip()]
        if any(len(name) > 40 for name in self.streams):
            raise ValueError("Stream names cannot exceed 40 characters")
        if len({name.casefold() for name in self.streams}) != len(self.streams):
            raise ValueError("Stream names must be unique")
        return self


class FeeStructureSummary(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    stream_id: uuid.UUID | None
    name: str
    academic_year: int
    term: int
    currency: str
    total_amount: Decimal
    target_type: str
    boarding_status: str | None
    status: str
    selected_learner_count: int = 0
    installments: list[dict] = Field(default_factory=list)


class FeeCategoryCreate(BaseModel):
    school_id: uuid.UUID
    name: str = Field(min_length=1, max_length=80)
    code: str = Field(min_length=2, max_length=12, pattern="^[A-Za-z0-9_-]+$")
    category_type: str = Field(default="other", max_length=30)
    is_required: bool = True
    is_recurring: bool = True
    priority: int = Field(default=1, ge=1, le=100)


class FeeLineCreate(BaseModel):
    category_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class InstallmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    calculation_type: str = Field(default="fixed", pattern="^(fixed|percentage)$")
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    percentage: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=4)
    due_date: date
    sort_order: int = Field(ge=1, le=20)

    @model_validator(mode="after")
    def validate_calculation(self) -> "InstallmentCreate":
        if self.calculation_type == "fixed" and self.amount is None:
            raise ValueError("A fixed installment requires an amount")
        if self.calculation_type == "percentage" and self.percentage is None:
            raise ValueError("A percentage installment requires a percentage")
        if self.calculation_type == "fixed":
            self.percentage = None
        else:
            self.amount = None
        return self

    def calculated_amount(self, total: Decimal) -> Decimal:
        if self.calculation_type == "fixed":
            assert self.amount is not None
            return self.amount
        assert self.percentage is not None
        return (total * self.percentage / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


class FeePlanCreate(BaseModel):
    school_id: uuid.UUID
    class_id: uuid.UUID
    stream_id: uuid.UUID | None = None
    period_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    academic_year: int = Field(ge=2000, le=2100)
    term: int = Field(ge=1, le=3)
    currency: str = Field(default="UGX", pattern="^[A-Z]{3}$")
    target_type: str = Field(default="cohort", pattern="^(cohort|selected)$")
    boarding_status: str | None = Field(
        default=None, pattern="^(day|boarding|half_boarding)$"
    )
    student_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    items: list[FeeLineCreate] = Field(min_length=1, max_length=30)
    installments: list[InstallmentCreate] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_plan(self) -> "FeePlanCreate":
        item_total = sum(item.amount for item in self.items)
        installment_total = sum(
            (item.calculated_amount(item_total) for item in self.installments), Decimal("0")
        )
        if item_total != installment_total:
            raise ValueError("Installments must total the fee category amounts")
        if len({item.category_id for item in self.items}) != len(self.items):
            raise ValueError("Each fee category may appear only once")
        if len({item.sort_order for item in self.installments}) != len(self.installments):
            raise ValueError("Installment order values must be unique")
        if len(set(self.student_ids)) != len(self.student_ids):
            raise ValueError("Each selected learner may appear only once")
        if self.target_type == "selected" and not self.student_ids:
            raise ValueError("Select at least one learner for a selected-learner plan")
        if self.target_type == "cohort" and self.student_ids:
            raise ValueError("Cohort plans cannot contain selected learner IDs")
        return self


class RequirementCreate(BaseModel):
    school_id: uuid.UUID
    period_id: uuid.UUID | None = None
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=20, pattern="^[A-Za-z0-9_-]+$")
    requirement_type: str = Field(pattern="^(payment|school_item|bring_item|document)$")
    description: str | None = Field(default=None, max_length=1000)
    academic_year: int = Field(ge=2000, le=2100)
    term: int = Field(ge=1, le=3)
    amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    quantity: Decimal = Field(default=Decimal("1"), gt=0, max_digits=10, decimal_places=2)
    unit: str = Field(default="item", min_length=1, max_length=30)
    due_date: date | None = None
    stream_id: uuid.UUID | None = None
    boarding_status: str | None = Field(
        default=None, pattern="^(day|boarding|half_boarding)$"
    )
    is_mandatory: bool = True
    class_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    student_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_requirement(self) -> "RequirementCreate":
        self.name = self.name.strip()
        self.code = self.code.strip().upper()
        self.unit = self.unit.strip().lower()
        if self.requirement_type in {"payment", "school_item"} and self.amount <= 0:
            raise ValueError("Payable requirements must have an amount greater than zero")
        if self.requirement_type in {"bring_item", "document"} and self.amount != 0:
            raise ValueError("Brought items and documents cannot have a cash amount")
        if len(set(self.class_ids)) != len(self.class_ids):
            raise ValueError("Each target class may appear only once")
        if len(set(self.student_ids)) != len(self.student_ids):
            raise ValueError("Each selected learner may appear only once")
        if not self.is_mandatory and not self.student_ids:
            raise ValueError("Optional requirements must identify the learners who selected them")
        return self


class BillingAdjustmentCreate(BaseModel):
    school_id: uuid.UUID
    period_id: uuid.UUID | None = None
    student_id: uuid.UUID
    category_id: uuid.UUID | None = None
    adjustment_type: str = Field(
        pattern="^(addition|discount|sponsorship_credit|waiver)$"
    )
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    description: str = Field(min_length=2, max_length=160)
    reason: str = Field(min_length=3, max_length=500)


class BillingPublishCreate(BaseModel):
    school_id: uuid.UUID
    period_id: uuid.UUID
    preview_token: str = Field(min_length=64, max_length=64, pattern="^[a-f0-9]+$")
    idempotency_key: str = Field(min_length=8, max_length=80, pattern="^[A-Za-z0-9_-]+$")


class RequirementFulfilmentCreate(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    note: str | None = Field(default=None, max_length=240)


class PaymentCreate(BaseModel):
    school_id: uuid.UUID
    student_id: uuid.UUID
    period_id: uuid.UUID | None = None
    external_reference: str = Field(min_length=3, max_length=100)
    payer_name: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=240)
    channel: str = Field(pattern="^(cash|bank|mobile_money|schoolpay|card|sponsor)$")
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    requirement_assignment_id: uuid.UUID | None = None


class PaymentSummary(BaseModel):
    id: uuid.UUID
    receipt_no: str
    external_reference: str
    student_name: str
    admission_no: str
    channel: str
    amount: Decimal
    currency: str
    status: str
    purpose: str
    stellar_status: str
    commitment_hash: str
    received_at: str


class ReceiptDetail(PaymentSummary):
    school_name: str
    school_district: str | None
    payer_name: str | None
    note: str | None
    billed: Decimal
    paid_to_date: Decimal
    balance: Decimal


class ArrearAccount(BaseModel):
    student_id: uuid.UUID
    admission_no: str
    student_name: str
    class_name: str
    guardian_name: str | None
    guardian_phone: str | None
    billed: Decimal
    paid: Decimal
    balance: Decimal
    overdue_amount: Decimal
    overdue_since: date
    days_overdue: int
    severity: str


class ArrearsRegister(BaseModel):
    as_of: date
    total_accounts: int
    total_overdue: Decimal
    critical_accounts: int
    items: list[ArrearAccount]


class StatementRowCreate(BaseModel):
    transaction_date: date
    source_reference: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=240)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class StatementImportCreate(BaseModel):
    school_id: uuid.UUID
    file_name: str = Field(min_length=1, max_length=160)
    rows: list[StatementRowCreate] = Field(min_length=1, max_length=500)


class ReconciliationConfirm(BaseModel):
    student_id: uuid.UUID
    period_id: uuid.UUID | None = None


class ProgrammeCreate(BaseModel):
    school_id: uuid.UUID
    sponsor_name: str = Field(min_length=2, max_length=160)
    sponsor_type: str = Field(pattern="^(foundation|ngo|corporate|individual|government|other)$")
    country: str = Field(default="Uganda", max_length=80)
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    budget: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="UGX", pattern="^[A-Z]{3}$")


class ProgrammeAllocationCreate(BaseModel):
    student_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class SupportCaseCreate(BaseModel):
    school_id: uuid.UUID
    period_id: uuid.UUID | None = None
    student_id: uuid.UUID
    requirement_assignment_id: uuid.UUID | None = None
    title: str = Field(min_length=4, max_length=120)
    public_summary: str = Field(min_length=20, max_length=500)
    need_category: str = Field(
        pattern="^(fees|examination|uniform|learning_materials|meals|transport|other)$"
    )
    target_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class SupportConsentCreate(BaseModel):
    guardian_link_id: uuid.UUID
    method: str = Field(pattern="^(otp|signed_form|witnessed_in_person)$")
    scope_version: str = Field(default="2026-10", min_length=4, max_length=24)
    anonymous_publication: bool = True
    gemma_processing: bool
    cross_border_processing: bool
    child_assent_status: str = Field(pattern="^(agreed|declined|not_applicable|unable_to_express)$")

    @model_validator(mode="after")
    def validate_gemma_scope(self):
        if self.gemma_processing and not self.cross_border_processing:
            raise ValueError("Gemma processing requires separate cross-border consent")
        return self


class SupportAiReviewCreate(BaseModel):
    evidence_image_base64: str | None = Field(default=None, max_length=8_000_000)
    evidence_mime_type: str | None = Field(default=None, pattern="^image/(jpeg|png|webp)$")
    evidence_redacted: bool = False

    @model_validator(mode="after")
    def validate_evidence(self):
        if bool(self.evidence_image_base64) != bool(self.evidence_mime_type):
            raise ValueError("Evidence image and MIME type must be provided together")
        if self.evidence_image_base64 and not self.evidence_redacted:
            raise ValueError("Confirm that identifying information was redacted")
        return self


class SupportPledgeCreate(BaseModel):
    external_reference: str = Field(min_length=4, max_length=100)
    donor_display_name: str | None = Field(default=None, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class SupportPledgeVerify(BaseModel):
    action: str = Field(pattern="^(verify|reject)$")
    reason: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def validate_rejection_reason(self):
        if self.action == "reject" and not (self.reason or "").strip():
            raise ValueError("A rejection reason is required")
        return self


class SupportAttestationCreate(BaseModel):
    attestation_type: str = Field(
        pattern="^(guardian_acknowledgement|fulfilment|enrolment|independent_audit)$"
    )
    statement: str = Field(min_length=10, max_length=500)
    attendance_band: str | None = Field(
        default=None, pattern="^(below_50|50_to_69|70_to_79|80_to_89|90_plus)$"
    )
    evidence_hash: str | None = Field(default=None, pattern="^[a-fA-F0-9]{64}$")
    is_public: bool = True


class GuardianInvitationCreate(BaseModel):
    school_id: uuid.UUID
    guardian_link_id: uuid.UUID


class GuardianInvitationAccept(BaseModel):
    token: str = Field(min_length=32, max_length=200)


class DonorProfileCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    show_public_name: bool = False


class PortalPreferenceUpdate(BaseModel):
    preferred_workspace: str | None = Field(
        default=None, pattern="^(school|guardian|donor)$"
    )


class SupportReferralCreate(BaseModel):
    school_id: uuid.UUID
    period_id: uuid.UUID
    student_id: uuid.UUID
    guardian_link_id: uuid.UUID


class SupportReferralConsent(BaseModel):
    action: str = Field(pattern="^(grant|decline)$")
    privacy_notice_version: str = Field(default="2026-10-v1", max_length=24)
    guardian_authority_confirmed: bool
    age_verification_method: str = Field(
        pattern="^(school_record|birth_certificate|guardian_declaration|national_id|other)$"
    )
    anonymous_publication: bool = False
    gemma_processing: bool = False
    cross_border_processing: bool = False
    child_assent_status: str = Field(
        pattern="^(agreed|declined|not_applicable|unable_to_express)$"
    )
    child_assent_reason: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def validate_support_consent(self):
        if self.action == "grant" and not self.guardian_authority_confirmed:
            raise ValueError("Confirm guardian authority before giving consent")
        if self.action == "grant" and not self.anonymous_publication:
            raise ValueError("Anonymous publication consent is required to participate")
        if self.child_assent_status in {"not_applicable", "unable_to_express"} and not (
            self.child_assent_reason or ""
        ).strip():
            raise ValueError("Explain why learner assent was not applicable or unavailable")
        if self.gemma_processing and not self.cross_border_processing:
            raise ValueError("Gemma processing requires separate cross-border consent")
        return self


class PublicSupportPledge(BaseModel):
    public_reference: str
    amount: Decimal
    currency: str
    status: str
    created_at: datetime
    verified_at: datetime | None
