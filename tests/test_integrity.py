"""IDs, keys, joins and the validation summary (brief steps 3 and 8)."""
import re

from supply_planning.ids import PATTERNS


def test_validation_passes_with_only_labelled_exceptions(run):
    s = run["summary"]
    assert s["overall_status"] == "PASS"
    assert s["n_unexpected"] == 0
    assert s["n_expected_labelled"] > 0          # the injected edge cases are caught by validation too


def test_every_check_category_ran(run):
    cats = set(run["summary"]["checks"].category)
    for c in ["schema", "primary_key", "foreign_key", "duplicate", "date_ordering", "arithmetic", "lifecycle",
              "reconciliation", "explainability", "policy", "capacity", "leakage"]:
        assert c in cats, c


def test_primary_and_foreign_keys_clean(run):
    checks = run["summary"]["checks"]
    keys = checks[checks.category.isin(["primary_key", "foreign_key"])]
    assert len(keys) > 30
    assert keys.violations.sum() == 0


def test_required_id_patterns(run):
    t, o = run["inputs"], run["outputs"]
    assert t["sku"].sku_id.str.match(PATTERNS["sku_id"]).all()
    assert t["sku"].sku_id.iloc[0] == "SKU-000001"
    assert t["forecast_demand"].demand_id.str.match(PATTERNS["demand_id"]).all()
    assert (t["forecast_demand"].demand_id == "DEM-" + t["forecast_demand"].sku_id + "-" +
            t["forecast_demand"].location_id + "-" + t["forecast_demand"].week_id).all()
    assert t["purchase_order"].po_id.str.match(PATTERNS["po_id"]).all()
    assert "PO-2026-000001" in set(t["purchase_order"].po_id)
    assert o["shortage"].shortage_id.str.match(PATTERNS["shortage_id"]).all()
    assert (o["shortage"].shortage_id.str[-6:].astype(int) == o["shortage"].priority_rank).all()
    mo = o["mitigation_option"]
    assert mo.mitigation_id.str.match(PATTERNS["mitigation_id"]).all()
    assert (mo.mitigation_id == "MIT-" + mo.shortage_id + "-" + mo.option_rank.astype(int).map("{:02d}".format)).all()


def test_ids_consistent_across_csv_and_json(run):
    import json
    root = run["root"]
    j = json.loads((root / "data/exports/test/json/purchase_order.json").read_text())
    assert [r["po_id"] for r in j] == sorted(run["inputs"]["purchase_order"].po_id)


def test_sql_seed_loads_with_foreign_keys(run):
    import sqlite3
    root = run["root"]
    con = sqlite3.connect(":memory:")
    con.executescript((root / "data/exports/test/sql/schema.sql").read_text())
    con.executescript((root / "data/exports/test/sql/seed.sql").read_text())
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert con.execute("select count(*) from purchase_order").fetchone()[0] == len(run["inputs"]["purchase_order"])
