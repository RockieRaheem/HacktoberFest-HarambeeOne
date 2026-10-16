# HarambeeOne

<p align="center">
  <img src="HarambeeOne/apps/web/public/harambeeone-logo.png" alt="HarambeeOne logo" width="120" />
</p>

<p align="center">
  <strong>One reliable financial record for every learner.</strong><br />
  A bursar-first school finance and learner-support platform built for Uganda.
</p>

HarambeeOne gives schools one accountable workspace for learner billing, payments, requirements, receipts, reconciliation, arrears, and reporting. Instead of storing unexplained balances, it calculates every learner's position from a traceable, immutable financial ledger.

The platform also includes **Harambee Support**: a privacy-conscious workflow through which a school can convert a verified learner obligation into an anonymous support campaign. A donation affects the learner's balance only after the school verifies settlement.

> [!IMPORTANT]
> HarambeeOne is an actively developed MVP. Production financial use requires licensed payment integrations, backups, operational controls, security review, and applicable Ugandan legal and privacy review.

## What the platform provides

- Institution onboarding and tenant-isolated school workspaces
- Owner, bursar, cashier, and auditor access controls
- Ugandan academic years, terms, classes, and streams
- Learner registration, guardian records, placement, import, and transfer workflows
- Flexible fee plans and controlled, idempotent billing publication
- Monetary, physical, mandatory, optional, and learner-specific requirements
- Payment recording, allocations, official receipts, and running statements
- Arrears tracking, reconciliation, collections reports, and audit events
- Guardian consent and privacy-minimized learner-support campaigns
- Human-reviewed AI assistance for support-case drafting
- Stellar Soroban contract prototypes for future accountable settlement

## Core design principle

```text
Learner balance = charges - payments - credits
```

Balances are derived from ledger entries; they are not freely editable totals. Published bills are not silently rewritten, finalized receipts are immutable, and financial corrections use explicit reversal or adjustment entries.

## Typical workflow

```text
Create institution
  -> Configure classes and academic periods
  -> Register or import learners
  -> Define fees and requirements
  -> Preview and publish bills
  -> Record and allocate payments
  -> Issue receipts and reconcile collections
  -> Review arrears and reports
  -> Close the term and carry balances forward
```

## Technology

| Area | Technology |
| --- | --- |
| Web application | Next.js, React, TypeScript |
| Primary API | FastAPI, SQLAlchemy, Alembic, Python 3.12 |
| Authentication | Supabase Auth |
| Database | PostgreSQL with tenant-aware row-level security |
| Legacy API prototype | NestJS and Prisma |
| Contract prototype | Rust and Stellar Soroban |
| Monorepo tooling | pnpm and Turborepo |

## Repository layout

The application source is in [`HarambeeOne/`](HarambeeOne/).

```text
HarambeeOne/
├── apps/
│   ├── web/          # Next.js user interface
│   ├── backend/      # Active FastAPI service, migrations, and tests
│   └── api/          # Retained NestJS/Prisma prototype
├── packages/
│   ├── shared/       # Shared TypeScript package
│   └── soroban/      # Stellar Soroban contract prototype
├── docs/             # Architecture, API, security, and roadmap documents
├── scripts/          # Development setup helpers
└── SUPPORT/          # Product reference materials
```

## Quick start

### Prerequisites

- Node.js 20 or newer
- pnpm 9
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 15 or newer
- A Supabase project for authentication

### Install and configure

```bash
git clone https://github.com/RockieRaheem/HacktoberFest-HarambeeOne.git
cd HacktoberFest-HarambeeOne/HarambeeOne
cp .env.example .env
pnpm install
uv sync --directory apps/backend
```

Update `.env` with your database and Supabase settings, then apply the database migrations:

```bash
uv run --directory apps/backend alembic upgrade head
```

Start the backend and web application in separate terminals:

```bash
uv run --directory apps/backend uvicorn harambeeone_api.main:app --reload
pnpm --filter @harambeeone/web dev
```

Open [http://localhost:3000](http://localhost:3000). The FastAPI service runs at [http://localhost:8000](http://localhost:8000), with interactive API documentation at `/docs`.

## Quality checks

```bash
# Backend tests and linting
uv run --directory apps/backend pytest
uv run --directory apps/backend ruff check .

# Web lint and production build
pnpm --filter @harambeeone/web lint
pnpm --filter @harambeeone/web build
```

## Project status

The bursar finance foundation and initial Harambee Support workflow are implemented. Current work focuses on guardian-authored support cases, school review and publication controls, duplicate-obligation protection, and automatic handling of ledger changes.

For accurate scope and progress, see:

- [MVP roadmap](HarambeeOne/docs/MVP_ROADMAP.md)
- [Architecture](HarambeeOne/docs/ARCHITECTURE.md)
- [API overview](HarambeeOne/docs/API_OVERVIEW.md)
- [Security model](HarambeeOne/docs/SECURITY.md)
- [Integration boundaries](HarambeeOne/docs/INTEGRATIONS.md)
- [Harambee Support expansion plan](HarambeeOne/docs/HARAMBEE_SUPPORT_EXPANSION_PLAN.md)

## Contributing

Contributions should preserve the platform's financial and privacy guarantees:

1. Keep every query and mutation tenant-scoped.
2. Never replace ledger history with editable balance totals.
3. Make financial operations atomic and idempotent.
4. Keep receipts and audit history immutable.
5. Expose only the minimum learner information required for a workflow.
6. Add or update tests for behavioral changes.
7. Run the relevant checks before opening a pull request.

Please review the [roadmap](HarambeeOne/docs/MVP_ROADMAP.md) before starting a large contribution so that work aligns with the active delivery phase.

## License

This project is available under the [MIT License](HarambeeOne/LICENSE).
