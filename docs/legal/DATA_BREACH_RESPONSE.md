# Data Breach Response Procedure

**Internal operational document — restrict access to maintainers and authorised incident responders.**  
**Last reviewed: November 24, 2026**

## 1. Trigger

Use this procedure when there is a suspected or confirmed accidental or unlawful loss, alteration, disclosure of, or access to personal data. Examples include exposed Discord/OAuth tokens, a public archive object that should be private, unauthorised database access, lost backups, or disclosure of private member records.

Report suspected incidents privately to the maintainer responsible for security. Do not put credentials, personal data, exploit details, or private logs in a public issue or Discord channel.

## 2. Immediate response

1. Open an incident record with discovery time, reporter, affected service, and current confidence.
2. Assign an incident lead and a technical responder.
3. Contain the incident proportionately: revoke or rotate exposed credentials, disable affected access paths, isolate compromised systems, or restrict affected objects.
4. Preserve relevant logs and evidence with restricted access. Avoid unnecessary copying of personal data.
5. Establish the affected data categories, individuals, guilds, systems, time window, recipients, likely consequences, and whether the incident is ongoing.
6. Record each decision and timestamp. Do not destroy evidence during containment.

## 3. Risk assessment

Assess the likelihood and severity of risks to people's rights and freedoms. Consider sensitivity and volume of data, number and vulnerability of affected people, ease of identification, exposure duration, likely misuse, and whether effective safeguards such as encryption were in place.

Distinguish a security incident from a personal-data breach. Not every security incident involves personal data; not every personal-data breach is reportable to a supervisory authority. Document the reasoning either way.

## 4. Notification decisions

Where GDPR applies, the controller must notify the competent supervisory authority without undue delay and, where feasible, within 72 hours after becoming aware of a personal-data breach unless the breach is unlikely to result in a risk to individuals' rights and freedoms. If notification is later than 72 hours, document the reasons for delay.

Where the breach is likely to result in a high risk to individuals' rights and freedoms, the controller must communicate the breach to affected individuals without undue delay unless a legal exception applies.

If Lemegeton is acting as a processor for a guild or another controller for the affected activity, notify that controller without undue delay under the applicable contract and provide the information needed for its assessment. Do not assume the project operator is always the controller or always the processor; determine the role for the affected processing.

The incident lead must identify the competent supervisory authority based on the controller's establishment and applicable rules. For an Irish controller, consult the [Data Protection Commission](https://www.dataprotection.ie/) and applicable GDPR requirements.

## 5. Incident record

Record at minimum:

- Nature of the breach, including affected data categories and approximate numbers where known.
- Contact point for further information.
- Likely consequences.
- Measures taken or proposed to address the breach and mitigate effects.
- Risk assessment and reasons for notification or non-notification.
- Times of awareness, escalation, decisions, notifications and containment.
- Whether further investigation or user support is required.

Keep the record even when the breach is not notified, where required by applicable law.

## 6. Recovery and review

Restore service only after the incident lead confirms the affected access path is controlled. Rotate secrets, patch the root cause, validate access controls, review backups and audit logs, and test recovery.

After containment, complete a post-incident review: root cause, impact, response effectiveness, corrective actions, owners and due dates. Update the security audit, privacy notice, retention schedule, and processor/controller contacts where necessary.

Do not promise that a breach is contained or that affected people have been notified until those actions are verified.
