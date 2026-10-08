---
name: scope-ricefw-fiori
description: >-
  Extracts custom development scope from an SAP RFP into the bid ledger - RICEFW / WRICEF objects
  (reports, interfaces, conversions, enhancements, forms, workflows) as per-type rows or a stated
  lump total with its complexity split, the stated total interface count, and custom Fiori apps
  (count, names, stated hours). Records only what the RFP states; Tech Dev effort is computed by the
  tools from these counts. Use when building the effort estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "0.1.0-draft"
  ledger_sections: "ricefw,fiori"
---

# RICEFW and custom Fiori

> Draft authored without the old prompt text (sections B and C of
> third_party_integration_extraction_layer.py). TODO(port): diff against it when npc-dev is available.

You write two objects: `ricefw` and `fiori`. The Tech Dev sheet is computed from them: per-object
policy hours by complexity unless the RFP states hours, Fiori floored at a minimum per app, and the
stated interface total minus the integrations already priced (so do not subtract them yourself).

## ricefw
Look for RICEFW / WRICEF / "custom developments" / "development objects" tables, counts in the
scope narrative, annexure object lists, and phrases like "approximately 40 custom reports".
- `rows`: when the RFP lists objects per type - one row per (object_type, complexity) with
  `no_of_objects`; `object_type` one of Report, Interface, Conversion, Enhancement, Form, Workflow.
  Put man-HOURS for the whole row in development / configuration / unit_testing / qa_testing ONLY
  when the RFP states them; otherwise leave them null.
- `development_objects_total` + `complexity_split_pct` ({complex, medium, simple} percentages): when
  the RFP gives only a total ("150 WRICEF objects, 30% complex, 50% medium, 20% simple"). No split
  stated -> leave it empty (all Medium is assumed). `development_object_type` only if the total is
  of one type.
- `interface_total_count`: the total number of interfaces the RFP states (including third-party
  ones). Do not list the systems here - scope-integrations owns them.
- Map complexity words: simple/low -> Low, medium -> Medium, complex/high -> High.
- Never estimate counts the RFP does not state. "Bidder to estimate custom development" with no
  numbers -> write `ricefw` empty with that quote as the none_reason.

## fiori
Custom (not standard SAP-delivered) Fiori / UI5 apps: `app_count`, `app_names` as listed,
`per_app_hours` only if stated. Standard Fiori apps, the Fiori launchpad, theming and role-based
launchpad configuration are NOT custom apps (security / basis scope). No custom apps -> empty with a
reason.

## Evidence
Every non-empty object carries verbatim evidence (the table or sentence with the counts), file and
page; per-row evidence where the rows come from different places.

## Output
`ledger_write_ricefw(data={...})` and `ledger_write_fiori(data={...})`, or each with
`none_reason` when the RFP has nothing. Fix and resend anything rejected.
