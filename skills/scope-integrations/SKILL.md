---
name: scope-integrations
description: >-
  Extracts the third-party (non-SAP) system integrations an SAP RFP requires into the bid ledger -
  one row per named system that must exchange data with SAP, with functionality, SAP modules,
  direction, middleware, interface count, complexity and an effort estimate in person-days within
  the skill's bands. Uses the RFP text, interface lists, landscape tables and transcribed
  architecture diagrams. Use when building the effort estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "0.1.0-draft"
  ledger_sections: "integrations"
---

# Third-party integrations

> Draft authored without the old prompt text (section A of
> third_party_integration_extraction_layer.py). TODO(port): diff against it when npc-dev is available.

## What counts
A NAMED system that is not SAP-branded and that the RFP says must exchange data with the SAP
solution: time and attendance (Kronos, UKG), payroll providers, banks / payment platforms (SWIFT,
host-to-host), tax engines (Vertex, ZATCA e-invoicing portals), procurement suites (Coupa), CRM
(Salesforce), MES / LIMS / WMS, logistics carriers, e-commerce, BI / data lakes (Snowflake, AWS data
lake), project-management systems (Primavera, MS Project), legacy ERP kept alongside S/4HANA,
government portals. Sources: interface lists, system-landscape tables, "integration with ..."
sentences, and `[EMBEDDED IMAGE]` diagram transcriptions (one line per edge: `A <-> B : detail`).
The index lists table-scan candidates - check each, but decide on the text.

## Never an integration
- SAP-branded products (SuccessFactors, Ariba, Concur, IBP, BTP, Analytics Cloud, Solution
  Manager): they are SAP scope (catalogue or non-catalogue), even when "integrated".
- Middleware itself (SAP CPI / Integration Suite, MuleSoft, Boomi, PI/PO): record it in the
  `middleware` field of the systems it carries, not as a row.
- Protocols and formats (REST, SOAP, IDoc, SFTP, EDI as a format) without a named counterpart.
- Systems the RFP only mentions as context, or that are being retired with no interface.
- Generic "interfaces as required" with no system: that is the RICEFW interface count, owned by
  scope-ricefw-fiori.

## Rules
- One row per system. A system named in a table, a diagram and a paragraph is ONE row with the
  richest facts; several interfaces to one system raise `interface_count`, not rows.
- Keep the client's system name exactly; put the vendor product in `functionality` if it helps.
- `direction`: inbound (to SAP), outbound (from SAP), bidirectional, or unknown.
- `sap_modules`: the SAP side as the RFP or diagram labels it (FI, MM, HCM, Treasury ...).
- `is_project_management`: true for project / portfolio management systems (Primavera, MS Project,
  Jira, Planview) - they get a named lead in the staffing plan.
- Evidence: the sentence, table row or diagram line naming the system and the integration need,
  verbatim, with file and page.

## Complexity and effort (person-days for the whole integration, build + test)
| Complexity | Typical case | effort_days |
|---|---|---|
| Low | one-way file / flat interface, standard adapter, one object | 10-20 |
| Medium | a few objects or both directions, mapping logic, scheduled | 20-40 |
| High | real-time / event-driven, many objects, complex mapping, external certification (banks, tax authorities) | 40-60 |
Scale above 60 only when the RFP lists many distinct interfaces to the same system (justify in
`rationale`, max 500). `complexity_driver` names what drives it.

## Output
`ledger_write_integrations(rows=[...], mode="append")` with system, functionality, sap_modules,
direction, data_exchanged, middleware, protocol, interface_count, frequency, complexity_driver,
source_system, target_system, complexity, is_project_management, effort_days, rationale, evidence.
No third-party integration in the RFP -> `rows=[]` with a none_reason naming what you checked.
Fix and resend every rejected row.
