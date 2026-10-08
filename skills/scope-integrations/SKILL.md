---
name: scope-integrations
description: >-
  Extracts every third-party (non-SAP) integration module or system an SAP RFP names into the bid
  ledger - one row per external system that must connect to the client's SAP landscape, with its
  labelled facts (functionality, SAP modules, direction, data exchanged, middleware, protocol,
  interface count, frequency, complexity driver), the Tech Dev columns (object name, middleware,
  source and target system) and a planning-level person-day estimate. Reads prose, interface tables
  and transcribed architecture diagrams. Use when building the effort estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "1.0.0"
  ledger_sections: "integrations"
---

# Third-party integration modules

Ported from section (A) of the old scope prompt
(third_party_integration_extraction_layer.py) and its Tech Dev structuring prompt.

## Where to look
Read the whole RFP, not only an obviously-titled integration section. Integration modules,
interface counts and complexity splits are VERY OFTEN shown only inside `[EMBEDDED IMAGE]` blocks
(an integration architecture diagram), PDF diagram text between `<!-- Start of picture text -->` and
`<!-- End of picture text -->` (the box labels of a vector diagram, in jumbled order - every name in
it that is not an SAP module, protocol or "DB" is a candidate system, e.g. "Wincos", "Brill",
"Sadad", "HHT - MIRNA", "Qlik", "ZATCA", "IMOC"), or `[EXTRACTED TABLE]` blocks, transcribed as
lines like:

    REST <-> SAP FI/CO : Real-time RFC interfaces (SAP side)
    Coupa <-> SAP (Treasury / Cash / Bank)
    Data Lake (AWS) <-> SAP (reporting feeds)

Treat these blocks with the same rigor as prose and do not skip them. `/rfp/index.md` lists the
deterministic table scan's third-party candidates - check every one, but decide on the RFP text.

The richest source is often NOT the integration diagram but an inventory table of the client's
existing / legacy applications (an annexure such as "Legacy applications details & integrations
required", "Existing systems", "Application landscape"): one row per system with its function, the
SAP modules it touches and often a number of interfaces. Every row of such a table that must be
integrated with SAP is one integration row, with that number as `interface_count`.

## Procedure
1. The pages in your brief are a starting point, not the boundary. Run ONE grep over /rfp/ (literal
   words, `|` between them) for
   `integrat|interface|legacy|third party|third-party|3rd party|existing system|existing application|landscape|middleware`
   and read (`read_section`) every page with a hit, tables and diagram text included.
2. Write each source's systems as soon as you have read it (batches of at most 10 rows); do not hold
   everything back until the end.
3. Before each later batch, `ledger_read("integrations")`. A system already saved is NOT sent again
   as a new row: to add facts from another source (interface count, middleware), resend that row
   with its `row_id`. Names that differ only by case, punctuation, a company prefix or a suffix such
   as "DB", "system" or "app" are the same system. A rejected row: fix it and resend THAT row only.
4. `rows=[]` only when the grep found no third-party system anywhere; the none_reason names the
   searches and pages checked.

## What qualifies
Every THIRD-PARTY INTEGRATION MODULE or SYSTEM the RFP mentions: any external, non-SAP vendor
product, tool or system that needs to be integrated with, or connected to, the client's SAP
landscape - a tax engine, a transportation management system, a banking / payment gateway, a
warehouse / WMS system, an e-commerce platform, a CRM, a document management system, an EDI / B2B
gateway, an IoT / shop-floor system, a client's homegrown portal, a non-SAP cloud service (e.g.
Coupa, Qlik, Wincos, Blancco). Do NOT invent an integration that is not evidenced.

## What never qualifies
- Any SAP-BRANDED product, even a separately deployed cloud / satellite system with its own
  interface: SAP Ariba, SAP SuccessFactors, SAP Concur, SAP Fieldglass, SAP SAC, SAP Signavio, SAP
  GRC, SAP CRM, BTP-hosted apps. SAP owns these - they are the non-catalogue track (catalogue-mapper)
  or the Security / Analytics specialists. Anything carrying the SAP name is excluded here.
- Functional modules within the S/4HANA core being implemented (FI, CO, MM, SD, PP, QM, TM ...).
- Middleware itself (SAP Integration Suite / CPI, PI/PO, MuleSoft): it goes into the `middleware`
  field of the systems it carries.
- Bare protocols (REST, IDoc, SFTP) with no named counterpart system.

## One row per system
Consolidate at the SYSTEM level: a system named in a diagram, a table and a paragraph is ONE row
with the richest facts; several interfaces to it raise `interface_count`. Keep the RFP's name.

## Fields (use "" / "unknown" when the RFP does not evidence a fact - never guess)
| Field | Content |
|---|---|
| `system` | the system's name as the RFP names it |
| `functionality` | what the system is / does, as the RFP describes it |
| `sap_modules` | SAP modules / processes / areas it integrates with |
| `direction` | inbound (data into SAP), outbound (out of SAP), bidirectional, unknown - read arrow directions and "Inbound" / "Outbound" / "Bi-Directional" labels in diagrams |
| `data_exchanged` | business objects flowing (sales orders, vendor invoices, stock movements) |
| `middleware` | the platform this system is routed through ONLY when the RFP connects THIS system to it (a diagram line from the system to the middleware box); append the protocol in brackets when stated, e.g. "SAP Integration Suite (CPI) (REST)" |
| `protocol` | REST, SOAP, OData, API, RFC/BAPI, IDoc, DB, file/SFTP, EDI ... as shown for this system |
| `interface_count` | the RFP's stated number of interfaces for this system, else 1 |
| `frequency` | real-time, batch/scheduled, or "" |
| `complexity_driver` | what drives the estimate: interface count, direction, data volume / frequency, or "no complexity signal in RFP - baseline estimate" |
| `source_system`, `target_system` | write the SAP side as "SAP S/4HANA (<SAP modules>)" (just "SAP S/4HANA" when none): inbound: source = system, target = SAP side; outbound: source = SAP side, target = system; bidirectional: source = "<system> / <SAP side>", target = "<SAP side> / <system>"; not stated: source = system, target = SAP side |
| `complexity` | Low / Medium / High |
| `is_project_management` | true for project / portfolio management systems (Primavera, MS Project, Jira ...) |
| `effort_days`, `rationale` | see below |
| `evidence` | verbatim RFP words (sentence, table row or diagram line) with file and page |

## Effort (person-days, one plain number)
None of these has a standard SAP Best Practice catalogue entry, so base the estimate on your own
knowledge of typical effort for a comparable third-party / auxiliary system at a similar
complexity: a simple REST / file-based interface costs far less than a real-time bidirectional
interface touching several SAP modules. Name the driver in `complexity_driver` / `rationale` so the
figure reads as auditable. When the RFP gives no complexity signal, still give your best
planning-level estimate - never leave it blank. Policy band `third_party_integration`: 10-60 PD;
go above 60 only with several stated interfaces to the same system (max 500). Effort grows with the
interface count but much less than proportionally - interfaces to one system share design, mapping,
connectivity and test set-up. Illustrative only: 1 interface 10-15; about 5-10 interfaces 20-35;
about 20 interfaces 50-70; 50 or more 100-160.

## Output
`ledger_write_integrations(rows=[...])`. No third-party integration in the RFP -> `rows=[]` with a
none_reason naming what you checked. Fix and resend every rejected row (only the rejected ones);
never drop one silently.
