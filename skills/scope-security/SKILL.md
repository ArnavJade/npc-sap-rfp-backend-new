---
name: scope-security
description: >-
  Extracts the SAP Security activities an RFP states (role and authorisation design and build, user
  provisioning, SoD, GRC Access Control / Cloud IAG, GRC Process Control / Risk Management, single
  sign-on and identity, data-access restrictions, security testing and hypercare) into the bid ledger
  under a strict evidence rule - one row per capability with SAP product, scope status, complexity
  and whole man-days. Use when building the effort estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "1.0.0"
  ledger_sections: "security"
---

# SAP Security scope

Ported from section (F) of the old scope prompt and security_scope.py.

## What counts
Role and authorisation design and build (S/4HANA, Fiori, SAP cloud applications), user provisioning,
Segregation of Duties / role-conflict management, SAP GRC Access Control or SAP Cloud Identity Access
Governance, GRC Process Control / Risk Management, single sign-on and identity (SAP Secure Login
Service, SAP Cloud Identity Services), restricting data access by entity / organisational unit /
table, and security testing, cutover, go-live and hypercare support.

## Never Security
Basis / infrastructure tasks (system set-up, transports, certificates, backups), network / hosting /
cyber security, generic statements that the solution must be secure, functional approval workflows
and release strategies (Ariba, SuccessFactors, purchasing), legal / financial compliance (audit,
IFRS, tax).

## STRICT EVIDENCE RULE
List an activity ONLY when the RFP states it or puts the SAP product that delivers it in scope.
Nothing from general SAP knowledge; when unsure, leave it out. No evidence -> `rows=[]` with a
none_reason.

## One row per capability
A product named in a licence / SKU / application list and the implementation work described for it
elsewhere are the SAME activity - one row, with the most specific evidence. A section heading, table
of contents entry or objective grouping several activities ("GRC Enablement scope for ...") is never
an activity itself - not even when its content is elsewhere; list only the activities under it. Never
the same activity twice in different words (rows whose names share all significant words are
duplicates).

## Fields
- `activity`: a concise capability name ("GRC Access Control / Cloud IAG implementation") - never a
  copy of the RFP sentence.
- `sap_product`: the SAP product it implements, without edition / version suffixes ("SAP Cloud
  Identity Access Governance", "GRC Process Control", "SAP Secure Login Service"); "" when not tied to
  a product.
- `status`: "Out of Scope" when the RFP excludes it or gives it to someone other than the
  implementation partner (client IT, another vendor, the hosting provider); otherwise "In Scope".
- `complexity`: Low / Medium / High from the number of entities / business units / waves, the modules
  and cloud applications covered, and whether a GRC product or custom development is involved.
- `effort_days`: the partner's effort for the whole activity across all waves, in MAN-DAYS, a WHOLE
  NUMBER 1-120; null when Out of Scope. Illustrative only: single sign-on set-up 3-8; role design and
  build for a multi-entity S/4HANA landscape 15-40; GRC Access Control / Cloud IAG 20-40; GRC Process
  Control 30-60; table-level data restriction 10-25. Defaults when unsure: Low 5, Medium 10, High 20.
- `evidence`: the exact RFP words (verbatim substring), file and page.

## Output
`ledger_write_security(rows=[...])`. Fix any row the tool rejects; never drop a rejected row silently.
