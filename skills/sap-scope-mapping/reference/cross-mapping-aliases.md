# SAP module cross-mapping (generated - edit the source workbook, then rerun scripts/build_assets.py)

How a client's module name resolves before any catalogue search. `cross_map_lookup` applies these rows
exactly; this guide is for reasoning about names the lookup does not match verbatim.

* **Catalogue target** - search only inside these LOB / Business Area filters.
* **Others** - an SAP tool or system with no Best Practice scope items: it goes to `non_catalogue`,
  never to `scope_items`. The label says what kind of tool it is.

| Module | Aliases | Resolves to |
|---|---|---|
| Project Systems (PS) | Project Systems, PS, Project Management | Others (SAP Module, but No Best Practises) - SAP tool/system, no catalogue scope items |
| Investor Relations Management | Investor Relations, IR | Others (General Aspect) - SAP tool/system, no catalogue scope items |
| IT Asset Disposition (ITAD) | ITAD, IT Asset Disposition | R&D/Engineering | Product Compliance [Component contains 'EHS'] |
| Hyperscale ITAD | Hyperscale ITAD | R&D/Engineering | Product Compliance [Component contains 'EHS'] |
| e-Waste Recycling | eWaste Recycling, Electronic Waste Recycling | R&D/Engineering | Product Compliance [Component contains 'EHS'] |
| Battery Recycling | Battery Recycling | R&D/Engineering | Product Compliance [Component contains 'EHS'] |
| MDS | Master Data Services | Others (EHS) - SAP tool/system, no catalogue scope items |
| SAP Analytics Cloud (SAC) | SAC, Analytics Cloud, SAP Analytic Cloud | Others (SAP Reporting Tool) - SAP tool/system, no catalogue scope items |
| SAP Solution Manager 7.2 | Solution Manager, SolMan | Others (SAP Tool) - SAP tool/system, no catalogue scope items |
| Controlling (CO) | CO, Controlling, Cost Controlling, Management Accounting | Finance | Cost Management and Profitability Analysis |
| Materials Management (MM) | MM, Materials Management, Material Management, Inventory Management | Sourcing and Procurement (whole LOB); Supply Chain | Inventory |
| Procure to Pay | Procure-to-Pay, P2P, Purchase to Pay | Sourcing and Procurement (whole LOB); Supply Chain | Inventory |
| Production Planning (PP) | PP, Production Planning, Production & Planning, Production and Planning, Manufacturing Planning, Shop Floor Control | Manufacturing | Production Planning; Manufacturing | Manufacturing Operations; Manufacturing | Manufacturing Options |
| Quality Management (QM) | QM, Quality Management, Quality Assurance, Quality Control | Manufacturing | Quality Management |
| Sales & Distribution (SD) | SD, Sales and Distribution, Sales & Distribution | Sales (whole LOB) |
| Order to Cash | Order-to-Cash, O2C, OTC | Sales (whole LOB) |
| Plant Maintenance (PM) | PM, Plant Maintenance | Asset Management | Maintenance Management |
| Warehouse Management (WM) | WM, Warehouse Management | Supply Chain | Warehousing; Supply Chain | Advanced Warehousing |
| Extended Warehouse Management (EWM) | EWM, Extended Warehouse Management | Supply Chain | Warehousing; Supply Chain [Description contains 'EWM'] |
| Product Lifecycle Management (PLM) | PLM, Product Lifecycle Management | R&D/Engineering | Product Lifecycle Management |
| Customer Service (CS) | CS, Customer Service, Field Service Management, Field Service | Service (whole LOB) |
| Revenue Accounting & Reporting (RAR) | RAR, Revenue Accounting and Reporting, Revenue Recognition | Finance [Description contains 'Revenue'] |
| Transportation Management (TM) | TM, Transportation Management, Transporation Management, Transporation | Supply Chain | Delivery and Transportation; Supply Chain | Advanced Transportation |
| Logistics Execution (LE) | LE, Logistics Execution | Supply Chain | Warehousing; Supply Chain | Transportation |
| Human Capital Management (HCM) | HCM, Human Capital Management, Human Resources, HR and Payroll, Payroll | Human Resources (whole LOB) |
| HR | Human Resources, HR | Human Resources (whole LOB) |
| SAP BTP | BTP, Business Technology Platform | Others (SAP Technical Service) - SAP tool/system, no catalogue scope items |
| Joule | SAP Joule, Joule AI | Others (SAP Technical Service) - SAP tool/system, no catalogue scope items |
| SAP MDG | MDG, Master Data Governance, Master Data Management | Others (SAP other tool) - SAP tool/system, no catalogue scope items |
| SAP GRC | GRC, Governance Risk and Compliance | Others (SAP other tool) - SAP tool/system, no catalogue scope items |
| SAP Signavio | Signavio, Process Mining, Process Insights | Others (SAP Process tool) - SAP tool/system, no catalogue scope items |
| SAP Ariba | Ariba | Sourcing and Procurement [Description contains 'Ariba'] |
| SAP Concur | Concur, Travel and Expense, Expense Management | Others (Unclassified) - SAP tool/system, no catalogue scope items |
| SAP SuccessFactors | SuccessFactors, SF, Employee Central | Others (Unclassified) - SAP tool/system, no catalogue scope items |
| SAP IBP | IBP, Integrated Business Planning | Others (Unclassified) - SAP tool/system, no catalogue scope items |
| SAP DMS | DMS, Document Management System | Others (Unclassified) - SAP tool/system, no catalogue scope items |
| SAP EHS Management | EHS, Environment Health and Safety | R&D/Engineering | Product Compliance [Component contains 'EHS'] |
| SAP Integration Suite | Integration Suite, PI/PO, SAP PI, SAP PO | Others (SAP Integration tool) - SAP tool/system, no catalogue scope items |
| SAP Logistics Business Network | LBN, Logistics Business Network | (all LOBs) [Description contains 'business network'] |
| Transportation Planning & Execution | Transportation Planning and Execution, TP&E | Supply Chain | Transportation |
| Transportation Charge Management | Freight Settlement, Freight Audit | Supply Chain | Transportation |
| Cash Management | Cash and Liquidity Management, Cash Flow Management, Liquidity Management | Finance | Treasury Management [Description contains 'Cash'] |
| Environment Management | Environmental Management | R&D/Engineering | Product Compliance [Component contains 'EHS'] |
| Health & Safety Management | Health and Safety Management, EHS Health and Safety | R&D/Engineering | Product Compliance [Component contains 'EHS'] |
| Incident Management | EHS Incident Management | R&D/Engineering | Product Compliance [Component contains 'EHS'] |
| Management of Change | MOC | R&D/Engineering | Product Compliance [Component contains 'EHS'] |
| Digital Access | SAP Digital Access | Others (Unclassified) - SAP tool/system, no catalogue scope items |
| Work Clearance Management | WCM | Others (Unclassified) - SAP tool/system, no catalogue scope items |
| Yard Logistics | Yard Management | Supply Chain | Warehousing; Supply Chain [Description contains 'EWM']; Supply Chain | Transportation |
| Work Zone | SAP Work Zone | Others (SAP Technical UI Tool) - SAP tool/system, no catalogue scope items |
| CX | SAP Customer Experience, Customer Experience | Others (SAP System) - SAP tool/system, no catalogue scope items |
| EC | Employee Central | Others (SAP System) - SAP tool/system, no catalogue scope items |
| ECP | Employee Central Payroll | Others (System Name. Not consider for BP) - SAP tool/system, no catalogue scope items |
| SAP S/4 HANA | S/4HANA, S4, S/4 | Others (SAP System) - SAP tool/system, no catalogue scope items |
| SAP Fiori | Fiori | Others (SAP Technical UI Tool) - SAP tool/system, no catalogue scope items |
| Group Reporting | Consolidation, Financial Consolidation | Finance [Description contains 'Group Reporting'] |
| Leasing | Lease Accounting, Lease Management | Finance [Description contains 'Lease'] |
| Finance | Finance & Controlling, FICO, Financial Management, Financial Accounting | Finance | Advanced Financial Operations; Finance | Accounting and Financial Close; Finance | Cost Management and Profitability Analysis |
| Real Estate Management | RE Management, Flexible Real Estate Management, REFX | Finance | Real Estate Management |
| Group Reporting/Consolidation | - | Finance | Advanced Accounting and Financial Close |
