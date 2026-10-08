# Capability extraction: country -> SAP module / capability -> scope -> evidence

The rules the previous extraction prompt applied, kept near-verbatim. "The RFP" is the whole
document set in `/rfp/`.

## SAP module / capability examples

Examples of SAP modules, SAP solutions, and SAP-related capabilities that may appear as scope:

FI, CO, FICO, MM, SD, PP, QM, PM, PS, WM, EWM, IBP, TM, GRC (dedicated software only), SAC, Ariba,
Concur, Signavio, Joule, CX, ITAD, Hyperscale ITAD, e-Waste Recycling, Battery Recycling, MDS, and
other functional SAP modules, solutions, or capabilities explicitly requested in the RFP.
(Only extract HR/HCM, Product Compliance, or GRC / Enterprise Risk and Compliance if the RFP
explicitly procures dedicated core software packages for them, adhering strictly to the functional
module scope boundaries below.)

Preserve the terminology used by the RFP. Do not unnecessarily rename, reinterpret, or convert a
capability into a different SAP module name.

## How to analyse the RFP

Use the complete RFP and your judgment to determine:

1. Which countries are actually associated with the SAP scope.
2. Which SAP modules/capabilities are required for each country.
3. Whether each requirement is in scope or optional scope.
4. What evidence from the RFP supports the country and its SAP scope.

Consider the complete document, including but not limited to: scope of work, scope of initiative,
functional requirements, country / location coverage, SAP bill of materials, country x module
matrices, implementation phases, rollouts, global templates, workstreams, country-specific
localization, SAP transformation / migration requirements, SAP module requirements, relevant
tables, and the surrounding text and document structure. Use the RFP as the source of truth and
your reasoning to understand the relationship between countries and SAP scope.

## Country x module matrices

When the RFP contains a country x module matrix/table with countries as rows and
modules/capabilities as columns (or the reverse), use that matrix as the PRIMARY source for the
modules applicable to each country. Read the individual country row and identify only the
modules/capabilities marked or explicitly applicable to that country.

Do NOT propagate modules from a global SAP scope, a global template, another country, another row,
or surrounding text into a country when the matrix indicates that the module is not applicable to
that country. If a matrix exists, the country-specific matrix takes precedence over general/global
statements when determining that country's modules.

Example - if the matrix reads

```
USA         -> FCM, SCM, CRM
Germany     -> FCM, SCM, CRM, HRM
Netherlands -> FCM, Concur
```

then do NOT give HRM to USA merely because HRM appears elsewhere in the RFP's global SAP scope.

## When there is no country x module matrix

Use the complete RFP and determine the country-module relationship from the document's context. A
relationship may be established through:

