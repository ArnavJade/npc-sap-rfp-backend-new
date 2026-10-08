# Mapping guardrails

The qualification rules the previous mapping prompts enforced, kept near-verbatim. They stop
"phantom LOBs": catalogue lines a capability only resembles. The write tool enforces part of this
(a sensitive-LOB item needs `capability_refs` or evidence); the judgement is yours.

## Sensitive LOBs

These six LOBs are never resolved from a rulebook row or a keyword alone - qualify each against the
capability's RFP evidence:

- Application Platform and Infrastructure
- Asset Management
- Database and Data Management
- Human Resources
- IT Management
- R&D/Engineering

Assign one of them ONLY if there is a legitimate need for that LOB to exist as a dedicated
functional module in the effort workbook. If a capability relates to one of these areas but does NOT
meet the qualification below, give it no catalogue items for that LOB - do not assign the LOB, and
do not force the capability into an unrelated LOB.

1. **Application Platform and Infrastructure**
   - Qualify ONLY if the RFP explicitly procures dedicated SAP BTP custom extension development or SAP
     Build Process Automation platform builds.
   - Do NOT qualify for standard APIs, middleware conduits, interface protocols, approval workflows,
     Fiori launchpad setup, or bank/system integrations - in SAP RFP bidding, technical interfaces and
     middleware conduits are technical delivery workstreams or WRICEF items, NOT functional Best
     Practice modules.
2. **Asset Management**
   - Qualify ONLY if the RFP explicitly procures/implements SAP Plant Maintenance (EAM/PM) for
     physical industrial plant machinery, maintenance orders, maintenance notifications, and
     preventive maintenance plans for technical objects and functional locations.
   - Scope items warning: BH1 ("Corrective Maintenance"), BH2 ("Emergency Maintenance"), BJ2
     ("Preventive Maintenance"), 4HI ("Proactive Maintenance"), and 4HH ("Reactive Maintenance")
     apply EXCLUSIVELY to physical equipment and shop-floor machinery (SAP PM/EAM). They NEVER apply
     to IT software bug fixing, patch management, or application maintenance.
   - Do NOT qualify for IT software maintenance, application management services (AMS), software
     bug fixes, emergency hotfixes, server/database upkeep, system patching, IT system uptime, or SLA
     incident tickets.
   - Do NOT qualify for "Master Data Maintenance" (maintaining customer, vendor, material, price, or
     BOM master records) - route to the operational LOB (Finance, Sourcing and Procurement, Sales,
     Supply Chain) or Database and Data Management, or give it nothing.
   - Do NOT qualify for financial fixed asset accounting, asset depreciation, asset capitalization,
     or asset registers - route to Finance.
   - Do NOT qualify for customer equipment servicing, field service, or warranty maintenance - route
     to Service.
   - Do NOT qualify for third-party vendor facility/office maintenance contracts (AMC) - route to
     Sourcing and Procurement - or for CAPA (Manufacturing / Quality Management).
3. **Database and Data Management**
   - Qualify ONLY if the RFP explicitly procures dedicated SAP Master Data Governance (SAP MDG)
     software or an enterprise-wide master data governance platform (or SAP Datasphere semantic
     architecture procured as a standalone functional solution).
   - Do NOT qualify for legacy data migration, data cutover, staging, cleansing, ETL, or master data
     loading - those are project delivery workstreams, NOT functional Best Practice modules.
4. **Human Resources**
   - Qualify ONLY if the RFP explicitly procures/implements core SAP HCM or Payroll software (core
     HR, statutory payroll, time management, attendance, or SuccessFactors Employee Central as
     in-scope functional software).
   - Do NOT qualify if the RFP only interfaces with existing HR systems (Workday, SuccessFactors,
     ADP) to sync employee records for approvers, workflows, or cost centers.
   - Technical enablement, employee replication interfaces, user provisioning, or scope item 1FD
     (Employee Integration - SAP S/4HANA Enablement) are technical integration conduits to supply
     employee data for approvers or cost centers, NOT implementations of Human Resources. If the
     client is not procuring/implementing dedicated core HR or payroll software, give it nothing.
   - Named external HR tools (SuccessFactors, Workday, ADP, Kronos): an SAP-branded one that the
     rulebook lists as "Others" (e.g. SAP SuccessFactors) goes to non_catalogue; a non-SAP one is a
     third-party integration (not yours). Never map them to the functional Best Practice module
     "Human Capital Management (HCM)".
