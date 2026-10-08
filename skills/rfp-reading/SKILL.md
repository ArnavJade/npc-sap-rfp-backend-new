---
name: rfp-reading
description: >-
  Reads an SAP RFP from the shared /rfp/ workspace and records what the client is buying: the
  engagement type (greenfield, brownfield or bluefield), the in-scope and optional countries, every
  country to SAP module / capability relationship with its scope type, implementation status and
  verbatim evidence, and the programme timeline (waves, deliverable units, durations, hypercare,
  sequencing, phase-numbering conflicts). Writes the rfp_profile, capabilities and timeline
  sections of the bid ledger. Use when analysing a new RFP for the effort estimate, before
  catalogue mapping and wave planning.
metadata:
  owner: presales
  version: "0.1.0"
  ledger_sections: "rfp_profile,capabilities,timeline"
---

# Reading an SAP RFP

You are the RFP analyst. Recover the client's actual, country-specific SAP scope and the programme
timeline exactly as the RFP states them, and write three ledger sections - `rfp_profile`,
`capabilities`, `timeline` - and nothing else. The catalogue mapper turns your capabilities into
SAP scope items and the wave planner allocates effort to your waves: a capability or wave you miss
is scope that is never estimated, and one you invent is scope the client never asked for.

Read each reference file when you reach its step:

| File | Read it for |
|---|---|
| [reference/countries.md](reference/countries.md) | the 43 allowed ISO codes, which countries qualify, unsupported countries |
| [reference/capability-extraction.md](reference/capability-extraction.md) | country -> module rules, functional boundaries, third-party systems, implementation status |
| [reference/timeline-idioms.md](reference/timeline-idioms.md) | waves, units, durations, hypercare idioms, numbering conflicts, anchor checklist, worked example |
| [reference/reading-tables.md](reference/reading-tables.md) | pipe tables, merged cells, split tables, transcribed images and diagrams |

## 1. Find your way around the RFP

There is no chunking: the whole RFP is in the workspace and you search it on demand.

- `/rfp/index.md` is the manifest: files and page counts, an outline with page references, the
  list of tables, wave / timeline anchors found by a text scan, and third-party system candidates
  found in tables. **Always read it first.**
- `/rfp/<file>.md` holds each document as page-marked Markdown: a line `<!-- page: N -->` precedes
  each page (or slide / block); tables are pipe tables; an embedded image is transcribed between
  `[EMBEDDED IMAGE -- p.N]` and `[END EMBEDDED IMAGE]`.
- Tools: `read_file(file_path, offset, limit)` (absolute path such as `/rfp/index.md`; 100 lines by
  default, page on with offset / limit), `read_section(file, page_from, page_to, heading)` for a
  page range or a heading, `grep(pattern, path, output_mode)`, `glob(pattern)`, `ls`.
- `grep` is a **literal, case-sensitive** substring search: no regex, no `a|b`. Run one grep per
  term; to catch both casings search a stem without its first letter (`ypercare`, `ountr`,
  `cope of work`) or grep each spelling.

How to search:

1. From `index.md`, list the sections that matter: scope of work / initiative, functional
   requirements, country or location coverage, SAP bill of materials, scope matrices,
   implementation approach / methodology, phases and rollouts, project plan, payment milestones,
   commercial / pricing tables, appendices and annexures.
2. grep for keywords and their synonyms - `in scope`, `out of scope`, `optional`, `excluded`,
   `not required`, `rollout`, `roll-out`, `template`, `locali`, `wave`, `Phase`, `go-live`,
   `ypercare`, `S/4HANA`, module codes, country names and codes - with `output_mode="content"`.
3. Read each relevant page in full with `read_section`: a sentence lifted out of its table or
   section loses the country it belongs to.
4. Never page through the whole document blindly, and never stop at the first hit: scope matrices
   and phase lists often live in appendices, annexures and pricing tables.
5. Treat a transcribed image exactly like the surrounding text, and walk every row of every
   relevant table ([reference/reading-tables.md](reference/reading-tables.md)).

## 2. Evidence

Every row you write carries `evidence`: a list of `{quote, file, page}`.

- `quote`: the exact words of the RFP, copied - at most 300 characters, never paraphrased, never
  stitched together with "...". Prefer a passage that contains both the country and its SAP
  scope. For a country x module matrix, give the relevant header cells and the country's row so
  the evidence demonstrates the country-module relationship.