- an explicit country + module statement,
- a country-specific section,
- a grouped country statement,
- a workstream,
- an implementation phase,
- a rollout,
- a country-specific localization requirement,
- an SAP Bill of Materials combined with relevant country/location scope,
- an upgrade, migration, or enhancement statement against an existing SAP or legacy system for
  that country (e.g. "upgrade to S/4HANA", "migrate 5 years of AR history", "enhance the current GL
  close process") - treat this the same as a new-implementation statement; a gap/delta requirement
  against an existing system is still in-scope evidence for that country/module,
- or other strong document context.

Use your judgment to determine the most reasonable interpretation supported by the RFP. Do not
require the country and module to appear in the same sentence when the document structure clearly
establishes their relationship.

## Global templates and rollouts

If the RFP describes a global SAP template and subsequent country rollouts, determine whether the
document indicates that the template modules apply to the rollout countries. A global template does
not automatically mean that every module applies to every country. If a country-specific matrix or
explicit country-specific requirement exists, use that information for the country. If the RFP
explicitly states that a global template containing certain SAP modules will be rolled out to a
group of countries, associate those modules with those countries.

## Workstreams

If different countries or country groups are associated with different SAP workstreams, preserve
those relationships. For example:

```
Brazil + Uruguay        -> S/4HANA -> FI, CO, MM, PP, QM, SD
India + United States   -> MDG, SAC, Signavio
```

Do not combine the module sets of different workstreams merely because they appear in the same RFP.

## Scope type

Include both in-scope (`in_scope`) and optional (`optional_scope`) requirements. If a
country/module requirement is explicitly part of an optional SAP scope, record it with
`scope_type: "optional_scope"`. Do NOT include requirements explicitly identified as OUT OF SCOPE,
EXCLUDED, or NOT REQUIRED.

## Implementation status

For every module/capability, classify whether it is genuinely work to be done in this engagement,
or functionality the client explicitly says will remain untouched.

- `existing_no_change`: the RFP explicitly states, for this SPECIFIC capability, that it will NOT
  be changed, configured, migrated, or touched by this engagement - e.g. "will remain unchanged",
  "out of scope for this project", "already fully meets requirements, no further work needed",
  "excluded from this RFP".
- `existing_change`: the capability exists in the current landscape and the RFP asks for it to be
  upgraded, converted, migrated, enhanced, or changed. It is costed exactly like new work; the
  status only records that the client already runs it.
- `new_implementation`: everything else - the safe default. It explicitly INCLUDES a capability the
  RFP describes as part of the CURRENT/AS-IS system when that description is context for what the
  new/upgraded system must do. A brownfield or upgrade RFP routinely says things like "Invoice
  Verification is currently performed in SAP ECC" or "Physical Inventory counts are currently done
  manually" purely to set the scene before describing the new requirement for that same capability -
  that is NOT evidence of `existing_no_change`. Only use `existing_no_change` when the RFP is telling
  you NOT to touch something, never when it is merely describing how something works today.

Do not infer `existing_no_change` from silence, from a brownfield/existing-landscape mention alone,
from words like "as-is" or "currently in use" on their own, or from AS-IS/current-state narrative
describing what the new system must replace or upgrade - only from an explicit statement that this
specific capability is excluded from or unaffected by the engagement.

When genuinely uncertain, prefer `new_implementation` - an incorrect `existing_no_change` silently
removes real scope from the estimate, which is the more costly mistake. (Downstream, an
`existing_no_change` capability is kept visible to the reviewer as an excluded line, but it is never
costed.)

## Module identification

Only record SAP modules, SAP solutions, or SAP-related capabilities that are actually part of the
requested scope. A module may only be attached to a country that has already qualified (see
countries.md, "The country gate").

Do NOT record as a capability: countries, cities, plants, legal entities, business locations,
generic business processes, operational departments, vendor names, partner networks, generic
services - unless the RFP explicitly treats that item as an SAP-related capability or solution
within the requested scope. Preserve the RFP's terminology where appropriate.

## Do not extract technical architecture, Basis, or infrastructure items

These are NOT functional SAP business modules (other specialists capture them):

1. **Technical cutover, staging and data migration.** Do NOT extract "Data migration", "Cutover
   plan", "Legacy data extraction", "Data cleansing", "Staging", "Master data conversion", "Data
   cutover". These are technical delivery activities, not functional software capabilities (they
   must NOT be extracted as modules like Database & Data Management).
2. **Basis, security and user administration.** Do NOT extract "User access matrix", "Roles &
   Authorizations", "Segregation of Duties (SoD)", "Single Sign-On (SSO)", "System monitoring",
   "Technical operations". These are Basis/Security technical administration, not functional
   business LOBs (they must NOT be extracted as IT Management or Application Platform &
   Infrastructure).
3. **Technical integration protocols and middleware conduits.** Do NOT extract generic technical
   interface protocols or transport mechanisms (e.g. "REST", "SOAP", "ODBC", "SFTP", "Web services",
   "BTP/CPI interface") when they merely serve as technical plumbing. Named destination business
   systems or platforms such as "Data Lake(AWS)" DO qualify under the third-party rules below.

## Functional module scope boundaries (critical)

Apply strict functional boundaries for the following areas to prevent false scope extraction:

1. **Service.**
   - Do NOT extract vendor proposal commitments, warranty periods, consultant support desks,
     ticketing SLAs (e.g. "P1/P2 resolution times", "help desk setup"), defect management, or
     hypercare as SAP Service modules.
   - Only extract "Service" when the RFP explicitly states the client wants to implement software
     to manage customer service, warranties, field technicians, or service orders for their own
     external customers.
