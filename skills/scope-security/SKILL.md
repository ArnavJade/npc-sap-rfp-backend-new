---
name: scope-security
description: >-
  Extracts the SAP Security workstream (roles and authorisations, SoD, GRC Access Control / Cloud
  IAG, GRC Process Control / Risk Management, single sign-on and identity, data-access restrictions)
  from an SAP RFP into the bid ledger - one row per security capability with SAP product, scope
  status, complexity and whole man-days 1-120. Use when building the effort estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "0.1.0-draft"
  ledger_sections: "security"
---

# SAP Security scope

> Built from the architecture review's appendix sketch of section F
> (third_party_integration_extraction_layer.py:576-626). TODO(port): diff against the full prompt
> and security_scope.py when npc-dev is available.

## What counts
Role and authorisation design and build (S/4HANA, Fiori, SAP cloud apps), user provisioning,
Segregation of Duties, SAP GRC Access Control or SAP Cloud Identity Access Governance, GRC Process
Control / Risk Management, single sign-on and identity (SAP Secure Login Service, SAP Cloud Identity
Services), restricting data access by entity or org unit, and security testing through hypercare.

## Never Security
Basis tasks (system set-up, transports, certificates, backups), network or cyber security, "the
solution must be secure", functional approval workflows (Ariba, SuccessFactors, purchasing), legal
or financial compliance (audit, IFRS, tax).

## Rules
- Evidence: list an activity only when the RFP states it or puts its SAP product in scope. Quote
  the exact words and the page.
- One row per capability: a product in a licence list and its implementation described elsewhere
  are one row.
- A heading that groups activities is not an activity.
- Out of Scope when the RFP gives it to the client's IT team, another vendor or the hosting provider
  (effort_days null).
- `sap_product`: the SAP product the activity uses (e.g. "SAP GRC Access Control"), else "".

## Effort guide (man-days, whole numbers 1-120)
| Activity | Range | Complexity |
|---|---|---|
| Single sign-on set-up | 3-8 | Low |
| Role design and build, single entity | 10-20 | Medium |
| Role design and build, multi-entity S/4 | 15-40 | High |
| GRC Access Control / Cloud IAG | 20-40 | High |
| GRC Process Control | 30-60 | High |
| Table-level / org-level data restriction | 10-25 | Medium |
| Security testing support | 5-10 | Low |
Scale within the range by the number of entities, countries and modules in scope.

## Output
`ledger_write_security(rows=[...])` with activity, sap_product, status, complexity, effort_days,
evidence. Fix any row the tool rejects; never drop a rejected row silently. No security scope ->
`rows=[]` with a none_reason.