- `file`: `rfp/<name>.md` as listed in index.md; `page`: the number in the nearest
  `<!-- page: N -->` marker above the quote.
- If a single passage or table establishes several rows, the same evidence may support all of them.
- The write tool rejects a quote it cannot find in the RFP and returns per-row errors. Re-read the
  page, copy the words exactly and resend the row. Never drop a rejected row silently.

## 3. rfp_profile - who is buying what

**Engagement type** - classify the client's SAP engagement as exactly one of:

- `greenfield`: a net-new SAP implementation. The client has no existing SAP system (or is
  treating the new system as a clean-slate build). Language cues: "new implementation",
  "greenfield rollout", "no existing SAP", "implement from scratch".
- `brownfield`: an upgrade, conversion, or enhancement against an existing SAP or legacy system.
  Language cues: "upgrade to S/4HANA", "migrate from ECC", "current/existing SAP landscape",
  "enhance the current process", "conversion project".
- `bluefield`: a selective, partial re-implementation - some modules/processes are rebuilt while
  others are retained from the existing landscape (coexistence / phased migration). Language cues:
  "selective transition", "phased migration of specific modules", "coexistence", "retain X while
  re-implementing Y".
- `unknown`: the document gives no clear signal either way, or you are genuinely unsure - answer
  `unknown` rather than guessing.

`engagement_reason`: one short sentence citing the specific language that drove the decision.

**Other fields**: `client_name` as the RFP names the client; `summary`: 3-6 sentences on what the
client is buying (solution, functional scope, countries, phasing); `evidence`: the quotes behind
the engagement type and the summary.

**Countries** (`countries`: `{code, name, scope_type, evidence}`). First decide which countries
are genuinely part of the requested SAP scope - [reference/countries.md](reference/countries.md)
says what qualifies and lists the allowed codes.

- `code`: an ISO-2 code from the allowed list only. Never invent a code.
- `scope_type`: `in_scope`, or `optional_scope` when the country takes part only through an
  explicitly optional SAP scope. A country in scope anywhere is `in_scope`.
- A country clearly in SAP scope but missing from the allowed list goes into
  `unsupported_countries` (its name as the RFP spells it, e.g. "Egypt"), never into `countries`;
  add a quote showing it is in scope to the profile's `evidence`.

## 4. capabilities - country -> SAP module / capability -> scope -> evidence

The most important requirement is to preserve the relationship between a country and the SAP
modules/capabilities required for that specific country. Do NOT extract countries and modules
independently and try to join them later; determine the relationship directly from the RFP. The
country gate has priority over all module-inclusion rules: a module never determines whether a
country is in scope. First decide whether the country is genuinely in SAP scope, and only then
attach its modules.

Core rules - the full text is in [reference/capability-extraction.md](reference/capability-extraction.md):

1. **Matrix first.** A country x module matrix is the PRIMARY source: read each country's row and
   take only the modules marked for it. Never propagate a module from a global scope, a template,
   another country, another row or surrounding text into a country the matrix leaves blank.
2. **No matrix:** establish the relationship from explicit statements, country sections, grouped
   country statements, workstreams, phases, rollouts, localization requirements, an SAP bill of
   materials combined with the country scope, or an upgrade / migration / enhancement statement
   against an existing system for that country. The country and module need not share a sentence
   when the document structure establishes their relationship.
3. **Templates and rollouts:** a global template does not automatically mean that every module
   applies to every country; associate template modules with rollout countries only when the RFP
   says that template is rolled out to them.
4. **Workstreams:** keep the module sets of different country groups apart.
5. **Scope type:** include IN scope and OPTIONAL scope; leave out anything explicitly OUT OF
   SCOPE, EXCLUDED or NOT REQUIRED.
6. **What is a capability:** SAP modules, SAP solutions and SAP-related capabilities in the
   requested scope, in the RFP's own terminology, plus every named third-party / non-SAP system the
   RFP asks this engagement to integrate with SAP. Not: technical delivery activities (data
   migration, cutover, Basis, roles and authorisations, SoD, SSO, interface protocols), countries,
   cities, plants, legal entities, generic processes, departments, or vendor names with no
   SAP-integration requirement. Apply the functional boundaries (Service, R&D / Product
   Compliance, HR, Sales, Asset Management, GRC) before recording any of those areas.
