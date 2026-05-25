# Runbook: Data Breach Notification (DPDP / GDPR)

## Incident Summary

A personal data breach has occurred (or is suspected) that may require notification to the Data Protection Board of India (DPDP Act, 2023) and/or EU Data Protection Authorities (GDPR), as well as to affected data principals (individuals whose data was exposed).

**The 72-hour regulatory notification clock starts at the moment of detection, not at confirmation. Act immediately.**

## Legal Definitions (Quick Reference)

- **Personal Data Breach (DPDP):** Any unauthorized processing, access, disclosure, destruction, or loss of personal data.
- **Personal Data Breach (GDPR):** A breach of security leading to accidental or unlawful destruction, loss, alteration, unauthorized disclosure of, or access to personal data.
- **Data Principal:** The individual whose personal data was breached (e.g., an HR contact whose email or phone number was exposed).
- **Data Fiduciary:** CorporateMind AI (the company processing the data).

## Trigger Conditions

- Any suspected or confirmed cross-tenant data exposure (see `cross-tenant-data-suspected.md`).
- Unauthorized access to the production database or object storage.
- Loss or theft of an employee device containing unencrypted personal data.
- A third-party vendor (Euri, Railway, Cloudinary) notifies us of a breach affecting our data.
- Sentry or logs reveal that PII was exposed in an API response to the wrong user.

## Severity Level

**SEV1** — always. Any breach that may require regulatory notification is a P0 incident.

## Immediate Steps (First Hour)

1. **Assign IC and open incident channel** immediately.
2. **Notify DPO (Data Protection Officer)** — contact details in `ops/secrets.md`. Must happen within 1 hour of detection.
3. **Document the detection timestamp** precisely — this is the legal start of the 72-hour clock.
4. **Assess whether notification is required:**
   - **DPDP:** Notification to DPBI is required if the breach is likely to cause harm to data principals.
   - **GDPR:** Notification to supervisory authority is required unless the breach is "unlikely to result in a risk to the rights and freedoms of natural persons."
   - When in doubt: notify. It is always safer to report than to not report.
5. **Contain and remediate** — follow `cross-tenant-data-suspected.md` steps 4+.

## Breach Assessment Checklist (Complete Within 6 Hours)

- [ ] Type of data exposed: (name / email / phone / financial / health / none)
- [ ] Number of data principals affected: _______
- [ ] Tenants whose data was involved: _______
- [ ] Time window of exposure: from _______ to _______
- [ ] Nature of breach: (accidental disclosure / unauthorized access / system vulnerability / third-party)
- [ ] Likely consequences for data principals: _______
- [ ] Mitigation measures taken: _______
- [ ] Has the breach been contained? (yes / no / partial)

## Regulatory Notification (Within 72 Hours of Detection)

### DPDP (India)

Notify the Data Protection Board of India via the prescribed form. Template prepared by legal; IC must approve before sending.

**Required information:**
- Nature of the personal data breach.
- Contact details of the DPO.
- Likely consequences of the breach.
- Measures taken to address the breach.

### GDPR (EU)

If any EU data principals are affected, notify the relevant supervisory authority (likely in Ireland if the EU data subjects are primarily there, or in the member state of the data subject).

**Required information (same as DPDP, plus):**
- Categories and approximate number of personal data records concerned.
- Categories and approximate number of data subjects concerned.
- Name and contact details of the DPO.

## Data Principal Notification

Notify affected individuals (HR contacts, trainers) if the breach is likely to result in high risk to their rights and freedoms:
- Use plain language — no legal jargon.
- State what data was exposed, for how long, and what we are doing about it.
- Provide a contact point for questions.
- Do NOT send until IC and Legal have approved the message.

## Recovery Checklist

- [ ] DPO notified within 1 hour.
- [ ] Regulatory notification filed within 72 hours (or decision documented that notification is not required with justification).
- [ ] Affected data principals notified if high-risk breach.
- [ ] All breach details documented in `audit_events` (immutable log).
- [ ] Breach assessment document retained for 7 years (Enterprise) / 2 years (others).
- [ ] Postmortem completed within 5 business days.

## Contacts (Stored in `ops/secrets.md`)

- DPO contact
- Legal counsel contact
- Railway security contact
- Euri AI security contact
- Cloudinary security contact