5. **IT Management**
   - Qualify ONLY if the RFP explicitly procures dedicated SAP Cloud ALM, Solution Manager, or
     specialized ITSM software.
   - Do NOT qualify for standard Basis administration, user roles & authorizations, SoD, SSO,
     background batch jobs, printer/spool setup, system monitoring, or technical operations.
6. **R&D/Engineering**
   - Qualify ONLY if the RFP explicitly procures dedicated enterprise PLM software (e.g.
     recipe/formulation authoring) or a dedicated SAP Product Compliance software suite license.
   - Do NOT qualify for incidental dangerous goods transport handling or shipping papers in
     logistics/warehouse (these belong strictly to Supply Chain / TM / EWM).
   - Do NOT qualify for safety data sheet (SDS) storage or supplier compliance in purchasing (these
     belong strictly to Sourcing & Procurement / MM).
   - Do NOT qualify for environmental, REACH, RoHS, or general regulatory declarations (Finance or
     the operational areas); general regulatory, legal, IT, or financial compliance belongs under
     Finance.
   - Standard manufacturing BOMs and routings belong strictly under Manufacturing.
   - Scope items such as 3FC, 31H, 31G, 31J, 3G8, 3VR, 3VQ, 5OJ (Assess Dangerous Goods, Manage
     Safety Data Sheets, Chemical Compliance Approval) belong to Product Compliance - never select
     them for operational logistics, purchasing, or manufacturing compliance notes.
   - If a capability relates to dangerous goods shipping, route it to Supply Chain. If it relates to
     purchasing SDS or supplier compliance, route it to Sourcing and Procurement. If the client is not
     procuring dedicated PLM or SAP Product Compliance software, NEVER assign R&D/Engineering.

## Special warnings about what the catalogue lists

1. Under Human Resources the catalogue lists "Employee Integration - SAP S/4HANA Enablement" (scope
   item 1FD). Do NOT assign Human Resources for employee integration, employee data replication, user
   sync, or approver workflows.