2. **R&D / Engineering and Product Compliance.**
   - Do NOT extract corporate legal, IT, privacy, or general regulatory compliance (e.g. GDPR, ISO
     27001, NIS2, SOX, audit readiness) as SAP Product Compliance.
   - Do NOT extract incidental hazardous material handling or dangerous goods transport notes in
     shipping/warehousing (these belong to Supply Chain / TM / EWM).
   - Do NOT extract safety data sheet (SDS) storage, hazardous material notes, or supplier
     compliance certificates in purchasing (these belong to Sourcing & Procurement / MM).
   - Do NOT extract REACH, RoHS, or general environmental declarations as Product Compliance or
     R&D/Engineering.
   - Bills of Materials (BOM), routings, and production structures belong strictly to Manufacturing
     (PP / Production Engineering), NOT R&D/Engineering.
   - Only extract "Product Compliance" or "R&D/Engineering" when the RFP explicitly scopes
     implementing or procuring a dedicated SAP Product Compliance software package or a dedicated
     enterprise PLM / recipe / formulation / CAD authoring platform.
3. **Human Resources (HR).**
   - Named HR software or cloud tools requiring SAP integration (e.g. "SuccessFactors", "Workday",
     "ADP", "Kronos") ARE legitimate capability entries under their own specific product/system name
     (third-party rules below). However, do NOT extract them as the generic Best Practice functional
     module "Human Resources" or "HCM".
   - Do NOT extract routine employee master data replication, user account provisioning, or approver
     hierarchies for ERP cost centers / purchase orders as "Human Resources" or "HCM".
   - Only extract "Human Resources" or "HCM" when the RFP explicitly scopes procuring, implementing,
     or reconfiguring core SAP S/4HANA HR, statutory payroll, or time management software.
4. **Sales.**
   - Do NOT extract purchasing/supplier contracts under Sales (these belong to Sourcing and
     Procurement).
   - Routine customer accounts-receivable invoicing belongs to Finance (FI-AR); only extract Sales
     when complete Order-to-Cash, customer quotations, sales orders, or commercial contract
     management is requested.
