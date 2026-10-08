# Programme timeline: waves, units, durations, hypercare

Extract the PROGRAMME TIMELINE exactly as the document states it, as an SAP delivery planner would
read it. Near-verbatim from the previous timeline prompt, mapped onto the ledger's `timeline`
fields.

## 1. Waves / phases of delivery

Many RFPs split delivery into waves, tranches, phases or releases. Return one entry per wave, in
delivery order.

**What counts as a wave.** A wave is ANY named, ordinal segment of the programme that the RFP
schedules, prices, or scopes separately - whatever it contains. It does NOT have to roll anything
out to anybody. All of these are waves and must each be returned as their own entry:

- a design / build / integration phase that deploys to no country at all ("Phase 1) Interface design
  and implementation between SAP FCM and the web application");
- a global-template or blueprint phase whose output is a template rather than a live country;
- a pilot, major-country or first-go-live phase;
- a subsequent global roll-out phase that takes that template to the remaining countries.

A programme described as "Phase 1, Phase 2 and Phase 3" is THREE waves, even when only the later
ones name countries. Returning only the first, or collapsing all three into one, is the single most
common error on this task and is always wrong.

**Never split a single wave into multiple waves.** This is the SECOND most common error. When the
RFP says "Wave 2: Corporate + FEED + GTU + Logistics + AlEmar", that is ONE wave containing FIVE
entities, NOT five separate waves. The entities go into `units` (listed once at timeline level) and
their ids go into that wave's `unit_ids`. The number of waves you return must match the number of
waves THE RFP NAMES - no more, no less. If the RFP defines 3 waves and one of them bundles 5
entities, you return 3 waves, not 7. The per-entity detail elsewhere in the RFP (scope tables,
module lists) tells you each unit's `lobs` - it does NOT mean each entity is its own wave.

Return exactly ONE wave named "Wave 1" covering the whole programme ONLY when the RFP names no
phases, waves, tranches or releases anywhere. If the document names them, never substitute a single
synthetic wave for them.

**Never judge a wave's scope or deliverability.** Some waves name countries that are small,
unfamiliar, neighbouring another country in the list, or that you believe are not served by the
delivery organisation. That is NOT your decision and it is NOT a reason to drop, merge, shorten or
footnote the wave. Whether a country can be serviced, and how its effort is costed, is settled
later; your job here is only to report what the document says. Return every such wave; record each
of its countries as an ISO code in `countries` when it is in the allowed list, and as a unit with
`iso: "OTHER:<name>"` (name as the RFP spells it) when it is not - including ones you do not
recognise.

**Where to look.** Waves are rarely defined in only one place, and the clearest statement is often
NOT in the methodology section. Check all of:

- the implementation methodology / delivery approach section;
- the PAYMENT MILESTONE or commercial/pricing tables - an RFP that prices each wave separately is
  defining its waves there, often more precisely than anywhere else;
- the table of contents and section headings (the outline in `/rfp/index.md`);
- project plan, timeline or Gantt tables (often transcribed image blocks);
- the SCOPE OF WORK / request-for-proposal section, which frequently enumerates the phases one by
  one as its own sub-headings ("Phase 1) ...", "Phase 2) ...", "Phase 3) ...") - on many RFPs this
  is the most complete statement of the phase list anywhere in the document;
- any instruction to the bidder to price, schedule or resource "each phase" separately, which
  confirms the phase list is real and contractual.

Useful greps (literal, case-sensitive - run each): `Wave`, `wave`, `Phase`, `phase`, `Tranche`,
`Release`, `ollout`, `oll-out`, `o-live`, `ypercare`, `tabiliz`, `tabilis`, `months`, `weeks`,
`sequential`, `parallel`, `milestone`.

**Reconcile them.** If the methodology names three waves and the pricing table lists the same
three, that is THREE waves, not six - merge by name/content.

**Merge only true duplicates.** Two mentions describe the SAME wave only when they carry the same
ordinal (both "Phase 2") or plainly the same scope. Two mentions carrying DIFFERENT ordinals are
always different waves, however similar their wording. Never merge Phase 2 into Phase 1 because they
are adjacent, because one has no dates, or because their scope overlaps.

A heading that carries its own date range ("Phase 1: ... (August 2025 to May 2026)"), its own price
line, or its own scope list is a delivery wave - that is decisive evidence, not a hint.

**What a wave partitions on (`partition_axis`)**, one of:

- `entity` - legal entities, subsidiaries, business units, brands ("Wave 1: FOODS", "Wave 2:
  Corporate + Logistics"). This is the MOST COMMON axis and the easiest to miss, because the wave is
  named after companies you will not recognise. A capitalised proper noun you cannot identify is
  almost always an entity, not a typo - put it in `entities` verbatim.
- `country` - geographies or countries ("Wave 1: KSA", "Wave 2: UAE + Egypt").
- `module` - functional/module groups ("Phase 1: Finance & Procurement").
- `site` - plants, factories, warehouses, depots, stores.
- `mixed` - genuinely more than one of the above.

Use `""` when the RFP names a wave but says nothing about what it covers, AND for a build /
integration / global-template phase that is partitioned on none of the axes above because it deploys
to no geography. A wave whose partition_axis is `""` is a completely normal answer on a phased
programme - it is NEVER a reason to drop the wave, to merge it into the next one, or to reclassify it
as a methodology stage.

**Never drop a named wave.** If the RFP names a wave but gives it no duration, no entities and no
modules, still return it, with `total_weeks` 0 and empty lists. A named wave with nothing attached is
information; silently omitting it is not. The same applies to a wave you consider out of scope,
speculative, conditional on a schedule not yet agreed, or dependent on another programme: if the RFP
names it as a phase of THIS project, return it.

## 2. Duration per wave, in weeks

Convert months to weeks at 4.345 weeks/month. Read the document's own idiom carefully:

- "Wave 1: 44 weeks including 12 weeks Hypercare" -> `total_weeks` 44, `hypercare_weeks` 12. The
  hypercare is INSIDE the total; the total is NOT 56. (`hypercare_mode`: `inclusive`.)
- "12 months implementation followed by 3 months hypercare" -> the hypercare is APPENDED, so
  `total_weeks` is 15 months = 65 weeks and `hypercare_weeks` is 13. (`hypercare_mode`: `appended`.)

In BOTH cases `total_weeks` is the full elapsed duration and `hypercare_weeks` is the portion of it
that is post-go-live support. Hypercare can never exceed its wave's total.

Use ONLY durations the document actually states. Do NOT invent or estimate a duration from your own
judgement - if the RFP gives no duration for a wave, set its `total_weeks` to 0. A wave with
`total_weeks` 0 is a VALID and useful answer; it is never a reason to omit the wave or to merge it
into another one (the wave planner sizes undated waves later). Set `duration_source: "rfp"` on every
wave whose duration the RFP states, and leave it `""` otherwise. Record `start` and `go_live` dates or
months exactly as stated, when stated.

## 3. Hypercare

Hypercare is the staffed post-go-live support period immediately following a go-live. TREAT A
STATED HYPERCARE AS IN SCOPE BY DEFAULT. If the RFP states a hypercare, stabilisation or post-go-live
support period, report it. Exclude it ONLY where the document itself explicitly takes it out, namely
where the RFP says in so many words that the period is:

- optional, "if required", at the customer's discretion, or priced separately from the
  implementation;
- AMS / managed services / a long-term application support contract, which is a different service
  from hypercare;
- part of a FUTURE ENGAGEMENT this RFP is not bidding for - a follow-on programme, a roadmap item,
  "subsequent years". This exclusion is about work OUTSIDE this RFP's scope. It has NOTHING to do
  with the numbered phases of the programme being bid. If this RFP covers Phase 1, Phase 2 and Phase
  3, then all three are in scope and so is the hypercare of each. NEVER deny a wave its hypercare
  merely because it is the second or third phase, or because it rolls out later than the others;
- a warranty period stated as an obligation with no staffed effort.

Where the RFP is silent or ambiguous about whether a stated support period is in scope, INCLUDE it -
excluding hypercare requires explicit words in the document, never an inference. Hypercare is
frequently stated PER WAVE ("each wave: 3 months hypercare") - when it is, put it on every wave, not
just the last.

Timeline-level fields:

- `hypercare_required`: true when the RFP states an in-scope hypercare / stabilisation period
  (with or without a duration); false when it states none anywhere.
- `hypercare_mode`: `inclusive` (stated inside the wave totals), `appended` (stated after the
  implementation), `none` (no hypercare stated).
- If the RFP requires hypercare but states no length, leave `hypercare_weeks` 0 - do not invent a
  figure; the policy default (about 3 months) is applied later. If the RFP states no hypercare
  anywhere at all, set `hypercare_required` false and every `hypercare_weeks` 0.

## 4. The programme's deliverable units (`units`)

Listed ONCE at timeline level and referred to by each wave through `unit_ids`. A unit is one legal
entity, country or site the programme deploys to. List them once, never repeated inside the waves.
For each unit give:

- `id`: a short handle you invent ("u1", "u2", ...) and use in the waves' `unit_ids`;
- `name`: the RFP's own name for it, verbatim;
- `aliases`: other names the same RFP uses for it ("ACAII" and "ARASCO Food" for FOODS), so the
  same unit is not counted twice;
- `kind`: `entity`, `country` or `site`;
- `iso`: for a country unit, its ISO-2 code ("SA", "DE", "SG"); write `OTHER:<name>` when you know
  the country but it has no allowed code. Leave `""` for an entity or site that is not itself a
  country. This is a code, never a display name: per-country scope lines are matched on it;
- `lobs`: the catalogue LOBs the RFP's SCOPE TABLE gives to THAT unit. Many RFPs carry a unit x
  module matrix (rows are entities, columns are modules, or the reverse). That matrix is the single
  most valuable thing on this task: it decides which consultants a wave needs. Read it per unit.
  Leave the list EMPTY when the RFP does not break scope down per unit - an empty list means "not
  stated" (the unit then takes whatever its wave names), and guessing one is worse than leaving it
  empty.

Return an empty `units` list when the RFP phases by module only, or names no units at all. Keep only
units that some wave refers to.

LOB names to use in `units[].lobs` and `waves[].lobs` (catalogue LOBs; keep the RFP's own module
wording in `waves[].modules`):

| RFP module wording | Catalogue LOB |
|---|---|
| FI, CO, FICO, Finance, Treasury, Cash Management, Group Reporting | Finance |
| MM, Procurement, Procure to Pay, P2P, Ariba (sourcing / buying) | Sourcing and Procurement |
| SD, Sales, Order to Cash, O2C | Sales |
| PP, QM, Production, Manufacturing | Manufacturing |
| WM, EWM, TM, LE, Inventory, Logistics, Warehousing | Supply Chain |
| PM, EAM, Plant Maintenance | Asset Management |
| CS, Customer Service, Field Service | Service |
| HCM, HR, Payroll (core HR implementation only) | Human Resources |
| PLM, EHS, Product Compliance (dedicated software only) | R&D/Engineering |

Modules with no catalogue LOB (PS, Solution Manager, BTP, SAC, Concur, SuccessFactors, MDG, ...)
stay out of `lobs`; keep them in `waves[].modules`.

## 5. What each wave builds (`kind`)

- `template_build` - builds the global template / blueprint that later waves roll out;
- `rollout` - deploys an already-built template to further units;
- `technical` - deploys NO business unit: an interface, integration or platform build ("Phase 1)
  Interface design and implementation between SAP FCM and the web application");
- `full` - the RFP does not distinguish template from rollout.

This is NOT the same question as `partition_axis`. The axis says what the wave is divided by; the
kind says whether it designs the solution or repeats it. A programme that builds a template in Wave 1
and rolls it out in Waves 2 and 3 must say so here - it is the difference between a wave carrying
full design effort and a fraction of it.

Also per wave:

- `unit_ids`: the ids from `units` that this wave deploys. Empty for a technical wave.
- `countries`: ISO codes delivered in this wave (allowed list only).
- `entities`: the entity names the RFP attaches to the wave, verbatim.
- `modules`: module wording as the RFP gives it for the wave; `lobs`: the catalogue LOBs it
  delivers, when the RFP scopes the wave by module.
- `integrations`: the third-party systems or interfaces this wave builds, named as the RFP names
  them ("REST web application", "Concur").
- `name`: "Wave <sequence>" ("Wave 1", "Wave 2", ...) - the RFP's own label (Phase 2, Tranche B,
  Global Template) goes in the wave's evidence quote. `sequence`: 1, 2, 3 in delivery order.
- `evidence`: one short verbatim quote that defines the wave (its heading or table row), plus the
  line that states its duration when that is elsewhere.

## 6. Phase numbering (`numbering`)

Some RFPs number their phases DIFFERENTLY IN DIFFERENT SECTIONS - a milestone or payment table calls
something "Phase 1" while the scope section calls the same work "Phase 2". When that happens:

- set `conflict: true`;
- set `basis: "scope"` and build your `waves` from the section that says what gets BUILT. The scope /
  statement-of-work reading always wins over a milestone or payment table, because it is what the
  delivery is actually organised around. Use `"milestone"` only if there is no scope-side phase list
  at all, and `"undecided"` only when the document gives you no way to choose;
- put the OTHER reading in `alt`, in one line under 160 characters ("milestone table calls FCM+4
  countries Phase 1 and the interface Phase 2").

Set `conflict: false` and leave the other two fields `""` when the RFP numbers its phases
consistently, which is the normal case.

## 7. Sequencing - how the waves relate in time

- `sequential` - each wave starts only after the previous one goes live ("three sequential waves",
  "phase 2 commences after phase 1 go-live");
- `parallel` - the waves run at the same time;
- `staggered` - they overlap but start at different times.

Report what the DOCUMENT says. Look for the wording near the wave mentions (sequential,
sequentially, one after, back-to-back, consecutive / in parallel, simultaneous, concurrent /
staggered, overlapping) - an unrelated "parallel processing" elsewhere does not count. If it does not
say, use `parallel` (a multi-country rollout with no stated ordering is normally simultaneous). A
single wave is always `parallel`.

## 8. Anchor checklist (from `/rfp/index.md`)

`index.md` lists lines found by a plain text scan that look like a wave/phase heading or a wave
count. Treat them as a reference CHECKLIST:

1. **Distinguish delivery waves from methodology lifecycle phases.**
   - DELIVERY WAVES / TRANCHES are what partition the programme scope across entities, countries,
     modules, or sites (e.g. "Wave 1: FOODS", "Wave 2: Corporate + FEED + GTU", "Phase 1: Interface
     Build", "Wave 1: KSA pilot", "Wave 2: UAE rollout").
   - METHODOLOGY STAGES (such as ASAP or SAP Activate phases: Discover, Prepare, Explore, Blueprint,
     Realization, Final Preparation, Deploy, Cutover, Go-Live, Run, Hypercare) describe the
     lifecycle stages WITHIN a wave, even if numbered Phase 1..6. These are NEVER separate delivery
     waves of the programme.
2. **A stated wave count and the named delivery waves govern.**
   - When the RFP explicitly states a wave count (e.g. "implemented in 3 waves", "three sequential
     waves", or explicitly defines "Wave 1: ...", "Wave 2: ...", "Wave 3: ..."), the programme has
     EXACTLY that number of delivery waves.
   - NEVER create 6 waves just because a wave bundles multiple entities or because the methodology
     describes 6 project phases.
   - If Wave 2 bundles multiple entities ("Wave 2: Corporate + FEED + GTU + Logistics + AlEmar"),
     return ONE wave named Wave 2 with all entities bundled in its `unit_ids` and `entities`.
3. **Verify all named delivery waves.** Ensure every delivery wave named in the RFP (Wave 1, Wave 2,
   Wave 3, ...) is included. Do not drop Wave 3 or any later wave. Every entity a declared wave line
   lists ("Wave 3: MEFSCO + IDAC") belongs to that wave's units.

The number of waves must equal the number of waves the RFP defines (2, 3, 4, 5, ...): four phases
(Phase 1-4) means exactly 4 waves; a wave bundling 5 entities is a single wave whose `unit_ids` list
all 5.

## 9. Timeline-level fields and limits

- `source`: `rfp` when the waves or the programme duration come from the RFP; `derived` only when
  the RFP states neither (one "Wave 1", `total_weeks` 0).
- `reason`: one line describing the programme as read ("three sequential waves: Wave 1 FOODS, Wave 2
  Corporate+FEED+GTU+Logistics+AlEmar, Wave 3 MEFSCO+IDAC").
- `evidence`: the quote that states the wave count or the overall plan, when there is one.
- Plausibility (enforced by the write tool): at most 12 waves and 40 units; wave names unique; every
  `unit_ids` entry defined in `units`; no wave longer than 260 weeks - a longer figure is an AMS or
  contract term, not an implementation window, so leave `total_weeks` 0 when the RFP states no
  implementation duration.

## 10. Worked example (ledger shape)

```json
{
  "units": [
    {"id": "u1", "name": "FOODS", "aliases": ["ACAII"], "kind": "entity", "iso": "", "lobs": ["Finance", "Sales"]},
    {"id": "u2", "name": "Corporate", "aliases": [], "kind": "entity", "iso": "", "lobs": ["Finance"]},
    {"id": "u3", "name": "FEED", "aliases": [], "kind": "entity", "iso": "", "lobs": ["Finance"]},
    {"id": "u4", "name": "GTU", "aliases": [], "kind": "entity", "iso": "", "lobs": ["Finance"]},
    {"id": "u5", "name": "Logistics", "aliases": [], "kind": "entity", "iso": "", "lobs": ["Finance"]},
    {"id": "u6", "name": "AlEmar", "aliases": [], "kind": "entity", "iso": "", "lobs": ["Finance"]},
    {"id": "u7", "name": "MEFSCO", "aliases": [], "kind": "entity", "iso": "", "lobs": ["Finance"]},
    {"id": "u8", "name": "IDAC", "aliases": [], "kind": "entity", "iso": "", "lobs": ["Finance"]}
  ],
  "numbering": {"conflict": false, "basis": "", "alt": ""},
  "waves": [
    {"name": "Wave 1", "sequence": 1, "total_weeks": 44, "hypercare_weeks": 12,
     "partition_axis": "entity", "kind": "template_build", "unit_ids": ["u1"],
     "entities": ["FOODS"], "countries": [], "modules": [], "lobs": [], "integrations": [],
     "duration_source": "rfp", "start": "", "go_live": "",
     "evidence": [{"quote": "<the RFP line defining Wave 1>", "file": "rfp/<name>.md", "page": "<n>"}]},
    {"name": "Wave 2", "sequence": 2, "total_weeks": 28, "hypercare_weeks": 12,
     "partition_axis": "entity", "kind": "rollout", "unit_ids": ["u2", "u3", "u4", "u5", "u6"],
     "entities": ["Corporate", "FEED", "GTU", "Logistics", "AlEmar"], "countries": [], "modules": [],
     "lobs": [], "integrations": [], "duration_source": "rfp", "evidence": ["..."]},
    {"name": "Wave 3", "sequence": 3, "total_weeks": 28, "hypercare_weeks": 12,
     "partition_axis": "entity", "kind": "rollout", "unit_ids": ["u7", "u8"],
     "entities": ["MEFSCO", "IDAC"], "countries": [], "modules": [], "lobs": [], "integrations": [],
     "duration_source": "rfp", "evidence": ["..."]}
  ],
  "sequencing": "sequential",
  "hypercare_required": true,
  "hypercare_mode": "inclusive",
  "source": "rfp",
  "reason": "three sequential waves: Wave 1 FOODS, Wave 2 Corporate+FEED+GTU+Logistics+AlEmar, Wave 3 MEFSCO+IDAC",
  "evidence": []
}
```

(`"..."` stands for evidence objects like the first one; every quote must be real RFP text.)
