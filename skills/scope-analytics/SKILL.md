---
name: scope-analytics
description: >-
  Extracts the named SAP analytics / BI deliverables an RFP puts in scope (SAP Analytics Cloud
  stories, dashboards and planning models, BW/4HANA models and queries, Datasphere, BusinessObjects,
  embedded analytical CDS views and apps, named KPI packs) into the bid ledger - object type, custom vs
  standard build, SAP product, count, status, complexity - and records an explicit whole-scope
  exclusion. No effort figures: they come from reference rates. Use when building the effort
  estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "1.0.0"
  ledger_sections: "analytics,analytics_scope"
---

# SAP Analytics scope

Ported from section (G) of the old scope prompt and analytics_scope.py.

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

Signals (grep): `analytic`, `dashboard`, `KPI`, `BI|business intelligence`, `SAC|Analytics Cloud`,
`BW|Datasphere|BusinessObjects`, `embedded analytics|CDS`, `management reporting|performance
management|insight`, `reporting and analytics|analytics and reporting`.

Per-module scope tables (annexures listing each module's processes) often carry lines or areas
titled as analytics / reporting deliverables ("Treasury Analytics and Reporting", "Performance
Management Reporting & Analytics"): each such line is one Report row, even without a product name.

## What counts
Named SAP ANALYTICS / BI deliverables in scope: SAP Analytics Cloud (stories, dashboards, planning
models), SAP BW/4HANA or BW (models, cubes, datamarts, queries), SAP Datasphere, SAP BusinessObjects,
S/4HANA embedded analytics (analytical CDS views / queries, analytical Fiori apps, KPI tiles), named
management dashboards / KPI packs, and scope lines explicitly titled as analytics / BI ("Treasury
Analytics and Reporting").

## Never Analytics
ABAP / ALV / custom operational reports and forms (RICEFW - scope-ricefw-fiori), reporting steps that
are part of a module's business process ("Perform Financial Reporting", "VAT Reporting", "MIS
Reporting"), group-reporting consolidation functionality, non-SAP BI tools (Qlik, Power BI, Tableau -
third-party integrations), marketing statements about the platform's analytics, project-management
reporting.

## Evidence
STRICT: list a deliverable ONLY when the RFP states it or puts its SAP product in scope; nothing from
general knowledge. A scope-table area or line titled as analytics / BI IS a deliverable, even when
process lines are listed under it. Never the same deliverable twice in different words; when the RFP
states a count for a kind of object ("25 SAC dashboards"), ONE row carrying that count.

## Fields (`analytics` rows)
- `object`: a concise name in the RFP's terms.
- `object_type`: Model (cube, datamart, BW / SAC / Datasphere model), Report (story, dashboard, query,
  KPI, analytical app) or CDS View.
- `build`: Standard ONLY when the RFP says the content is standard / SAP-delivered / pre-built;
  otherwise Custom.
- `sap_product`: the SAP analytics product the RFP names for it ("SAP Analytics Cloud"); "" when none
  is named - never inferred.
- `no_of_objects`: the stated count, else 1 (max 500).
- `status`: Out of Scope when excluded or given to someone else; otherwise In Scope.
- `complexity`: Low / Medium / High from the data sources, entities, KPIs, planning / write-back and
  real-time needs stated.
- `evidence`: verbatim RFP words, file and page.
No effort figures.

## Whole-scope exclusion (`analytics_scope`)
Set `excluded: true` ONLY when the RFP explicitly removes the analytics / reporting / BI workstream AS
A WHOLE from the implementation partner's scope ("Analytics and reporting are out of scope", "BI will
be delivered by the client's team"), with its exact words in `exclusion_evidence`. Excluding one tool
or report is NOT a whole exclusion - mark that object Out of Scope instead. Silence is not exclusion.

## Output
`ledger_write_analytics(rows=[...])` (or `rows=[]` with a none_reason), and
`ledger_write_analytics_scope(data={...})` only for an explicit whole-scope exclusion. Fix and resend
rejected rows.
