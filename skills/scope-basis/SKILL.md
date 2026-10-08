---
name: scope-basis
description: >-
  Extracts the SAP Basis / technical scope of an SAP RFP into the bid ledger - one row per Basis
  activity (installation, landscape and client set-up, system copies, transports, Solution Manager
  / Cloud ALM, performance and HA/DR set-up, upgrades) with scope status and whole man-days 1-5 per
  system for DEV, QA and PRD. Use when building the effort estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "0.1.0-draft"
  ledger_sections: "basis"
---

# SAP Basis

> Draft authored without the old prompt text (section E of
> third_party_integration_extraction_layer.py and basis_scope.py). TODO(port): diff when npc-dev is
> available.

## What counts
Technical SAP activities the bidder must perform: system installation / provisioning of the SAP
landscape (when not delivered by RISE / the hyperscaler), client and landscape set-up, transport
management (TMS / CTS+ / ChaRM), system copies and refreshes, SAP Solution Manager or SAP Cloud ALM
set-up, SAP Router / connectivity, printing and output management, performance tuning, backup and
HA / DR configuration, system monitoring set-up, technical upgrades or conversions, Fiori launchpad
technical configuration, SAP BTP subaccount set-up.

## Never Basis
Role and authorisation design (scope-security), infrastructure the hosting provider or RISE delivers
(mark those activities Out of Scope with the quote), network / firewall / cyber security, functional
configuration, interface development.

## Rows
- `activity`: a clean name; one row per activity (merge duplicates).
- `status`: "In Scope", or "Out of Scope" when the RFP gives it to the client, the hosting provider
  or SAP (RISE). Out of Scope rows keep dev / qa / prd null.
- `dev`, `qa`, `prd`: whole man-days 1-5 per system. Guide: simple set-up 1, standard activity 2-3,
  complex (HA/DR, conversion, multi-client landscapes) 4-5. A two-tier landscape (no QA) -> qa null
  is not allowed for In Scope rows: use 1 and say so in `note`.

## Output
`ledger_write_basis(rows=[...])` with verbatim evidence (file, page) per row. The RFP silent on Basis
-> `rows=[]` with a none_reason. Fix and resend rejected rows.
