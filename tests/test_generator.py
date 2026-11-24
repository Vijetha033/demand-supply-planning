"""Generator: volumes, parameterised scale, dependency order, lifecycle consistency."""
from dataclasses import replace

import pandas as pd

from supply_planning.config import load_config
from supply_planning.generator import BaselineGenerator, allocate_counts, pareto_abc


def test_volumes_match_config(run, cfg):
    t = run["inputs"]
    assert len(t["sku"]) == cfg.n_skus
    assert len(t["location"]) == cfg.n_locations
    assert (t["location"].location_type == "PLANT").sum() == cfg.n_plants
    assert len(t["supplier"]) == cfg.n_suppliers
    assert len(t["calendar_week"]) == cfg.n_weeks == 52
    gt = run["gt"]
    injected = gt[(gt.label_category == "EDGE_CASE") & (gt.record_type == "purchase_order")].shape[0] + \
        gt[(gt.label_category == "EDGE_CASE") & gt.issue_type.isin(["SUPPLIER_CAPACITY_EXCEEDED", "UOM_MISMATCH"])].shape[0]
    assert len(t["purchase_order"]) == cfg.n_purchase_orders + injected


def test_same_generator_scales_by_parameters():
    small = replace(load_config("test"), n_skus=40, n_suppliers=10, n_purchase_orders=150, n_locations=5)
    t, _ = BaselineGenerator(small).run()
    assert len(t["sku"]) == 40 and len(t["supplier"]) == 10 and len(t["purchase_order"]) == 150


def test_full_preset_meets_brief_volumes():
    full = load_config("full")
    assert (full.n_skus, full.n_locations, full.n_weeks, full.n_suppliers, full.n_purchase_orders) == \
        (3000, 50, 52, 500, 10000)
    assert full.seed == 20261022


def test_variation_present(run):
    t = run["inputs"]
    po = t["purchase_order"]
    assert po.transport_delay_days.gt(0).any(), "transport delays"
    assert (po.status == "CANCELLED").any() and (po.status == "RECEIVED").any() and (po.status == "IN_TRANSIT").any()
    assert len(t["sku_substitute"]) > 0, "substitute SKUs"
    pol = t["purchase_order_line"]
    assert (pol.order_qty < pol.requested_qty).any(), "constrained supplier cuts"
    pp = t["production_plan"]
    assert (pp.planned_qty < pp.required_qty).any(), "constrained plant"
    assert (t["lead_time"].version > 1).any(), "effective-dated lead-time revisions"
    assert set(t["sku"].lifecycle_status) == {"NEW", "ACTIVE", "PHASE_OUT"}


def test_po_status_is_derived_from_event_history(run):
    t = run["inputs"]
    last = t["purchase_order_event"].sort_values(["po_id", "event_seq"]).groupby("po_id").to_status.last()
    po = t["purchase_order"].set_index("po_id")
    assert (po.status == last.reindex(po.index)).all()


def test_allocate_counts_exact():
    alloc = allocate_counts(1000, pd.Series([1, 5, 10, 0.5]).to_numpy(), cap=400)
    assert sum(alloc) == 1000 and min(alloc) >= 2 and max(alloc) <= 400


def test_pareto_abc():
    abc = pareto_abc(pd.Series({"a": 80.0, "b": 15.0, "c": 5.0}))
    assert abc == {"a": "A", "b": "B", "c": "C"}
