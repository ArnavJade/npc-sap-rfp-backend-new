from bidcore.evidence import CorpusIndex
from bidcore.ledger.models import new_ledger
from bidcore.ledger.overlap import find_overlaps, normalize_system_name
from bidcore.ledger.sections_effort import Integration, NonCatalogueItem, ScopeItem, SecurityActivity
from bidcore.ledger.store import LedgerStore
from bidcore.ledger.validate import is_catalogue_covered, validate
from tests.conftest import ev


def test_corpus_index_finds_split_and_paraphrase_rejected(rfp_dir):
    corpus = CorpusIndex.from_dir(rfp_dir)
    assert corpus.contains("cash and liquidity management")
    assert corpus.contains("Wave 1: 44 weeks including 12 weeks Hypercare")
    assert not corpus.contains("treasury workstation for global banks")


def test_store_update_is_versioned_and_audited(tmp_path):
    store = LedgerStore(tmp_path / "ledger")
    store.save(new_ledger("b1"))
    store.update(lambda l: setattr(l.meta, "client_name", "ARASCO"), actor="test", action="rename")
    led = store.load()
    assert led.meta.client_name == "ARASCO" and led.meta.version == 2 and led.audit[-1].actor == "test"
    assert store.checkpoint("after").name.startswith("v002")


def test_scope_item_filled_from_catalogue_and_availability_enforced(vctx):
    [v] = validate("scope_items", [ScopeItem(scope_item_id="J78", countries=["SA"], evidence=[ev("cash and liquidity management")])], vctx)
    assert v.ok, v.errors
    assert v.row.lob == "Finance" and v.row.business_area == "Treasury Management"
    [bad] = validate("scope_items", [ScopeItem(scope_item_id="ZZZ")], vctx)
    assert not bad.ok and "not in the catalogue" in bad.errors[0]


def test_evidence_must_be_verbatim(vctx):
    [v] = validate("integrations", [Integration(system="Kronos", effort_days=20, evidence=[ev("Kronos | Time and attendance")])], vctx)
    assert v.ok, v.errors
    [bad] = validate("integrations", [Integration(system="Kronos", effort_days=20, evidence=[ev("payroll engine replacement")])], vctx)
    assert not bad.ok and "not found in the RFP" in bad.errors[0]


def test_security_and_dm_values_are_normalised(vctx):
    [sec] = validate("security", [SecurityActivity(activity="Role design", effort_days=500,
                                                   evidence=[ev("Role design and authorizations")])], vctx)
    assert sec.ok and sec.row.effort_days == 120 and sec.notes
    [dm] = validate("data_migration", [{"object": "Material Master", "func_spec": 2.6, "evidence": [ev("material master")]}], vctx)
    assert dm.ok and dm.row.func_spec == 3.0


def test_non_catalogue_rules(vctx):
    assert is_catalogue_covered("FI", {"fi", "co"}) and is_catalogue_covered("Controlling (CO)", {"co"})
    [covered] = validate("non_catalogue", [NonCatalogueItem(name="MM/SD", effort_band="sap_tool_light", effort_days=10)], vctx)
    assert not covered.ok
    [ok] = validate("non_catalogue", [NonCatalogueItem(name="SAP Solution Manager", effort_band="sap_tool_standard",
                                                       effort_days=30, evidence=[ev("SAP Solution Manager")])], vctx)
    assert ok.ok, ok.errors


def test_wave_plan_normalises_and_rejects_unknown_waves(vctx, ledger):
    ledger.scope_items.rows = [ScopeItem(row_id="si-1", scope_item_id="J78", lob="Finance", countries=["SA"])]
    plan = {"allocations": [{"workstream": "lob:Finance", "shares": {"Wave 1": 0.95}}],
            "phases": [{"wave": "Wave 1", "phase_split": {"Prepare": 0.1, "Hypercare": 0.5}}]}
    [v] = validate("wave_plan", [plan], vctx)
    assert v.ok, v.errors
    assert v.row.allocations[0].shares == {"Wave 1": 1.0} and "Hypercare" not in v.row.phases[0].phase_split
    [bad] = validate("wave_plan", [{"allocations": [{"workstream": "lob:Finance", "shares": {"Wave 9": 1}}]}], vctx)
    assert not bad.ok


def test_overlaps_reported_with_winner(ledger):
    ledger.integrations.rows = [Integration(row_id="int-1", system="Kronos system", effort_days=20)]
    ledger.non_catalogue.rows = [NonCatalogueItem(row_id="nc-1", name="Kronos", effort_days=10),
                                 NonCatalogueItem(row_id="nc-2", name="SAP GRC Access Control", effort_days=30)]
    ledger.security.rows = [SecurityActivity(row_id="sec-1", activity="GRC Access Control implementation",
                                             sap_product="SAP GRC Access Control", effort_days=30)]
    found = {(o.keep_row_id, o.drop_row_id) for o in find_overlaps(ledger)}
    assert ("int-1", "nc-1") in found and ("sec-1", "nc-2") in found
    assert normalize_system_name("Marel system") == "marel"


def test_non_catalogue_band_is_derived_not_rejected(vctx):
    # Gemini sent effort_band "M" for every tool; the band is now derived from kind + effort with a note.
    [tool] = validate("non_catalogue", [NonCatalogueItem(name="SAP Solution Manager", effort_band="M", effort_days=5,
                                                         evidence=[ev("SAP Solution Manager")])], vctx)
    assert tool.ok and tool.row.effort_band == "sap_tool_light" and tool.notes
    [module] = validate("non_catalogue", [NonCatalogueItem(name="SAP Solution Manager", kind="sap_module_no_bp",
                                                           evidence=[ev("SAP Solution Manager")])], vctx)
    assert module.ok and module.row.effort_band == "sap_module_no_best_practice" and module.row.effort_days == 40
