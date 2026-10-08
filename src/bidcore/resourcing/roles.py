"""Who staffs a wave: the deterministic role roster (ported from resource_grid_layer4.py).

Why the roster is shaped this way:

* Programme roles come in two policy tiers. A programme has ONE Program Manager and ONE Solution
  Architect however many waves run (singular tier); every wave in flight needs its own Project Manager,
  Cutover Manager, OCM and Training leads at the same time (per-wave tier) - one Cutover Manager cannot
  cut over three countries at once. The tier is the policy list a role sits in, so it cannot drift.
* A LOB divided into cross-mapped sub-modules gets one lead per sub-module and none of its own (a lead
  per LOB AND per division double-staffs the stream). LOB and sub-module leads are DISTRIBUTIVE: the
  senior consultant of the pod, paid out of the LOB's approved catalogue days, and keyed on the parent
  LOB so all of a LOB's carrier rows reconcile against one total. Each lead is sized by the effort its
  entity brings, so a sub-module holding 60% of the scope is not staffed like one holding 5%.
* Every LOB also gets one distributive consultants row: where its approved catalogue days live.
* Non-catalogue tools and third-party integrations are POOLED and staffed by capacity
  (days / (working days x programme months) people: one lead, the rest consultants), because a lead
  per entry inflated small blocks into whole teams. Project-management systems are the exception the
  client asked for: they keep a named (additive) lead. Which systems those are is a keyword floor here
  (`is_project_management`) plus whatever the agent flagged; the old LLM classifier is gone.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from bidcore.policy import Policy, get_policy
from bidcore.resourcing.models import ONSITE, RoleSpec, WaveResourceGrid
from bidcore.resourcing.rounding import quantize_half

PROGRAMME_ENTITY = "Programme"
# Reference row order inside a location block (the reference proposal's Tables 22/23).
_KIND_ORDER = {"programme": 0, "lob": 1, "submodule": 2, "technical": 3, "non_catalogue": 4, "third_party": 5}


def clean(name: Any) -> str:
    """Whitespace-collapsed, stripped text (the key every LOB / entity map is matched on)."""
    return re.sub(r"\s+", " ", str(name or "")).strip()


def is_project_management(name: str, policy: Policy | None = None) -> bool:
    """True when `name` contains a policy project-management keyword ("MS Project Online" hits
    "ms project"). Keyword list only - the deterministic floor the old LLM classifier sat on."""
    lowered = clean(name).lower()
    if not lowered:
        return False
    keywords = (policy or get_policy()).resourcing.project_management_keywords
    return any(keyword in lowered for keyword in keywords)


def project_management_names(
    names: Iterable[str], flagged: Iterable[str] = (), policy: Policy | None = None
) -> set[str]:
    """The systems that keep a named lead: keyword hits among `names` plus everything the agent flagged
    (`is_project_management` on a ledger row). Use the same set to take their days out of the pools."""
    hits = {clean(n) for n in names if clean(n) and is_project_management(n, policy)}
    return hits | {clean(n) for n in flagged if clean(n)}


def third_party_display_name(name: Any) -> str:
    """A plain system name for a lead title: whitespace collapsed, and an interface description
    ("Kronos <-> SAP HCM: time and attendance") cut back to the system it opens with."""
    text = clean(name)
    head = clean(re.split(r"\s*(?:<->|->|<-|:)\s*", text, maxsplit=1)[0])
    return head or text


def effort_scaled_fte(
    base_fte: float, entity_days: float, peer_days: Iterable[float], policy: Policy | None = None
) -> float:
    """A lead's FTE scaled by the effort its entity carries relative to its peers' average.

    An average entity is staffed at `base_fte`, one with twice the average at twice it, within the
    policy lead bounds and on the FTE grain. Falls back to `base_fte` when there is nothing to scale by."""
    res = (policy or get_policy()).resourcing
    low, high = res.lead_fte_bounds
    peers = [float(d or 0.0) for d in peer_days if float(d or 0.0) > 0]
    entity_days = float(entity_days or 0.0)
    if entity_days <= 0 or not peers:
        return quantize_half(base_fte, res.fte_grain) or low
    average = sum(peers) / len(peers)
    scaled = base_fte * (entity_days / average)
    return min(max(quantize_half(scaled, res.fte_grain), low), high)


def pooled_lead_count(
    effort_days: float,
    programme_months: float,
    working_days_per_month: float | None = None,
    policy: Policy | None = None,
) -> int:
    """People a pooled block needs end to end: days / (working days x programme months), half-up.

    The client's rule: 300 PD over a 5-month programme at 21 days/month = 2.9 -> 3 people. Never 0 for
    a block that carries any effort (a fortnight's work still needs an owner)."""
    if working_days_per_month is None:
        working_days_per_month = (policy or get_policy()).commercials.working_days_per_month
    effort_days = float(effort_days or 0.0)
    if effort_days <= 0:
        return 0
    capacity = float(working_days_per_month or 0) * float(programme_months or 0)
    if capacity <= 0:
        return 1
    return max(1, int(math.floor(effort_days / capacity + 0.5)))


def submodules_for(submodules_by_lob: Mapping[str, Iterable[str]] | None, lob_name: str) -> list[str]:
    """The LOB's cross-mapped sub-module names (matched case-insensitively, de-duplicated).

    A LOB whose only "sub-module" repeats its own name is NOT divided (Finance -> ["Finance"] is the
    same stream under another spelling): that returns []."""
    if not submodules_by_lob:
        return []
    wanted = clean(lob_name).casefold()
    names: list[str] = []
    for key, values in submodules_by_lob.items():
        if clean(key).casefold() != wanted:
            continue
        for value in values or []:
            name = clean(value)
            if name and name not in names:
                names.append(name)
        break
    if len(names) == 1 and names[0].casefold() == wanted:
        return []
    return names


def pooled_roles(
    third_party_days: float,
    non_catalogue_days: float,
    programme_months: float,
    policy: Policy | None = None,
) -> list[RoleSpec]:
    """Lead + numbered consultants for each pooled block, sized by `pooled_lead_count`.

    DISTRIBUTIVE on purpose: the block's person-days are already in the project total, so these rows
    only spread them over months and people; staffing them additively would bill the client twice."""
    policy = policy or get_policy()
    res = policy.resourcing
    specs: list[RoleSpec] = []
    for kind, days in (("third_party", third_party_days), ("non_catalogue", non_catalogue_days)):
        count = pooled_lead_count(days, programme_months, policy=policy)
        if count <= 0:
            continue
        profile, titles, entity = res.lead_profiles[kind], res.pool_roles[kind], res.pools[kind]
        specs.append(RoleSpec(
            role_title=titles["lead"], location=profile.location, entity_kind=kind, entity_name=entity,
            contribution="distributive", fte=1.0, window=profile.window,
            entity_effort_days=round(float(days or 0.0), 2),
        ))
        for index in range(1, count):
            specs.append(RoleSpec(
                role_title=f"{titles['consultant']} {index}", location=res.consultant_profile["location"],
                entity_kind=kind, entity_name=entity, contribution="distributive", fte=1.0,
                window=profile.window,
            ))
    return specs


def required_roles(
    lobs: Iterable[str],
    non_catalogue_names: Iterable[str] = (),
    third_party_names: Iterable[str] = (),
    include_singular_programme_roles: bool = True,
    submodules_by_lob: Mapping[str, Iterable[str]] | None = None,
    submodule_effort_by_lob: Mapping[str, Mapping[str, float]] | None = None,
    approved_effort_by_lob: Mapping[str, float] | None = None,
    programme_months: float = 0.0,
    pooled_third_party_days: float = 0.0,
    pooled_non_catalogue_days: float = 0.0,
    pm_names: Iterable[str] | None = None,
    policy: Policy | None = None,
) -> list[RoleSpec]:
    """The roles one wave's grid must cover (see the module docstring).

    `lobs` are the LOBs this wave staffs, in order. `include_singular_programme_roles=False` omits only
    the one-per-programme tier; the per-wave tier always stays. Keys of the effort maps are cleaned
    LOB names (`clean`)."""
    policy = policy or get_policy()
    res = policy.resourcing
    formats = res.role_title_formats
    consultant = res.consultant_profile
    roles: list[RoleSpec] = []
    seen: set[str] = set()

    def add(spec: RoleSpec) -> None:
        if spec.role_title and spec.key not in seen:
            seen.add(spec.key)
            roles.append(spec)

    tier = [*res.programme_singular_roles, *res.programme_per_wave_roles] if include_singular_programme_roles \
        else list(res.programme_per_wave_roles)
    for role in tier:
        add(RoleSpec(role_title=role.title, location=role.location, entity_kind="programme",
                     entity_name=PROGRAMME_ENTITY, contribution="additive", fte=role.fte, window=role.window))

    lobs = [clean(lob) for lob in lobs]
    submodule_effort_by_lob = submodule_effort_by_lob or {}
    approved = approved_effort_by_lob or {}
    # Only the LOBs that raise a LOB-level lead compete with one another for its sizing.
    lob_peer_days = [float(approved.get(lob, 0.0) or 0.0) for lob in lobs
                     if not submodules_for(submodules_by_lob, lob)]

    for lob in lobs:
        if not lob:
            continue
        submodules = submodules_for(submodules_by_lob, lob)
        if submodules:
            effort = submodule_effort_by_lob.get(lob) or {}
            peers = [float(effort.get(name, 0.0) or 0.0) for name in submodules]
            profile = res.lead_profiles["submodule"]
            for name in submodules:
                add(RoleSpec(
                    role_title=formats["lead"].format(name=name), location=profile.location,
                    entity_kind="submodule", entity_name=lob, contribution="distributive",
                    fte=effort_scaled_fte(profile.fte, effort.get(name, 0.0), peers, policy),
                    window=profile.window, entity_effort_days=round(float(effort.get(name, 0.0) or 0.0), 2),
                ))
        else:
            profile = res.lead_profiles["lob"]
            add(RoleSpec(
                role_title=formats["lead"].format(name=lob), location=profile.location, entity_kind="lob",
                entity_name=lob, contribution="distributive",
                fte=effort_scaled_fte(profile.fte, approved.get(lob, 0.0), lob_peer_days, policy),
                window=profile.window, entity_effort_days=round(float(approved.get(lob, 0.0) or 0.0), 2),
            ))
        # Raised per LOB whether or not it is divided: approved effort reconciles by LOB.
        add(RoleSpec(
            role_title=formats["consultants"].format(name=lob), location=consultant["location"],
            entity_kind="lob", entity_name=lob, contribution="distributive", fte=consultant["fte"],
            window=tuple(consultant["window"]),
        ))

    # Project-management systems keep a named lead; everything else in the two blocks is pooled.
    pm = {clean(n).casefold() for n in (pm_names or ()) if clean(n)}
    profile = res.lead_profiles["non_catalogue"]
    for raw in non_catalogue_names or ():
        name = clean(raw)
        if name and name.casefold() in pm:
            add(RoleSpec(role_title=formats["lead"].format(name=name), location=profile.location,
                         entity_kind="non_catalogue", entity_name=name, contribution="additive",
                         fte=profile.fte, window=profile.window))
    profile = res.lead_profiles["third_party"]
    for raw in third_party_names or ():
        name = third_party_display_name(raw)
        if name and (name.casefold() in pm or clean(raw).casefold() in pm):
            add(RoleSpec(role_title=formats["integration_lead"].format(name=name), location=profile.location,
                         entity_kind="third_party", entity_name=name, contribution="additive",
                         fte=profile.fte, window=profile.window))

    for spec in pooled_roles(pooled_third_party_days, pooled_non_catalogue_days, programme_months, policy):
        add(spec)
    return roles


def sort_rows(grid: WaveResourceGrid) -> None:
    """Onsite block first, then Offshore; within each: kind, additive before distributive, title."""
    grid.rows.sort(key=lambda r: (
        0 if r.location == ONSITE else 1,
        _KIND_ORDER.get(r.entity_kind, 9),
        0 if r.contribution == "additive" else 1,
        r.role_title.lower(),
    ))
