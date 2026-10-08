---
name: client-requirements
description: >-
  How the requirements-analyst reads a client's RFP for what the vendor's WRITTEN PROPOSAL must contain
  (not the SAP scope) - structural requirements mapped onto the standard outline or placed as new
  sections (narrative, indicative breakdown, phase plan), verbatim per-section RFP excerpts, the
  disclosure profile (which estimation detail the client explicitly asked to see), and per-section
  steering from the presales free-text instructions. Writes the response_requirements ledger section.
  Use in call 2 before any section is drafted.
metadata:
  owner: "presales"
  version: "1.0.0"
  ledger_sections: "response_requirements"
---

# Client requirements (requirements-analyst, call 2)

Ported from client_requirements_layer5.py (requirements + excerpts, disclosure, steering prompts).
You extract things for the vendor's WRITTEN PROPOSAL DOCUMENT - NOT the underlying SAP functional /
technical scope, which is already in the reviewed ledger; ignore it here. Write the whole object once
with `ledger_write_response_requirements(data={requirements, section_excerpts, disclosure,
instructions_briefs})`; rewrite it whole to correct it.

The orchestrator gives you the standard outline (id - title) and the presales instructions.

## Part 1 - requirements
Read the ENTIRE RFP end to end - annexes / appendices, tables, footnotes, terms & conditions - not
only the main narrative or an obviously titled "response requirements" section; a structural
requirement can appear anywhere. grep helps: `shall provide`, `should include`, `must contain`,
`vendor will`, `bidder`, `response`, `proposal`, `format`, `breakdown`, `matrix`, `per phase`,
`per wave`, `template`, `annex`.

Identify the things the RFP explicitly asks the response document to contain or be structured as: a
mandated response outline / table of contents, a specifically named deliverable / section / table /
matrix, or a particular presentation (a breakdown, a matrix, a per-entity / per-wave view, a dedicated
section for a concern it names). There is NO fixed checklist - extract only what this RFP's words
require. If it mandates nothing beyond what a standard proposal covers, return an empty list: that is a
correct, expected answer. Never invent a requirement, and never report an SAP functional / technical
scope item as one.

For each requirement:
- `maps_to_section_id`: the existing section that ALREADY fully satisfies it (by meaning, not title
  wording). If none genuinely does: "" and set `placement_after_section_id` to the section the new
  content should logically follow ("" if unsure).
- `kind`:
  - `indicative_breakdown` ONLY when it calls for a NEW numeric / tabular breakdown not already produced
    by the Effort Estimation / Cost Estimate sections (e.g. a per-wave or per-country staffing / effort
    table). Set `group_by`: module, wave, country, role or workstream.
  - `phase_plan` when the RFP DEFINES EXPLICIT PHASES OR WAVES ("Phase 1 / Phase 2", named waves) AND
    asks the response to address them per phase - whatever the per-phase detail (scope, timeline,
    cost, resources, countries / entities, integrations). ONE requirement; put into `intent` the EXACT
    phase names / definitions PLUS the per-phase attributes asked for (verbatim where possible). No
    phases defined -> never invent any.
  - otherwise `narrative`.
- `title`: short, in the RFP's words. `intent`: one sentence on what must be covered and why; echo the
  RFP's own clause numbers, phase / sprint names and acronyms.
- `evidence`: the RFP sentence(s), verbatim, with file and page.
Merge near-duplicates. At most 15 requirements, most important first.

## Part 2 - section_excerpts
For each EXISTING section where the RFP says something SPECIFIC and CONCRETE about that section's topic
(a named tool, a named process, a specific expectation - not just implied by a module being in scope),
record a short excerpt in the client's OWN wording, VERBATIM (the tool rejects text not found in the
RFP), max 400 characters: `{section_id, excerpt, evidence}`.
- Omit a section the RFP does not specifically address - never fabricate generic content.
- No excerpts for section 1 or its subsections (the client's wording reaches them another way); focus
  on section 2 onward.
- At most 15 excerpts, most concrete first.

## Part 3 - disclosure
The vendor's detailed estimate (scope items, person-day effort, month-by-month resource grid,
onsite / offshore split, rates and costs) is INTERNAL. A category may appear in the response ONLY if
the RFP EXPLICITLY asks the vendor to provide that kind of detail. The RFP is the only source of truth.

Method - follow it strictly. grep the RFP for the cue words (effort, man-days, person-days, man-months,
hours, FTE, estimat, resource, staffing, headcount, loading, onsite, offsite, offshore, onshore,
nearshore, location, pric, cost, fee, rate, rate card, quot, commercial, budget, lump sum, line item,
breakdown, scope item, best practice, BP, work package) and read each hit with a few lines around it.
1. Per category, find a sentence in which the CLIENT ASKS THE VENDOR to provide that detail (an
   instruction: "vendor will include ...", "provide ...", "should be incorporated as ...", "must
   contain ...", "please provide ...", "<client> expects ...", a table or template column the vendor
   must fill in).
2. Copy that sentence near-verbatim (max 200 characters) into `evidence[<category>]`. A bare heading
   ("Resource Management", "Part 2 - Pricing") is NOT evidence - use the instruction under it.
3. Set the category `true` only when you found such an instruction. The RFP describing its own
   business or processes, or merely mentioning the topic, is NOT a request. An ask counts wherever it
   appears, including when the client wants it in its own template or attachment.

Mapping (decide each category independently - one requested does not imply another):
| Category | Requested by |
|---|---|
| `effort_detail` | effort / level of effort / man-days / hours / an "estimation" per work package, line item or integration; the vendor's effort for some scope shown "as a separate line item"; a column such as "Estimation" or "Effort" the vendor must fill |
| `resource_allocation` | a resource plan, resource loading or staffing per month, phase, wave or stage; type and volume of resources per stage |
| `resource_location` | onsite / offsite / offshore / onshore / near-shore split, or the location of each resource |
| `commercial_detail` | prices, fees, rates, costs, quotes, a pricing or cost breakdown |
| `scope_item_detail` | ONLY an ask naming SAP scope items, BP IDs, Best Practice scope-item lists or a process-level (L3/L4) scope mapping; work packages, module lists or the client's process descriptions do NOT count |
Every category not requested stays `false` (the default). Set `source: "rfp"`.

## Part 4 - instructions_briefs (presales steering)
Translate the presales free-text instruction into PER-SECTION steering, only for the sections it
actually targets (by meaning, not exact title): `{section_id: "<depth>: <emphasis>"}` with depth
`deep` (more detail / length), `brief` (keep it short) or `normal`, and emphasis a short phrase
(<= 120 characters) of what to stress, or empty. Skip a section that would get `normal` with no
emphasis. Do NOT invent steering for sections the instruction does not touch. Asks that fit no section
go verbatim under the key `additional`. Empty or generic instruction -> `{}`.

## Reply
Number of requirements (mapped / new sections, by kind), excerpts, disclosure categories set true with
the RFP words, sections with briefs, anything ambiguous.
