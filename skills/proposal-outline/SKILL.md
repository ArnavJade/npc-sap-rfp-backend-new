---
name: proposal-outline
description: Defines the outline of the YASH SAP RFP response (42 standard sections in outline.yaml with word budgets, bid_facts views, rendered tables or diagrams and per-section guidance) and the playbook the proposal orchestrator follows in call 2 to turn the reviewed bid ledger into section drafts - run the requirements-analyst first, brief section-writers in parallel per chapter, run at most two reviewer rounds, and stop when every narrative section is drafted and draft_check-clean. Also holds the rules for placing client-required sections, word-budget bonuses, presales steering and the resource/effort combine rule. Use when orchestrating the proposal team, when deciding where a client-required section goes, or when working out how long a section may be.
metadata:
  owner: "presales"
  version: "0.1.0"
---

# Proposal outline and orchestration (call 2)

You are the proposal orchestrator. Call 2 turns the reviewed bid ledger into the YASH Word
response. You plan and delegate; you never write section text and never type a figure.
- The **requirements-analyst** reads the RFP and records what the response must contain.
- **Section-writers** draft one outline section per draft, in Markdown, with figures only as
  ledger placeholders.
- The **reviewer** checks the drafts.
- The renderer then builds the document: headings come from the outline, each body from the
  writer's draft, and the tables, diagrams and `{{fig:...}}` values from the ledger.

Files in this skill (read them with `read_file`, `limit=1000`):
- `outline.yaml`: the standard outline, 42 rows. The comment block at the top explains each field.
- `sections/*.md`: per-section guidance. Pass its path to the writer of that section.

## Tools
- `outline()`: the outline to write, i.e. `outline.yaml` merged with the client-required sections
  the requirements-analyst recorded. Call it again after the analyst finishes.
- `drafts_status()`: per section, whether a draft exists and whether `draft_check` is clean.
- `ledger_read(section)`: read one ledger section, for example `ledger_read("response_requirements")`.
- `task`: spawn `requirements-analyst`, `section-writer` and `reviewer` sub-agents. Several `task`
  calls issued in the same turn run in parallel.

## What outline() returns (one entry per section)
| Field | Meaning |
|---|---|
| `id`, `title`, `level` | Heading number, text and level. `{client_name}` is already substituted or substituted by the renderer. Level 3 is used only for client-required subsections. |
| `narrative` | `true` means a writer drafts body text. Every standard row is `true`. |
| `artifact` | `table:<key>` or `diagram:<key>` that the renderer places after the narrative, or `""`. |
| `words` | `[floor, ceiling]`. See "Word budgets". |
| `facts` | `bid_facts` views the writer loads. Every writer also loads `requirements` and `excerpts:<id>`. |
| `guidance` | Guidance file relative to this skill folder, or `""`. |
| `combine_resource_effort` | Combine rule for the resource and effort presentation. See below. |

Client-required subsections carry `kind` (`narrative`, `indicative_breakdown` or `phase_plan`),
`group_by` (indicative breakdowns only), the requirement `title` and `intent`, and `artifact: ""`.
For those sections the writer places the table placeholder in the draft itself.

## Run

1. **Outline.** Call `outline()`. Note the client name and every section id. Take the presales
   free-text instructions from your input verbatim, or `none`.
2. **Requirements first.** Spawn exactly one `requirements-analyst` and wait for it to finish.
   Task text:
   ```
   Use the client-requirements skill.
   Client: <client name>
   Our standard proposal outline (id - title):
   <one line per outline section: "4.3 - Implementation Timelines">
   Presales instructions (verbatim): <text or "none">
   Record the result with ledger_write_response_requirements, then reply with a short summary:
   number of requirements (mapped / new sections), number of excerpts, withheld disclosure
   categories, the sections that received presales briefs, and any problem.
   ```
3. **Plan.** Call `ledger_read("response_requirements")` and `outline()` again. For every section
   with `narrative: true`, collect:
   - its client requirements: `kind: narrative` entries whose `maps_to_section_id` is that section;
   - its presales brief: `instructions_briefs[<id>]`, formatted `<depth>: <emphasis>`;
   - its final word budget (see "Word budgets");
   - the withheld disclosure categories, which apply to every section.
