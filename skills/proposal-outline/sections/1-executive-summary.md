# Executive Summary (1.1, 1.2, 1.3)

Grounding for every 1.x section: **the client's ACTUAL requirements from their RFP**, which you
echo or paraphrase so the client feels heard, grouped by area. `bid_facts('scope')` shows the
client's own requirement wording per LOB, as quotes. Use them. Do not use the catalogue
descriptions as if they were the client's words. The requirements-analyst does not extract
excerpts for chapter 1, because this mechanism already covers it.

Engagement type comes from `profile`. Describe it in these words, not as a bare label:
- greenfield: a net-new SAP implementation;
- brownfield: an upgrade or migration against an existing SAP or legacy landscape;
- bluefield: a selective, phased re-implementation alongside a retained legacy landscape.

## 1.1 Our Understanding of {client_name} Objectives
- Open with the client's objectives in their own wording. Use the profile summary and the scope
  quotes; quote short phrases exactly, in double quotation marks.
- Show you understand why they are doing this now and what success looks like for them. Use only
  what the RFP says, and invent no drivers.
- Do not restate the module or scope-item list. The scope chapter tabulates it.

## 1.2 YASH Proposed Solution
- Describe the shape of the answer: the SAP solution, the business areas it covers, the countries,
  and how delivery is phased (waves and sequencing from `timeline`).
- Keep scale qualitative: "a multi-wave programme", "phased by country", "a single template
  rolled out". Give **no effort, cost or durations**. Durations belong to the timeline section,
  and effort and cost to chapter 6.
- Name only the modules, processes and integrations that matter to the client's stated
  objectives. Do not list everything in scope.

## 1.3 Why YASH?
- Every YASH fact must come from `reference/yash-profile.md` or `reference/service-catalog.md` in
  the proposal-writing skill. Make it specific by tying those statements to this bid: the client's
  business areas, countries, integrations and staffing model (`team` view: roles and how they are
  engaged).
- Never claim delivery experience, references, local presence or delivery centres that the
  profile does not state. Earlier generated responses wrote "we have delivered this repeatedly
  across your target geographies" and "regional delivery centres in each of your target
  geographies". Those claims were invented; do not write them.
- Mention the onsite/offshore model only when `resource_location` is not withheld.
