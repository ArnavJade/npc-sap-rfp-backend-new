# The 13 catalogue LOBs

Semantic guidance for choosing a LOB. It is guidance, not a hard rule: the country-filtered
catalogue (`catalogue_search`, `catalogue_business_areas`) remains the source of truth for the
available LOBs and Business Areas - never invent a LOB from this text. Six LOBs are sensitive and
need explicit qualification ([guardrails.md](guardrails.md)): Application Platform and
Infrastructure, Asset Management, Database and Data Management, Human Resources, IT Management,
R&D/Engineering. Business Areas per LOB with example scope items: [catalogue-structure.md](catalogue-structure.md).

For each LOB: **In one line**, **Classify here when** (the decision corpus), and **Scope** (the
detailed definition).

## Application Platform and Infrastructure (sensitive)

**In one line.** Process Management and Integration: business event handling, workflow
orchestration, and integration capabilities that connect systems and processes.

**Classify here ONLY when it primarily concerns** Process Management and Integration: dedicated SAP
Business Technology Platform (BTP) custom extension development, SAP Build Process Automation
platform builds, or standalone event-driven process orchestration platforms explicitly procured as
functional software modules. CRITICAL BOUNDARY: do NOT classify under this LOB for standard API
connectivity, middleware conduits, bank/vendor integration interfaces, workflow approval routing,
Fiori launchpad setup, or standard application integration. In SAP RFP bidding, technical interfaces
and middleware conduits are technical delivery workstreams or WRICEF items, NOT functional Best
Practice modules. Only qualify when a dedicated platform extension build is explicitly in scope.

**Scope.** The sole business area is Process Management and Integration. It governs how business
events are captured, routed, and acted upon across connected systems: workflow orchestration,
event-driven automation, integration scenarios across cloud and on-premise systems, error handling,
monitoring of business events, and extensibility for custom process flows - the connective tissue of
the platform rather than a functional domain.

## Asset Management (sensitive)

**In one line.** Maintenance Management for physical industrial assets, machinery and plant
equipment (SAP PM/EAM). CRITICAL BOUNDARY: its Maintenance Management scope items (BH1, BH2, BJ2,
4HI, 4HH) apply ONLY to physical plant/machinery maintenance - not financial fixed asset accounting
(Finance / FI-AA), IT software maintenance / AMS / bug fixes, master data maintenance, or customer
equipment servicing (Service).

**Classify here ONLY when it primarily concerns** Maintenance Management: dedicated SAP Plant
Maintenance (EAM/PM), maintenance resource scheduling, reactive maintenance, preventive and
corrective maintenance of physical production equipment and machinery, breakdown maintenance,
maintenance notifications, maintenance orders, technical objects, equipment masters, functional
locations, maintenance plans, maintenance strategies, maintenance task lists, and plant condition
monitoring. CRITICAL BOUNDARY: Best Practice scope items BH1 (Corrective Maintenance), BH2 (Emergency
Maintenance), BJ2 (Preventive Maintenance), 4HI (Proactive Maintenance), and 4HH (Reactive
Maintenance) apply EXCLUSIVELY to internal physical plant equipment and machinery upkeep. Do NOT
classify here IT software maintenance, application management support (AMS), defect resolution/bug
fixes, emergency hotfixes, server/database patching, IT infrastructure upkeep, SLA response times, or
IT asset disposal (ITAD); master data maintenance (customer, vendor, material, BOM, or pricing
records); financial fixed asset accounting, asset capitalization, depreciation, asset disposal, or
asset registers (Finance / FI-AA); customer-owned equipment repairs, service agreements, or warranties
(Service); third-party facility maintenance contracts or CAPA. Classify here ONLY when the client
explicitly procures or implements internal physical plant, machinery, or facilities equipment
maintenance (SAP PM/EAM).

