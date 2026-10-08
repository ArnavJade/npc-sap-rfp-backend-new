# Integrations write-up (3.3 Technical Scope)

Load `bid_facts('integrations')` and `bid_facts('tech_dev')`. The renderer does not append an
integrations table to 3.3, so place `{{table:integrations}}` on its own line when the bid has any
third-party integration; place `{{table:tech_dev}}` when RICEFW / Fiori objects exist.

Structure (use `###` sub-headings only if more than one block applies):
1. **Integration landscape** - one or two sentences on how S/4HANA connects to the client's
   systems: the middleware the ledger names (e.g. SAP Integration Suite / CPI) or, when none is
   named, "an integration layer to be confirmed during Explore". Never invent a middleware.
2. **Third-party systems** - name each system with its purpose and direction in prose only when
   there are five or fewer; otherwise refer to the table. Group by business area (HR, procurement,
   banking, tax, logistics) when it helps the reader. Keep the client's spelling of each system.
3. **Project-management systems** (Primavera, MS Project, Jira ...) - mention that they are
   integrated with the project-systems scope only when the ledger lists them.
4. **Custom development** - RICEFW objects and custom Fiori apps by type as the RFP states them;
   counts only as `bid_facts` shows them; no hours or effort.
5. **Assumptions** - interface specifications, test systems and third-party vendor support are the
   client's responsibility unless the RFP says otherwise (one sentence; detail belongs in 3.4).

Do not describe protocols, frequencies or data objects the ledger does not record.
