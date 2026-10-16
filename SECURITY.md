# Security Policy

HarambeeOne handles school, learner, guardian, and financial information. Security and privacy issues must therefore be reported responsibly and resolved before public disclosure.

## Supported versions

HarambeeOne is currently an actively developed MVP. Security fixes are applied to the latest version of the `main` branch. Older commits, forks, prototypes, and deployments are not maintained by this repository.

## Reporting a vulnerability

Do **not** open a public issue, discussion, or pull request for a suspected vulnerability.

Use GitHub's private vulnerability-reporting feature on the repository's **Security** tab. If that feature is unavailable, contact the repository owner privately through their GitHub profile and request a secure reporting channel. Do not include secrets or sensitive learner data in the initial message.

Include the following where possible:

- A concise description of the vulnerability and its impact.
- The affected component, route, role, and commit.
- Safe reproduction steps or a minimal proof of concept.
- Whether tenant isolation, authentication, financial records, or personal data are affected.
- Suggested mitigations, if known.
- Your preferred name for acknowledgement, or whether you prefer anonymity.

Reports should use synthetic data. Never test against a school or learner account without explicit authorization.

## What to expect

Maintainers will aim to:

1. Acknowledge a complete report within five business days.
2. Assess severity, affected scope, and immediate containment options.
3. Keep the reporter informed when material progress is made.
4. Coordinate a fix and responsible disclosure timeline.
5. Credit the reporter when requested and appropriate.

Response times are targets rather than guarantees because this is a community-maintained project.

## Security-sensitive areas

Reports are especially important when they involve:

- Cross-school or cross-tenant data access.
- Authentication, authorization, or role escalation.
- Exposure of learner, guardian, or support-campaign identities.
- Modification or deletion of ledger entries, receipts, or audit history.
- Duplicate, replayed, or incorrectly allocated financial transactions.
- Bypassing consent, publication, or four-eyes approval controls.
- Injection, request forgery, unsafe file handling, or secret exposure.
- Vulnerable dependencies with a practical impact on this project.

## Safe-harbor expectations

Good-faith research should avoid privacy violations, service disruption, social engineering, persistence, data destruction, and access beyond what is necessary to demonstrate the issue. Stop testing and report immediately if real personal or financial data becomes accessible.

This policy does not authorize testing of third-party services such as Supabase, payment providers, banks, mobile-money networks, or hosting platforms. Follow each provider's own security policy.

## Public security guidance

For the project's security architecture and deployment boundaries, see [HarambeeOne/docs/SECURITY.md](HarambeeOne/docs/SECURITY.md). General hardening suggestions that do not reveal an exploitable vulnerability may be submitted through the normal contribution process.
