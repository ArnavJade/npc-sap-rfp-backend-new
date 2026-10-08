---
name: scope-data-migration
description: >-
  Extracts the data migration scope of an SAP RFP into the bid ledger - one row per conversion
  object (master data, transactional / open items, balances, MDG domains) with its SAP module,
  category, scope status and per-phase effort in days on the allowed grid (0.5, 1, 2, 3, 4), plus
  the compulsory MM master data objects when SAP MM is in scope. Use when building the effort
  estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "0.1.0-draft"
  ledger_sections: "data_migration"
---

# Data migration

> Draft authored without the old prompt text (section D of
> third_party_integration_extraction_layer.py and data_migration_scope.py). TODO(port): diff when
> npc-dev is available.

Each row becomes a line on the Data Migration sheet, repeated in one table per delivery wave. Its
effort columns are days per object per wave.

## What counts
Objects the RFP says must be migrated / converted / loaded: master data (material, customer,
vendor / business partner, GL accounts, cost centres, profit centres, assets, BOMs, routings,
pricing conditions, employees), transactional data (open POs / SOs, open AR / AP items, stock,
open orders), balances (GL balances, asset values), and MDG domains. Data-migration object lists,
annexures and "the following data shall be migrated" sentences are the source.

## Never data migration
Archiving, historical-data reporting from a data lake, data cleansing done by the client alone,
integration data flows (scope-integrations), and generic statements ("data migration is in scope")
without objects - then list the objects that the in-scope modules make unavoidable only under the
MM rule below, and otherwise record the section with a none_reason quoting the generic statement.

## Rows
- `object`: a clean name ("Material Master"); `rfp_label`: the RFP's own words.
- `sap_module`: FI, CO, MM, SD, PP, QM, PM, HCM ...; `category`: "Master Data" (default),
  "Transactional", "Balances", or an MDG domain name.
- `status`: "In Scope", or "Out of Scope" when the RFP assigns the object to the client or another
  party.
- Effort (days, snapped to 0.5 / 1 / 2 / 3 / 4): func_spec, program_dev, iteration_1, iteration_2,
  iteration_3, cutover. Defaults 1 / 1 / 2 / 2 / 2 / 1. Raise to 3-4 for very high-volume or
  multi-source objects (e.g. material master from several legacy systems), lower to 0.5-1 for small
  configuration-like objects (e.g. payment terms).
- One row per object - merge the same object named in two places.

## MM compulsory rule
When SAP MM (procurement / inventory) is in scope, Material Master, Vendor / Business Partner
(supplier) Master, Purchasing Info Records and Source Lists are always needed for go-live even when
the RFP does not list them. Add any of them the RFP omits with `sap_module: "MM"`,
`mm_compulsory: true` and no evidence (the validator exempts exactly these rows). Do not use the flag
for anything else.

## Output
`ledger_write_data_migration(rows=[...])`, every non-compulsory row with verbatim evidence (file,
page). No migration scope -> `rows=[]` with a none_reason. Fix and resend rejected rows.
