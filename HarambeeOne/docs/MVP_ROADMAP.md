# HarambeeOne Bursar Implementation Plan

This is the canonical delivery plan for HarambeeOne. Read this file before making any code, database, configuration, or interface change. Work on only the first incomplete delivery slice, complete it end to end, verify every completion gate, update this document, and commit the finished slice before moving to the next one.

## Product boundary

HarambeeOne serves the school bursar. Every active feature must directly support learner billing, requirements, collections, receipts, reconciliation, arrears follow-up, financial reporting, or the minimum learner and school structure needed for those duties.

Sponsor administration and blockchain settlement remain deferred until the bursar completion gate passes. The user-authorized Harambee Support hackathon pilot is the sole exception: it is an isolated, privacy-preserving workflow backed by existing learner obligations and does not reopen general sponsor administration or blockchain settlement. Academic grading, attendance, teaching, payroll, procurement, and general school administration are outside the current product.

## Delivery discipline

For every slice:

1. Re-read this plan and confirm the slice is the first incomplete priority.
2. Inspect the existing implementation and preserve working behaviour.
3. Define database, API, interface, authorization, audit, loading, empty, error, and success behaviour before editing.
4. Implement the complete vertical workflow rather than isolated screens.
5. Add migrations and indexes where required; never edit production data manually as the implementation.
6. Test success, validation, authorization, tenant isolation, duplicate submission, retry, and rollback behaviour.
7. Run relevant backend tests, frontend checks, production builds, and database verification.
8. Update the status and evidence in this file only after the completion gate passes.
9. Commit the completed coherent change with one concise, single-line commit message.
10. Do not start the next slice while required work or failing verification remains in the current slice.

Money must use exact decimal values. Posted financial history must be corrected through traceable reversals or adjustments, never destructive edits. Every school-owned record must be tenant-scoped and every consequential financial action must be audited.

## Target bursar workflow

```text
Create school
  -> Configure classes and streams
  -> Open academic period
  -> Register or promote learners
  -> Configure fees and requirements
  -> Preview and publish learner bills
  -> Receive and allocate payments
  -> Issue official receipts
  -> Reconcile cash, bank and provider collections
  -> Follow up arrears
  -> Produce accountability reports
  -> Close the term and carry balances forward
```

## Current capability baseline

| Area | Current position | Gap to close |
| --- | --- | --- |
| Authentication | Supabase email/password and Google entry points exist | Operational APIs need consistent membership enforcement |
| School structure | School levels, classes, optional streams, and editable names exist | Period-aware controls must govern all downstream records |
| Learners | Registration, guardians, placement, import, status, and movement exist | Bulk progression and controlled period rollover are missing |
| Fees | Categories, class plans, and installments exist | Fixed 50/30/balance UI and uncontrolled publishing must be replaced |
| Requirements | Class targeting, assignment, fulfilment, and payment allocation exist | Requirements must appear in the unified learner obligation view |
| Payments | Recording, allocations, ledger entries, and receipts exist | Credits, reversals, refunds, and cashier controls are incomplete |
| Reconciliation | Statement import, suggestions, and confirmation exist | Duplicate protection, undo, unidentified funds, and cash-up are incomplete |
| Arrears | Overdue calculations and filters exist | Aging, follow-up history, promises, and exports are incomplete |
| Reports | Collections report exists | Control reports, statements, close reports, and exports are incomplete |
| Governance | Demonstration interface exists | Real roles and approval policies are not implemented |
| Settlement | Demonstration interface exists | Deferred until bursar operations are complete |
| Verification | Limited backend tests exist | Financial, authorization, frontend, and end-to-end coverage is insufficient |

## Ordered implementation slices

### Slice 1 - Tenant security and bursar authorization

Status: **COMPLETE**

Implement:

- Require a valid Supabase session for every operational API.
- Resolve the active school from `school_memberships`; do not authorize from a submitted `school_id` alone.
- Add owner, bursar, cashier, and auditor permissions with least privilege.
- Enforce school ownership in API queries and Supabase row-level security policies.
- Record the authenticated actor on every consequential audit event.
- Keep service-role or secret credentials out of browser code.

Completion gate:

- Unauthenticated requests return `401`.
- Authenticated users without permission return `403`.
- Cross-school reads and writes fail in API and database tests.
- Authorized workflows continue to work through the web application.
- Security-relevant Supabase guidance is checked against current official documentation.

Verification evidence:

- 26 backend tests pass, including unauthenticated, role, cross-school query, cross-school resource, cross-school write, and authenticated audit-actor cases.
- Ruff passes for backend source, tests, migrations, and verification scripts.
- Web lint and the optimized Next.js production build pass.
- Live Supabase is at Alembic head `5342e3f4519b`; tenant RLS, membership-role constraints, policy counts, and private helper privileges pass `verify_tenant_security.py`.
- Development smoke tests return `401` from both the same-origin gateway and direct Python API without a session, while the public health endpoint remains available.