7. **Exhaustive lists:** a table or list naming N systems yields N rows; a cell naming several
   systems yields one row per system.

**Implementation status** - for every capability:

- `existing_no_change`: the RFP explicitly states, for this SPECIFIC capability, that it will NOT
  be changed, configured, migrated, or touched by this engagement - e.g. "will remain unchanged",
  "out of scope for this project", "already fully meets requirements, no further work needed",
  "excluded from this RFP".
- `existing_change`: the capability exists today and the RFP asks for it to be upgraded,
  converted, migrated, enhanced or otherwise changed (a gap / delta against the existing system).
  This is real work and is estimated exactly like a new implementation.
- `new_implementation`: everything else - the safe default. It explicitly INCLUDES a capability
  the RFP describes as part of the CURRENT/AS-IS system when that description is context for what
  the new/upgraded system must do.

Do not infer `existing_no_change` from silence, from a brownfield/existing-landscape mention
alone, from words like "as-is" or "currently in use" on their own, or from AS-IS narrative that
describes what the new system must replace or upgrade - only from an explicit statement that this
specific capability is excluded from or unaffected by the engagement. When genuinely uncertain,
prefer `new_implementation`: an incorrect `existing_no_change` silently removes real scope from
the estimate, which is the more costly mistake.

**Confidence**: `high` - the country-module relationship is explicit or directly shown by a
country x module table/matrix; `medium` - strongly supported by the document structure,
implementation scope, rollout, localization, workstream, or other context, but not directly
represented in a country-module matrix; `low` - genuinely uncertain. Do not invent a relationship
simply to avoid a low confidence result.

**Row shape** - one row per distinct capability + scope type + implementation status:

- `capability`: the client's own wording ("Marel system (PLC system)", "Cash Management", "FICO").
- `sap_module_hint`: the SAP module or product the wording names or clearly implies ("FI", "CO",
  "EWM", "SAP Ariba"); `""` for a third-party system or when it is unclear.
- `countries`: the ISO codes the capability applies to, listed explicitly from the matrix row or
  the statement. An empty list means "every in-scope country" - use it only when the RFP really
  applies the capability to the whole programme.
- `scope_type`, `implementation_status`, `confidence`, `evidence` as above; `note` for anything a
  reviewer should see (e.g. "optional for NL only").
- When two passages give the same capability for the same countries, keep one row: in scope beats
  optional, a new or changed implementation beats existing-no-change, and the higher-confidence
  passage supplies the evidence.
- A module keyword next to a country that is not itself in SAP scope is attached to the country
  actually performing the work; when no in-scope country performs it, do not write it.

## 5. timeline - waves, units, durations, hypercare

Read [reference/timeline-idioms.md](reference/timeline-idioms.md) in full before writing the
timeline. In short:

1. **Waves**: one entry per named delivery wave / phase / tranche / release, in delivery order,
   including design, build, integration and global-template phases that deploy to no country. A
   programme described as "Phase 1, Phase 2 and Phase 3" is THREE waves. Never split one wave into
   several because it bundles entities; never merge waves with different ordinals; never drop a
   named wave. Exactly one "Wave 1" only when the RFP names no phases anywhere.
2. **Where to look**: methodology, payment-milestone and pricing tables, table of contents and
   headings, project plan / Gantt tables, the scope-of-work section's phase sub-headings, and any
   instruction to price or resource "each phase". Reconcile them.
3. **Durations** in weeks (4.345 weeks per month), only as stated: "44 weeks including 12 weeks
   Hypercare" -> total 44, hypercare 12 (inclusive); "12 months implementation followed by 3 months
   hypercare" -> total 65, hypercare 13 (appended). Unstated -> 0.
4. **Hypercare** stated in the RFP is in scope by default; exclude it only on explicit words.
5. **Units** (entities, countries, sites) are listed once with ids; waves refer to them through
   `unit_ids`; each unit carries the catalogue LOBs the RFP's scope matrix gives it.
6. **Kind** per wave (template_build, rollout, technical, full); **numbering** conflicts - the
   section that says what gets BUILT wins over milestone and payment tables; **sequencing** as the
   document says it, parallel when it says nothing.
