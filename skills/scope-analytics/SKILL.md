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
reporting, custom Fiori applications (scope-ricefw-fiori), and Finance close / consolidation process
lines such as financial statements, disclosure or segment reporting (catalogue scope).

## Procedure
1. The pages in your brief are a starting point, not the boundary. Run ONE grep over /rfp/ (literal
   words, `|` between them) for
   `analytic|dashboard|KPI|business intelligence|Analytics Cloud|BW/4|BusinessObjects|Datasphere|CDS view|insight`
   and read (`read_section`) every page with a hit. Per-module scope tables (annexures listing each
   module's processes) are where the titled lines usually sit.
2. In those tables, a line or area whose OWN title names analytics, dashboards or KPIs as the thing
   delivered ("<Area> Analytics and Reporting", "<Area> Dashboards") is one Report row; a process
   line that merely mentions reporting is not.
3. Before a later batch, `ledger_read("analytics")` and send only objects not saved yet. A rejected
   row: fix it and resend THAT row only.
4. `rows=[]` only when the grep found nothing that qualifies; the none_reason names the searches and
   pages checked.

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
rejected rows only.