### Slice 2 - Academic period lifecycle

Status: **COMPLETE**

Implement:

- School-owned academic years and terms with names, opening dates, closing dates, due dates, and statuses.
- Draft, open, closing, and closed lifecycle rules.
- One active operational period per school, with historical period selection.
- Configurable Uganda calendar defaults without hard-coded dates.
- Safe correction, close, and authorized reopen behaviour.
- Replace every hard-coded or manually duplicated period selector across the application.

Completion gate:

- Changing the active period changes dashboard, enrollment, fees, requirements, arrears, payments, and reports consistently.
- Closed periods reject ordinary mutations.
- Periods containing financial activity cannot be destructively deleted.

### Slice 3 - Controlled term billing

Status: **COMPLETE**

Implement:

- Flexible fee plans by class, stream where needed, boarding status, or selected learner group.
- Any number of fixed-amount or percentage installments.
- Monetary and physical requirements, including candidate-only P.7, S.4, and S.6 items.
- Optional items such as uniforms, transport, meals, trips, and other school-defined charges.
- Learner-specific additions, discounts, sponsorship credits, and waivers with reasons.
- A billing preview showing included learners, exclusions, conflicts, and exact totals.
- Atomic, idempotent publication that creates immutable learner charge entries exactly once.

Completion gate:

- A bursar can configure and publish a complete term bill to every eligible learner.
- Repeated submission cannot double-bill a learner.
- Preview totals equal posted ledger totals at learner, class, and school level.

### Slice 4 - Learner financial account

Status: **COMPLETE**

Implement:

- One chronological statement containing opening balances, charges, requirements, payments, allocations, discounts, waivers, credits, reversals, refunds, and carried balances.
- A running balance after every ledger entry.
- Clear separation between tuition, other charges, optional purchases, and physical requirements.
- Printable and downloadable learner statements.
- Guardian and payer context without exposing unnecessary personal information.
- Preserved history when a learner changes class, stream, status, or period.

Completion gate:

- Every displayed learner balance can be independently recalculated from immutable ledger entries.
- Statement totals agree with billing, payment, arrears, and reporting totals.

### Priority override - Harambee Support pilot

Status: **COMPLETE**

This one-off override was explicitly authorized for the 2026 Wakiso hackathon. It does not change the next bursar priority, which remains Slice 5.

Implemented:

- Private, tenant-scoped support cases tied to a real learner ledger balance or monetary requirement.
- Scoped guardian consent, learner assent state, anonymous-publication enforcement, and separate consent for Gemma and cross-border processing.
- Gemma 4 multimodal review of pseudonymous facts and optional redacted evidence, with deterministic schema validation and mandatory human approval.
- A separate signed-out donor portal that exposes campaign codes, verified totals, pending totals, redacted AI findings, and anonymous outcome attestations without learner or guardian identity.
- Idempotent donor pledges with public tracking references; pending pledges never count as funded.
- Atomic settlement verification that rechecks the live obligation and creates the payment, learner allocation, ledger credit, receipt, audit record, and pending settlement commitment together.
- Tenant RLS, revoked Data API grants, immutable verified contributions, indexed lookups, public-text identity checks, and an MIT open-source license.

Completion gate:

- The full private-case-to-public-campaign-to-verified-learner-credit journey passes automated tests.
- Identity leakage, over-target support, duplicate references, cross-tenant access, unconsented publication, and partial settlement failure are rejected.
- The optimized web build includes the private school workspace, public donor portal, and public tracking gateway.
- The live Supabase migration and database security verification pass.

Verification evidence:

- Ruff passes and all 40 backend tests pass, including three Harambee Support end-to-end, validation, tenant, duplicate, and rollback tests.
- Web lint and the optimized 30-route Next.js production build pass.
- The campaign workspace is now directly reachable from a dedicated Support navigation group and from the public portal; case creation exposes live requirement obligations, explains the consent-review-owner-publication sequence, and was reverified with web lint, the 30-route production build, public campaign API HTTP 200, signed-out admin redirect, and database readiness HTTP 200.
- Google OAuth now starts through a server-owned PKCE route and explicitly carries verifier and session cookies across redirects; invalid callbacks fail safely, campaign API responses reject HTML/error payloads cleanly, the 31-route production build passes, and live checks confirm login and Support stylesheets, database readiness, and the public campaign endpoint return HTTP 200.
- Support case creation now previews the server-calculated eligible balance, constrains targets to the selected obligation, rejects learner identity before submission, and keeps precise API validation errors inside the active modal; Ruff, all 41 backend tests, web lint, the 31-route production build, and the rolled-back live Supabase Support verification pass.
- Live Supabase reached Alembic head `9d2a6f08c4b1`; `verify_support.py` passed tenant RLS, revoked grants, policy, trigger, immutability, and index checks, then completed the private-case-to-public-campaign-to-payment-to-ledger-to-proof journey inside a fully rolled-back transaction.
- Current official Supabase guidance was reviewed: exposed tables require RLS plus explicit grants, secrets stay server-side, and schema changes remain migration-managed. The October 2026 Data API exposure and TLS changelog items do not require an implementation change here.
- Current official Google documentation confirms `gemma-4-26b-a4b-it`, image input, and the Gemini API endpoint used by the server integration.
- The hardened live integration now locks the exact model, keeps its credential in the server-only API header, validates a strict privacy-safe response contract, rejects returned identity across every review field, and passed a real Gemini API smoke test. Ruff, all 56 backend tests, web lint and the optimized 36-route build pass; this does not mark the later multi-role assistant slice complete.

