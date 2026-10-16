# HarambeeOne Architecture

## Product boundary

HarambeeOne has one active product area: **Bursar Operations**. It covers the minimum learner identity and placement data needed for finance, fee setup, learner ledgers, collections, receipts, arrears, statement reconciliation, finance reports and audit evidence.

Sponsor administration and programmable settlement are deferred product areas. They must not expand the active interface or implementation workload until the bursar product passes its end-to-end completion gate. General school administration and academics remain outside the product.

## Delivery gate

Sponsor and settlement development can resume only after learner accounts, fee setup, collections, receipts, arrears, reconciliation, reporting and audit workflows are complete, production-built and covered by backend verification.

## Core rule

The operational PostgreSQL ledger is authoritative for school finance. Personally identifiable learner information remains in the protected operational database.

## Financial truth

- Provider transaction = immutable source event.
- Payment allocation = how a source event is applied to a learner.
- Ledger entries = authoritative explanation of the learner balance.
- Reconciliation = evidence that a provider transaction was matched to the correct learner account.

## Production topology

Web client → Python API → PostgreSQL, object storage and background jobs.

Integration adapters connect SchoolPay, banks, Mobile Money and messaging services.

## Automation boundary

Automation can read authorised finance data, explain, recommend and flag. It cannot bypass business rules, approve financial changes or merge uncertain learner identities.