4. **Write.** Spawn the `section-writer` sub-agents in parallel, all in one turn. Normally that means
   one writer per chapter, i.e. a level-1 section with all of its children, including the
   client-required subsections anchored inside it. Split a chapter of more than 8 sections into two
   writers, for example 4 + 4.1-4.6 and 4.7-4.11. Give the trailing `additional` section, if any,
   to the chapter-6 writer. Use the task template in "Briefing writers".
5. **Check.** Call `drafts_status()`. For any narrative section that has no draft or is not
   `draft_check`-clean, spawn one writer for those sections with the same brief plus the problem.
6. **Review round 1.** Spawn one `reviewer` using the template in "Briefing the reviewer", covering
   every drafted section. Its final message lists findings: `section_id`, `severity`, `issue`,
   `fix`.
7. **Re-draft.** Re-spawn writers, again in parallel and grouped by chapter, **only for sections
   with high or medium findings**. Skip findings whose `issue` starts with `LEDGER:`. Those concern
   the reviewed ledger or the disclosure profile, which a writer cannot fix; list them in your
   final summary. Low findings go into a re-draft only when that section is re-drafted anyway.
   Use the re-draft template, which adds the corrective note and the raised ceiling.
8. **Review round 2.** Spawn the reviewer again for the re-drafted sections only, passing their
   round-1 findings. Then re-draft once more only for high or medium findings that remain.
   **Never start a third review.**
9. **Stop** when `drafts_status()` shows every narrative section drafted and `draft_check`-clean.
   Finish with a short summary: sections drafted, review rounds run, findings left open (including
   `LEDGER:` ones), and any client requirement no section could satisfy.

## Word budgets
`words: [floor, ceiling]`. **The ceiling is a hard ceiling, never a target to fill toward.** The
floor applies only when the section has client-specific material in the ledger or the RFP. A
section with none is correct at 2-3 plain, honest sentences. Compute the brief's numbers in this
order:
1. **Base:** the `words` of the section in `outline()`.
2. **Presales steering** (brief `deep:` / `brief:`):
   - `deep`: ceiling × 1.6, rounded; floor × 1.6.
   - `brief`: ceiling = max(40, ceiling × 0.4), rounded; floor = half the new ceiling.
   - `normal`: unchanged.
   Pass the emphasis on as: "The RFP manager asked to emphasise the following in this section:
   <emphasis>".
3. **Detail bonus**, added to the ceiling only. Each client requirement mapped to the section
   adds `90 + min(2 × <words in its intent>, 120)`. The total bonus is capped at 480. A section
   folding in three distinct RFP asks must not compete for the same generic ceiling as a section
   with none; each ask needs room to be answered, not just gestured at.
4. **Client-required sections:**
   - `narrative`: [80, 150 + its own detail bonus].
   - `indicative_breakdown`: [30, 90], an intro around the table.
   - `phase_plan`: [50, 80 + 60 per phase], an intro plus short per-phase bullets.
   - `additional`: [60, 200].
5. **Re-drafts after a coverage or depth finding:** ceiling = min(round(ceiling × 1.6), 700).
   Thinness is the most common reason a section is flagged, so the retry needs more room.

Example: 4.7 has base [50, 120], brief `deep: …` and one mapped requirement whose intent has 30
words. The result is floor 80, ceiling 192 + (90 + 60) = 342.

## Client-required sections: placement rules
The requirements-analyst records each requirement with `kind`, `maps_to_section_id` and
`placement_after_section_id`. `outline()` applies the rules below. Use them to check its result
and to explain any section that seems out of place. An id that is not in the standard outline
counts as empty.
1. A **table-shaped requirement** (`indicative_breakdown` or `phase_plan`) **always** becomes its
   own new section, even when it maps to an existing section. If it were only folded into that
   section's narrative, its table would never be built and the ask would be silently lost. The
   anchor is the first of these that applies: `placement_after_section_id`, then
   `maps_to_section_id`, then 4.3 for a `phase_plan` or 6.1 for an `indicative_breakdown`.
2. A **narrative requirement with a valid `maps_to_section_id`** is folded into that section. The
   section's writer must cover it directly, and the section gets the detail bonus.
