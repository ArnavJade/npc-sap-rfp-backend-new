# Client-required sections

The requirements-analyst records what the client's RFP explicitly asks the response to contain.
A requirement either maps onto a standard section (it arrives in that section's briefs) or becomes
a NEW subsection (id `<anchor>.<n>`, level 3, e.g. `6.1.1`) placed right after its anchor section. You draft new subsections
like any other section, with these additions per `kind`.

## kind: narrative
The client asks for a topic the standard outline does not cover (e.g. "describe your approach to
localisation in KSA", "warranty terms", "local partner model").
- Open with the client's ask in their own words (one short clause, quoted if verbatim).
- Answer it with substance: the mechanism, the named steps, the commitment. A restatement of the
  question is not an answer; the reviewer checks depth against the intent.
- Stay inside the facts: ledger views and the RFP. Where the bid has no fact for something the
  client asks (e.g. a named partner), describe the approach and say it will be confirmed during
  contracting - never invent.

## kind: indicative_breakdown
The client asked for a NEW breakdown (by module, wave, country, role or workstream) that the effort
and cost sections do not already give. Ported from the old indicative-breakdown prompt, with one
change: the table is now built by the renderer from the approved workbook figures, so every number in
it is approved, never derived.
- Write a 2-3 sentence professional introduction: what the breakdown shows and that it comes from the
  approved effort estimate (SAP Best Practice rate card and the reviewed scope).
- Put `{{table:indicative_breakdown:<group_by>}}` on its own line, using the section's `group_by`.
- Do not comment on individual figures, compute shares or totals, or label approved figures
  "indicative".
- If effort_detail is withheld, the renderer drops the table: describe the basis qualitatively and do
  not place the placeholder.

## kind: phase_plan
The client's RFP defined explicit phases / waves and asked for the response per phase (ported from the
old phase-plan prompt). Use the EXACT phases in the requirement's intent - do not invent, merge or
rename them. An entity, country or scope element the client names that is not clearly assigned to a
phase: name it in the intro as not yet assigned per the RFP, to be confirmed with the client during
Prepare - never invent an assignment.
- Intro: 2-3 sentences, no numbers, no figures.
- ONE clean, READABLE pipe table, at most 4-5 columns, from this set in this order (only the ones
  genuinely needed):
  1. Phase / Wave & Entities - phase name / number and the client entities or business units covered;
  2. Timeline & SAP Activate Phases - the month range (M1-M6 style, from the timeline view) and the
     SAP Activate sub-phases inside it (Prepare, Explore, Realize, Deploy, Hypercare); nothing more;
  3. Key Activities & Deliverables - a SHORT list (max 4-6 items, separated by "; ") of headline
     activities and named deliverables; no prose paragraphs;
  4. Modules & Integrations Covered - bare names only ("Finance, MM, PP, QM, SD; ZATCA, LIMS"): no
     effort, no descriptions, no parenthetical notes.
- HARD RULES: no RACI column or matrix (the RACI section has it); no Key Assumptions column (3.4 has
  them); no Entry / Exit Criteria or Quality Gate columns (governance has them); NO person-days,
  man-months, money or rates anywhere in the table or intro; every cell at most about 60 words.
- Then `{{table:wave_plan}}` on its own line for the dated wave facts. Do not place
  `{{diagram:timeline}}` - it belongs to 4.3; refer to it by name.

## The trailing "additional" section
When the orchestrator asks for an `additional` section (requirements that fit nowhere else), write
one short paragraph per requirement with a bold lead-in naming it, then the answer. Same rules.