**Scope.** Maintenance Management governs how organizations plan, execute, and monitor the upkeep of
physical assets and equipment: preventive maintenance scheduling, corrective maintenance triggered by
breakdowns, condition-based monitoring, the full lifecycle of maintenance orders from creation
through completion and cost settlement, technical objects such as equipment and functional locations,
maintenance history, spare parts availability, safety compliance, technician resource planning, work
scheduling, and integration with procurement for repair materials.

## Database and Data Management (sensitive)

**In one line.** Enterprise Information Management: data governance, quality, integration, and
lifecycle management.

**Classify here ONLY when it primarily concerns** Enterprise Information Management: dedicated SAP
Master Data Governance (SAP MDG) software implementation, enterprise master-data governance
platforms, or SAP Datasphere semantic architecture explicitly procured as standalone functional
solutions. CRITICAL BOUNDARY: do NOT classify here project data migration, legacy data conversion,
data extraction/loading, staging, cutover planning, data cleansing, or transactional master data
setup. In SAP RFP bidding, legacy data migration and cutover are project delivery workstreams, NOT
functional Best Practice modules.

**Scope.** Enterprise Information Management covers how organizations govern, structure, and
maintain master and transactional data across systems: data quality, consistency and validation
rules, data lifecycle from creation to archiving, deduplication, harmonization of data from multiple
sources, metadata management, data cataloging, and governance frameworks defining data ownership.

## Finance

**In one line.** Accounting and Financial Close, Advanced Accounting, Financial Operations, Billing
and Revenue Innovation Management, Cost Management and Profitability Analysis, Enterprise Risk and
Compliance, Environmental Footprint Management, Real Estate Management, Treasury Management
(including SAP Cash Management, cash and liquidity management, bank account management), and Working
Capital Management.

**Classify here when it primarily concerns** Accounting and Financial Close: group ledger, IFRS,
asset accounting, financial close and statutory accounting. Advanced Accounting and Financial Close:
group reporting, financial consolidation, lease-in accounting and advanced close. Advanced Financial
Operations: credit management, collections and dispute management. Cost Management and Profitability
Analysis: financial plan upload, predictive commitments, universal allocation, cost and profitability
analysis. Enterprise Risk and Compliance: dedicated SAP GRC, enterprise risk management, legal
control, Global Trade Services master-data transfer, and embargo control (distinct from routine
statutory tax compliance or core accounting audit trails). Environmental Footprint Management:
product footprint management and environmental accounting. Financial Operations: direct debit,
invoices, taxes, complementary postings and lockbox. Real Estate Management: use and contract
management, occupancy and real-estate contracts. Subscription Billing and Revenue Management: contract
accounting, convergent invoicing, usage and service billing, revenue processes. Treasury Management:
dedicated SAP Cash Management (SAP S/4HANA Cloud for Cash Management / Cash and Liquidity
Management), cash positioning, cash operations, bank account management (BAM), cash flow forecasting,
cash pooling, in-house banking, electronic bank statements (EBS), payment processing, bank
communication management (BCM), bank integration, liquidity, cash, treasury operations and risk
analytics. Classify here when the business purpose is cash management, accounting, controlling,
financial operations, risk, revenue, real estate or treasury.

**Scope.** Accounting and Financial Close (and its advanced counterpart) covers general ledger,
period-end and year-end closing, financial statement preparation, intercompany reconciliation, and
consolidation across entities and currencies. Financial Operations and Advanced Financial Operations
handle accounts payable, accounts receivable, credit and collections, and day-to-day transactional
finance. Billing and Revenue Innovation Management covers flexible billing models and subscription /
usage-based revenue recognition. Cost Management and Profitability Analysis provides cost structures,
overhead allocation, margin and profitability by product, customer or segment. Enterprise Risk and
Compliance covers dedicated enterprise risk management, standalone SAP GRC (Risk Management, Process
Control, Audit Management), and Global Trade Services (embargo and legal control) - it requires
dedicated risk/GRC software tooling and must NOT be assigned for baseline statutory accounting
compliance, local tax rules, or standard audit trails in routine AP/AR/GL accounting. Environmental
Footprint Management tracks carbon accounting and environmental impact reporting. Real Estate
Management handles lease accounting, property portfolio management and real estate cost tracking.
Treasury Management covers dedicated Cash Management (SAP Cash Management, cash positioning, cash
operations, BAM, cash flow forecasting, cash pooling, in-house banking, EBS, payment processing),
cash and liquidity management, banking relationships, FX exposure hedging, and investment or
borrowing. Working Capital Management optimizes receivables, payables, and inventory financing. Area
by area: [finance-business-areas.md](finance-business-areas.md).