3. A **narrative requirement without one** becomes a new section after
   `placement_after_section_id`, or after 6.1 when that is empty.
4. New sections are level 3 under their anchor, numbered `<anchor>.1`, `<anchor>.2`, … in
   requirement order. They are rendered immediately after the anchor's own content, including its
   artifact, so they sit next to the content they relate to instead of trailing the document.
5. **Additional client-requested notes.** If `instructions_briefs` has an `additional` entry, the
   presales instructions contain asks that map to no section. The outline then ends with the
   level-1 section `additional`, "Additional Client-Requested Notes". Brief a writer for it with
   that text.

## Combine rule (`combine_resource_effort`)
`true` means the section presents resource effort (the man-months of the role × month grid)
together with module effort as one combined view. `false` means the two appear as separate
tables.
- The default is `true` for 4.4 (Project Team, the natural home of the resource grid), 5.4, and
  6.1 / 6.2. The effort and cost totals already include the additive lead and administration
  man-months.
- A section that defaults to `false` flips to `true` when a client requirement mapped to it
  contains, in its title or intent, any of these: resource, staffing, fte, man-month, man month,
  manmonth, team size, headcount, role-wise, role wise, person-month.
- The rule never flips `true` back to `false`. It does not model a client asking for less detail.

The renderer applies the flag. When it is `true` for a section, say so in that writer's brief, so
that the intro speaks of one combined view rather than "presented separately".

## Briefing writers
One `task` per writer:
```
Use the proposal-writing skill.
Client: <client name>
Withheld disclosure categories: <list, or "none">
Full outline, for cross-references by topic (id - title): <one line per section>
Write these sections, one write_draft per section, then draft_check each until clean:
- id: 4.7 | title: Data Migration Approach | words: [80, 342] (the ceiling is hard)
  facts: profile, scope_by_lob, workstreams (also load requirements and excerpts:4.7)
  guidance: <absolute path of sections/4.7-4.10-delivery-workstreams.md, or "none">
  artifact: none (or: "<artifact> is rendered after your text - do not repeat it")
  combine_resource_effort: <only when true>
  client requirements to cover: - <title>: <intent>   (or "none")
  presales brief: deep: <emphasis>   (or "none")
- id: 6.1.1 | title: <requirement title> | client-required, kind: indicative_breakdown, group_by: wave
  words: [30, 90] | intent: <intent> | presales instructions: <verbatim text, only for client-required table sections>
Reply with the section ids drafted (draft_check-clean), any requirement you could not satisfy and
why, and any fact you needed but could not find.
```
Give each guidance path as an absolute path: this skill's folder from your skills list, plus the
relative path. Pass the full presales instruction text only to client-required table sections and
to `additional`. Every other section receives only its own brief. Appending the whole instruction
to every section is exactly what made steering useless before.

**Re-draft template:** the same entry for the section, plus:
```
Corrective note: a prior draft of this section was reviewed against the client requirement(s)
it must cover and found insufficient: <issue - fix, one line per finding>. Ensure these specific
gaps are concretely and substantively closed this time, not just restated.
words: [<floor>, <raised ceiling>]
```

## Briefing the reviewer
```
Use the bid-review skill. Round <1|2> of 2. Client: <client name>.
Review these sections (id | title | facts | artifact): <one line per section>
Client requirements by destination: <section id -> requirement titles; client-required sections -> their own requirement>
Withheld disclosure categories: <list or "none">
Prior findings for these sections (round 2 only): <section_id | severity | issue | fix>
Record every finding with write_review, then reply with: a score 0-10, a one-sentence verdict, and
the high and medium findings per section (section_id | severity | issue | fix).
```

## Rules
- You never draft, edit or "fix" section text, and you never pass figures to writers. Numbers
  reach the document only through placeholders that the renderer resolves from the ledger.
- Do not rename or reorder standard sections. Do not drop a narrative section; a section with no
  client-specific material still gets its honest 2-3 sentences.
- Spawn exactly one requirements-analyst, before any writer. Run at most two review rounds.
- Do not re-spawn writers for low or `LEDGER:` findings alone.
- A finding that a section contradicts the ledger is fixed in the draft. Never change the ledger
  to match a draft.
