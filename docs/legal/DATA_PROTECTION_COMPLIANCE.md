# Data Protection Compliance Record

**Internal working document — not a legal certification.**  
**Last reviewed: November 25, 2026**

**Status: INCOMPLETE — this record is not a GDPR compliance certification.**

This document records the privacy governance work required for the Lemegeton v3 hosted deployment. It must be completed against the real operator, production configuration, and actual processing. It does not decide the legal role or lawful basis by assumption. Do not describe a deployment as GDPR-compliant until its roles, lawful bases, contracts, notices, transfers, retention, rights handling and operational controls have been assessed and evidenced.

## 1. Controller / processor role assessment

Assess each activity separately. The project operator may be a controller for its own service security, account consent, and operational records. A server owner may independently determine purposes for guild community activity. The project operator may act as a processor for a server owner only where the facts and instructions support that role. Infrastructure and media providers may be processors or independent controllers depending on their service and terms.

| Activity | Possible role to assess | Required evidence |
|---|---|---|
| Bot account, policy acceptance and service security | Project operator may be controller | Operator identity, purpose, lawful basis, privacy contact |
| Guild settings and member-linked features | Assess operator and guild owner roles per purpose | Feature configuration, instructions, access and deletion model |
| Community archive submissions and moderation | Assess guild owner/operator roles and global visibility | Who decides purpose, audience, retention and moderation |
| Dashboard OAuth and sessions | Project operator may be controller for authentication/security | OAuth scopes, session data, access logs and retention |
| Hosting, database and object storage | Vendor may be processor or other role | Contract, DPA, subprocessor list, location and deletion terms |
| External media metadata APIs | Often independent provider role; verify terms | Provider terms, request fields, account linkage and transfer details |

Do not publish a definitive controller/processor statement until this assessment is complete.

## 2. Processing activity inventory

Maintain a record for each purpose with: data subjects, personal-data categories, purpose, lawful basis, recipients, transfer locations, retention, security controls, and deletion mechanism.

Initial activity inventory:

1. Discord command and interaction handling.
2. Guild configuration, permissions and member lifecycle.
3. Dashboard OAuth authentication, sessions and consent.
4. Media-provider account linking and metadata requests.
5. Community archive submissions, attachments, collections and moderation.
6. Community discussions, votes, nominations and session participation.
7. Feedback, diagnostics, abuse/security events and audit history.
8. Object storage, database backups and recovery operations.

For each activity, identify the actual fields used in the current schema and remove obsolete or speculative categories.

## 3. Lawful-basis assessment

For every processing purpose, record the chosen legal basis and why it applies. Where legitimate interests are used, document the purpose, necessity and balancing assessment. Where consent is used, verify that it is specific, informed, freely given, unambiguous, recorded, and withdrawable without detriment beyond the feature that depends on it. Do not infer consent to unrelated processing from acceptance of the Terms of Service.

## 4. Data protection impact assessment screening

Complete and retain a screening before enabling a new feature or provider that materially changes processing. Consider scale, monitoring, sensitive or vulnerable data, matching/profiling, public visibility, cross-guild aggregation, and the consequences of exposure.

If the processing is likely to result in a high risk to individuals' rights and freedoms, complete a full DPIA before processing begins. Record the screening result, decision, safeguards, residual risk and approver. A DPIA is not automatically required merely because the bot uses Discord IDs or PostgreSQL.

## 5. International transfers

For each hosting, storage, platform and provider service, record the country where data is accessed or stored and whether transfers outside the EEA occur. Identify the applicable adequacy decision or transfer safeguard, complete any required transfer assessment, and document supplementary measures. Do not infer data residency from the provider's billing address or brand.

## 6. Data subject rights and retention

Use the [Data Deletion & Privacy Request Procedure](DATA_DELETION_AND_PRIVACY_REQUESTS.md) and [Data Retention Schedule](DATA_RETENTION_SCHEDULE.md). Ensure request handling includes data held by processors, object storage, logs, exports and backups, and that any legal exceptions are recorded.

## 7. Required records before production

- [ ] Identify the legal operator/controller and publish a working privacy contact.
- [ ] Complete controller/processor role assessment per processing activity.
- [ ] Record lawful bases and legitimate-interest assessments where used.
- [ ] Complete the processing activity register.
- [ ] Complete DPIA screening; perform a full DPIA if required.
- [ ] Complete provider/subprocessor register and required DPAs.
- [ ] Determine which service relationships are controller-to-processor relationships and execute an Article 28 DPA before the relevant processing begins; the [DPA template](DATA_PROCESSING_AGREEMENT_TEMPLATE.md) is a draft only.
- [ ] Publish and maintain the [Third-Party Disclosure](THIRD_PARTY_DISCLOSURE.md) and complete the actual deployment's provider/legal-entity register.
- [ ] Verify international transfer locations and safeguards.
- [ ] Set and test retention periods, backup expiry and deletion jobs.
- [ ] Verify access, correction, export, objection and deletion request handling.
- [ ] Confirm breach escalation and notification ownership.
- [ ] Reconcile the public Privacy Policy with the deployed system.

## 8. Review and ownership

Assign a named operator owner to every item before production. Review at least annually and whenever a new feature, data category, provider, storage location, or material processing purpose is introduced. Keep evidence of decisions and implementation tests alongside the deployment's restricted operational records.
