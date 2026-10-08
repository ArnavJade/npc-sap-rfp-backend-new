"""Rules every ledger write passes through. A rejected row comes back to the agent with a reason it
can act on; small, unambiguous corrections are applied and reported as notes instead.

Ported rules: evidence grounding (CorpusIndex), the allowed-country list, catalogue existence and
country availability (Layer 3), catalogue-covered codes barred from non_catalogue, Data Migration
effort snapping + MM-compulsory exemption, Basis 1-5 / Security 1-120 whole days, Analytics counts
and evidenced exclusion, timeline plausibility, and wave-plan consistency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel

from bidcore.catalogue.store import Catalogue
from bidcore.evidence import CorpusIndex
from bidcore.ledger.models import SECTIONS, Ledger
from bidcore.policy import Policy

LOB_WORKSTREAM_PREFIX = "lob:"
FIXED_WORKSTREAMS = ("integrations", "non_catalogue", "tech_dev", "data_migration", "basis", "security", "analytics")


@dataclass
class ValidationContext:
    policy: Policy
    catalogue: Catalogue
    corpus: CorpusIndex | None
    ledger: Ledger

    @property
    def bid_countries(self) -> list[str]:
        profile = self.ledger.rfp_profile.data
        return [c.code for c in profile.countries] if profile else []


@dataclass
class Verdict:
    index: int
    row: BaseModel
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


# ------------------------------------------------------------------------------ shared checks
def _grounded(evidence: list, v: Verdict, ctx: ValidationContext, required: bool = True, label: str = "") -> list:
    """Return the evidence whose quotes really occur in the RFP; record errors/notes on `v`."""
    evidence = list(evidence or [])
    if not evidence:
        if required:
            v.errors.append(f"{label}no evidence: add at least one verbatim RFP quote with file and page")
        return evidence
    if ctx.corpus is None:
        return evidence
    found = [e for e in evidence if e.quote and ctx.corpus.contains(e.quote)]
    if not found:
        v.errors.append(f"{label}evidence quote not found in the RFP: {evidence[0].quote[:80]!r} - copy the exact "
                        "words (grep the /rfp/ files) instead of paraphrasing")
        return evidence
    if len(found) < len(evidence):
        v.notes.append(f"{label}{len(evidence) - len(found)} of {len(evidence)} quotes not found verbatim; dropped")
    return found


def _check_evidence(v: Verdict, ctx: ValidationContext, required: bool = True, label: str = "") -> None:
    v.row.evidence = _grounded(getattr(v.row, "evidence", None), v, ctx, required, label)


def _check_countries(codes: list[str], ctx: ValidationContext, v: Verdict, label: str = "countries") -> list[str]:
    allowed = set(ctx.policy.catalogue.allowed_countries)
    cleaned, bad = [], []
    for code in codes or []:
        c = str(code).strip().upper()
        (cleaned if c in allowed else bad).append(c)
    if bad:
        v.errors.append(f"{label}: {bad} not in the allowed ISO-2 list (non-catalogue countries go to "
                        "rfp_profile.unsupported_countries)")
    return sorted(set(cleaned))


# ------------------------------------------------------------------------------ per section
def _rfp_profile(v: Verdict, ctx: ValidationContext) -> None:
    allowed = set(ctx.policy.catalogue.allowed_countries)
    kept = []
    for c in v.row.countries:
        c.code = c.code.strip().upper()
        if c.code in allowed:
            kept.append(c)
        else:
            v.row.unsupported_countries.append(c.name or c.code)
            v.notes.append(f"{c.code} is not a catalogue country - moved to unsupported_countries")
    v.row.countries = kept


def _capabilities(v: Verdict, ctx: ValidationContext) -> None:
    v.row.countries = _check_countries(v.row.countries, ctx, v)
    _check_evidence(v, ctx)


def _timeline(v: Verdict, ctx: ValidationContext) -> None:
    t, p = v.row, ctx.policy.timeline
    if len(t.waves) > p.max_waves:
        v.errors.append(f"{len(t.waves)} waves exceeds the plausible maximum of {p.max_waves}: merge or "
                        "re-read - repeated mentions of one wave are not separate waves")
    names = [w.name.strip() for w in t.waves]
    if len(set(n.casefold() for n in names)) != len(names):
        v.errors.append("wave names must be unique")
    unit_ids = {u.id for u in t.units}
    for w in t.waves:
        if w.total_weeks > p.max_plausible_weeks:
            v.errors.append(f"{w.name}: {w.total_weeks} weeks is an AMS/contract term, not a wave - leave "
                            "total_weeks 0 if the RFP states no implementation duration")
        if w.hypercare_weeks > w.total_weeks > 0:
            v.notes.append(f"{w.name}: hypercare {w.hypercare_weeks} > total {w.total_weeks}; clamped")
            w.hypercare_weeks = w.total_weeks
        if w.total_weeks > 0:
            w.duration_source = w.duration_source or "rfp"
        w.countries = _check_countries(w.countries, ctx, v, f"{w.name} countries")
        missing = [u for u in w.unit_ids if u not in unit_ids]
        if missing:
            v.errors.append(f"{w.name}: unit_ids {missing} are not defined in units")
    if t.waves and not any(w.evidence for w in t.waves) and not t.evidence:
        v.errors.append("cite the RFP text that defines the waves (evidence on the timeline or on each wave)")
    for w in t.waves:
        w.evidence = _grounded(w.evidence, v, ctx, required=False, label=f"{w.name}: ")


def _scope_items(v: Verdict, ctx: ValidationContext) -> None:
    item = v.row
    hit = ctx.catalogue.get([item.scope_item_id]).get(item.scope_item_id.strip())
    if hit is None:
        v.errors.append(f"scope item '{item.scope_item_id}' is not in the catalogue - use catalogue_search; "
                        "a module with no Best Practice items belongs in non_catalogue")
        return
    for attr, key in (("lob", "lob"), ("business_area", "business_area"), ("description", "description")):
        if getattr(item, attr) != hit[key]:
            if getattr(item, attr):
                v.notes.append(f"{attr} corrected to the catalogue value '{hit[key]}'")
            setattr(item, attr, hit[key])
    countries = _check_countries(item.countries, ctx, v) or list(ctx.bid_countries)
    avail = ctx.catalogue.availability([hit["scope_item_id"]], countries).get(hit["scope_item_id"], {})
    unavailable = [c for c in countries if not avail.get(c)]
    if unavailable and len(unavailable) == len(countries) and countries:
        v.errors.append(f"{item.scope_item_id} is not available in {unavailable} (check_country_availability); "
                        "pick an available alternative or leave it out")
        return
    if unavailable:
        v.notes.append(f"{item.scope_item_id} not available in {unavailable}; kept only for the other countries")
    item.countries = [c for c in countries if avail.get(c)]
    if item.lob in ctx.policy.catalogue.sensitive_lobs and not item.capability_refs and not item.evidence:
        v.errors.append(f"'{item.lob}' is a sensitive LOB: link the capability (capability_refs) or quote the RFP")
    _check_evidence(v, ctx, required=False)


_PAREN_RE = re.compile(r"^(.*?)\s*\(([^)]+)\)\s*$")
_CODE_SPLIT_RE = re.compile(r"[/&,]|\band\b", re.IGNORECASE)
_PURE_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,6}(\s*[/&,]\s*[A-Za-z0-9]{1,6})*$")


def is_catalogue_covered(name: str, covered: set[str]) -> bool:
    """Ported is_catalogue_covered_module: 'FI', 'MM/SD', 'Controlling (CO)' -> covered."""
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()  # noqa: E731
    name = (name or "").strip()
    if not name:
        return False
    if norm(name) in covered:
        return True
    if _PURE_CODE_RE.match(name) and any(norm(t) in covered for t in _CODE_SPLIT_RE.split(name) if t.strip()):
        return True
    m = _PAREN_RE.match(name)
    if m and _PURE_CODE_RE.match(m.group(2).strip()):
        return any(norm(t) in covered for t in _CODE_SPLIT_RE.split(m.group(2)) if t.strip())
    return False


def _non_catalogue(v: Verdict, ctx: ValidationContext) -> None:
    item, pol = v.row, ctx.policy.effort.non_catalogue
    if is_catalogue_covered(item.name, set(pol.catalogue_covered_codes)):
        v.errors.append(f"'{item.name}' is a catalogue module - map it to scope_items with catalogue_search")
    item.countries = _check_countries(item.countries, ctx, v)
    band = pol.effort_bands.get(item.effort_band)
    if band is None:   # e.g. 'M' or '': derive the band from kind + effort instead of rejecting the row
        guessed = _guess_band(item, pol.effort_bands)
        v.notes.append(f"effort_band {item.effort_band!r} is not a band key; set to '{guessed}' "
                       f"(keys: {sorted(pol.effort_bands)})")
        item.effort_band, band = guessed, pol.effort_bands[guessed]
    if not item.effort_days or item.effort_days <= 0:
        item.effort_days = float(band[0])
        v.notes.append(f"effort_days missing; set to the '{item.effort_band}' band minimum {band[0]} PD")
    if not (0 < item.effort_days <= 500):
        v.errors.append("effort_days must be > 0 and <= 500")
    elif not (band[0] <= item.effort_days <= band[1]):
        v.notes.append(f"{item.effort_days} PD is outside the '{item.effort_band}' band {band}; rationale required")
        if not item.rationale.strip():
            v.errors.append("effort outside its band needs a rationale")
    _check_evidence(v, ctx)


def _guess_band(item: Any, bands: dict[str, Any]) -> str:
    """The policy band an item most plausibly belongs to, from its kind and effort."""
    if item.kind == "sap_module_no_bp" and "sap_module_no_best_practice" in bands:
        return "sap_module_no_best_practice"
    if "third" in (item.label or "").lower() and "third_party_integration" in bands:
        return "third_party_integration"
    light, standard = bands.get("sap_tool_light"), bands.get("sap_tool_standard")
    if light and (not standard or (item.effort_days or 0) <= light[1]):
        return "sap_tool_light"
    return "sap_tool_standard" if standard else sorted(bands)[0]


# Planning-level person-days for an integration whose estimate the agent left out (it sent 0 for all six
# rows in the second live run); inside the policy band third_party_integration (10-60).
INTEGRATION_DEFAULT_DAYS = {"Low": 10, "Medium": 20, "High": 40}


def _integrations(v: Verdict, ctx: ValidationContext) -> None:
    if not v.row.system.strip():
        v.errors.append("system name is required")
    if not v.row.effort_days or v.row.effort_days <= 0:
        days = INTEGRATION_DEFAULT_DAYS.get(v.row.complexity, 20) * max(int(v.row.interface_count or 1), 1)
        v.notes.append(f"effort_days missing for {v.row.system}; set to {days} PD ({v.row.complexity} complexity "
                       f"x {max(int(v.row.interface_count or 1), 1)} interface(s)) - give your own estimate if you have one")
        v.row.effort_days = float(min(days, 500))
    elif v.row.effort_days > 500:
        v.errors.append("effort_days must be > 0 and <= 500 (skill effort guide)")
    _check_evidence(v, ctx)


def _ricefw(v: Verdict, ctx: ValidationContext) -> None:
    r = v.row
    if any(x.no_of_objects < 0 for x in r.rows) or r.development_objects_total < 0:
        v.errors.append("object counts cannot be negative")
    split = sum(r.complexity_split_pct.values())
    if r.complexity_split_pct and not 95 <= split <= 105:
        v.notes.append(f"complexity split sums to {split}%, not 100% (the remainder goes to the last bucket)")
    for i, row in enumerate(r.rows):
        row.evidence = _grounded(row.evidence, v, ctx, required=False, label=f"row {i + 1}: ")
    _check_evidence(v, ctx, required=bool(r.rows or r.development_objects_total or r.interface_total_count))


def _fiori(v: Verdict, ctx: ValidationContext) -> None:
    if v.row.app_count < 0:
        v.errors.append("app_count cannot be negative")
    _check_evidence(v, ctx, required=bool(v.row.app_count or v.row.app_names))


def _data_migration(v: Verdict, ctx: ValidationContext) -> None:
    allowed = ctx.policy.workstreams["data_migration"]["allowed_effort_days"]
    for key in ctx.policy.workstreams["data_migration"]["effort_keys"]:
        value = float(getattr(v.row, key) or 0)
        snapped = min(allowed, key=lambda a: (abs(a - value), a))
        if snapped != value:
            v.notes.append(f"{key} {value} snapped to {snapped} (allowed {allowed})")
            setattr(v.row, key, snapped)
    exempt = v.row.mm_compulsory and v.row.sap_module.strip().upper() == "MM"
    _check_evidence(v, ctx, required=not exempt)


def _basis(v: Verdict, ctx: ValidationContext) -> None:
    lo, hi = ctx.policy.workstreams["basis"]["effort_range"]
    for key in ("dev", "qa", "prd"):
        value = getattr(v.row, key)
        if v.row.status == "Out of Scope":
            setattr(v.row, key, None)
        elif value is None or not (lo <= value <= hi):
            fixed = int(min(max(round(value or ctx.policy.workstreams["basis"]["default_effort_days"]), lo), hi))
            v.notes.append(f"{key} {value} -> {fixed} (whole days {lo}-{hi})")
            setattr(v.row, key, fixed)
    _check_evidence(v, ctx)


def _security(v: Verdict, ctx: ValidationContext) -> None:
    lo, hi = ctx.policy.workstreams["security"]["effort_range"]
    if v.row.status == "Out of Scope":
        v.row.effort_days = None
    elif v.row.effort_days is None or not (lo <= v.row.effort_days <= hi):
        default = ctx.policy.workstreams["security"]["default_effort_days"][v.row.complexity]
        fixed = int(min(max(round(v.row.effort_days or default), lo), hi))
        v.notes.append(f"effort {v.row.effort_days} -> {fixed} (whole days {lo}-{hi})")
        v.row.effort_days = fixed
    _check_evidence(v, ctx)


def _analytics(v: Verdict, ctx: ValidationContext) -> None:
    cap = ctx.policy.workstreams["analytics"]["max_objects"]
    if not (1 <= v.row.no_of_objects <= cap):
        v.errors.append(f"no_of_objects must be 1-{cap}")
    _check_evidence(v, ctx)


def _analytics_scope(v: Verdict, ctx: ValidationContext) -> None:
    if v.row.excluded:
        v.row.exclusion_evidence = _grounded(v.row.exclusion_evidence, v, ctx, label="exclusion: ")


def _wave_plan(v: Verdict, ctx: ValidationContext) -> None:
    plan, timeline = v.row, ctx.ledger.timeline.data
    waves = [w.name for w in timeline.waves] if timeline and timeline.waves else ["Wave 1"]
    lobs = {s.lob for s in ctx.ledger.scope_items.rows}
    phases = set(ctx.policy.resourcing.default_phase_split)
    for a in plan.allocations:
        ws = a.workstream.strip()
        if ws.startswith(LOB_WORKSTREAM_PREFIX):
            if ws[len(LOB_WORKSTREAM_PREFIX):] not in lobs:
                v.errors.append(f"{ws}: no scope items carry that LOB (use 'lob:<LOB>' exactly as in scope_items)")
        elif ws not in FIXED_WORKSTREAMS:
            v.errors.append(f"unknown workstream '{ws}'; use lob:<LOB> or one of {list(FIXED_WORKSTREAMS)}")
        unknown = [w for w in a.shares if w not in waves]
        if unknown:
            v.errors.append(f"{ws}: unknown waves {unknown}; waves are {waves}")
        total = sum(max(s, 0.0) for s in a.shares.values())
        if total <= 0:
            v.errors.append(f"{ws}: shares must be positive")
        elif abs(total - 1.0) > 0.001:
            if abs(total - 1.0) <= 0.1:
                a.shares = {w: round(max(s, 0.0) / total, 6) for w, s in a.shares.items()}
                v.notes.append(f"{ws}: shares summed to {total:.3f}; normalised to 1")
            else:
                v.errors.append(f"{ws}: shares sum to {total:.3f}; they must sum to 1")
    items = {s.row_id: s for s in ctx.ledger.scope_items.rows}
    for tag in plan.item_tags:
        if tag.wave not in waves:
            v.errors.append(f"tag {tag.row_id}: unknown wave '{tag.wave}'")
        item = items.get(tag.row_id)
        if item is None:
            v.errors.append(f"tag {tag.row_id}: no such scope_items row")
        elif tag.country and tag.country not in item.countries:
            v.errors.append(f"tag {tag.row_id}: {item.scope_item_id} is not delivered in {tag.country}")
    dm_ids = {r.row_id for r in ctx.ledger.data_migration.rows}
    dm_keys = set(ctx.policy.workstreams["data_migration"]["effort_keys"])
    seen_dm: set[str] = set()
    for d in plan.data_migration_waves:
        if d.wave not in waves:
            v.errors.append(f"data_migration_waves: unknown wave '{d.wave}'; waves are {waves}")
        if d.wave in seen_dm:
            v.errors.append(f"data_migration_waves: '{d.wave}' given twice")
        seen_dm.add(d.wave)
        if not 0 < d.scale <= 10:
            v.errors.append(f"data_migration_waves {d.wave}: scale {d.scale} must be > 0 and <= 10")
        bad_keys = [k for k in d.key_scale if k not in dm_keys]
        if bad_keys:
            v.errors.append(f"data_migration_waves {d.wave}: unknown key_scale keys {bad_keys}; use {sorted(dm_keys)}")
        if any(not 0 <= x <= 10 for x in d.key_scale.values()):
            v.errors.append(f"data_migration_waves {d.wave}: key_scale factors must be 0-10")
        unknown = [o for o in d.objects if o not in dm_ids]
        if unknown:
            v.errors.append(f"data_migration_waves {d.wave}: no data_migration rows {unknown[:10]}")
    for p in plan.phases:
        if p.wave not in waves:
            v.errors.append(f"phase plan for unknown wave '{p.wave}'")
        dropped = [k for k in p.phase_split if k not in phases or p.phase_split[k] <= 0]
        if dropped:
            v.notes.append(f"{p.wave}: ignored phase weights {dropped} (phases are {sorted(phases)})")
            p.phase_split = {k: x for k, x in p.phase_split.items() if k in phases and x > 0}


def _response_requirements(v: Verdict, ctx: ValidationContext) -> None:
    for e in v.row.section_excerpts:
        if len(e.excerpt) > 400:
            e.excerpt = e.excerpt[:400]
            v.notes.append(f"excerpt for {e.section_id} cut to 400 chars")
        if ctx.corpus is not None and not ctx.corpus.contains(e.excerpt[:200]):
            v.errors.append(f"excerpt for {e.section_id} is not verbatim RFP text")
    for r in v.row.requirements:
        if not r.evidence:
            v.notes.append(f"requirement '{r.title}' has no evidence quote")


_RULES: dict[str, Callable[[Verdict, ValidationContext], None]] = {
    "rfp_profile": _rfp_profile, "capabilities": _capabilities, "timeline": _timeline,
    "scope_items": _scope_items, "non_catalogue": _non_catalogue, "integrations": _integrations,
    "ricefw": _ricefw, "fiori": _fiori, "data_migration": _data_migration, "basis": _basis,
    "security": _security, "analytics": _analytics, "analytics_scope": _analytics_scope,
    "wave_plan": _wave_plan, "response_requirements": _response_requirements,
}


def validate(section: str, items: list[Any], ctx: ValidationContext) -> list[Verdict]:
    """Coerce each item to the section model, then apply the section's rules."""
    model = SECTIONS[section].model
    verdicts: list[Verdict] = []
    for index, raw in enumerate(items):
        try:
            row = raw if isinstance(raw, model) else model.model_validate(
                raw.model_dump() if isinstance(raw, BaseModel) else raw)
        except Exception as exc:  # pydantic ValidationError -> readable message
            verdicts.append(Verdict(index, model.model_construct(), [f"schema: {exc}".replace("\n", " ")[:600]]))
            continue
        verdict = Verdict(index, row)
        _RULES[section](verdict, ctx)
        verdicts.append(verdict)
    return verdicts
