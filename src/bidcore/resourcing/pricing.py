"""Price a resource plan (ported from resource_grid_layer4.price_grid).

Why the split: adding the whole grid to the catalogue effort would double-count the delivery team,
so each row says what it costs.

* Implementation months of ADDITIVE rows (roles the rate card never prices: programme roles, named
  PM-system leads, specialist category consultants) are billed at the blended daily rate.
* Implementation months of DISTRIBUTIVE rows cost nothing here: the catalogue already paid for them.
* Hypercare (PGLS) months of EVERY row are billed at the hypercare onsite/offshore rates, because
  catalogue effort covers implementation only - no PGLS month is ever already paid for.

1 man-month = policy working_days_per_month person-days.
"""

from __future__ import annotations

from bidcore.policy import Policy, get_policy
from bidcore.resourcing.models import ONSITE, ResourcePlan


def price_plan(
    plan: ResourcePlan,
    policy: Policy | None = None,
    *,
    daily_rate: float | None = None,
    hc_onsite_rate: float | None = None,
    hc_offshore_rate: float | None = None,
) -> ResourcePlan:
    """Price `plan` in place (recomputing every grid's totals) and return it.

    Rates default to policy commercials; pass them to price with reviewer-overridden rates."""
    policy = policy or get_policy()
    commercials = policy.commercials
    daily_rate = commercials.daily_rate_usd if daily_rate is None else daily_rate
    hc_onsite_rate = commercials.hypercare.onsite_rate_usd if hc_onsite_rate is None else hc_onsite_rate
    hc_offshore_rate = commercials.hypercare.offshore_rate_usd if hc_offshore_rate is None else hc_offshore_rate
    days_per_month = commercials.working_days_per_month
    hypercare_phase = policy.resourcing.hypercare_phase

    additive_days = onsite_days = offshore_days = 0.0
    for grid in plan.grids:
        grid.recompute_totals()
        for row in grid.rows:
            for cell in row.cells:
                days = cell.fte * days_per_month
                if cell.phase == hypercare_phase:
                    if row.location == ONSITE:
                        onsite_days += days
                    else:
                        offshore_days += days
                elif row.contribution == "additive":
                    additive_days += days

    plan.additive_effort_days = round(additive_days, 2)
    plan.additive_cost_usd = round(additive_days * daily_rate, 2)
    plan.hypercare_effort_days = round(onsite_days + offshore_days, 2)
    plan.hypercare_onsite_cost_usd = round(onsite_days * hc_onsite_rate, 2)
    plan.hypercare_offshore_cost_usd = round(offshore_days * hc_offshore_rate, 2)
    return plan
