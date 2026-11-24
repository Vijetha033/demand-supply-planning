"""Projected available balance, shortages, causes and prioritisation."""
import numpy as np

from supply_planning.generator import dependent_demand_units
from supply_planning.planning import local_baseline, master_uom_factor


def test_pab_reconciles_week_by_week(run):
    pab = run["outputs"]["projected_balance"].sort_values(["sku_id", "location_id", "week_index"])
    calc = pab.opening_balance + pab.scheduled_receipts + pab.planned_production - pab.forecast_demand - \
        pab.dependent_demand
    assert (calc == pab.closing_balance).all()
    prev = pab.groupby(["sku_id", "location_id"]).closing_balance.shift()
    assert ((prev == pab.opening_balance) | prev.isna()).all()


def test_receipts_reconcile_to_purchase_orders(run):
    sr, pab = run["outputs"]["scheduled_receipt"], run["outputs"]["projected_balance"]
    assert sr[sr.counted_in_plan.astype(bool)].planning_base_qty.sum() == pab.scheduled_receipts.sum()
    assert not sr.po_status.eq("RECEIVED").any(), "received POs are already in on-hand"


def test_every_shortage_has_explainable_causes(run):
    sh, sc = run["outputs"]["shortage"], run["outputs"]["shortage_cause"]
    assert len(sh) > 0
    assert set(sh.shortage_id) == set(sc.shortage_id)
    assert sh.cause_summary.str.contains("opening").all()
    m = sc.merge(sh[["shortage_id", "shortage_qty"]])
    assert (m.contribution_qty <= m.shortage_qty).all()
    # at least some shortages are attributed to each of the generator's scenario drivers
    codes = set(sc.cause_code)
    assert {"SUPPLIER_CAPACITY_CONSTRAINT", "DEMAND_SPIKE", "PRODUCTION_CAPACITY_CONSTRAINT"} <= codes


def test_shortage_is_peak_deficit_of_negative_run(run):
    pab = run["outputs"]["projected_balance"].set_index(["sku_id", "location_id", "week_index"]).closing_balance
    for r in run["outputs"]["shortage"].itertuples():
        seg = [pab[(r.sku_id, r.location_id, w)] for w in range(r.start_week_index, r.end_week_index + 1)]
        assert max(seg) < 0 and -min(seg) == r.shortage_qty


def test_priority_ranking(run):
    sh = run["outputs"]["shortage"].sort_values("priority_rank")
    assert sh.priority_score.is_monotonic_decreasing
    assert set(sh.priority_tier) <= {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    crit = sh[sh.priority_tier == "CRITICAL"]
    assert ((crit.within_lead_time.astype(bool)) | (crit.priority_score >= 75)).all()


def test_uom_factor_rules():
    assert master_uom_factor("CS", "CS", 12, "EA", 12) == 12
    assert master_uom_factor("EA", "CS", 12, "EA", 12) == 1
    assert master_uom_factor("CS", "EA", 1, "EA", 24) == 24
    assert np.isnan(master_uom_factor("KG", "CS", 12, "EA", 12))


def test_dependent_demand_rounding():
    assert dependent_demand_units(5.000000000001) == 5
    assert dependent_demand_units(5.2) == 6


def test_spike_baseline_ignores_inactive_weeks():
    D = np.array([[0, 0, 0, 10, 10, 30, 10, 10, 10]])
    active = D > 0
    base = local_baseline(D, active, 9)
    assert base[0, 5] == 10
