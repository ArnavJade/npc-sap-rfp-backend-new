---
name: bid-review
description: >-
  How the reviewer audits the YASH response drafts before rendering - per client requirement,
  COVERAGE and DEPTH against the RFP's own instruction (the old requirement-verification gate), cost
  gaps the placeholders must close, agreement with the reviewed ledger, disclosure compliance, typed
  figures, invented YASH or client facts, duplication and the cross-section coherence rules of the old
  harmonisation pass - and records findings with severity and a concrete fix. At most two rounds. Use
  when reviewing proposal drafts in call 2.
metadata:
  owner: "presales"
  version: "1.0.0"
---

# Bid review (reviewer, call 2)

Ported from the old generator's requirement-verification gate and cost-gap check, the narrative
harmonisation rules, and the bid evaluator (routers/evaluator.py). You never edit drafts and never
change the ledger: findings go back to the writers through the orchestrator, so each must be specific
enough to act on without you.

## Inputs
- The brief: sections to review, client requirements by destination, withheld disclosure categories,
  and (round 2) prior findings.
- `outline()`, `drafts_status()`, the drafts (`read_file /drafts/<id>.md`), `bid_facts(view)` for the
  ledger, `draft_check(id)` for the mechanical figure check, and the RFP (`/rfp/`, `read_section`).

## 1. Requirement coverage (the gate - most important)
For every section a client requirement was folded into, and every client-required section: judge EACH
instruction against the drafted content - not whether it mentions the topic or echoes the
instruction's wording back.
- COVERAGE: does the content specifically address every part of the instruction? A passage that
  quotes / paraphrases the instruction but does not deliver the substance it asks for (a concrete
  mechanism, a named list, a described structure, a specific commitment) is NOT satisfied.
- DEPTH: given the client's own wording, is the detail proportionate, or a thin one- or two-sentence
  treatment where the instruction implies something more substantial?
For an unsatisfied instruction, the finding's `fix` names the SPECIFIC missing element(s), concrete
and actionable.
- **Cost gaps**: when the missing element is a cost / price / effort figure, the fix is a placeholder
  or table (`{{fig:total_project_cost}}`, `{{table:cost}}`, `{{table:indicative_breakdown:<group>}}`)
  - never a typed number. If the category is withheld by disclosure, the gap is not the writer's:
  prefix the issue `LEDGER:`.

## 2. Ledger agreement
Waves, sequencing, countries, modules, systems, objects and statuses match `bid_facts`. Naming a
country, module, integration or wave the ledger does not have, or describing an Out of Scope object as
delivered, is wrong. Out-of-scope asks the system cannot deliver (a country outside the allowed list,
a product outside the catalogue) are not the draft's fault - do not penalise their absence.

## 3. Disclosure
Nothing from a withheld category in prose, tables, parentheticals or hints. Any breach is `high`.

## 4. Figures
`draft_check` must be clean. Also flag spelt-out counts and figures outside their home sections
(effort / money outside chapter 6, FTE / man-months outside 4.4 / 5.4, durations outside 4.3 and
phase plans).

## 5. Facts
No specific YASH claim the proposal-writing yash-profile reference bans (numbers, named clients, tiers,
certifications, offices); no invented client facts. A blank template or RFP instructions copied
verbatim instead of a bespoke answer is a `high` finding.

## 6. Coherence across sections (the old harmonisation rules)
Sections were drafted in parallel; flag what makes them read as disconnected:
- identical opening shapes across sections ("To address <client>'s requirement ...");
- drifting terminology - different names for the same entity, system, phase or wave;
- verbatim repetition and boilerplate recurring across sections;
- a section reproducing another section's table, diagram or scope list;
- cross-references by section number to client-required subsections (use topic / name).
These are `low` unless they mislead (then `medium`).

## Severity
- `high`: disclosure breach; contradiction of the ledger; invented fact; a client requirement not
  addressed at all; a typed figure; copied template text.
- `medium`: a requirement addressed only superficially (coverage or depth); a figure outside its home
  section; duplication of another section's content; misleading wording.
- `low`: editorial and coherence.
Prefix the issue with `LEDGER:` when the problem lies in the reviewed ledger or the disclosure profile
itself - a writer cannot fix it.

## Recording and reply
Call `write_review(findings=[{section_id, severity, issue, fix}, ...])` once per round with every
finding (`issue` cites the draft's words; `fix` says exactly what to add or change). Round 2: re-check
only the re-drafted sections against their round-1 findings; record only what remains. Reply with a
score 0-10, a one- or two-sentence honest verdict, and the high and medium findings per section
(`section_id | severity | issue | fix`).
