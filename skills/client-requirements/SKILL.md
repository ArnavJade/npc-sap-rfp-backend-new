---
name: client-requirements
description: >-
  How the requirements-analyst reads the RFP for what the client wants the RESPONSE to contain - the
  sections, breakdowns and plans it explicitly asks bidders to provide, the per-section RFP wording
  each outline section should answer, which internal estimation detail the client asked to see
  (disclosure profile: scope-item detail, effort, resource allocation, resource location,
  commercials), and how presales free-text instructions become per-section briefs. Writes the
  response_requirements ledger section. Use in call 2 before any section is drafted.
metadata:
  owner: "presales"
  version: "0.1.0"
  ledger_sections: "response_requirements"
---

# Client requirements (requirements-analyst, call 2)

You read the RFP for its RESPONSE instructions, not for scope. Scope is already in the reviewed
ledger. You write one object with `ledger_write_response_requirements`:

```
{requirements: [...], section_excerpts: [...], disclosure: {...}, instructions_briefs: {...}}
```

## Where to look
Start with `/rfp/index.md`. Response instructions usually sit in sections titled "Instructions to
bidders", "Proposal format / structure / content", "Response requirements", "Technical proposal",
"Commercial proposal", "Evaluation criteria", "Submission", and in questionnaires or annexures
("Bidder shall provide ..."). grep for: `shall provide`, `should include`, `bidder must`,
`proposal must`, `response should`, `describe`, `provide details`, `breakdown`, `man-days`,
`man days`, `effort`, `rate card`, `price`, `commercial`, `onsite`, `offshore`, `resource`,
`team structure`, `CV`, `evaluation`. Read the pages around each hit with `read_section`.

## requirements - what the response must contain
One entry per distinct ask: `{title, intent, kind, maps_to_section_id, placement_after_section_id,
group_by, evidence}`.
- `title`: short, the client's wording ("Indicative effort by phase").
- `intent`: one or two sentences: what the client wants to read and why, specific enough for a
  writer to answer it and a reviewer to check depth.
- `kind`:
  - `narrative`: a topic to describe (approach, method, team, warranty, local presence ...);
  - `indicative_breakdown`: effort split by a dimension. Set `group_by` to `module`, `wave`,
    `country`, `role` or `workstream` (phase / workstream splits -> `workstream`; per resource
    type -> `role`);
  - `phase_plan`: a phase / wave plan or delivery schedule.
- `maps_to_section_id`: the standard outline section that already covers it (the orchestrator gives
  you the outline: id - title). Map generously for narrative asks: "describe your testing approach"
  -> 4.8; "project governance" -> 5.1; "team structure" -> 4.4.
- `placement_after_section_id`: only for an ask no section covers: the section it should follow.
- `evidence`: the verbatim sentence(s) with file and page.
Do not record generic boilerplate (page limits, fonts, submission addresses, signatures) or scope
requirements ("the system shall support three-way match") - those are not response content.
Merge duplicates (the same ask in the instructions and the evaluation criteria is one requirement).

## section_excerpts - the client's words per section
For outline sections whose subject the RFP describes in its own words, record up to 3 excerpts per
section: `{section_id, excerpt, evidence}`. An excerpt is VERBATIM RFP text of at most 400
characters - the tool rejects anything it cannot find in the RFP. Prefer sentences that state an
objective, a constraint or an expectation ("The solution must support local VAT reporting in all
GCC countries"). Typical targets: 1.1 objectives, 3.x scope, 4.1 approach, 4.3 timeline, 4.7 data
migration, 4.8 testing, 4.9 training, 4.10 change management, 5.x governance, 6.x commercials.

## disclosure - what estimation detail the client asked to see
Each category is `false` (withheld - stays in the Excel workbook only) unless the RFP EXPLICITLY asks
bidders to provide it. When you set `true`, put the RFP wording that asks for it in
`evidence[<category>]`. Set `source: "rfp"`.
| Category | Set true only when the RFP asks for ... |
|---|---|
| `scope_item_detail` | the list of SAP Best Practice scope items / BP IDs, or a process-level scope list |
| `effort_detail` | effort figures: man-days, person-days, effort per module / phase / wave, total effort |
| `resource_allocation` | FTE, man-months, a resource loading plan, team size per phase or month |
| `resource_location` | the onsite / offshore (onshore / nearshore) split or location per role |
| `commercial_detail` | prices, rates, a rate card, fees, cost breakdown, commercial proposal content |
A request for a "commercial proposal" or "price schedule" counts for `commercial_detail`; a request
for "team structure" alone does NOT count for `resource_allocation` (roles, not FTE). When the RFP
is silent on a category, leave it false - unrequested commercial or staffing detail in a response
is worse than its absence.

## instructions_briefs - presales instructions per section
The orchestrator passes the presales free text verbatim (or "none"). Split it into per-section briefs
`{section_id: "<depth>: <emphasis>"}` where depth is `deep`, `normal` or `brief` and emphasis is the
instruction's substance for that section ("deep: stress the Riyadh delivery centre and Arabic
training material" for 4.9). Map each instruction to the most specific section(s); an instruction
about the whole document ("keep it concise") becomes `brief: ...` for the long chapters only. Asks
that fit no section go to the key `additional`, verbatim. No instructions -> `{}`.

## Finish
Write the whole object once (rewrite it whole to correct it). Reply: number of requirements (mapped
/ new sections), excerpts, disclosure categories set true (with the RFP words), sections with
briefs, and anything ambiguous.
