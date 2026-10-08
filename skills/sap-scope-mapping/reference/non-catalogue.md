# Non-catalogue SAP tools and modules

`non_catalogue` holds SAP-owned tools, products and modules that the client needs but that have no
SAP Best Practice scope items, so no rate-card effort exists for them. Each row carries your planning
estimate inside a policy band. Third-party (non-SAP) systems never go here - they are integrations.

## What belongs here

- A capability the rulebook resolves to **"Others"** - e.g. SAP Solution Manager 7.2 ("SAP Tool"),
  SAP BTP and Joule ("SAP Technical Service"), SAP MDG and SAP GRC ("SAP other tool"), SAP Signavio
  ("SAP Process tool"), SAP Analytics Cloud ("SAP Reporting Tool"), SAP Integration Suite ("SAP
  Integration tool"), SAP Fiori / Work Zone ("SAP Technical UI Tool"), SAP Concur, SAP
  SuccessFactors, SAP IBP ("Unclassified"), Project Systems (PS) ("SAP Module, but No Best
  Practises"). The label in [cross-mapping-aliases.md](cross-mapping-aliases.md) becomes `label`.
- A genuine SAP product/tool/solution that is not in the rulebook and has no catalogue content:
  `label` = a short (a few words) description of what it is, grounded in the evidence and your SAP
  knowledge - never blank.

`kind`: `sap_module_no_bp` for an SAP functional module that has no Best Practice content (Project
Systems is the reference case); `sap_tool` for every other tool, platform or product.

**Never here:**

- a catalogue-covered module - FI, CO, FICO, MM, SD, PP, QM, WM, EWM, TM. The check is exact-token on
  the whole name or on its bracketed abbreviation: "FCM (FI/CO)" and "MM/SD" are covered (map them to
  scope items); "SD Worx" or "Solver (Finance Consolidation)" are not;
- a named third-party / non-SAP system - it is an integration (written by the integrations
  specialist);
- an existing-no-change catalogue item - it is a `scope_items` row with status `excluded_existing`;
- a generic process or delivery workstream (data migration, Basis, cutover) - not applicable.

## SAP-branded versus third-party

- **Non-catalogue SAP tool**: a core SAP module / capability / product that is missing or unclear in
  the standard Best Practice catalogue. This INCLUDES SAP-owned products that were originally
  acquired by SAP - they are now part of SAP's own portfolio, not external third-party systems.
  Examples: SAP SuccessFactors, SAP Ariba, SAP Concur, SAP Fieldglass, SAP Customer Experience (CX).
- **Third-party integration**: a named external system that is NOT owned or branded by SAP, running
  separately from core SAP and needing its own dedicated integration / interface effort - a vendor's
  own named system (e.g. Coupa, Blancco, Qlik, Kronos, Workday), a client's homegrown portal, or a
  non-SAP cloud service.

An SAP-branded product is an SAP tool even if it was acquired rather than built natively. A short or
ambiguous name with no clear evidence either way is not a reason to guess: read the capability's
evidence before deciding.

SAP security and analytics products (GRC Access Control, Cloud Identity Access Governance, GRC
Process Control, Secure Login Service, SAP Analytics Cloud, BW/4HANA, Datasphere, BusinessObjects)
are priced on the Security / Analytics sheets when those workstreams carry them. Read `security` and
`analytics` first; write the product here only when neither carries it.

## One row per tool

Collapse to one row per distinct tool name (case- and space-insensitive: "SAP Ariba", "sap ariba"
and "  SAP  Ariba " are the same), with `countries` = the union of every country it applies to - never
one row per country. The first mention supplies the name and label; the first non-empty description
wins.

Merge two names only when they are genuinely the SAME real-world tool under a different spelling,
casing or naming (e.g. a typo in one part of the RFP versus the correct name elsewhere). Use the name
AND the description / evidence together; do not rely on spelling similarity alone. Several genuinely
different tools are frequently listed together in one row ("X, Y and Z are used for ...") - one item
merely mentioning another's name because they were listed together is NOT evidence they are the same
tool. If you are not confident two items are the same real thing, keep them separate: a wrong merge
silently hides a real, distinct tool from the estimate.

## Project-management systems (`is_project_management`)

TRUE only if the system is a PROJECT / PORTFOLIO / PROGRAMME MANAGEMENT system - software whose
purpose is planning, scheduling, tracking or governing projects, portfolios, programmes or
engineering work packages. The question is what the tool IS, not what the integration to it happens
to do.

- TRUE examples: Primavera P6, Microsoft Project, Microsoft Project Online, Jira, Asana, Monday.com,
  Smartsheet, Planview, Clarity PPM, Wrike, Trello, SAP Portfolio and Project Management (PPM), SAP
  Project System (PS), SAP Enterprise Project Connection, Oracle Primavera Unifier, Autodesk
  Construction Cloud.
- FALSE examples: Kronos, Workday, Salesforce, Concur, Ariba, SuccessFactors, ServiceNow ITSM,
  DocuSign, Power BI, Tableau, Blancco, a bank host-to-host payment interface, a tax e-invoicing
  portal, a warehouse management system, an HR time and attendance clock, a CRM, a data-migration
  tool, a middleware or API gateway.
- A name containing any of these is always a project-management system: primavera, ms project,
  microsoft project, msproject, jira, asana, monday.com, smartsheet, planview, clarity ppm, wrike,
  trello, project system, portfolio and project management, project management, ppm, project online,
  project server.

Why it matters: non-catalogue and third-party leads are pooled (one lead and N consultants sized by
capacity) UNLESS the system is a project-management system, which keeps a lead of its own.

## Effort (`effort_days`, `effort_band`, `rationale`)

None of these tools has an entry in the Best Practice catalogue, so no precise effort figure exists -
your figure is a reasonable planning placeholder, not a quote. Estimate a ROUGH, APPROXIMATE
person-day effort for each tool within the larger SAP implementation project:

- Base the estimate on typical effort for integrating or accounting for a comparable auxiliary SAP
  tool at a similar level of complexity.
- Scale sensibly for the number of countries involved - a tool needed in several countries usually
  costs more than the same tool in one, but rarely a flat per-country multiple; account for shared
  setup effort.
- Estimate every tool independently - do not let one tool's complexity influence another's estimate.
- `rationale`: one short sentence naming the specific complexity driver behind the number - e.g. its
  country count, integration type, number of entities, or "no complexity signal available - baseline
  estimate" - not a generic restatement of the figure.

Choose the band first, then a figure inside it (policy `effort.non_catalogue.effort_bands`,
person-days):

| `effort_band` | Range | Use for |
|---|---|---|
| `sap_tool_light` | 5 - 20 | enabling or configuring an SAP tool with little or no build, few users or one country |
| `sap_tool_standard` | 20 - 60 | implementing an SAP tool or product: design, configuration, integration to S/4HANA, testing, several countries or entities |
| `sap_module_no_best_practice` | 40 - 150 | a full SAP functional module without Best Practice content (e.g. Project Systems): design, configuration, testing and rollout like a catalogue module |
| `third_party_integration` | 10 - 60 | an SAP tool whose effort is essentially an interface build (rare here; true third-party systems are integrations) |

A figure outside its band is accepted only with a rationale that says why (the tool reports it), and
`effort_days` must stay above 0 and at most 500.
