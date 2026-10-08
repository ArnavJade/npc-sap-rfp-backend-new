---
name: estimating
description: >-
  How the effort orchestrator of call 1 gets the bid ledger complete and consistent so the
  deterministic sizing tools can price it - which specialist owns which section, how to brief them,
  how to judge the coverage check, how to resolve cross-section overlaps (integration vs
  non-catalogue, Security/Analytics sheets vs non-catalogue, catalogue GRC vs Security GRC), what
  effort_preview is for, and the rule that no agent ever states a number a tool did not return.
  Use when orchestrating the effort team or resolving ledger_check findings.
metadata:
  owner: "presales"
  version: "0.1.0"
---

# Estimating (effort orchestrator)

Every number in the workbook is computed after you stop: the rate card prices scope items per
country, Tech Dev is derived from RICEFW / Fiori / integration counts, the four workstream sheets
from their rows, the resource plan and the Summary of Project Effort from all of that. Your job is
the INPUT: a ledger in which every section is written (or recorded empty with a reason), each fact
appears exactly once, and the wave plan says which wave delivers what.

## Who writes what
| Section(s) | Specialist | Needs first |
|---|---|---|
| rfp_profile, capabilities, timeline | `rfp-analyst` | - |
| integrations | `scope-integrations` | - |
| ricefw, fiori | `scope-ricefw-fiori` | - |
| data_migration | `scope-data-migration` | - |
| basis | `scope-basis` | - |
| security | `scope-security` | - |
| analytics, analytics_scope | `scope-analytics` | - |
| scope_items, non_catalogue | `catalogue-mapper` | rfp_profile + capabilities |
| wave_plan | `wave-planner` | timeline + scope_items + the workstream sections |

The `scope-*` list is whatever skills/scope-* folders exist; your roster in the prompt is
authoritative.

## Briefs
A good brief names: the client; the RFP files; the 3-8 index entries (file + pages) most likely to
hold that specialist's material - outline headings, tables, transcribed diagrams; and anything the
index's pre-scans flag for it (wave anchors -> rfp-analyst, third-party candidates ->
scope-integrations). End every brief with: "Write your sections with your ledger tools; if the RFP
has nothing for a section, record it as empty with a none_reason citing what you checked." Never
paste RFP text into a brief - point to pages.

## Coverage
`ledger_status` / `ledger_check` show each section as `written`, `empty` (looked, nothing there,
reason given) or `pending` (nobody wrote it). Only `pending` is a gap. For a gap, re-spawn its owner
once with a sharper brief: what is missing, which pages to read. An `empty` section with a weak
reason ("not found") deserves one retry when the index shows a likely page.

## Overlaps (`ledger_check` -> `overlaps`)
Each overlap names a suggested `keep` and `drop`. Resolve with `ledger_resolve_overlap`; give the
reason in one sentence.
- **integration_vs_non_catalogue** - keep the integration: it carries the interface columns and is
  priced on Tech Dev. Drop the non-catalogue row. Exception: the RFP asks for the SAP product
  itself to be implemented (e.g. "implement SAP Ariba") AND an integration to it - then both are
  real; keep both by not resolving and say so in your summary.
- **security_vs_non_catalogue / analytics_vs_non_catalogue** - keep the Security / Analytics sheet
  row (it is sized by that sheet's rules); drop the non-catalogue duplicate.
- **catalogue_grc_vs_security** - this is a flag, not a duplicate by construction. If the RFP asks
  for GRC as a business process (risk / compliance management scope items) AND for GRC access
  control configuration, keep both. If it is one ask, keep the Security row and drop the catalogue
  item.
Never resolve a pair `ledger_check` did not report.

## effort_preview
`effort_preview(group_by)` shows the deterministic person-days per workstream, LOB or country line
from the ledger as it stands. Use it to sanity-check proportions (e.g. a Finance-only RFP whose
largest line is Analytics means a specialist over-read). It is for your judgement and the
wave-planner's; never copy its numbers into a brief, the ledger or your summary.

## Numbers
You and every specialist record facts (counts, durations, statuses, complexities, effort bands for
non-catalogue items and integrations) - never totals, costs, FTE or percentages. If an RFP states a
figure (a budget, a stated effort), it may be quoted as evidence, not used as an input.

## Finish
Stop when `ledger_check` reports no missing sections and no unresolved overlaps you intend to
resolve, or after one retry per gap. Summarise per specialist in a few lines (counts, notable
exclusions, open doubts). The flow re-checks coverage after you stop and may send you back once.
