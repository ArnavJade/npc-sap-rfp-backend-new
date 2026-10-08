# Finance Business Areas

When a capability belongs to the Finance LOB, classify it into one or more of these Business Areas,
using only the exact strings below. Several areas sound similar but have deliberately narrow
boundaries - read them carefully.

| Business Area | Precise scope |
|---|---|
| Accounting and Financial Close | Core, single-entity accounting: GL journal entries, AP/AR subledger accounting, period/month-end close, fixed asset accounting, standard lease accounting (e.g. ASC 842 / IFRS 16 at the entity level), bank reconciliation. |
| Advanced Accounting and Financial Close | Multi-entity / GROUP-level extensions only: group consolidation, intercompany eliminations, currency translation for statutory/group reporting, central finance, corporate group reporting under IFRS/US GAAP. Do NOT use this for single-entity close activities - those belong to Accounting and Financial Close instead. |
| Advanced Financial Operations | RECEIVABLES RISK AND RECOVERY. In the SAP BP catalogue this area is exactly credit, collections and disputes - Basic Credit Management, Advanced Credit Management, and Collections and Dispute Management. Assign it whenever the capability asks for: customer credit limits, credit scoring/segments/credit checks, credit exposure or blocked sales orders on credit; collections strategies, collection worklists, promise-to-pay, dunning as a collections process; or customer disputes, deductions, claims and their resolution workflow. AI/ML/predictive variants of these same processes (predictive collections, intelligent cash application, AI credit scoring) also belong here - but the AI angle is NOT required, and its absence is never a reason to exclude this area. Plain AP/AR posting, invoice processing, three-way matching and payment runs are NOT this area - they are Financial Operations. |
| Billing and Revenue Innovation Management | Subscription billing, usage/consumption-based metering, convergent invoicing, and revenue recognition (IFRS 15/ASC 606) WHEN tied to billing/subscription/usage contracts. Revenue recognition mentioned here should NOT also trigger Advanced Accounting and Financial Close unless group consolidation is explicitly involved. |
| Cost Management and Profitability Analysis | Product/service costing, overhead allocation, standard costing and variance analysis, profitability analysis by segment/customer/product. |
| Enterprise Risk and Compliance | STRICT REQUIREMENT: assign ONLY when the capability explicitly requests implementing or procuring a dedicated Enterprise Risk Management (ERM) system, standalone SAP GRC (such as SAP Process Control, SAP Risk Management, SAP Audit Management), or Global Trade Services (GTS embargo/sanctions screening). ABSOLUTE PROHIBITION: NEVER assign it for (1) general statutory, legal, fiscal, or regulatory compliance; (2) local tax regulations, VAT, e-invoicing, or tax filing; (3) IFRS, US GAAP, or local GAAP accounting standards; (4) routine audit trails, change logs, document history, or financial audit readiness; (5) user authorizations, Segregation of Duties (SoD), role-based security, or approval workflows. Items (1)-(5) belong strictly to Accounting and Financial Close or Financial Operations. |
| Environmental Footprint Management | Carbon accounting, emissions tracking (Scope 1/2/3), sustainability KPI/ESG reporting. Use this even if the capability mentions "financial statements" or "compliance" in passing - the core subject is environmental/emissions data, not core accounting or governance. |
| Financial Operations | AP/AR TRANSACTIONAL PROCESSING: supplier invoice processing and verification, three-way matching, automatic payment runs, outgoing/incoming payment processing, cash application and clearing, customer billing document posting. Do NOT use this for credit limits/credit checks, collections strategies or dispute/deduction handling - those are Advanced Financial Operations, which is where the catalogue puts credit, collections and disputes. The presence or absence of AI/ML does not decide between these two areas; the PROCESS does. |
| Real Estate Management | Lease contracts, rent payments, facility/space management for a corporate real estate portfolio. |
| Treasury Management | MANDATORY FOR CASH MANAGEMENT: assign it whenever the capability mentions Cash Management, SAP Cash Management, cash positioning, cash operations, cash flow forecasting, liquidity management, bank account management (BAM), electronic bank statements (EBS), bank communication management (BCM), payment factory, in-house cash / cash pooling, debt/investment management, or FX/hedging. In the SAP BP catalogue, ALL cash management and liquidity operations reside strictly under Treasury Management. |
| Working Capital Management | ONLY for capabilities whose PRIMARY, explicit ask is working-capital measurement or optimization itself - e.g. DSO/DPO/DIO metrics, cash conversion cycle, working-capital analytics/dashboards. Do NOT select this just because a capability involves AP, AR, cash, or treasury processes that happen to affect working capital indirectly. |

## Rules

- Return the smallest set of Business Areas (1-2, rarely 3) that accurately captures the
  capability's PRIMARY, explicit intent. Do not over-assign.
- Do NOT add an area just because it is tangentially related, indirectly impacted, or "could
  support" that area. Only assign an area if the capability's core, stated ask falls within that
  area's definition above.
- Accounting and Financial Close and Advanced Accounting and Financial Close are mutually exclusive
  in the common case: the base one for single-entity activity, the advanced one for multi-entity /
  group activity. Use both only if the RFP explicitly describes both a single-entity process AND a
  separate group-level process.
- Working Capital Management requires an explicit working-capital metric or optimization ask (DSO,
  DPO, DIO, cash conversion cycle, working-capital analytics). Never add it just because AP, AR,
  cash, or treasury is mentioned.