2. Under R&D/Engineering the catalogue lists Product Compliance capabilities ("Assess Dangerous Goods
   for a Product", "Manage Safety Data Sheets for Products", "Chemical Compliance Approval", ...). Do
   NOT assign R&D/Engineering for dangerous goods shipping/transport, warehouse hazardous storage,
   safety data sheet storage, or supplier compliance certificates.
3. Under Asset Management the catalogue lists Maintenance Management capabilities (BH1, BH2, BJ2,
   4HI, 4HH). They apply ONLY to heavy machinery and physical plant equipment. Do NOT assign Asset
   Management for IT software/hardware maintenance, AMS support contracts, emergency bug fixes, SLA
   response, server/database upkeep, master data maintenance, customer equipment servicing, or
   financial fixed assets. Fixed assets -> Finance; customer warranty servicing -> Service.

## Finance, cash management and compliance

1. **Cash management and Treasury.** Capabilities involving Cash Management, SAP Cash Management,
   cash positioning, cash flow forecasting, liquidity management, bank account management (BAM),
   in-house banking, cash pooling, electronic bank statements (EBS), bank communication management
   (BCM), or treasury operations belong strictly to LOB Finance, Business Area Treasury Management.
   Always qualify Finance for cash management; never map it to Financial Operations or Working
   Capital Management, and never leave the Business Area empty.
2. **Enterprise Risk and Compliance - absolute prohibition for general accounting / statutory
   compliance.** Almost all RFPs mention "statutory compliance", "local tax regulations", "IFRS/GAAP
   compliance", "audit trails", "internal controls", or "approval segregation of duties". These are
   core baseline accounting practices belonging to Accounting and Financial Close or Financial
   Operations. NEVER assign Enterprise Risk and Compliance for statutory compliance, tax rules,
   standard audit logs, or approval workflows. Assign it ONLY if the evidence explicitly scopes
   implementing dedicated Enterprise Risk Management software, standalone SAP GRC (SAP Process
   Control, SAP Risk Management, SAP Audit Management), or Global Trade Services (GTS embargo /
   sanctions screening). A compliance or risk capability whose evidence describes routine statutory
   compliance, tax reporting, audit trails or approval controls maps to nothing.
3. Routine regulatory or statutory compliance does NOT justify standalone compliance modules, and
   does not by itself qualify Finance unless an explicit core accounting process is involved.

## Keyword guardrails (deterministic)

Applied on the capability wording plus its evidence quote:

| Rule | Keywords |
|---|---|
| Remove Enterprise Risk and Compliance unless one is present | `grc`, `process control`, `risk management`, `audit management`, `global trade services`, `gts` |
| Always include Finance / Treasury Management when one is present | `cash management`, `cash positioning`, `cash flow forecast`, `cash forecast`, `liquidity management`, `bank account management`, `in-house cash`, `electronic bank statement` |
| Always include Finance / Advanced Financial Operations when one is present | `credit limit`, `credit check`, `credit exposure`, `credit control`, `credit scoring`, `credit segment`, `credit management`, `creditworthiness`, `collection strategy`, `collections strategy`, `collection worklist`, `collections management`, `promise to pay`, `promise-to-pay`, `dispute management`, `dispute case`, `deduction management` |

## Not applicable (write nothing)

A capability with no rulebook match that is a generic business process, a location, noise, or a
secondary operational delivery workstream / technical conduit - data migration, Basis
administration, incidental safety compliance notes - is NOT APPLICABLE: no scope item, no
non-catalogue row. Do not classify generic operational workstreams as non-catalogue tools. Likewise
a rulebook match that violates a qualification rule above (Basis, cutover data migration, employee
sync) maps to nothing. Mention these in your final message.

## Final pre-write checks

Before writing each capability's mapping:

1. Did you assign **Human Resources**? Verify: is the client implementing/procuring a dedicated core
   SAP HCM or Payroll system? If it is merely employee replication, user provisioning, or approver
   hierarchies (such as scope item 1FD), REMOVE Human Resources.
2. Did you assign **R&D/Engineering**? Verify: is the client procuring dedicated enterprise PLM or a
   dedicated SAP Product Compliance suite? If the requirement relates to dangerous goods shipping,
   warehouse hazardous handling, supplier safety data sheets (SDS), or environmental declarations
   (such as scope items 3FC, 31H, 31G), re-route to Supply Chain (transport/shipping), Sourcing and
   Procurement (purchasing/supplier SDS), or map nothing. NEVER qualify R&D/Engineering for
   operational logistics or purchasing compliance notes.
3. Did you assign **Asset Management**? Verify: is the capability explicitly for physical plant
   machinery or industrial equipment maintenance (SAP PM/EAM)? If it relates to IT software bug
   fixing, emergency hotfixes, database/server patching, application maintenance (AMS), SLA support,
   master data maintenance, or facility vendor contracts, REMOVE Asset Management. Fixed asset
   accounting (depreciation, asset register, CapEx) -> Finance. Customer warranty repairs or field
   technicians -> Service. NEVER assign Asset Management (which triggers BH1, BH2, BJ2, 4HI, 4HH) for
   IT maintenance, software support, or master data records.
4. Did you assign Business Area **Enterprise Risk and Compliance**? Verify: does the evidence
   explicitly scope procuring or implementing dedicated SAP GRC software, SAP Process Control, SAP
   Risk Management, or Global Trade Services? If NO (it merely mentions statutory compliance, tax
   rules, audit trails, internal controls, SoD, or GAAP/IFRS), DELETE it and re-route to Accounting
   and Financial Close or Financial Operations.
5. Did you evaluate **Cash Management**, cash forecasting, bank account management or liquidity
   management? Verify that LOB Finance, Business Area Treasury Management is assigned.
