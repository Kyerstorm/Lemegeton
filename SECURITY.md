# Security Policy

Lemegeton is actively developed on the `lemegeton-v3` branch. The v3 implementation is still under development and its migration pull request remains Draft; no production release or maintenance window is declared by this policy.

## Reporting a vulnerability

**Please do not publish exploitable details in a public issue, discussion, commit, or Discord message.**

1. Open the repository's **Security** tab and use **Report a vulnerability** if private vulnerability reporting is available.
2. If GitHub does not offer private reporting for this repository, open a minimal public issue titled **Request for a private security contact**. Do not include the suspected weakness, exploit steps, affected data, tokens, logs, or other sensitive details. The maintainers can then provide a private reporting route.
3. Include technical details only through the private channel supplied by the maintainers.

A useful private report includes the affected branch or commit, the relevant component, impact, a concise reproduction, and any suggested mitigation. Redact Discord IDs, user data, credentials, private URLs, and production identifiers unless a maintainer specifically requests a safe way to share them.

## Researcher expectations

- Test only systems and accounts you own or have explicit permission to assess.
- Do not access, modify, or retain another person's data.
- Avoid service disruption, destructive tests, unsolicited load, social engineering, or persistence.
- Give maintainers a reasonable opportunity to investigate and prepare a fix before public disclosure.
- Do not publish secrets, private logs, or proof-of-concept material that exposes users or operators.

## Maintainer response

The maintainers will review reports in good faith and may request a minimal follow-up to confirm scope or impact. Response and remediation times depend on report completeness, severity, maintainer availability, and whether the issue can be reproduced. This policy does not promise a fixed service-level agreement.

## Scope notes

The security controls described in [the security audit](docs/SECURITY_AUDIT.md) are source-level findings, not a guarantee that every deployment is secure. Production OAuth registration, HTTPS termination, host firewalls, database backups, provider credentials, and live Discord permissions require deployment-specific verification.