### Priority override - Harambee Support multi-role expansion

Status: **IN PROGRESS — S3 NEXT**

The user explicitly authorized a second Support priority override on 2026-10-16. It expands the privacy-preserving pilot into guardian and donor workspaces while keeping every campaign tied to the bursar ledger and every settlement directed to a school-controlled payment channel. The ordered, completion-gated implementation and legal safeguards are defined in `docs/HARAMBEE_SUPPORT_EXPANSION_PLAN.md`.

Work through Support slices S1-S6 in order. Do not resume Slice 5 or begin another Support slice until the active slice meets every completion gate and is committed. The normal bursar roadmap resumes at Slice 5 after this override is complete.

### Slice 5 - Payment desk and official receipts

Status: **NEXT**

Implement:

- Fast learner search by name, admission number, guardian, or phone.
- Open obligations displayed before money is entered.
- Cash, bank, mobile money, SchoolPay, and configurable payment channels.
- Split allocation across fees and requirements, partial payments, and unallocated learner credit.
- Duplicate external-reference protection.
- Sequential school-specific official receipt numbers, printing, and reprinting.
- Authorized reversals and refunds that preserve the original transaction and require a reason.
- One canonical payment workflow; remove or redirect duplicate dashboard payment behaviour.

Completion gate:

- A payment updates the learner account, requirements, arrears, dashboard, receipt, and reports in one database transaction.
- Failed posting leaves no partial financial records.
- Reversal restores balances without deleting evidence.

### Slice 6 - Reconciliation and daily cash-up

Status: **PENDING**

Implement:

- Validated CSV adapters for supported banks, mobile money providers, and SchoolPay exports.
- File and transaction duplicate protection.
- Suggested learner matches with explainable confidence.
- Confirm, reject, and authorized undo actions.
- An unidentified-funds holding register.
- Cashier collection batches, expected cash, counted cash, variance, deposits, and supervisor sign-off.
- Reconciliation summaries by channel and period.
- Route dashboard statement imports through the canonical reconciliation API.

Completion gate:

- Every collected amount is reconciled, awaiting review, unidentified, or formally reversed.
- Provider totals, posted payments, deposits, and variances can be traced and reproduced.

### Slice 7 - Arrears management

Status: **PENDING**

Implement:

- Current, 1-30, 31-60, 61-90, and 90+ day aging.
- Filters by period, class, stream, boarding status, fee category, and severity.
- Guardian contact history, notes, next actions, and payment promises.
- Printable worklists and guardian statement exports.
- Internal follow-up workflow before adding SMS or WhatsApp integrations.

Completion gate:

- A bursar can identify who owes what, why it is owed, who was contacted, what was promised, and what action is due next.

### Slice 8 - Reports, close, and rollover

Status: **PENDING**

Implement:

- Daily collections, cashier, channel, class, stream, fee-category, and requirements reports.
- Learner balances, arrears aging, adjustments, reversals, refunds, unidentified funds, reconciliation variance, cash-up, deposit, and billing-versus-collection reports.
- Exportable and printable reports with consistent filters and totals.
- Pre-close validation for unresolved reconciliation, unallocated payments, and control variances.
- Period locking, closing control summary, balance carry-forward, and learner promotion or movement.
- Authorized reopening with complete audit evidence.

Completion gate:

- `opening balance + charges - credits - payments = closing balance` at learner, class, and school level.
- A closed term remains historically reproducible after the next term opens.

## Bursar completion gate

Sponsor administration may resume only when all eight slices are marked **COMPLETE** and the following journey passes against a Supabase-backed test environment:

