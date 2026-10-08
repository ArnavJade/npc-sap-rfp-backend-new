---
name: scope-analytics
description: >-
  Extracts the analytics and reporting scope of an SAP RFP into the bid ledger - one row per
  analytics object (SAC / BW models, reports and dashboards, HANA CDS views) with object type,
  custom vs standard build, count, scope status and complexity - and records an explicit exclusion
  of the whole analytics workstream with its evidence. Effort is computed from reference rates.
  Use when building the effort estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "0.1.0-draft"
  ledger_sections: "analytics,analytics_scope"
---

# Analytics

> Draft authored without the old prompt text (section G of
> third_party_integration_extraction_layer.py and analytics_scope.py). TODO(port): diff when npc-dev
> is available.

Effort per row = count x reference rate[type][complexity] (x the Standard factor for SAP-delivered
content). You record objects and counts, never effort.

## What counts
Reporting and analytics the bidder must build or configure on SAP: SAP Analytics Cloud stories,
dashboards and planning models, BW/4HANA or embedded BW models, Analysis for Office workbooks, custom
HANA CDS views / analytical queries, embedded analytics KPI apps, statutory / management reports
the RFP lists by name or count.

## Never analytics
Operational ABAP reports (RICEFW reports - scope-ricefw-fiori), standard Fiori analytical apps that
need no work, third-party BI tools the client builds itself, data-lake engineering (an integration).

## Rows (`analytics`)
- `object`: the report / model / view name or a group label ("Finance management reports").
- `object_type`: Model | Report | CDS View. `build`: Custom | Standard (SAP-delivered content that
  is activated and adapted).
- `no_of_objects`: the stated count (1-500); a list of 12 named reports may be one row with 12 or
  several rows - group by type and complexity.
- `complexity`: Low / Medium / High (simple list report = Low; multi-source dashboards, planning
  models = High).
- `status`: In Scope, or Out of Scope when assigned to the client / another vendor.
- One row per distinct object group; merge duplicates.

## Exclusion (`analytics_scope`)
When the RFP explicitly excludes analytics / reporting from the bidder's scope ("BI and reporting
are out of scope of this RFP"), write `analytics_scope` with `excluded: true` and the verbatim
`exclusion_evidence`. Silence is not exclusion: if the RFP says nothing, write `analytics` as empty
with a none_reason and leave `analytics_scope` unset.

## Output
`ledger_write_analytics(rows=[...])` with evidence per row (file, page), and
`ledger_write_analytics_scope(data={...})` only for an explicit exclusion. Fix and resend rejected
rows.