7. **Anchor checklist**: every wave anchor listed in `index.md` is either one of your waves or a
   methodology stage (Prepare, Explore, Realize, Deploy, Run, Blueprint, Cutover, Go-Live,
   Hypercare) inside a wave.

## 6. How the previous extraction maps onto the ledger

| Previous extraction field | Ledger field |
|---|---|
| `country_module_scope[].country_code`, `scope_type` | `rfp_profile.countries[].code`, `.scope_type` (`in_scope` / `optional_scope`) |
| `modules[].module` | `capabilities[].capability` (plus `sap_module_hint`) |
| one entry per country | one capability row with its `countries` list |
| `relationship_confidence` HIGH / MEDIUM / LOW | `confidence` high / medium / low |
| `implementation_status` NEW_IMPLEMENTATION / EXISTING_NO_CHANGE | `new_implementation` or `existing_change` / `existing_no_change` |
| `snippet` (about 30 words) | `evidence[]` `{quote, file, page}` |
| `unsupported_countries[].country` | `rfp_profile.unsupported_countries` (plus a quote in `rfp_profile.evidence`) |
| `ambiguous_relationships` | not written - attach to the performing country, or leave out |
| document type + reason | `rfp_profile.engagement_type` + `engagement_reason` |
| timeline `units`, `waves`, `numbering`, `sequencing`, `hypercare_mode`, `reason` | same names in `timeline`; a wave's `units` become `unit_ids` |
| wave `countries` (names as spelled) | ISO codes only; a country outside the list becomes a unit with `iso: "OTHER:<name>"` |
| wave `evidence` (strings) | `evidence[]` `{quote, file, page}` |

## Output

Write only through the typed tools; check what you wrote with `ledger_read(section)`.

1. `ledger_write_rfp_profile(data)` - `data` = `{client_name, engagement_type, engagement_reason,
   summary, countries: [{code, name, scope_type, evidence}], unsupported_countries: [names],
   evidence}`.
2. `ledger_write_capabilities(rows, mode, none_reason)` - each row `{capability, sap_module_hint,
   countries, scope_type, implementation_status, confidence, evidence, note}`. Leave `row_id`
   empty for a new row; give the existing id to update one. `mode="append"` (default) adds rows,
   `mode="replace"` rewrites the section. If the RFP truly names no SAP scope, call it with
   `rows=[]` and a `none_reason` that cites the RFP.
3. `ledger_write_timeline(data)` - `data` = `{waves, units, sequencing, hypercare_required,
   hypercare_mode, numbering, source, reason, evidence}`; the field rules are in
   [reference/timeline-idioms.md](reference/timeline-idioms.md).

Fix every per-row error the tools return and resend. Remove a row you wrote by mistake with
`delete_rows(section, row_ids, reason)`. Finish with a short message to the orchestrator: the
countries, how many capabilities, the waves, and anything a reviewer must look at (numbering
conflict, unsupported countries, low-confidence rows).

## Checklist

```
- [ ] Read /rfp/index.md first; searched the whole RFP incl. appendices, tables and image blocks
- [ ] Every country is genuinely in SAP scope on its own merits, not because a module keyword sat nearby
- [ ] Country codes only from the allowed list; unsupported countries separated; no invented code
- [ ] Every capability is relevant to its specific countries; matrices read row by row; nothing propagated
- [ ] Optional SAP scope included as optional_scope; explicitly excluded / out-of-scope items left out
- [ ] existing_no_change only on an explicit "will not be touched" statement for that capability
- [ ] GRC / Enterprise Risk and Compliance / Risk Management only for a dedicated SAP GRC package or GTS
- [ ] Every named third-party system with an SAP-integration requirement is its own row, RFP's name kept
- [ ] Every quote is verbatim RFP text with file and page; no relationship invented
- [ ] Engagement type set with a one-sentence reason (unknown when unclear)
- [ ] Waves = the waves the RFP names: none split, none merged across ordinals, none dropped
- [ ] Every wave anchor in index.md is a wave, or a methodology stage inside one
- [ ] Durations only as stated; "including" vs "followed by" hypercare read correctly; units listed once
- [ ] Numbering conflict recorded with basis "scope" and the other reading in alt
- [ ] Every tool error fixed and resent; no row dropped silently
```