## Human Resources (sensitive)

**In one line.** HR Administration: core employee data, organizational structure, personnel
administration and workforce records.

**Classify here ONLY when it primarily concerns** HR Administration: dedicated implementation,
configuration, or business processes for SAP S/4HANA core HR, statutory payroll, time management,
attendance, or SuccessFactors Employee Central as in-scope functional software modules. CRITICAL
BOUNDARY: do NOT classify here when the RFP merely mentions an existing or external HR system (such as
Workday or SuccessFactors) to replicate employee master data, user accounts, organizational
hierarchies, or approver workflows for ERP cost centers or purchase orders. Technical enablement,
employee replication interfaces, user provisioning, or scope item 1FD (Employee Integration - SAP
S/4HANA Enablement) are technical integration conduits, NOT implementations of Human Resources.

**Scope.** HR Administration handles employee master data maintenance, organizational management,
personnel administration, employment events (hiring, transfers, promotions, terminations), position
management and reporting lines, time and attendance basics, employee self-service, personnel files,
and labour-regulation record keeping - the backbone for payroll, benefits and talent processes.
Applies ONLY when the client explicitly procures or implements a dedicated core SAP HR, HCM, or
Payroll solution.

## IT Management (sensitive)

**In one line.** Administration and Usability: system configuration, user management, application
administration and usability enhancements.

**Classify here ONLY when it primarily concerns** Administration and Usability: dedicated
implementation of SAP Cloud ALM, SAP Solution Manager, or specialized IT Service Management (ITSM)
software explicitly procured as functional scope. CRITICAL BOUNDARY: do NOT classify here routine
Basis system administration, user roles and authorizations, Segregation of Duties (SoD), Single
Sign-On (SSO), background batch jobs, printer/spool setup, system monitoring, or technical
operations. In SAP RFP bidding, Basis, security administration, and user management are technical
architecture workstreams, NOT functional Best Practice modules.

**Scope.** Administration and Usability centres on configuring, securing, and optimizing the
technical environment of enterprise applications: user account setup, role and authorization
management, access control, personalization and navigation, performance monitoring, troubleshooting
and change deployment.

## Manufacturing

**In one line.** Manufacturing Operations, Manufacturing Options, Production Engineering, Production
Planning and Quality Management - shop floor execution, production scheduling, engineering and
quality control.

**Classify here when it primarily concerns** Manufacturing Operations: make-to-order production,
semifinished-goods planning and assembly, production operations and manufacturing execution.
Manufacturing Options: Kanban replenishment, external procurement for production supply,
just-in-time supply and in-house replenishment. Production Engineering: manufacturing BOM changes,
mass BOM changes, production structures and engineering-to-production handover. Production Planning:
demand-driven buffer levels, replenishment planning and execution, production capacity evaluation,
MRP, planned orders, production scheduling and PPDS. Quality Management: quality management in
discrete manufacturing, procurement and sales, inspection, quality control, quality notifications
and defects. Use this LOB when the requested capability primarily plans, executes, controls or
improves production, manufacturing resources, production engineering or production quality. PP, QM,
production planning, shop-floor execution, manufacturing BOM and PPDS belong here when the business
task is manufacturing-focused rather than procurement, logistics or product engineering.

**Scope.** Manufacturing Operations handles real-time execution of production orders, resource
allocation and shop floor reporting; Manufacturing Options addresses discrete, process or repetitive
production approaches; Production Engineering defines bills of materials, routings and work
instructions; Production Planning manages scheduling, capacity planning and material requirements;
Quality Management covers inspections, quality checks and defect tracking.

