# Placeholders and bid_facts views

Every figure, table and diagram in the response comes from the ledger through a placeholder. The
renderer replaces it; you never type the value. `bid_facts('figures')` lists the keys that exist for
THIS bid and removes the keys the client's disclosure profile withholds - use only those.

## Figures - `{{fig:<key>}}` (inline, unit words after it are already part of the value)

| Key | Renders as | Withheld by |
|---|---|---|
| `total_project_effort` | "1,234.5 person-days" | effort_detail |
| `total_build_effort` | build effort up to Realize | effort_detail |
| `functional_scope_effort`, `tech_dev_effort`, `data_migration_effort`, `security_effort`, `basis_effort`, `analytics_effort` | workstream effort | effort_detail |
| `final_prep_effort`, `go_live_effort`, `project_mgmt_effort`, `hypercare_effort`, `risk_contingency_effort`, `summary_of_imp_effort` | ladder steps | effort_detail |
| `total_project_cost` | "USD 412,000" | commercial_detail |
| `daily_rate`, `hypercare_rate` | "USD 320 per person-day" | commercial_detail |
| `peak_fte` | "6.5 FTE" | resource_allocation |
| `total_man_months` | "54 man-months" | resource_allocation |
| `programme_months` | "16 months" | - |
| `programme_weeks` | "70 weeks" | - |
| `wave_count`, `country_count`, `lob_count`, `integration_count` | a bare number | - |
| `scope_item_count` | a bare number | scope_item_detail |

Write the unit only when the value has none: "{{fig:wave_count}} delivery waves",
"{{fig:country_count}} countries". Never "{{fig:total_project_effort}} person-days" (doubled unit).

## Tables - `{{table:<key>}}` (on a line of its own)

| Key | Content | Owning section | Withheld by |
|---|---|---|---|
| `module_summary` | LOB, business areas, scope-item count (+ effort) | 3.1 | - (effort column needs effort_detail) |
| `functional_scope` | every Best Practice scope item per LOB and country | 3.2 | effort_detail, scope_item_detail |
| `resource_plan` | man-months per role per wave | 4.4 | resource_allocation |
| `raci` | standard RACI matrix | 4.6 | - |
| `role_roster` | roles (+ location) and waves | 5.4 | - (location column needs resource_location) |
| `effort` | Summary of Project Effort ladder | 6.1 | effort_detail |
| `cost` | implementation + hypercare cost | 6.2 | commercial_detail |
| `wave_plan` | waves, countries, start month, duration, hypercare, go-live | phase_plan sections | - |
| `integrations` | third-party systems, purpose, direction, middleware | 3.3 (you place it) | - |
| `data_migration` | conversion objects and scope status | 4.7 (you place it) | - |
| `tech_dev` | RICEFW / Fiori / interface objects (no effort) | 3.3 (you place it) | - |
| `indicative_breakdown:<module|wave|country|role|workstream>` | effort (or man-months for `role`) by dimension | client-required breakdowns | effort_detail (role: resource_allocation) |

A section's own artifact (outline column `artifact`) is appended by the renderer - do not place it
again. Tables marked "(you place it)" have no outline slot: the writer of that section places them.
Use any other table key only in a client-required section that asks for it.

## Diagrams - `{{diagram:<key>}}` (on a line of its own)

`timeline` (4.3: waves on the calendar, coloured by SAP Activate phase), `methodology` (4.1: the
SAP Activate phases), `architecture` (4.2: S/4HANA core, lines of business, middleware, third-party
systems). Each belongs to its section; never repeat one elsewhere.

## bid_facts views

| View | Gives you |
|---|---|
| `profile` | client, engagement type, summary, countries |
| `scope` | LOB -> business area -> number of scope items |
| `scope_by_lob` | LOB -> business area -> scope-item names (ids hidden when withheld) |
| `non_catalogue` | SAP tools / modules without Best Practice content |
| `integrations` | third-party systems, purpose, direction, middleware, SAP modules |
| `tech_dev` | RICEFW rows / totals and Fiori apps as the RFP states them |
| `workstreams` | data migration objects, Basis / Security activities, analytics objects, with status |
| `timeline` | waves (duration, hypercare, countries, go-live), sequencing, programme length key |
| `team` | roles per wave (location hidden when withheld) |
| `commercials` | which effort / cost placeholders you may use, withheld categories |
| `requirements` | client requirements, disclosure profile, presales briefs |
| `excerpts:<section_id>` | verbatim RFP text the section must answer |
| `figures` | the placeholder keys available to you and the bare numbers you may type |

`figures.bare_numbers_allowed` lists the ledger counts (waves, countries, LOBs, integrations, wave
weeks / months, programme months) that draft_check accepts as typed numbers.