1. A user signs up, creates a school, and receives an authorized role.
2. The bursar creates the school structure and opens a term.
3. Learners and guardians are registered or imported and placed correctly.
4. Fees and targeted requirements are previewed and published exactly once.
5. Cash and electronic payments are allocated and receipted.
6. Statements are imported, matched, reconciled, and included in cash-up.
7. Arrears are followed up and statements are produced.
8. Reports balance and the term closes with balances carried forward.
9. Audit evidence identifies who performed every consequential action.
10. Cross-school access, unauthorized actions, duplicate submissions, and partial failures are rejected by automated tests.

## Deferred roadmap

Only after the bursar completion gate:

1. Sponsor onboarding and programme administration.
2. Beneficiary allocation and sponsor reporting.
3. Audited Stellar testnet settlement controls.
4. Settlement-provider and fiat-delivery reconciliation.
5. Independent security and corridor validation before any mainnet activity.

## Progress log

Add a dated entry only when a slice changes status. Include the verification commands or evidence used to justify completion.

- 2026-10-09: Replaced the broad roadmap with the ordered bursar implementation plan. Slice 1 is the next authorized delivery target.
- 2026-10-09: Completed Slice 1. Supabase-backed tenant policies, server-derived roles, authenticated web/API transport, scoped resource queries, audit attribution, 26 backend tests, frontend lint/build, and live database verification passed. Slice 2 is next.
- 2026-10-11: Completed Slice 2. Academic-year and period setup, lifecycle transitions, historical selection, tenant-scoped permissions, database-enforced closed-period protection, and period-aware bursar registers were implemented. Ruff and 31 backend tests passed, including cross-period enrollment, fees, requirements, arrears, payments, dashboard, and reporting coverage; web lint and the 28-route production build passed; live Supabase reached Alembic head `20e3e44669b3`, and `verify_academic_periods.py` passed its RLS, policy, trigger, backfill, uniqueness, privilege, and closed-period checks. Slice 3 is next.
- 2026-10-12: Completed Slice 3. Flexible class, stream, residence, and selected-learner fee plans; arbitrary fixed or percentage installments; monetary, physical, optional, and candidate requirements; reasoned learner additions and credits; exact conflict-aware previews; and atomic idempotent publication to immutable ledger entries were implemented. Ruff and 35 backend tests passed, including learner-, class-, and school-level preview/posting equality, replay protection, and safe draft removal; web lint and the 28-route production build passed; live Supabase reached Alembic head `81d7c62772c3`; `verify_controlled_billing.py` passed RLS, policy, grant, trigger, backfill, uniqueness, and immutability checks; and `verify_requirements.py` completed draft-to-publication-to-payment-to-issue in a rollback transaction. Slice 4 is next.
- 2026-10-15: Completed Slice 4. Selected-period learner statements now combine brought-forward balances, categorized charges and requirements, payments and allocations, discounts, waivers, sponsorship credits, reversals, refunds, physical obligations, and carried balances in deterministic chronological order with a recalculated running balance. Historical placement, authorized guardian and payer context, print styling, CSV download, loading, empty, error, filtering, and responsive states were implemented. Ruff and 37 backend tests passed, including exact ledger recalculation, movement history, tenant isolation, auditor access, contact privacy, CSV output, and agreement with dashboard, arrears, and reporting totals; web lint and the 28-route production build passed; live Supabase reached Alembic head `189d96d367f9`; and `verify_learner_accounts.py` passed the chronological index, immutable-ledger, opening-balance, period-activity, and running-balance checks in a rollback transaction. Slice 5 is next.
- 2026-10-16: Completed the explicitly authorized Harambee Support pilot override. Anonymous obligation-backed campaigns, scoped guardian consent and learner assent, Gemma 4 review, owner approval, donor pledges and public tracking, atomic learner-account settlement, outcome proof, tenant controls, and the public portal were delivered. Ruff and all 40 backend tests, web lint, the 30-route production build, live migration `9d2a6f08c4b1`, and the rolled-back live Supabase workflow in `verify_support.py` passed. Slice 5 remains next.
- 2026-10-16: Completed Support expansion S1. Server-derived multi-role portal discovery, school staff continuity, donor activation, hashed 72-hour single-use guardian invitations, verified guardian-account links, role-aware login routing, and separate guardian/donor interfaces were delivered. Ruff, web lint, all 46 backend tests, the optimized 36-route build, live migration `a5da2b77f0d5`, portal RLS/grant/audit verification, and the original rolled-back Support financial workflow passed. Support expansion S2 is next.
- 2026-10-16: Completed Support expansion S2. Canonical arrears-derived referral candidates, verified guardian routing, versioned privacy notice, authority and age checks, independent publication/Gemma/cross-border choices, capable-learner assent, refusal and withdrawal were delivered. Withdrawal closes matching open campaigns without deleting financial evidence. Ruff, web lint, all 48 backend tests, the optimized 36-route build, live migration `e30afe762c9b`, referral RLS/grant/audit verification, and the original rolled-back Support settlement workflow passed. Support expansion S3 is next.
