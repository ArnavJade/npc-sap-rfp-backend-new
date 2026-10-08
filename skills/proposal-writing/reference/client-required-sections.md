# Client-required sections

The requirements-analyst records what the client's RFP explicitly asks the response to contain.
A requirement either maps onto a standard section (it arrives in that section's briefs) or becomes
a NEW subsection (id `R<n>`, level 3) placed after its anchor section. You draft new subsections
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
The client asks for an effort split (by module, wave, country, role or workstream).
- 2-4 sentences: what the breakdown shows, the basis (SAP Best Practice rate card, YASH estimation
  model, the reviewed scope) and that it is indicative pending fit-to-standard.
- Put `{{table:indicative_breakdown:<group_by>}}` on its own line, using the section's `group_by`.
- Do not comment on individual figures; do not compute shares or totals.
- If effort_detail is withheld, the table is dropped by the renderer: write the basis
  qualitatively and do not place the placeholder.

## kind: phase_plan
The client asks for a phase / wave plan or a delivery schedule.
- Describe the sequencing and what each wave delivers (countries, scope), using `timeline` facts.
- Put `{{table:wave_plan}}` on its own line. Durations come from the table; you may type a wave's
  stated duration only as `figures.bare_numbers_allowed` lists it.
- Do not place `{{diagram:timeline}}` - it belongs to 4.3; refer to it ("as shown in the
  implementation timeline").

## The trailing "additional" section
When the orchestrator asks for an `additional` section (requirements that fit nowhere else), write
one short paragraph per requirement with a bold lead-in naming it, then the answer. Same rules.
