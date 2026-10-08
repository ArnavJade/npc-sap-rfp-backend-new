# Integrations write-up (3.3 Technical Scope)

Load `bid_facts('integrations')` and `bid_facts('tech_dev')`. The renderer does not append an
integrations table to 3.3, so place `{{table:integrations}}` on its own line when the bid has any
third-party integration; place `{{table:tech_dev}}` when RICEFW / Fiori objects exist.

Ported from the old integrations prompt: for EACH third-party system and non-catalogue SAP tool, one
or two sentences on the SOLUTION / IMPLEMENTATION APPROACH, deduced from the client's own description
(`functionality`, direction, data exchanged, middleware): how the integration will be delivered - the
interface direction, the master / transactional data objects exchanged, and the technology (SAP
Integration Suite / CPI, BTP, APIs, IDoc / RFC, batch vs real-time) where the description supports it.
Name each item explicitly; group naturally (SAP tools vs third-party integrations) if it reads better.
Do not invent specifics beyond the descriptions; no effort or cost; no filler - if an item's
description is thin, keep its sentence short.

Structure (use `###` sub-headings only if more than one block applies):
1. **Integration landscape** - one or two sentences on how S/4HANA connects to the client's
   systems: the middleware the ledger names (e.g. SAP Integration Suite / CPI) or, when none is
   named, "an integration layer to be confirmed during Explore". Never invent a middleware.
2. **Third-party systems and non-catalogue SAP tools** - one or two approach sentences each, as
   above, keeping the client's spelling of each system; the integrations table lists them.
3. **Project-management systems** (Primavera, MS Project, Jira ...) - mention that they are
   integrated with the project-systems scope only when the ledger lists them.
4. **Custom development** - RICEFW objects and custom Fiori apps by type as the RFP states them;
   counts only as `bid_facts` shows them; no hours or effort.
5. **Assumptions** - interface specifications, test systems and third-party vendor support are the
   client's responsibility unless the RFP says otherwise (one sentence; detail belongs in 3.4).

Do not describe protocols, frequencies or data objects the ledger does not record.
