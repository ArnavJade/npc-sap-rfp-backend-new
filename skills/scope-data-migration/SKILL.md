---
name: scope-data-migration
description: >-
  Extracts the MASTER DATA objects an SAP RFP puts in data migration scope into the bid ledger - from
  migration / conversion sections, running text, per-module scope tables and MDG data domains - with
  the RFP's area name, the SAP module, the MDG domain, the RFP's verbatim label, the MM compulsory
  objects, and per-phase effort on the allowed grid (0.5, 1, 2, 3, 4 days). Transactional data never
  qualifies. Use when building the effort estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "1.0.0"
  ledger_sections: "data_migration"
---

# Data migration - master data objects

Ported from section (D) of the old scope prompt and data_migration_scope.py. Table-reading rules:
[reference/reading-tables.md](reference/reading-tables.md).

## Where to look
RFPs present migration scope in many ways, often several at once. Search the WHOLE RFP - prose,
lists, `[EXTRACTED TABLE]` and `[EMBEDDED IMAGE]` blocks, PDF diagram text ("Start of picture
text") - and use every source you find. Per-module process-scope tables (e.g. "Order to Cash",
"Procure to Pay", "Plan to Produce", "Transport Management", "MDG") are the usual source: their
master-data rows / sub-processes name the objects:
- a dedicated data migration / conversion / cutover section, table, appendix or annexure (object
  list, data object inventory, load plan, record volumes per object);
- running text naming master data to be migrated, converted, loaded or cleansed ("customer, vendor
  and material masters will be migrated from the legacy ERP");
- per-module / process scope descriptions calling out that area's master data - a "Master Data"
  heading, row group or sub-area, a sub-process such as "Maintain accounting master data", a bullet
  list of master records. Master data named in a module's in-scope implementation must be migrated;
- Master Data Governance (SAP MDG or another MDG solution): include EVERY entry listed under an MDG
  data domain that is an actual data object, view or segment (material, material sales / plant /
  storage / valuation data, business partner, customer, supplier, GL account, cost / profit centre,
  asset, equipment, functional location) - one entry per listed item, never collapsed into its
  parent, never dropped because a similar item sits next to it ("Maintenance Plan /Item" and
  "Maintenance Plan /Item (MI)" are two entries). NOT MDG capabilities that are not data: workflows,
  approval rules, data quality / validation rules, replication, consolidation, mass processing, UI,
  governance processes.

## Never qualifies
- Transactional or balance data - open orders, open items, stock balances, GL balances, historical
  transactions - and process steps (orders, requisitions, confirmations, deliveries, invoices,
  postings), even when a table lists them under a master data heading.
- Generic mentions naming no object ("all master data will be migrated"). A sub-process naming only
  "master data" shows the area is in scope but is not itself an object - take the objects the RFP
  names for that area.
- Objects the RFP places OUT of migration scope (created manually, not migrated).
- Anything the RFP does not show. Never add an object from your own knowledge of what SAP projects
  usually migrate - the single exception is the MM rule.

## Fields per object
| Field | Content |
|---|---|
| `module` | the RFP's area name EXACTLY as it lists the object (hyphen breaks rejoined) - the module-level label ("MM", "Order to Cash"), never a sub-heading such as "Master Data"; only with no area at all, the SAP module short name |
| `sap_module` | the standard SAP module short name that owns the object, decided from the area AND the object; MDG objects use that solution's short name; the same short name every time |
| `category` | for MDG objects the MDG data domain ("Finance Master data"); otherwise "Master Data" |
| `object` | the object's name as the RFP words it (concise: "Customer Master", "Cost Centers", "Equipment (EQ)"), except the MM compulsory names |
| `rfp_label` | the exact RFP words naming it - a verbatim substring (table cell or sentence words), used to ground the row; "" only for an MM compulsory object the RFP does not name |
| `mm_compulsory` | true only for the four MM compulsory objects |
| `status` | "In Scope" |
| `func_spec`, `program_dev`, `iteration_1`, `iteration_2`, `iteration_3`, `cutover` | person-days for that ONE object per phase |

Every master data area the RFP scopes is covered, however it is labelled. List the same object under
two areas when the RFP lists it under both (the area prefixes the sheet label).

## MM compulsory objects
Judge from the whole RFP whether Materials Management master data is in migration scope (MM is in the
implementation scope and its master data - materials, vendors / suppliers, purchasing or inventory
masters - is named for migration, however labelled). When it is, the rows with `sap_module: "MM"`
(under the RFP's own MM / procurement area name) MUST include these four, named EXACTLY: "Material
Master", "Vendor Master", "Info records", "Source List". Use these names for the RFP's equivalents
("Supplier Master" -> "Vendor Master"; never the same object twice), add any of the four the RFP does
not name, and mark all four `mm_compulsory: true` (the evidence rule exempts exactly these). Other MM
objects as usual with false. MM master data not in scope -> do not add them.

## Effort per phase (each value one of 0.5, 1, 2, 3, 4 - other values are snapped)
`func_spec` = functional spec / data template finalisation; `program_dev` = migration program
development / changes; `iteration_1..3` = one mock-load iteration each (loading and changes after
feedback); `cutover` = data cutover to production. Judge every object on its own merits from typical
volume, number of views / segments, dependencies and cleansing effort. Illustrative only:
- complex, high-volume (business partners, material master): 2 / 1 / 3 / 3 / 2 / 2
- medium (purchasing info records, batches): 2 / 1 / 2 / 2 / 2 / 2
- simple (GL accounts, cost centres, bank masters): 1 / 1 / 2 / 2 / 2 / 1
- small dependent (a BOM, inspection method): 1 / 0.5 / 1 / 1 / 1 / 0.5

## Completeness
For every area return EVERY entry of its master data list - walk the list row by row and check the
count before writing. One row per entry per area even when the RFP names it several times, but never
merge or drop genuinely different entries (different views, segments or codes). In your reply, list
the candidates you deliberately left out, with the reason ("transactional data", "explicitly out of
migration scope", "generic mention, no object named", "MDG capability, not a data object",
"duplicate of <object>").

## Output
`ledger_write_data_migration(rows=[...])`, every row (except MM compulsory additions) with verbatim
evidence (file, page). No master data object in migration scope -> `rows=[]` with a none_reason.
Fix and resend rejected rows.