- Enterprise Risk and Compliance - strict prohibition: do NOT assign it unless the evidence
  explicitly names dedicated enterprise risk management software, standalone SAP GRC (SAP Process
  Control, SAP Risk Management, SAP Audit Management), or Global Trade Services (GTS). If there is no
  explicit mention of dedicated GRC or enterprise risk management software, never assign it.
- Treasury Management - cash management mandate: if the capability mentions Cash Management, cash
  positioning, cash forecasting, bank accounts (BAM), electronic bank statements (EBS), bank
  communication (BCM), liquidity management, cash pooling, or treasury operations, you MUST include
  Treasury Management. Never map cash management to Financial Operations or Working Capital
  Management, and never leave its Business Area empty.
- Advanced Financial Operations - credit / collections / disputes mandate: if the capability
  mentions credit limits, credit checks, credit exposure, credit scoring or credit-blocked orders;
  collections strategy, collection worklists or promise-to-pay; or customer disputes, deductions or
  claims resolution, you MUST include Advanced Financial Operations. Do not withhold it because no
  AI/ML capability was mentioned, and do not route these processes to Financial Operations instead -
  that area is for invoice and payment PROCESSING only. Both may apply together when a capability
  genuinely asks for both.
- Only use Business Areas from the list above, verbatim. Never invent new ones.
- If nothing survives the country's availability, fall back to the area you would otherwise keep,
  else Accounting and Financial Close.

## Worked examples

| Capability / evidence | Areas | Why |
|---|---|---|
| "Maintain customer credit limits and automatically block sales orders that exceed the approved credit exposure for that customer" | Advanced Financial Operations | Credit limits, credit checks and credit-based order blocking are Credit Management, which the catalogue files under Advanced Financial Operations. No AI is mentioned and none is needed. |
| "Provide collection worklists for the receivables team and track customer disputes and deductions through to resolution" | Advanced Financial Operations | Collections and Dispute Management is Advanced Financial Operations, not Financial Operations - the latter covers invoice and payment PROCESSING, not receivables risk and recovery. |
| "Automate cash receipt posting and customer statement generation for the shared services accounts receivable team" | Financial Operations | Plain AR processing with no AI/ML angle, and no explicit DSO/working-capital metric is requested, so Working Capital Management is NOT added just because it touches cash. |
| "The system should consolidate financial results from 15 subsidiaries with automated intercompany elimination and multi-GAAP reporting" | Advanced Accounting and Financial Close | Multi-entity consolidation is the advanced area, not the base one (which is for single-entity close activities). |
| "Post monthly depreciation runs and reconcile the fixed asset subledger to the general ledger" | Accounting and Financial Close | Single-entity fixed asset / GL close activity stays in the base area, not the advanced variant. |
| "Generate usage-based invoices for cloud consumption and recognize revenue over the subscription term per IFRS 15" | Billing and Revenue Innovation Management | Revenue recognition tied to a subscription/usage billing contract stays here alone - it does not also trigger Advanced Accounting and Financial Close unless group consolidation is explicitly mentioned. |
| "Calculate the company's Scope 1 and Scope 2 emissions and disclose them alongside quarterly financial statements" | Environmental Footprint Management | Even though "financial statements" is mentioned, the core ask is emissions tracking. |
| "Forecast daily cash positions across regional bank accounts and automate intercompany cash pooling" | Treasury Management | Centralized cash/liquidity forecasting and pooling is Treasury Management. Working Capital Management is not added just because cash is involved - there is no DSO/DPO/cash-conversion-cycle ask. |
| "Implement SAP Cash Management module for daily cash positioning, cash flow forecasting, bank account management, and automated bank reconciliation" | Treasury Management | Dedicated Cash Management (cash positioning, bank account management, liquidity forecasting) is Treasury Management under Finance. |
| "Provide a dashboard tracking days sales outstanding, days payable outstanding and the cash conversion cycle across business units" | Working Capital Management | The primary and explicit ask IS the working-capital metrics themselves. |

## Keyword guardrails (always applied, on the capability wording plus its evidence)

- Enterprise Risk and Compliance is removed unless the text contains one of: `grc`, `process
  control`, `risk management`, `audit management`, `global trade services`, `gts`.
- Treasury Management is added when the text contains one of: `cash management`, `cash
  positioning`, `cash flow forecast`, `cash forecast`, `liquidity management`, `bank account
  management`, `in-house cash`, `electronic bank statement`.
- Advanced Financial Operations is added when the text contains one of: `credit limit`, `credit
  check`, `credit exposure`, `credit control`, `credit scoring`, `credit segment`, `credit
  management`, `creditworthiness`, `collection strategy`, `collections strategy`, `collection
  worklist`, `collections management`, `promise to pay`, `promise-to-pay`, `dispute management`,
  `dispute case`, `deduction management`. The catalogue files exactly three scope items here - Basic
  Credit Management, Advanced Credit Management, Collections and Dispute Management - so these
  keywords are the area's own scope, not a heuristic.

## Finance core

Whenever the Finance LOB is in scope for a country, the Finance core Business Areas set in policy
(`catalogue.finance_core_business_areas` - currently Accounting and Financial Close, Advanced
Financial Operations, Cost Management and Profitability Analysis) must always be represented for
that country: the model-only mapping consistently omitted them. Add every country-available scope
item of those areas that is not already selected (so effort is never double-counted), with
`mapping_basis: "finance_core"`.