5. **Asset Management and maintenance.**
   - Scope items warning (BH1, BH2, BJ2, 4HI, 4HH): in SAP Best Practices, Asset Management scope
     items BH1 ("Corrective Maintenance"), BH2 ("Emergency Maintenance"), BJ2 ("Preventive
     Maintenance"), 4HI ("Proactive Maintenance"), and 4HH ("Reactive Maintenance") refer STRICTLY
     to maintaining physical industrial plant machinery, production equipment, and functional
     locations (SAP PM/EAM). They do NOT represent software maintenance or IT tasks.
   - IT / software maintenance and AMS (critical): do NOT extract IT software maintenance,
     application maintenance and support (AMS), bug fixing, patch management, emergency hotfixes,
     database tuning, server patching, proactive/reactive IT monitoring, SLA response times, helpdesk
     support, or IT asset disposal (ITAD) as "Asset Management", "Maintenance Management", or as
     maintenance modules. If an RFP section discusses IT application maintenance or support
     commitments, these are project delivery / SLA obligations, NOT SAP functional modules.
   - Master data maintenance: do NOT extract "Master Data Maintenance" (maintaining customer,
     vendor, material, BOM, routing, or pricing records) as Asset Management or Maintenance
     Management. It belongs to the respective functional LOB (Finance, Sourcing & Procurement,
     Sales, Supply Chain) or Database and Data Management.
   - Financial fixed assets: do NOT extract financial fixed assets, asset accounting, capital
     expenditure (CapEx), asset depreciation, asset retirement, asset tracking, or asset registers as
     "Asset Management" or "Maintenance Management". Extract them under "Fixed Asset Accounting
     (FI-AA)" or "Finance - Asset Accounting" (which belong strictly to Finance).
   - Customer service / warranties: do NOT extract after-sales customer equipment maintenance,
     warranties, field service repairs, customer service agreements, or customer service requests
     under Asset Management (these belong strictly to Service).
   - Facility / office vendor contracts: do NOT extract third-party vendor facility maintenance,
     office upkeep, janitorial services, or building AMC managed via purchase orders as Asset
     Management (these belong to Sourcing & Procurement / Purchasing).
   - Quality CAPA: do NOT extract Corrective and Preventive Actions (CAPA) or quality inspection
     equipment upkeep as Asset Management (these belong to Manufacturing / Quality Management).
   - ONLY extract "Asset Management" or "Plant Maintenance (PM)" when the RFP explicitly scopes
     procuring or implementing software for internal physical plant maintenance, industrial
     machinery/equipment upkeep, maintenance work orders, technical objects (functional locations
     and equipment masters), and plant maintenance notification workflows.
6. **GRC and Enterprise Risk and Compliance.**
   - Almost all RFPs mention compliance requirements: "statutory compliance", "local tax
     regulations", "IFRS / US GAAP accounting compliance", "financial audit trails", "audit logs",
     "change history", "user security & Segregation of Duties (SoD)", or "internal controls &
     approval workflows". These belong to core Finance (FI) and baseline ERP platform configuration.
     Do NOT extract "GRC", "Enterprise Risk and Compliance", "Risk Management", or "Compliance" as an
     SAP module for any of these routine accounting or platform controls.
   - Extract "GRC" or "Enterprise Risk and Compliance" ONLY when the RFP explicitly scopes procuring
     or implementing a dedicated SAP GRC software package (such as SAP Access Control, SAP Process
     Control, SAP Risk Management, SAP Audit Management) or Global Trade Services (SAP GTS). If the
     RFP does not explicitly procure dedicated GRC software, do NOT extract GRC or Enterprise Risk
     and Compliance.

## Third-party / non-SAP systems requiring SAP integration

A named third-party or non-SAP system (a vendor product, an external platform, a partner solution)
IS a legitimate capability entry when the RFP states that this engagement must integrate it with
SAP, build an interface to it, or otherwise perform SAP-side work because of it - even though the
system itself is not an SAP product and the RFP may explicitly call it "3rd party".

The test is NOT whether the system is SAP-branded. The test is whether the RFP asks for SAP-side
work because of it.

Record it using the RFP's own name for the system (e.g. "Marel system (PLC system)", "MTech Poultry
Management Solution", "Mirna", "Workday", "SuccessFactors", "ADP") rather than discarding it as a
mere vendor name. Language cues that the test is met include: "3rd party integration", "will be
integrated with SAP", "integrated with SAP", "interface with", "integration with SAP systems",
"consumes a WRICEF count".

Do NOT extract a vendor/partner name mentioned only as company background, a customer reference, a
subcontractor relationship, or general business context with no SAP-integration requirement
attached - the distinguishing signal is the presence of an SAP-integration requirement, not merely
that a third-party name appears in the document.

These rows also tell the catalogue mapper and the orchestrator which systems the integrations
specialist must cover; the interface detail itself is recorded by that specialist.

## Named HR and integration systems - keep the specific name

Named external systems and SAP tools requiring SAP integration (e.g. "SuccessFactors", "Workday",
"ADP", "Kronos", "Salesforce", "Concur", "Ariba") ARE legitimate capability entries under their own
specific system name. Preserve that specific name exactly - the catalogue mapping already knows how
to route each named system (to a Best Practice scope item when one exists for it, otherwise to the
non-catalogue list); that routing decision is not yours. Do NOT convert or rename them to generic
catalogue module names like "Human Resources" or "HCM".

## Exhaustive extraction from system / application lists and tables

When the RFP contains a table, list, or column enumerating multiple named systems or applications
(e.g. a "Third-Party Applications" table, an "Interfaces" table, a column labeled "3rd Party
solutions" or "Legacy systems"), extract EVERY named system as its own separate capability entry -
not a representative sample. A table with N distinct system names across its rows must produce N
entries, not just the first few or the most prominent ones. `/rfp/index.md` lists third-party
system candidates found in tables: account for every one of them.

## Multiple systems in a single cell or list item

When a single table cell or list item names MULTIPLE systems together (separated by commas, "and",
slashes, or line breaks - such as "Coupa, Solver, Data Lake(AWS)" or "Branco, AutoPilot,
Sustainability-carbon system, etc."), extract EACH named system as its own separate entry. Do not
combine multiple system names into a single capability string, and do not extract only the first
name while dropping the rest. This applies whether or not the table's own language explicitly says
"3rd party" - use the same test as above: does the RFP indicate SAP-side work (interfacing,
integration, configuration) is needed because of it.

## SAP-acquired / adjacent products and platforms (do not skip these)

Continue to extract genuine SAP products, platforms, and acquired solutions that are explicitly part
of the client's business scope, including:

- SAP Concur (Travel & Expense)
- SAP Signavio (Process Mining & Modeling)
- SAP Ariba (Strategic Sourcing & Buying)
- SAP SuccessFactors (when new HR/payroll implementation is explicitly requested)
- SAP IT Asset Disposition (ITAD) / e-Waste Recycling
- SAP Customer Experience (CX) / Commerce
- SAP Joule / Business AI tools

## Confidence

- `high`: the country-module relationship is explicit or directly shown by a country x module
  table/matrix.
- `medium`: the relationship is strongly supported by the document structure, implementation scope,
  rollout, localization, workstream, or other context, but is not directly represented in a
  country-module matrix.
- `low`: the relationship is genuinely uncertain.

Do not invent a relationship simply to avoid a low confidence result.

## Evidence

For every country/module relationship, quote the passage of the RFP that best supports it (verbatim,
at most 300 characters). Prefer evidence that contains both the country and its SAP scope. The
evidence must come from the RFP: do not invent, fabricate, or paraphrase it. If a single passage or
table establishes multiple modules for the same country, the same evidence may support all of them.
For a country x module matrix, use the relevant table headers together with the country's row so
that the evidence demonstrates the country-module relationship.

## Repeated mentions

The same capability is often stated in several places. Keep one row per capability, countries and
status:

- in scope takes precedence over optional scope;
- a new or changed implementation takes precedence over existing-no-change;
- the higher-confidence passage supplies the confidence and the evidence (at equal confidence, keep
  the more complete quote);
- a country confirmed in scope anywhere is never listed as unsupported, and a relationship confirmed
  anywhere is never left as merely ambiguous.

## Important principle

Use your judgment. Do not follow rigid keyword rules. The objective is to recover the CLIENT'S
ACTUAL COUNTRY-SPECIFIC SAP SCOPE from the RFP. Think about the RFP as

```
Country -> SAP Module / Capability -> Scope -> Evidence
```

The relationship between the country and its SAP scope is more important than simply identifying
that the country and module appear somewhere in the document. The country gate has priority over all
module-inclusion rules: first decide whether the country is genuinely in SAP scope, and only then
attach its modules.

## Final validation

Before writing, verify that:

1. Every country is actually relevant to the SAP scope.
2. Every module/capability is actually relevant to that specific country.
3. Country-module relationships are not incorrectly propagated from other countries.
4. Country x module matrices have been interpreted row by row.
5. Optional SAP scope is included.
6. Explicitly excluded/out-of-scope requirements are excluded.
7. Unsupported countries are separated from supported countries.
8. Country codes come only from the allowed list.
9. Evidence quotes are taken from the RFP.
10. No unsupported country/module relationship has been invented.
11. Every country qualified on its own SAP-scope merits, independent of any single module keyword.
    If the only reason a country appears is a nearby module keyword, it has been removed entirely.
12. Did you record "GRC", "Enterprise Risk and Compliance", or "Risk Management"? Verify: is the
    client explicitly implementing a dedicated SAP GRC software package (e.g. Access Control,
    Process Control)? If it is merely general statutory accounting compliance, local tax
    regulations, IFRS/GAAP rules, audit trails, or approval workflows, you MUST NOT record GRC or
    Enterprise Risk and Compliance.