## R&D/Engineering (sensitive)

**In one line.** Product Compliance, Product Engineering and Product Lifecycle Management.

**Classify here ONLY when it primarily concerns** Product Compliance and PLM: dedicated SAP Product
Compliance (chemical compliance approval, dangerous goods management, safety data sheets, RoHS/REACH
compliance in the value chain) or dedicated SAP Product Lifecycle Management (PLM recipe development,
formulation management). CRITICAL BOUNDARY: do NOT classify here general environmental, safety, or
hazardous material handling in warehousing/transport (Supply Chain / TM / EWM), safety data sheet
(SDS) storage or supplier compliance certificates in purchasing (Sourcing and Procurement), or
standard manufacturing BOMs/routings (Manufacturing). General regulatory, legal, IT, or financial
compliance belongs under Finance. Scope items such as 3FC, 31H, 31G, 31J, 3G8, 3VR, 3VQ, 5OJ (Assess
Dangerous Goods, Manage Safety Data Sheets, Chemical Compliance Approval) belong to Product
Compliance; do NOT qualify R&D/Engineering for operational logistics, purchasing, or manufacturing
compliance notes. Qualify ONLY when the client explicitly procures a dedicated enterprise PLM/recipe
development platform or a dedicated SAP Product Compliance software suite.

**Scope.** Product Compliance manages regulatory, safety and environmental conformity of products
(certifications, hazardous substance tracking, compliance documentation); Product Engineering covers
technical design, specifications, engineering change management and product structures; Product
Lifecycle Management oversees a product from ideation through production, launch and phase-out with
version control and change traceability.

## Sales

**In one line.** Order and Contract Management and Solution Business Management - the sales cycle
from quoting through order fulfilment and contract management.

**Classify here when it primarily concerns** Order and Contract Management: sales rebate processing,
sales orders, customer orders, quotations, contracts, pricing, billing, delivery, returns, customer
agreements, order fulfillment, sales reporting and SAP Fiori analytical apps for sales. Solution
Business Management: solution quotation, solution quotation management, SAP CPQ,
configure-price-quote, complex solution selling, customer-specific commercial proposals, solution
contracts and integrated offerings. Use this LOB when the primary business purpose is selling,
contracting, quoting, ordering, pricing, delivering, billing or commercially managing customers.
Customer order-to-cash activities belong here even when they generate Finance postings. Procurement
contracts and supplier purchasing contracts belong to Sourcing and Procurement, while service
contracts primarily governing service delivery belong to Service. Routine customer AR invoicing alone
is Finance (FI-AR).

**Scope.** Order and Contract Management covers creating, processing and tracking sales orders and
administering customer contracts (terms, pricing, delivery commitments, renewals, amendments);
Solution Business Management covers selling bundled product-and-service solutions with
solution-specific pricing, project-based delivery and milestone billing.

## Service

**In one line.** Service Master Data & Agreement Management, Service Operations & Processes and
Service Parts Management - after-sales service delivery.

**Classify here when it primarily concerns** Service Master Data & Agreement Management: service
contract management, service monitoring and analytics, warranties, service agreements, installed
base, entitlements and service master data. Service Operations & Processes: interaction center with
service request management, service quotation and order management, recurring services, customer
service requests, cases, field service, service execution, technician scheduling, repair and
after-sales processes. Service Parts Management: service parts logistics, service-parts procurement,
parts availability, planning, inventory and distribution. Use this LOB when the business purpose is
delivering, managing or supporting customer service after or alongside a sale - service requests,
service orders, warranties, technicians, service agreements or service parts specifically for
service operations, rather than general sales orders, general inventory, manufacturing or
procurement. Vendor support desks, ticketing SLAs and hypercare are never Service.

**Scope.** Service contracts, warranties and entitlements; ticket management, field service
dispatching, technician scheduling and resolution tracking; spare parts planning, availability and
fulfilment for repairs.

## Solutions for Specific Industries

**In one line.** Automotive and Oil and Gas industry-specific processes.

