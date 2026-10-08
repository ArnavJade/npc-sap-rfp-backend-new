"""A complete, realistic call-1 ledger built in code (no LLM): the input of render / workflow tests."""

from __future__ import annotations

from bidcore.ledger.models import Ledger, new_ledger
from bidcore.ledger.sections_effort import (
    AnalyticsObject, AnalyticsScope, BasisActivity, Capability, CountryScope, DataMigrationObject, Fiori,
    Integration, ItemTag, NonCatalogueItem, RfpProfile, Ricefw, RicefwRow, ScopeItem, SecurityActivity, Timeline,
    Wave, WaveAllocation, WavePhasePlan, WavePlan,
)

FINANCE = ["J58", "1GA", "2FD", "33Q"]
PROCUREMENT = ["4QN", "2ME"]


def _ev(quote: str = "SAP S/4HANA", page: str = "1") -> list[dict]:
    return [{"quote": quote, "file": "rfp/acme.md", "page": page}]


def build_ledger(bid_id: str = "fixture01", client: str = "ACME Foods") -> Ledger:
    led = new_ledger(bid_id, client)
    led.rfp_profile.data = RfpProfile(
        client_name=client, engagement_type="greenfield", summary="SAP S/4HANA for two countries.",
        countries=[CountryScope(code="SA", name="Saudi Arabia"), CountryScope(code="AE", name="UAE")])
    led.capabilities.rows = [Capability(row_id="cap-1", capability="Finance", sap_module_hint="FI"),
                             Capability(row_id="cap-2", capability="Procurement", sap_module_hint="MM")]
    rows = [ScopeItem(row_id=f"si-{i + 1}", scope_item_id=sid, lob="Finance",
                      business_area="Accounting and Financial Close", countries=["SA", "AE"],
                      submodule="Financial Accounting (FI)" if i < 2 else "Controlling (CO)")
            for i, sid in enumerate(FINANCE)]
    rows += [ScopeItem(row_id=f"si-{len(FINANCE) + i + 1}", scope_item_id=sid, lob="Sourcing and Procurement",
                       business_area="Central Procurement", countries=["SA"]) for i, sid in enumerate(PROCUREMENT)]
    rows.append(ScopeItem(row_id="si-99", scope_item_id="ZZZ", lob="R&D/Engineering", business_area="Product Lifecycle",
                          countries=["SA"]))                       # unpriced -> zero line, '/' in sheet name
    led.scope_items.rows = rows
    led.non_catalogue.rows = [NonCatalogueItem(row_id="nc-1", name="SAP Solution Manager 7.2", effort_days=25,
                                               description="ALM and test management", evidence=_ev())]
    led.integrations.rows = [Integration(row_id="int-1", system="Kronos", effort_days=30, complexity="High",
                                         middleware="SAP CPI", source_system="Kronos", target_system="SAP HCM"),
                             Integration(row_id="int-2", system="Primavera", effort_days=20,
                                         is_project_management=True)]
    led.ricefw.data = Ricefw(rows=[RicefwRow(object_type="Report", no_of_objects=6, complexity="Medium"),
                                   RicefwRow(object_type="Form", no_of_objects=3, complexity="High")],
                             interface_total_count=5)
    led.fiori.data = Fiori(app_count=2)
    led.data_migration.rows = [DataMigrationObject(row_id="dm-1", object="Material Master", sap_module="MM"),
                               DataMigrationObject(row_id="dm-2", object="Vendor Master", sap_module="MM"),
                               DataMigrationObject(row_id="dm-3", object="Open Items", category="Transactional",
                                                   iteration_3=1.0)]
    led.basis.rows = [BasisActivity(row_id="bas-1", activity="System installation", dev=3, qa=2, prd=2),
                      BasisActivity(row_id="bas-2", activity="Solution Manager setup", status="Out of Scope")]
    led.security.rows = [SecurityActivity(row_id="sec-1", activity="Role design", effort_days=20, complexity="High"),
                         SecurityActivity(row_id="sec-2", activity="GRC Access Control", effort_days=15)]
    led.analytics.rows = [AnalyticsObject(row_id="ana-1", object="Sales dashboard", object_type="Model"),
                          AnalyticsObject(row_id="ana-2", object="AP ageing", no_of_objects=3, complexity="Low")]
    led.analytics_scope.data = AnalyticsScope()
    led.timeline.data = Timeline(
        waves=[Wave(name="Wave 1", sequence=1, total_weeks=44, hypercare_weeks=12, countries=["SA"],
                    duration_source="rfp"),
               Wave(name="Wave 2", sequence=2, total_weeks=30, hypercare_weeks=8, countries=["AE"],
                    duration_source="rfp")],
        sequencing="sequential", hypercare_required=True, hypercare_mode="inclusive")
    led.wave_plan.data = WavePlan(
        allocations=[WaveAllocation(workstream=ws, shares={"Wave 1": 0.7, "Wave 2": 0.3})
                     for ws in ("lob:Finance", "lob:Sourcing and Procurement", "lob:R&D/Engineering", "integrations",
                                "non_catalogue", "tech_dev", "data_migration", "basis", "security", "analytics")],
        item_tags=[ItemTag(row_id="si-1", country="AE", wave="Wave 2")],
        phases=[WavePhasePlan(wave="Wave 1", phase_split={"Prepare": 0.08, "Explore": 0.18, "Realize": 0.5,
                                                          "Deploy": 0.14}),
                WavePhasePlan(wave="Wave 2", phase_split={"Prepare": 0.05, "Explore": 0.1, "Realize": 0.6,
                                                          "Deploy": 0.25})])
    for name in ("rfp_profile", "capabilities", "timeline", "scope_items", "non_catalogue", "integrations", "ricefw",
                 "fiori", "data_migration", "basis", "security", "analytics", "analytics_scope", "wave_plan"):
        led.section(name).state = "written"
    return led
