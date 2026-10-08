---
name: bid-review
description: >-
  How the reviewer checks the YASH response drafts before rendering - coverage and depth of every
  client requirement, agreement with the reviewed ledger (scope, waves, countries, systems),
  disclosure compliance, figures only as placeholders, no invented YASH or client facts, no
  duplication across sections, and editorial quality - and records findings with severity and a
  concrete fix for the writers. At most two review rounds. Use when reviewing proposal drafts in
  call 2.
metadata:
  owner: "presales"
  version: "0.1.0"
---

# Bid review (reviewer, call 2)

You review drafts; you never edit them and never change the ledger. Findings go to the writers
through the orchestrator, so each one must be specific enough to act on without you.

## Inputs
- The orchestrator's brief: sections to review, client requirements by destination, withheld
  disclosure categories, and (round 2) the prior findings.
- `outline()` and `drafts_status()`; the drafts themselves with `read_file` on `/drafts/<id>.md`.
- `bid_facts(view)` for the ledger facts, `draft_check(id)` for the mechanical figure check, and
  the RFP (`/rfp/`, `read_section`) to verify quotes and asks.

## What to check, per section
1. **Coverage and depth (most important).** Every client requirement mapped to the section is
   answered with substance: a mechanism, named steps, a structure, a commitment. Quoting the ask
   back or "we will address this" is a miss. Client-required sections answer their own intent.
2. **Ledger agreement.** Waves, sequencing, countries, modules, systems, objects and statuses match
   `bid_facts`. A draft that names a country, module, integration or wave the ledger does not have,
   or contradicts a status (an Out of Scope object described as delivered), is wrong.
3. **Disclosure.** Nothing from a withheld category appears in prose, tables or hints (see the
   proposal-writing skill's disclosure table). Any breach is `high`.
4. **Figures.** `draft_check` must be clean. Also flag numbers that are clean only by accident:
   spelt-out counts, figures outside their home sections (effort / money outside chapter 6, FTE
   outside 4.4 / 5.4, durations outside 4.3 and phase plans).
5. **Facts about YASH and the client.** No specific YASH claim the yash-profile reference bans (numbers,
   named clients, tiers, certifications, offices); no invented client facts (systems, sites,
   history) the RFP does not state.
6. **Duplication.** No section reproduces another section's table, diagram or scope list; no
   repeated paragraphs across sections.
7. **Editorial.** Opens on the client's situation, not a generic scaffold; consistent naming;
   within the word ceiling; no top heading.

## Severity
- `high`: disclosure breach; contradiction of the ledger; invented fact; a client requirement not
  addressed at all; a typed figure.
- `medium`: a requirement addressed only superficially; a figure outside its home section;
  duplication of another section's content; misleading wording.
- `low`: editorial (tone, scaffolded opening, naming inconsistency, length).
Prefix `LEDGER:` to the issue when the problem is in the reviewed ledger or the disclosure profile
itself (e.g. the client asks for an effort breakdown but effort_detail is withheld) - a writer cannot
fix it; the orchestrator reports it.

## Recording
Call `write_review(findings=[{section_id, severity, issue, fix}, ...])` once per round with every
finding. `issue`: what is wrong, citing the draft's words. `fix`: what the writer must do, concretely
("Answer the client's ask for a cutover rehearsal plan: list the rehearsals, their purpose and
sign-off"). Round 2: re-check only the re-drafted sections against their round-1 findings; close the
ones that are fixed (do not repeat them) and record what remains.

## Reply
A score 0-10 for the response as a whole, a one-sentence verdict, and the high and medium findings
per section (`section_id | severity | issue | fix`).