**Classify here when it primarily concerns** Automotive: digital vehicle and automotive-specific
business processes, vehicle lifecycle, vehicle data and industry-specific automotive operations. Oil
and Gas: field logistics planning and execution, field logistics supplier items, direct procurement
for field operations, containers and voyages, oil and gas production, hydrocarbon operations and
revenue accounting for oil and gas production. Use this LOB when the requirement is explicitly a
vertical-industry solution or industry-specific business process not adequately described by the
generic SAP LOBs. Automotive-specific vehicle capabilities belong here even if they touch Sales,
Manufacturing or Supply Chain; oil-and-gas-specific field logistics and revenue processes belong here
even if generic logistics or Finance concepts are involved. Do not use this LOB merely because the
client operates in an industry; the requested SAP capability itself must be industry-specific.

**Scope.** Automotive covers vehicle management, dealer networks, parts logistics and automotive
manufacturing / supply chain specifics; Oil and Gas covers upstream, midstream and downstream needs,
asset-heavy infrastructure, energy regulation and specialised resource logistics.

## Sourcing and Procurement

**In one line.** Central Procurement, Invoice Management, Operational Procurement, Procurement
Analytics, Sourcing and Contract Management and Supplier Management - the procure-to-pay cycle.

**Classify here when it primarily concerns** Central Procurement: central requisitioning, central
purchase contracts and central purchasing. Invoice Management: supplier invoices, invoice
verification, invoice processing and procurement invoice exceptions. Operational Procurement:
purchase requisitions, purchase orders, guided buying, external suppliers, service procurement,
subcontracting and day-to-day purchasing. Procurement Analytics: real-time procurement reporting,
monitoring, purchase-order visibility and procurement-spend analytics. Sourcing and Contract
Management: request for price, RFQs, strategic sourcing, enterprise contract management, contract
assembly and supplier quotation processes. Supplier Management: supplier activity management,
supplier classification and segmentation, delivery-date prediction, supplier evaluation, performance
and collaboration. Use this LOB when the requirement is about buying, sourcing, supplier
relationships, procurement contracts, requisitioning or supplier invoices. SAP Ariba belongs here when
its purpose is sourcing, buying, contracting, supplier collaboration or procurement planning.

**Scope.** Coordinated purchasing across units, invoice verification and matching, requisitions,
purchase orders and goods receipt, spend analytics, strategic sourcing and contract lifecycle,
supplier onboarding, qualification and performance.

## Supply Chain

**In one line.** Advanced Order Promising, Advanced Transportation, Advanced Warehousing, Delivery and
Transportation, Inventory, Logistics Cross Topics, Order Promising, Service Parts Planning and
Warehousing.

**Classify here when it primarily concerns** Advanced Order Promising: advanced available-to-promise
and product availability confirmation. Advanced Transportation: planning external transportation
requirements, freight planning and transportation execution. Advanced Warehousing: advanced warehouse
outbound processing and warehouse execution. Delivery and Transportation: manual transportation
planning, transportation execution and freight settlement. Inventory: physical inventory, cycle
counting, stock management and inventory availability. Logistics Cross Topics: handling-unit
management and cross-logistics processes. Order Promising: available-to-promise processing and
fulfillment commitments. Service Parts Distribution: extended service-parts planning, demand planning
and service-parts distribution. Warehousing: basic warehouse inbound processing from suppliers,
initial stock upload, physical inventory, warehouse operations and replenishment. Use this LOB for
logistics, inventory, warehousing, transportation, delivery, ATP or supply-chain planning. IBP
belongs here when its purpose is integrated demand or supply planning rather than Finance or
Manufacturing (the rulebook routes SAP IBP as a non-catalogue tool). Dangerous-goods shipping and
warehouse hazardous handling belong here, not R&D/Engineering.

**Scope.** Delivery-date commitments based on inventory and capacity, shipment planning and tracking,
storage optimization, picking and packing, stock levels and replenishment, handling units, and
service-parts forecasting and positioning.
