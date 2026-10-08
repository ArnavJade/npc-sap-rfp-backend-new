---
name: wave-planning
description: >-
  How the wave-planner decides which delivery wave delivers which scope, so the deterministic
  sizing can turn effort into per-wave person-days and staffing - tagging per-country scope lines
  to waves, allocating each workstream's effort across waves as shares, setting each wave's SAP
  Activate phase split (default Prepare .08 / Explore .18 / Realize .50 / Deploy .14, relative) and
  sizing waves the RFP did not date. The planner records decisions with reasons; tools compute every
  number. Use when writing the wave_plan ledger section.
metadata:
  owner: "presales"
  version: "0.1.0"
  ledger_sections: "wave_plan"
---

# Wave planning

You decide; the tools compute. You write one object - `wave_plan` - with four parts:
`item_tags`, `allocations`, `phases` and `data_migration_waves`. Sizing then splits every workstream's person-days across
the waves exactly (largest remainder, so nothing is lost or invented), builds a staffing grid per
wave from your phase split, and prices it.

## Read first
1. `ledger_read("timeline")` - waves (names, countries, units, stated durations, hypercare),
   sequencing. Use the wave names EXACTLY as written there.
2. `ledger_read("scope_items")` and `effort_preview("lob_country")` - each catalogue line (scope
   item x country) with its person-days and scope_items row id.
3. `effort_preview("workstream")` - person-days per allocation key: `lob:<LOB>`, `integrations`,
   `non_catalogue`, `tech_dev`, `data_migration`, `basis`, `security`, `analytics`.
4. Where the timeline leaves it open, the RFP pages its evidence cites (`read_section`).

## Single wave
If the timeline has one wave (or none), write only `phases` for it (and its duration if undated)
with `allocations: []`, `item_tags: []` and `data_migration_waves: []`: everything belongs to that wave.

## item_tags - which wave delivers a catalogue line
Tag a line when the RFP makes its wave unambiguous: the wave's countries / entities / units match
the line's country, or the wave's module list covers its LOB. `{row_id, country, wave, rationale}`;
leave `country` empty to tag every country line of the item. Typical patterns:
- country / entity waves ("Wave 1: KSA", "Wave 2: UAE + Egypt"): tag each line by its country;
- module waves ("Phase 1: Finance, Phase 2: Supply Chain"): tag by LOB, every country;
- template + roll-out: the template wave builds the global design. Tag the template country's lines
  to it; roll-out countries' lines to their roll-out waves.
Untagged lines follow their LOB's allocation.

## allocations - shares per workstream
One allocation per workstream with effort: `{workstream, shares: {wave: share}, rationale}`. Shares
are fractions summing to 1 over the waves that do that work.
- `lob:<LOB>` - the untagged remainder of a LOB. If every line is tagged, you may omit it.
- `integrations`, `tech_dev` - build mostly where the template / first wave is designed; later waves
  reuse it (typical: 0.7-0.85 to the first wave of that scope, the rest spread by the roll-outs that
  add interfaces). A wave that adds its own systems (a country payroll, a local bank) takes more.
- `data_migration` - each wave loads its own countries' data: proportional to the countries /
  entities it carries (the per-wave tables in `data_migration_waves` take precedence for the split).
- `basis` - landscape set-up in the first wave; later waves a small share (transports, client copies).
- `security` - role design in the first wave; later waves role mapping for new users.
- `analytics` - by where the reporting scope is delivered; default with the first full wave.
- `non_catalogue` - where the tool is first needed.
Write the reason in one line, grounded in the timeline or the RFP. A workstream with no allocation
is spread by implementation weeks and flagged in the sizing notes - acceptable only when you have no
basis to do better.

## data_migration_waves - each wave's Data Migration table
The Data Migration sheet has one conversion-object table per wave. The data-migration specialist
wrote ONE base table (`ledger_read("data_migration")`): the objects and per-phase days for the
FIRST wave. Every other wave's table is that base scaled to what THAT wave has to migrate - never a
plain copy. Write one entry per wave (the first one too, normally `scale: 1.0`):
`{wave, scale, key_scale?, objects?, rationale}`.
- `scale` - the wave's data volume relative to the first wave, from its requirements in the
  timeline / RFP: number of entities, company codes, plants, countries or sites it carries, record
  volumes the RFP states, modules it adds. Two entities after a one-entity first wave -> about 2.0;
  a single small site -> 0.5. Never 1.0 by default for every wave - justify each number.
- `key_scale` (optional, per column) - what a roll-out reuses: templates and programs built in the
  first wave make `func_spec` and `program_dev` smaller (e.g. 0.5) while the load iterations and
  cutover follow the volume (`scale`). A wave that brings new source systems needs new programs
  (`program_dev` >= 1).
- `objects` (optional) - the data_migration row_ids this wave migrates, when the wave does not carry
  every module (e.g. a wave without Transport Management does not migrate TM masters). Empty = all.
The tool multiplies the base cells, snaps each to the allowed grid (0.5 / 1 / 2 / 3 / 4) and splits the
Data Migration person-days across the waves exactly as these tables do. Without an entry, a wave's
table is scaled by its `data_migration` allocation share relative to the first wave's, and without
that it is a copy (flagged in the sizing notes). Single-wave programmes: omit it.

## phases - SAP Activate split per wave
`{wave, phase_split: {Prepare, Explore, Realize, Deploy}, total_weeks?, hypercare_weeks?, rationale}`.
- Weights are relative (they need not sum to 1). Default .08 / .18 / .50 / .14.
- Template / first full wave: keep the default or put more weight on Explore (design).
- Roll-out waves reusing a template: lighter Explore (fit-gap against the template, e.g. .05 / .10 /
  .55 / .30) and a heavier Deploy (localisation testing, cutover, training).
- Technical waves (upgrade, conversion): small Explore, larger Realize / Deploy.
- `total_weeks` / `hypercare_weeks` ONLY for a wave the RFP did not date (timeline total_weeks 0):
  give total INCLUDING hypercare, reason from the RFP (go-live dates, phase descriptions) or from
  comparable scope. Never override a duration the RFP states. Leave both empty to let the tool size
  the wave from its effort.

## Rules
- Use only wave names from the timeline; unknown names are rejected.
- Never write person-days, FTE or costs; shares, tags and Data Migration scale factors are your only
  quantities.
- Every allocation and phase entry carries a one-line rationale.
- When done, reply with the plan in a few lines: tags (count), allocations (workstream -> shares),
  phase splits, Data Migration scale per wave, sized waves and any doubt.
