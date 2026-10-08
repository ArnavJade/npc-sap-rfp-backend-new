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

## Detection procedure (mandatory - an empty section is the most common error)
The first live runs left this section empty or short because the agent read one or two pages and
stopped. So:
1. Read the WHOLE RFP with `read_next_pages` (call it until it says the whole RFP is read). The write
   tool refuses `rows=[]` until you have, and the harness sends you back if you stop early.
2. While reading, note every candidate below with its page. Then grep for each signal word listed
   below as a second pass (`grep(pattern="a|b|c", path="/rfp/")` - case-insensitive).
3. Write what you found in batches of at most 10 rows.
4. `rows=[]` is right only when no signal matched anywhere. Its none_reason must name the signal
   words you searched and the pages you checked, e.g. "read p.1-52; grep 'basis|transport|backup|
   BTP|Cloud Connector|go-live' - no Basis activity stated". A none_reason without this is rejected
   in review.

Signals (grep): `integrat`, `interface`, `legacy`, `third party|3rd party`, `non-SAP`, `API|REST|
SOAP|OData|SFTP|EDI|IDoc`, `middleware|CPI|Integration Suite|PI/PO`, `landscape`, `bank|SWIFT`,
`e-invoic|ZATCA|tax authority|ministry`, `Active Directory`, `portal`.

Call `integration_candidates()` FIRST: it lists the table-scan candidates, every diagram text block
and the list lines of every page about integrations, interfaces or legacy applications. Then:
- every non-SAP application in a "legacy applications" / "current landscape" / "integrations
  required" list that must keep running next to SAP is a row (an application being REPLACED by SAP
  is not);
- every non-SAP name in an integration diagram (jumbled box labels - split them into names) is a row;
- government / bank / tax gateways (e-invoicing authority, ministry portals, SWIFT / bank networks),
  identity directories (Active Directory), document management (OpenText) and work-management tools
  (JIRA) count when the RFP connects them to SAP.
After each write the tool lists table-scan candidates no row covers yet - add them or say why not.
A client with a legacy-application annexure typically has 15-30 third-party rows; 5 or fewer usually
means a list was missed. Always give `effort_days` (a missing one is set to a Low 10 / Medium 20 /
High 40 PD default per interface).

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
go above 60 only with several stated interfaces to the same system (max 500).

## Output
`ledger_write_integrations(rows=[...])`. No third-party integration in the RFP -> `rows=[]` with a
none_reason naming what you checked. Fix and resend every rejected row; never drop one silently.
