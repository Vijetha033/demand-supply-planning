"""Mitigations respect policy and capacity and show trade-offs (acceptance criteria)."""
from datetime import date, timedelta


def test_one_recommendation_per_shortage(run):
    mo, sh = run["outputs"]["mitigation_option"], run["outputs"]["shortage"]
    rec = mo[mo.is_recommended.astype(bool)]
    assert rec.shortage_id.is_unique and set(rec.shortage_id) == set(sh.shortage_id)
    assert (rec.option_rank == 1).all()


def test_tradeoffs_have_cost_and_service(run):
    mo = run["outputs"]["mitigation_option"]
    for c in ["total_cost", "incremental_cost", "fill_rate_pct", "weeks_late", "service_score", "net_benefit"]:
        assert mo[c].notna().all(), c
    assert (mo.groupby("shortage_id").size() >= 1).all()
    assert mo.mitigation_type.nunique() >= 4


def test_new_orders_respect_moq_multiple_and_lead_time(run):
    t, o = run["inputs"], run["outputs"]
    mo, sh = o["mitigation_option"], o["shortage"].set_index("shortage_id")
    terms = t["supplier_sku"].set_index(["supplier_id", "sku_id"])
    as_of = date.fromisoformat(t["calendar_week"].week_start_date.min())
    pos = mo[mo.mitigation_type.isin(["NEW_PO_PRIMARY", "NEW_PO_ALTERNATE"])]
    assert len(pos) > 0
    for r in pos.itertuples():
        s = sh.loc[r.shortage_id]
        tm = terms.loc[(r.supplier_id, s.sku_id)]
        assert r.order_qty_purchase_uom >= tm.min_order_qty
        assert r.order_qty_purchase_uom % tm.order_multiple == 0
        earliest = (as_of + timedelta(days=int(r.lead_time_days)) - as_of).days // 7
        assert r.arrival_week_index >= earliest, "supply cannot arrive before the lead time"
        assert r.arrival_week_index <= s.end_week_index


def test_capacity_never_overbooked(run):
    u = run["outputs"]["supplier_capacity_utilization"]
    assert (u.planned_committed_units + u.mitigation_reserved_units <= u.capacity_units).all()
    p = run["outputs"]["production_capacity_utilization"]
    assert (p.planned_units + p.mitigation_reserved_units <= p.capacity_units).all()


def test_unapproved_substitutes_never_proposed(run):
    t, o = run["inputs"], run["outputs"]
    sub = t["sku_substitute"].set_index("substitution_id")
    used = o["mitigation_option"].substitution_id.dropna()
    assert (sub.loc[used].approval_status == "APPROVED").all()
    unapproved = set(sub.index[sub.approval_status != "APPROVED"])
    assert unapproved and not (set(used) & unapproved)
    rj = o["rejected_mitigation"]
    assert (rj.reason_code == "SUBSTITUTE_NOT_APPROVED").any()


def test_on_hold_suppliers_rejected(run):
    t, o = run["inputs"], run["outputs"]
    held = set(t["supplier"].supplier_id[t["supplier"].status == "ON_HOLD"])
    assert not (set(o["mitigation_option"].supplier_id.dropna()) & held - set(
        o["mitigation_option"][o["mitigation_option"].mitigation_type == "EXPEDITE_PO"].supplier_id))
