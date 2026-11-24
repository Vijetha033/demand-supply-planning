"""Evaluation: compare engine decisions with ground truth and report metrics.

This is the ONLY module (with the validator's classification step) that reads
ground truth.  The planning engine never does.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .schema import EDGE_CASE_TYPES, INPUT_TABLES, ISSUE_TYPES, LEAKAGE_COLUMNS

ENGINE_MODULES = ["planning.py", "mitigation.py"]


def detection_metrics(gt: pd.DataFrame, issues: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for it in ISSUE_TYPES:
        g = gt[gt.issue_type == it]
        d = issues[issues.issue_type == it] if len(issues) else issues
        gs, ds = set(g.record_id), set(d.record_id) if len(d) else set()
        tp = len(gs & ds)
        fp, fn = len(ds - gs), len(gs - ds)
        dec = d.set_index("record_id").decision.to_dict() if len(d) else {}
        dec_ok = sum(dec.get(r) == e for r, e in zip(g.record_id, g.expected_decision))
        rows.append(dict(issue_type=it, category="EDGE_CASE" if it in EDGE_CASE_TYPES else "SCENARIO",
                         labelled=len(gs), detected=len(ds), true_positive=tp, false_positive=fp, false_negative=fn,
                         precision=round(tp / len(ds), 4) if ds else (1.0 if not gs else 0.0),
                         recall=round(tp / len(gs), 4) if gs else 1.0,
                         decision_accuracy=round(dec_ok / len(gs), 4) if gs else 1.0))
    return pd.DataFrame(rows)


def edge_case_impact(gt, t_in, out) -> list[dict]:
    """Quantify what a naive calculation would have got wrong for each edge case."""
    res = []
    sr = out["scheduled_receipt"].set_index("po_line_id")
    inv = t_in["inventory"]
    for r in gt[gt.label_category == "EDGE_CASE"].itertuples():
        if r.issue_type == "INBOUND_DOUBLE_COUNT":
            q = int(inv.set_index("inventory_id").at[r.record_id, "quantity"])
            res.append(dict(gt_id=r.gt_id, issue_type=r.issue_type, record_id=r.record_id,
                            naive_effect=f"+{q} phantom units of supply", engine_effect="excluded (counted once)"))
        elif r.issue_type == "UOM_MISMATCH":
            row = sr.loc[r.record_id]
            res.append(dict(gt_id=r.gt_id, issue_type=r.issue_type, record_id=r.record_id,
                            naive_effect=f"{int(row.source_base_qty)} units",
                            engine_effect=f"{int(row.planning_base_qty)} units ({row.adjustment_codes})"))
        elif r.issue_type == "SHORTAGE_WITHOUT_LEAD_TIME":
            lines = sr[sr.po_id == r.record_id]
            row = lines.iloc[0]
            res.append(dict(gt_id=r.gt_id, issue_type=r.issue_type, record_id=r.record_id,
                            naive_effect=f"receipt {row.source_receipt_date}",
                            engine_effect=f"receipt {row.planning_receipt_date}"))
        elif r.issue_type == "SUPPLIER_CAPACITY_EXCEEDED":
            pid = str(r.related_record_ids).split("|")[0]
            row = sr[sr.po_id == pid].iloc[0]
            res.append(dict(gt_id=r.gt_id, issue_type=r.issue_type, record_id=r.record_id,
                            naive_effect=f"receipt {row.source_receipt_date} ({r.expected_value})",
                            engine_effect=f"receipt {row.planning_receipt_date} ({row.adjustment_codes})"))
        elif r.issue_type == "SUBSTITUTE_NOT_APPROVED":
            rj = out["rejected_mitigation"]
            hit = rj[rj.candidate_ref.str.startswith(r.record_id + ":") & (rj.reason_code == "SUBSTITUTE_NOT_APPROVED")]
            mo = out["mitigation_option"]
            used = int((mo.substitution_id == r.record_id).sum())
            res.append(dict(gt_id=r.gt_id, issue_type=r.issue_type, record_id=r.record_id,
                            naive_effect="substitute stock would be offered as a mitigation",
                            engine_effect=f"rejected in {len(hit)} shortage evaluation(s); used in {used} options"))
    return res


def leakage_audit(src_dir: Path, t_in: dict) -> dict:
    hits = {}
    for m in ENGINE_MODULES:
        text = (src_dir / m).read_text()
        hits[m] = "ground_truth" in text or "gt_id" in text
    cols = {n: sorted(LEAKAGE_COLUMNS & set(t_in[n].columns)) for n in INPUT_TABLES}
    return dict(engine_modules_reference_ground_truth=hits,
                label_columns_in_inputs={k: v for k, v in cols.items() if v},
                passed=not any(hits.values()) and not any(cols.values()))


def distribution_stats(t_in: dict, out: dict) -> dict:
    fd = t_in["forecast_demand"]
    g = fd.groupby(["sku_id", "location_id"]).forecast_qty
    mean = g.mean()
    cv = (g.std() / mean.replace(0, np.nan)).dropna()
    sku = t_in["sku"]
    po = t_in["purchase_order"]
    pol = t_in["purchase_order_line"]
    lt = t_in["lead_time"]
    pab = out["projected_balance"]
    q = lambda s: {k: round(float(v), 2) for k, v in s.quantile([0.05, 0.25, 0.5, 0.75, 0.95]).items()}
    return {
        "weekly_demand_per_sku_location_quantiles": q(mean),
        "demand_cv_quantiles": q(cv),
        "zero_demand_week_share": round(float((fd.forecast_qty == 0).mean()), 4),
        "sku_mix": {"item_type": sku.item_type.value_counts().to_dict(),
                    "sourcing_type": sku.sourcing_type.value_counts().to_dict(),
                    "abc_class": sku.abc_class.value_counts().to_dict(),
                    "lifecycle_status": sku.lifecycle_status.value_counts().to_dict(),
                    "base_uom": sku.base_uom.value_counts().to_dict()},
        "unit_cost_quantiles": q(sku.unit_cost),
        "lead_time_days_quantiles": q(lt.total_lead_days),
        "transport_mode_mix": lt.transport_mode.value_counts().to_dict(),
        "po_status_mix": po.status.value_counts().to_dict(),
        "po_lines_per_order_quantiles": q(pol.groupby("po_id").size()),
        "po_delayed_share": round(float((po.transport_delay_days > 0).mean()), 4),
        "sku_location_weeks_short_share": round(float(pab.is_shortage.astype(bool).mean()), 4),
        "sku_location_weeks_below_safety_stock_share": round(float(pab.below_safety_stock.astype(bool).mean()), 4),
    }


def coverage_matrix(t_in: dict, out: dict, gt: pd.DataFrame) -> list[dict]:
    po, pol = t_in["purchase_order"], t_in["purchase_order_line"]
    ss = t_in["supplier_sku"].set_index("supplier_sku_id")
    u = out["supplier_capacity_utilization"]
    pab = out["projected_balance"]
    mo, rj, sh = out["mitigation_option"], out["rejected_mitigation"], out["shortage"]
    lt = t_in["lead_time"]
    rows = [
        ("NORMAL", "open PO lines received on promise (no delay)",
         int(((po.status.isin(["PLANNED", "CONFIRMED", "IN_TRANSIT"])) & (po.transport_delay_days == 0)).sum())),
        ("NORMAL", "SKU-location-weeks at or above safety stock", int((~pab.below_safety_stock.astype(bool)).sum())),
        ("BOUNDARY", "supplier-weeks at exactly 100 % source utilisation",
         int((u.source_committed_units == u.capacity_units).sum())),
        ("BOUNDARY", "SKU-location-weeks with projected balance exactly 0", int((pab.closing_balance == 0).sum())),
        ("BOUNDARY", "PO lines ordered at exactly MOQ",
         int((pol.order_qty == pol.supplier_sku_id.map(ss.min_order_qty)).sum())),
        ("BOUNDARY", "PO lines cut by supplier capacity (confirmed < requested)",
         int((pol.order_qty < pol.requested_qty).sum())),
        ("BOUNDARY", "lead-time lanes with a mid-horizon revision (version 2)", int((lt.version > 1).sum())),
        ("BOUNDARY", "shortages starting inside replenishment lead time", int(sh.within_lead_time.astype(bool).sum())),
        ("FAILURE", "cancelled purchase orders", int((po.status == "CANCELLED").sum())),
        ("FAILURE", "transport/production delay events", int((po.transport_delay_days > 0).sum())),
        ("FAILURE", "rejected mitigation candidates", len(rj)),
        ("FAILURE", "shortages left unmitigated (backorder recommended)", int((sh.status == "UNMITIGATED").sum())),
        ("EXCEPTION", "labelled edge cases injected", int((gt.label_category == "EDGE_CASE").sum())),
        ("EXCEPTION", "engine exceptions logged (detected_issue)", len(out["detected_issue"])),
    ]
    return [dict(coverage_class=a, scenario=b, count=c) for a, b, c in rows]


def planning_kpis(t_in: dict, out: dict) -> dict:
    sh, mo, pab = out["shortage"], out["mitigation_option"], out["projected_balance"]
    rec = mo[mo.is_recommended.astype(bool)]
    sl = t_in["sku_location"]
    feasible = mo[mo.mitigation_type != "ACCEPT_BACKORDER"].shortage_id.nunique()
    shortages_value = float(sh.shortage_value.sum()) if len(sh) else 0.0
    covered_value = float((rec.covered_qty / sh.set_index("shortage_id").loc[rec.shortage_id].shortage_qty.to_numpy()
                           * sh.set_index("shortage_id").loc[rec.shortage_id].shortage_value.to_numpy()).sum()) \
        if len(rec) else 0.0
    return {
        "sku_locations": len(sl),
        "sku_locations_with_shortage": int(sh[["sku_id", "location_id"]].drop_duplicates().shape[0]),
        "shortage_episodes": len(sh),
        "shortages_by_tier": sh.priority_tier.value_counts().to_dict(),
        "shortages_by_primary_cause": sh.primary_cause_code.value_counts().to_dict(),
        "shortages_by_status": sh.status.value_counts().to_dict(),
        "total_shortage_qty": int(sh.shortage_qty.sum()),
        "total_shortage_value_usd": round(shortages_value, 2),
        "share_with_feasible_mitigation": round(feasible / len(sh), 4) if len(sh) else 1.0,
        "recommended_by_type": rec.mitigation_type.value_counts().to_dict(),
        "recommended_value_protected_usd": round(covered_value, 2),
        "recommended_incremental_cost_usd": round(float(rec[rec.mitigation_type != "ACCEPT_BACKORDER"]
                                                        .incremental_cost.sum()), 2),
        "mean_recommended_fill_rate_pct": round(float(rec.fill_rate_pct.mean()), 2) if len(rec) else 100.0,
        "mitigation_options": len(mo),
        "rejected_candidates_by_reason": out["rejected_mitigation"].reason_code.value_counts().to_dict(),
        "projected_service_level_pct": round(100 * float(1 - pab.is_shortage.astype(bool).mean()), 2),
    }


def evaluate(t_in: dict, out: dict, gt: pd.DataFrame, src_dir: Path) -> dict:
    det = detection_metrics(gt, out["detected_issue"])
    edge = det[det.category == "EDGE_CASE"]
    return {
        "detection_metrics": det,
        "edge_case_recall": round(float(edge.true_positive.sum() / max(1, edge.labelled.sum())), 4),
        "edge_case_precision": round(float(edge.true_positive.sum() / max(1, edge.detected.sum())), 4),
        "edge_case_decision_accuracy": round(float((edge.decision_accuracy * edge.labelled).sum()
                                                   / max(1, edge.labelled.sum())), 4),
        "edge_case_impact": edge_case_impact(gt, t_in, out),
        "planning_kpis": planning_kpis(t_in, out),
        "distribution": distribution_stats(t_in, out),
        "coverage_matrix": coverage_matrix(t_in, out, gt),
        "leakage_audit": leakage_audit(src_dir, t_in),
    }
