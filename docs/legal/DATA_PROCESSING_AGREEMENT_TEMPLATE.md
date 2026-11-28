# Data Processing Agreement (DPA) — Template

**Draft template — not signed, not in force, and not proof that a DPA exists.**  
**Last reviewed: November 25, 2026**

Use this template only after the parties have assessed that one party is acting as a processor for the other in relation to a specific processing activity. Controller/processor status is determined by the facts, not by labels in this document. A provider acting as an independent controller should not be added to this DPA as a processor merely because the service is integrated with Lemegeton.

Before use, replace every bracketed field, complete the schedules, verify the security and subprocessor information, obtain the required approvals, and have the agreement reviewed and signed by authorised representatives. Do not publish this blank template as an executed agreement.

This template is intended to help structure an agreement against Article 28 GDPR. It is not legal advice and may need changes for the applicable jurisdiction, transfer arrangements, sector rules and commercial agreement.

## 1. Parties and scope

**Controller:** [Full legal name, company/registration number, address and privacy contact]  
**Processor:** [Full legal name, company/registration number, address and privacy contact]  
**Effective date:** [Date of last signature]  
**Main agreement / service:** [Identify the signed service agreement and Lemegeton deployment]

The Processor will process personal data only on behalf of the Controller and only for the purposes and operations set out in this Agreement and its schedules.

## 2. Processing details

Complete Schedule 1 before processing begins:

- Subject matter and service: [Describe the specific Lemegeton service]
- Duration: [Start date, term and end/transition date]
- Nature and purpose: [Describe each operation and its purpose]
- Categories of data subjects: [For example, Discord members, server moderators and dashboard users]
- Types of personal data: [List actual fields processed; avoid generic or speculative lists]
- Special-category or criminal-offence data: [State whether intended, prohibited, or specifically authorised with safeguards]
- Controller's rights and obligations: [Document instructions, data accuracy, lawful basis and notices]

The schedule must reflect the real deployment, enabled features, storage locations, integrations and retention behaviour. Do not copy every feature or provider from the repository if it is not enabled.

## 3. Documented instructions

The Processor shall:

1. Process personal data only on documented instructions from the Controller, including instructions concerning international transfers, unless applicable law requires otherwise.
2. Inform the Controller before processing if the Processor is required by law to process data outside those instructions, unless that law prohibits notification.
3. Notify the Controller if, in the Processor's opinion, an instruction infringes applicable data-protection law.

Document instructions in Schedule 1 or an agreed written change record. The Controller is responsible for the lawfulness of its instructions and for identifying its purposes and legal basis.

## 4. Confidentiality and authorised personnel

The Processor shall ensure that persons authorised to process the personal data are bound by appropriate confidentiality obligations, receive access only as necessary for their duties, and are informed of relevant security and data-protection requirements.

## 5. Security

The Processor shall implement appropriate technical and organisational measures taking account of the nature, scope, context and purposes of processing and the risks to individuals. Record the measures actually in place in Schedule 2, including as appropriate:

- Access control, least privilege and authentication;
- Encryption in transit and, where suitable, at rest;
- Secure management of secrets and credentials;
- Logging, monitoring and security incident handling;
- Backup, restoration and resilience controls;
- Vulnerability and patch management;
- Secure deletion and media disposal;
- Personnel confidentiality and security training.

Do not represent a control as implemented unless it has been verified for the relevant deployment.

## 6. Subprocessors

The Processor shall not engage another processor without the Controller's prior specific or general written authorisation. Where general authorisation is used, the Processor shall give advance notice of intended additions or replacements and a meaningful opportunity to object.

The Processor shall impose data-protection obligations on each authorised subprocessor that provide at least the protection required by this Agreement, remain responsible for the subprocessor's performance, and keep the approved list in Schedule 3 current.

A third-party API or platform is not automatically a subprocessor. Its role must be assessed for the relevant processing.

## 7. Assistance to the Controller

Taking account of the nature of the processing, the Processor shall reasonably assist the Controller with:

- Requests by data subjects exercising their rights;
- Security obligations under Article 32 GDPR;
- Personal-data breach obligations under Articles 33 and 34 GDPR;
- Data protection impact assessments and prior consultation under Articles 35 and 36 GDPR;
- Demonstrating compliance with this Agreement and applicable processor obligations.

The assistance process, contact route and reasonable cost arrangements should be specified in the main agreement or Schedule 1.

## 8. Personal-data breaches

The Processor shall notify the Controller without undue delay after becoming aware of a personal-data breach affecting the Controller's data. The notice should provide information reasonably available to help the Controller assess the incident, meet statutory deadlines, contain the event and document the response. The parties should specify a practical contact route and escalation process in Schedule 2.

The Processor's notice to the Controller does not replace the Controller's responsibility to assess regulatory and individual notification duties.

## 9. International transfers

The Processor shall not transfer personal data to a third country or international organisation except on documented instructions or as otherwise permitted by applicable law and supported by a valid transfer mechanism. Identify destinations, recipients, transfer mechanism and supplementary measures in Schedule 4. Do not infer data residency from a provider's brand or billing address.

## 10. Return and deletion

At the end of the services, the Processor shall, at the Controller's choice, delete or return the personal data and delete existing copies, unless applicable law requires storage. The parties shall document the selected method, completion deadline, backup expiry and any legal retention exception in Schedule 1. Any retained data remains protected and is used only for the required legal purpose.

## 11. Compliance information and audits

The Processor shall make available information reasonably necessary to demonstrate compliance with this Agreement and applicable Article 28 obligations. It shall allow for and contribute to audits and inspections by the Controller or an auditor mandated by the Controller, subject to reasonable confidentiality, security, scope and scheduling safeguards.

## 12. Liability and precedence

[Set out liability allocation, indemnities, limitations, dispute process, order of precedence and any fees in the main agreement.] Nothing in this template removes rights or obligations imposed directly by applicable law.

## 13. Signatures

**For the Controller**  
Name: [ ]  
Title: [ ]  
Signature: [ ]  
Date: [ ]

**For the Processor**  
Name: [ ]  
Title: [ ]  
Signature: [ ]  
Date: [ ]

---

## Schedule 1 — Processing description and instructions

| Field | Deployment-specific entry |
|---|---|
| Service / environment | [ ] |
| Subject matter and purpose | [ ] |
| Nature of operations | [ ] |
| Duration | [ ] |
| Data subjects | [ ] |
| Personal-data categories | [ ] |
| Special-category data | [ ] |
| Controller instructions | [ ] |
| Data locations | [ ] |
| Retention and backup expiry | [ ] |
| Return/deletion method | [ ] |
| Controller contact | [ ] |
| Processor contact | [ ] |

## Schedule 2 — Security and incident measures

Record controls that have been verified in the actual deployment, owner, evidence and review date. Include the security measures from Section 5, incident response contacts, notification channel and escalation process.

## Schedule 3 — Approved subprocessors

| Legal entity | Service and purpose | Processing location | Data categories | Transfer mechanism | Authorisation / notice date |
|---|---|---|---|---|---|
| [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

Do not enter a provider until its legal entity, role, contract, location and transfer basis have been checked.

## Schedule 4 — International transfers

For every transfer, identify the exporting and importing entities, destination, data, purpose, applicable adequacy decision or safeguard, transfer assessment and supplementary measures: [Complete before transfer].
