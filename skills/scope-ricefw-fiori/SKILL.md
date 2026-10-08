---
name: scope-ricefw-fiori
description: >-
  Extracts the RICEFW / WRICEF technical-object build scope (development-object total excluding
  interfaces, complexity split, lump object type, interface total, or per-component rows with the
  RFP's own figures) and the SAP Fiori applications an RFP references (lump count, named apps,
  per-app effort) into the bid ledger. Records what the RFP states; the Tech Dev sheet is computed
  from it. Use when building the effort estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "1.0.0"
  ledger_sections: "ricefw,fiori"
---

# RICEFW and Fiori

Ported from sections (B) and (C) of the old scope prompt. Counts and complexity splits are often
only in `[EXTRACTED TABLE]` / `[EMBEDDED IMAGE]` blocks (a WRICEF summary table) - read them.

## RICEFW (`ledger_write_ricefw`)
RICEFW covers Reports, Interfaces, Conversions, Enhancements, Forms and Workflows (also written
WRICEF / "Development Objects" / "Technical Objects").

1. `development_objects_total`: the TOTAL number of development / WRICEF objects to be built,
   EXCLUDING interfaces (a stated total of "Development Objects", or a WRICEF-except-interfaces
   table). 0 when the RFP gives no such total.
2. `complexity_split_pct`: how those objects split, as percentages adding to 100, keys `complex`,
   `medium`, `simple`, read from the RFP's own figures. If a table and the prose disagree, PREFER
   THE TABLE. No split given -> leave it empty.
3. `development_object_type`: with a lump total (no per-component rows), the single most
   representative type - one of Report, Form, Enhancement, Conversion, Workflow - ONLY when the RFP
   indicates it. A bare total with no hint of type -> "" (do NOT guess "Report": empty tells the
   writer to label the lump rows with distinct RICEFW types).
4. `interface_total_count`: the TOTAL number of interface / integration objects the RFP demands -
   count every distinct interface / integration connection named in the integration section or
   architecture diagram (third-party ones included; the tools subtract the integrations priced
   separately). 0 when none is evidenced.
5. `rows` (preferred when available): when the RFP breaks the objects down PER COMPONENT with
   explicit figures (Forms, Reports, Enhancements, Conversions, Interfaces, Workflows, RF,
   Webdynpros ...), one row per component with the RFP's own figures:
   - `object_type`: the component as the RFP names it;
   - `no_of_objects`: the stated count;
   - `complexity`: the stated complexity, Low / Medium / High (Simple -> Low, Complex -> High);
     Medium only when a count is given without complexity;
   - `development`, `configuration`, `unit_testing`, `qa_testing`: the RFP's stated effort for that
     component per column, in man-HOURS for the whole row; ONLY when stated - otherwise null (it is
     estimated downstream from policy rates). A single lump effort goes in `development`.
   Return rows ONLY when the RFP genuinely gives per-component figures; otherwise rely on the total
   + split.
Do NOT invent scope: no technical-object / interface information at all -> write `ricefw` empty with
a none_reason.

## Fiori (`ledger_write_fiori`)
Count EVERY Fiori app referenced - custom / bespoke apps the client asks to be built AND standard
SAP Fiori apps named as in scope.
- `app_count`: the stated LUMP total ("~20 Fiori apps"). Only individual names and no total -> 0 and
  rely on `app_names`. Both given -> both.
- `app_names`: the apps the RFP explicitly names; [] for a lump total only.
- `per_app_hours`: man-HOURS for ONE High-complexity custom app, split development / configuration /
  unit_testing / qa_testing - only when the RFP states it; otherwise leave it empty (policy: 320 h =
  224 / 24 / 32 / 40, floor 40 man-days per app). The row is always High complexity.
No Fiori app referenced -> write `fiori` empty with a none_reason.

## Evidence
Each non-empty object carries the verbatim table / sentence with the counts, file and page; per-row
evidence where rows come from different places. Fix and resend anything rejected.
