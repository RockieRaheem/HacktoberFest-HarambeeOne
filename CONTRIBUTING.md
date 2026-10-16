# Contributing to HarambeeOne

Thank you for helping improve HarambeeOne. Contributions should make school finance more reliable, auditable, and privacy-conscious.

## Before you begin

1. Read the [README](README.md) for the product scope and local setup.
2. Review the [MVP roadmap](HarambeeOne/docs/MVP_ROADMAP.md) before starting substantial work.
3. Check existing issues and pull requests to avoid duplicate effort.
4. Discuss large features or schema changes in an issue before implementation.

## Local setup

```bash
git clone https://github.com/RockieRaheem/HacktoberFest-HarambeeOne.git
cd HacktoberFest-HarambeeOne/HarambeeOne
cp .env.example .env
pnpm install
uv sync --directory apps/backend
```

Configure `.env`, apply migrations, and start the services as described in the [README](README.md#quick-start).

## Development workflow

Create a focused branch from the latest `main`:

```bash
git switch main
git pull --ff-only
git switch -c fix/short-description
```

Keep each pull request limited to one coherent change. Use descriptive commit messages such as:

```text
Fix duplicate payment allocation handling
Add validation for academic period closure
Document Supabase callback configuration
```

## Required checks

Run the checks relevant to your change before opening a pull request:

```bash
# Python API
uv run --directory apps/backend pytest
uv run --directory apps/backend ruff check .

# Web application
pnpm --filter @harambeeone/web lint
pnpm --filter @harambeeone/web build
```

Changes to database behavior should include an Alembic migration and appropriate tests. Never rewrite an existing migration that may already have been applied.

## Engineering expectations

- Scope every database operation to the authenticated institution.
- Derive balances from ledger entries; do not introduce editable balance totals.
- Keep financial operations atomic and idempotent.
- Correct posted financial records with explicit adjustments or reversals.
- Preserve immutable receipts and audit history.
- Collect and expose only the learner information required by the workflow.
- Keep secrets and real learner data out of commits, fixtures, screenshots, and logs.
- Add tests for new behavior and regressions.
- Update documentation when behavior, configuration, or setup changes.

## Pull requests

A good pull request includes:

- A concise explanation of the problem and solution.
- The affected user workflow or roadmap item.
- Testing performed and its result.
- Screenshots for visible interface changes.
- Migration and rollback notes for database changes.
- Any security, privacy, or financial-integrity considerations.

Maintainers may request revisions when a change falls outside the active roadmap, weakens tenant isolation, or makes financial history less auditable.

## Reporting security issues

Do not disclose suspected vulnerabilities or exposed credentials in a public issue. Contact the repository maintainers privately and include only the information needed to reproduce and assess the problem.

## License

By contributing, you agree that your contribution may be distributed under the project's [MIT License](HarambeeOne/LICENSE).
