"""Planning engine: data-quality screen -> scheduled receipts -> projected
available balance -> shortages -> explainable causes -> prioritisation.

The engine only consumes *input* tables.  It never reads ground truth.
Source records are never modified: every correction is applied in the
derived ``scheduled_receipt`` layer and logged in ``detected_issue``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .calendar import week_id_for_date

POLICY = {
    "frozen_weeks": 2,                 # production cannot be changed inside this fence
    "spike_ratio": 2.0,                # forecast >= ratio * local median => spike
    "spike_min_excess": 8,
    "spike_window": 9,
    "constrained_supplier_util": 0.90,
    "constrained_supplier_min_weeks": 3,
    "constrained_plant_util": 0.95,
    "constrained_plant_min_weeks": 3,
    "component_value_multiplier": 2.0,  # value of a component shortage (production stoppage)
}
OPEN_STATUSES = ("PLANNED", "CONFIRMED", "IN_TRANSIT")


@dataclass
class Ctx:
    as_of: date
    W: int
    week_ids: list[str]
    year: int

    def widx(self, d) -> int:
        if isinstance(d, str):
            d = date.fromisoformat(d)
        return (d - self.as_of).days // 7

    def wid(self, i: int) -> str:
        return week_id_for_date(self.as_of + timedelta(weeks=int(i)))


@dataclass
class PlanState:
    ctx: Ctx
    t: dict
    issues: list = field(default_factory=list)
    out: dict = field(default_factory=dict)


def _none(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _s(v) -> str:
    return v if isinstance(v, str) else ""


def _d(s) -> date:
    return date.fromisoformat(str(s)[:10])


def make_ctx(t: dict) -> Ctx:
    cal = t["calendar_week"].sort_values("week_index")
    as_of = _d(cal.week_start_date.iloc[0])
    return Ctx(as_of=as_of, W=len(cal), week_ids=cal.week_id.tolist(), year=as_of.isocalendar()[0])


def add_issue(st: PlanState, issue_type, severity, record_type, record_id, decision, detail,
              related=None, sku=None, loc=None, sup=None, week=None, impact=None):
    st.issues.append(dict(issue_type=issue_type, severity=severity, record_type=record_type, record_id=record_id,
                          related_record_ids=related, sku_id=sku, location_id=loc, supplier_id=sup,
                          week_id=week, decision=decision, impact_qty=impact, detail=detail))


# ============================================================ 1. scheduled receipts
def master_uom_factor(order_uom, purchase_uom, ss_factor, base_uom, units_per_case):
    if order_uom == purchase_uom:
        return float(ss_factor)
    if order_uom == base_uom:
        return 1.0
    if order_uom == "CS":
        return float(units_per_case)
    return float("nan")      # not convertible to the SKU's base unit


def build_scheduled_receipts(st: PlanState) -> pd.DataFrame:
    t, ctx = st.t, st.ctx
    po = t["purchase_order"]
    pol = t["purchase_order_line"]
    ss = t["supplier_sku"][["supplier_sku_id", "purchase_uom", "uom_conversion_factor"]].rename(
        columns={"uom_conversion_factor": "master_ss_factor"})
    sku = t["sku"][["sku_id", "base_uom", "units_per_case"]].rename(columns={"base_uom": "sku_base_uom"})
    lt = t["lead_time"][["lead_time_id", "production_lead_days", "total_lead_days"]]
    df = (pol.merge(po[["po_id", "supplier_id", "location_id", "lead_time_id", "order_date", "ship_date",
                        "promised_receipt_date", "transport_delay_days", "expected_receipt_date", "status",
                        "created_at"]], on="po_id")
          .merge(ss, on="supplier_sku_id", how="left").merge(sku, on="sku_id", how="left")
          .merge(lt, on="lead_time_id", how="left"))
    df = df[df.status != "RECEIVED"].copy()
    rows = []
    lt_flagged = set()
    for r in df.itertuples(index=False):
        codes = []
        open_line = r.status in OPEN_STATUSES
        factor = master_uom_factor(r.order_uom, r.purchase_uom, r.master_ss_factor, r.sku_base_uom,
                                   r.units_per_case)
        src_base = int(r.base_qty)
        if math.isnan(factor):
            plan_base = 0
            codes.append("UOM_UNCONVERTIBLE_EXCLUDED")
            if open_line:
                add_issue(st, "UOM_MISMATCH", "HIGH", "purchase_order_line", r.po_line_id,
                          "EXCLUDE_UNCONVERTIBLE_LINE",
                          f"order_uom {r.order_uom} cannot be converted to base {r.sku_base_uom} "
                          f"(supplier terms {r.purchase_uom}); {src_base} units excluded from supply",
                          related=r.po_id, sku=r.sku_id, loc=r.location_id, sup=r.supplier_id, impact=src_base)
        else:
            plan_base = int(round(r.order_qty * factor))
            if (abs(float(r.uom_conversion_factor) - factor) > 1e-9 or plan_base != src_base
                    or r.base_uom != r.sku_base_uom):
                codes.append("UOM_CONVERTED")
                if open_line:
                    add_issue(st, "UOM_MISMATCH", "HIGH", "purchase_order_line", r.po_line_id,
                              "CONVERT_USING_MASTER_UOM",
                              f"{r.order_qty} {r.order_uom} recorded with factor {r.uom_conversion_factor} "
                              f"= {src_base}; master factor {factor:g} gives {plan_base} {r.sku_base_uom}",
                              related=r.po_id, sku=r.sku_id, loc=r.location_id, sup=r.supplier_id,
                              impact=plan_base - src_base)
        order = _d(r.order_date)
        promised = _d(r.promised_receipt_date)
        ship = _d(r.ship_date)
        required = order + timedelta(days=int(r.total_lead_days))
        if promised < required:
            codes.append("LEAD_TIME_RECALCULATED")
            ship = order + timedelta(days=int(r.production_lead_days))
            promised = required
            if open_line and r.po_id not in lt_flagged:
                lt_flagged.add(r.po_id)
                add_issue(st, "SHORTAGE_WITHOUT_LEAD_TIME", "HIGH", "purchase_order", r.po_id,
                          "RECALCULATE_RECEIPT_WITH_LEAD_TIME",
                          f"promised receipt {r.promised_receipt_date} ignores lead time {r.lead_time_id} "
                          f"({int(r.total_lead_days)} days); recalculated to {required.isoformat()}",
                          related=r.lead_time_id, loc=r.location_id, sup=r.supplier_id,
                          week=ctx.wid(ctx.widx(required)), impact=int(r.total_lead_days))
        receipt = promised + timedelta(days=int(r.transport_delay_days))
        rw = ctx.widx(receipt)
        if open_line and rw < 0:
            codes.append("OVERDUE_ASSUMED_WEEK0")
            rw = 0
        ship_w = ctx.widx(ship) if r.status in ("PLANNED", "CONFIRMED") else None
        rows.append(dict(po_line_id=r.po_line_id, po_id=r.po_id, sku_id=r.sku_id, location_id=r.location_id,
                         supplier_id=r.supplier_id, po_status=r.status, source_base_qty=src_base,
                         planning_base_qty=plan_base, source_receipt_date=r.expected_receipt_date,
                         planning_receipt_date=receipt.isoformat(), ship_week_index=ship_w,
                         receipt_week_index=rw, adjustment_codes="|".join(codes) or None,
                         planning_ship_date=ship.isoformat(), unit_cost=float(r.unit_cost),
                         supplier_cut_base=0 if math.isnan(factor) else int(round(
                             (int(r.requested_qty) - int(r.order_qty)) * factor)),
                         lead_time_id=r.lead_time_id,
                         counted_in_plan=bool(open_line and plan_base > 0 and rw < ctx.W),
                         created_at=r.created_at, line_number=int(r.line_number),
                         source_ship_week=ctx.widx(_d(r.ship_date)) if r.status in ("PLANNED", "CONFIRMED") else None,
                         promised_week=ctx.widx(_d(r.promised_receipt_date)),
                         transport_delay_days=int(r.transport_delay_days)))
    sr = pd.DataFrame(rows)
    sr["ship_week_index"] = sr["ship_week_index"].astype("Int64")
    sr["source_ship_week"] = sr["source_ship_week"].astype("Int64")
    return sr


# ============================================================ 2. supplier capacity
def apply_supplier_capacity(st: PlanState, sr: pd.DataFrame) -> dict:
    ctx, t = st.ctx, st.t
    W = ctx.W
    cap_df = t["supplier_capacity"]
    week_pos = {w: i for i, w in enumerate(ctx.week_ids)}
    sups = sorted(t["supplier"].supplier_id)
    sidx = {s: i for i, s in enumerate(sups)}
    cap = np.zeros((len(sups), W))
    for r in cap_df.itertuples():
        cap[sidx[r.supplier_id], week_pos[r.week_id]] = r.capacity_units
    src_load = np.zeros_like(cap)
    live_src = sr[sr.po_status.isin(["PLANNED", "CONFIRMED"]) & sr.source_ship_week.notna()]
    for r in live_src.itertuples():
        w = int(r.source_ship_week)
        if 0 <= w < W:
            src_load[sidx[r.supplier_id], w] += r.source_base_qty
    load = np.zeros_like(cap)
    live = sr[sr.po_status.isin(["PLANNED", "CONFIRMED"]) & sr.ship_week_index.notna() & (sr.planning_base_qty > 0)]
    by_sw: dict[tuple, list] = {}
    for idx, r in live.iterrows():
        w = int(r.ship_week_index)
        if 0 <= w < W:
            load[sidx[r.supplier_id], w] += r.planning_base_qty
            by_sw.setdefault((r.supplier_id, w), []).append(idx)
    codes = sr.adjustment_codes.copy()
    for s in sups:
        i = sidx[s]
        for w in range(W):
            if load[i, w] <= cap[i, w]:
                continue
            over = int(load[i, w] - cap[i, w])
            members = sorted(by_sw.get((s, w), []),
                             key=lambda k: (sr.at[k, "created_at"], sr.at[k, "po_id"], sr.at[k, "line_number"]))
            cum, deferred = 0.0, []
            for k in members:
                q = sr.at[k, "planning_base_qty"]
                if cum + q <= cap[i, w]:
                    cum += q
                    continue
                target = next((w2 for w2 in range(w + 1, W) if load[i, w2] + q <= cap[i, w2]), None)
                load[i, w] -= q
                deferred.append(k)
                if target is None:
                    sr.at[k, "counted_in_plan"] = False
                    code = "CAPACITY_DEFERRED_BEYOND_HORIZON"
                else:
                    load[i, target] += q
                    by_sw.setdefault((s, target), []).append(k)
                    shift = target - w
                    sr.at[k, "ship_week_index"] = target
                    sr.at[k, "planning_ship_date"] = (_d(sr.at[k, "planning_ship_date"])
                                                      + timedelta(weeks=shift)).isoformat()
                    new_receipt = _d(sr.at[k, "planning_receipt_date"]) + timedelta(weeks=shift)
                    sr.at[k, "planning_receipt_date"] = new_receipt.isoformat()
                    sr.at[k, "receipt_week_index"] = ctx.widx(new_receipt)
                    if ctx.widx(new_receipt) >= W:
                        sr.at[k, "counted_in_plan"] = False
                    code = f"CAPACITY_DEFERRED_{shift}W"
                codes.at[k] = "|".join([c for c in [codes.at[k], code] if _none(c)])
            add_issue(st, "SUPPLIER_CAPACITY_EXCEEDED", "HIGH", "supplier_capacity",
                      f"SCAP-{s}-{ctx.week_ids[w]}", "DEFER_EXCESS_TO_NEXT_AVAILABLE_WEEK",
                      f"committed {int(cap[i, w]) + over} > capacity {int(cap[i, w])} in {ctx.week_ids[w]}; "
                      f"{len(deferred)} line(s) deferred (latest-created first-out)",
                      related="|".join(sorted({sr.at[k, 'po_id'] for k in deferred} |
                                              {sr.at[k, 'po_line_id'] for k in deferred})),
                      sup=s, week=ctx.week_ids[w], impact=over)
    sr["adjustment_codes"] = codes
    return dict(sups=sups, sidx=sidx, cap=cap, src_load=src_load, load=load)


# ============================================================ 3. inventory screen
def screen_inventory(st: PlanState, sr: pd.DataFrame) -> pd.Series:
    inv = st.t["inventory"]
    it = inv[inv.stock_status == "IN_TRANSIT"].sort_values("inventory_id")
    dup = it[it.duplicated("po_line_id", keep="first")]
    first = it.drop_duplicates("po_line_id").set_index("po_line_id").inventory_id
    po_of = sr.set_index("po_line_id").po_id.to_dict()
    for r in dup.itertuples():
        add_issue(st, "INBOUND_DOUBLE_COUNT", "HIGH", "inventory", r.inventory_id, "EXCLUDE_DUPLICATE_INBOUND",
                  f"in-transit record duplicates {first[r.po_line_id]} for PO line {r.po_line_id}; "
                  f"inbound is counted once, from the PO line ({int(r.quantity)} units not added)",
                  related="|".join(x for x in [first[r.po_line_id], r.po_line_id, po_of.get(r.po_line_id)] if x),
                  sku=r.sku_id, loc=r.location_id, impact=int(r.quantity))
    # Available opening stock: ON_HAND only. IN_TRANSIT rows are informational (supply comes from PO lines),
    # QUALITY_HOLD is not available.
    oh = inv[inv.stock_status == "ON_HAND"].groupby(["sku_id", "location_id"]).quantity.sum()
    return oh


# ============================================================ 4. master-data screens
def screen_substitutes(st: PlanState):
    sub = st.t["sku_substitute"]
    for r in sub[sub.approval_status != "APPROVED"].itertuples():
        add_issue(st, "SUBSTITUTE_NOT_APPROVED", "MEDIUM", "sku_substitute", r.substitution_id,
                  "REJECT_SUBSTITUTE_MITIGATION",
                  f"{r.substitute_sku_id} as substitute for {r.sku_id} is {r.approval_status}; "
                  "excluded from all mitigation options", related=r.substitute_sku_id, sku=r.sku_id)


def local_baseline(D: np.ndarray, active: np.ndarray, window: int) -> np.ndarray:
    """Rolling median of neighbouring *active* weeks, excluding the week itself."""
    n, W = D.shape
    half = window // 2
    Dn = np.where(active, D.astype(float), np.nan)
    out = np.zeros((n, W), dtype=float)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for w in range(W):
            idx = [k for k in range(max(0, w - half), min(W, w + half + 1)) if k != w]
            out[:, w] = np.nanmedian(Dn[:, idx], axis=1)
    return np.nan_to_num(out, nan=0.0)


def detect_spikes(st: PlanState, sl: pd.DataFrame, D: np.ndarray, active: np.ndarray):
    base = local_baseline(D, active, POLICY["spike_window"])
    min_excess = np.maximum(POLICY["spike_min_excess"], 3 * np.sqrt(np.maximum(base, 0)))  # 3 sigma (Poisson)
    flag = (D >= POLICY["spike_ratio"] * np.maximum(base, 1)) & (D - base >= min_excess) & active
    ctx = st.ctx
    for i, w in zip(*np.nonzero(flag)):
        s, l = sl.sku_id.iat[i], sl.location_id.iat[i]
        add_issue(st, "DEMAND_SPIKE", "INFO", "forecast_demand", f"DEM-{s}-{l}-{ctx.week_ids[w]}",
                  "FLAG_FOR_DEMAND_REVIEW",
                  f"forecast {int(D[i, w])} vs local median {base[i, w]:.0f} ({D[i, w] / max(base[i, w], 1):.1f}x)",
                  sku=s, loc=l, week=ctx.week_ids[w], impact=int(D[i, w] - base[i, w]))
    return flag, base


# ============================================================ 5. matrices + PAB
def build_matrices(st: PlanState, sr: pd.DataFrame, on_hand: pd.Series):
    t, ctx = st.t, st.ctx
    W = ctx.W
    sl = t["sku_location"].sort_values(["sku_id", "location_id"]).reset_index(drop=True)
    key = {(a, b): i for i, (a, b) in enumerate(zip(sl.sku_id, sl.location_id))}
    n = len(sl)
    wpos = {w: i for i, w in enumerate(ctx.week_ids)}
    D = np.zeros((n, W), dtype=np.int64)
    active = np.zeros((n, W), dtype=bool)
    fd = t["forecast_demand"]
    ii = np.array([key[(a, b)] for a, b in zip(fd.sku_id, fd.location_id)], dtype=np.int64)
    ww = np.array([wpos[w] for w in fd.week_id], dtype=np.int64)
    D[ii, ww] = fd.forecast_qty.astype(np.int64).to_numpy()
    active[ii, ww] = True
    P = np.zeros((n, W), dtype=np.int64)
    PREQ = np.zeros((n, W), dtype=np.int64)
    pp = t["production_plan"]
    if len(pp):
        ii = np.array([key[(a, b)] for a, b in zip(pp.sku_id, pp.location_id)])
        ww = np.array([wpos[w] for w in pp.week_id])
        np.add.at(P, (ii, ww), pp.planned_qty.astype(np.int64).to_numpy())
        np.add.at(PREQ, (ii, ww), pp.required_qty.astype(np.int64).to_numpy())
    DD = dependent_demand_matrix(t, key, wpos, n, W)
    R = np.zeros((n, W), dtype=np.int64)
    cnt = sr[sr.counted_in_plan]
    ii = np.array([key[(a, b)] for a, b in zip(cnt.sku_id, cnt.location_id)], dtype=np.int64)
    np.add.at(R, (ii, cnt.receipt_week_index.astype(np.int64).to_numpy()),
              cnt.planning_base_qty.astype(np.int64).to_numpy())
    O = np.array([int(on_hand.get((a, b), 0)) for a, b in zip(sl.sku_id, sl.location_id)], dtype=np.int64)
    closing = O[:, None] + np.cumsum(R + P - D - DD, axis=1)
    SS = sl.safety_stock_qty.astype(np.int64).to_numpy()
    return dict(sl=sl, key=key, D=D, DD=DD, P=P, PREQ=PREQ, R=R, O=O, closing=closing, SS=SS, active=active)


def dependent_demand_matrix(t, key, wpos, n, W) -> np.ndarray:
    from .generator import dependent_demand_units
    pp, bom = t["production_plan"], t["bom"]
    DD = np.zeros((n, W), dtype=np.int64)
    if not len(pp) or not len(bom):
        return DD
    cal = t["calendar_week"].set_index("week_id").week_start_date
    m = pp.merge(bom, left_on="sku_id", right_on="parent_sku_id")
    ws = m.week_id.map(cal)
    eff = (m.effective_from <= ws) & (m.effective_to.isna() | (ws <= m.effective_to.fillna("9999-12-31")))
    m = m[eff]
    m = m.assign(req=m.planned_qty.astype(float) * m.qty_per.astype(float))
    g = m.groupby(["component_sku_id", "location_id", "week_id"]).req.sum()
    for (c, l, w), v in g.items():
        DD[key[(c, l)], wpos[w]] = dependent_demand_units(v)
    return DD


def projected_balance_table(st: PlanState, M: dict) -> pd.DataFrame:
    ctx = st.ctx
    sl, W = M["sl"], ctx.W
    n = len(sl)
    closing = M["closing"]
    opening = np.concatenate([M["O"][:, None], closing[:, :-1]], axis=1)
    sku = np.repeat(sl.sku_id.to_numpy(), W)
    loc = np.repeat(sl.location_id.to_numpy(), W)
    wk = np.tile(np.array(ctx.week_ids), n)
    ss = np.repeat(M["SS"], W)
    df = pd.DataFrame({
        "pab_id": ["PAB-" + a + "-" + b + "-" + c for a, b, c in zip(sku, loc, wk)],
        "sku_id": sku, "location_id": loc, "week_id": wk, "week_index": np.tile(np.arange(W), n),
        "opening_balance": opening.ravel(), "forecast_demand": M["D"].ravel(),
        "dependent_demand": M["DD"].ravel(), "scheduled_receipts": M["R"].ravel(),
        "planned_production": M["P"].ravel(), "closing_balance": closing.ravel(), "safety_stock_qty": ss})
    df["below_safety_stock"] = df.closing_balance < df.safety_stock_qty
    df["is_shortage"] = df.closing_balance < 0
    return df


# ============================================================ 6. utilisation screens
def plant_capacity(st: PlanState, M: dict) -> dict:
    t, ctx = st.t, st.ctx
    plants = sorted(t["location"].loc[t["location"].location_type == "PLANT", "location_id"])
    pidx = {p: i for i, p in enumerate(plants)}
    wpos = {w: i for i, w in enumerate(ctx.week_ids)}
    cap = np.zeros((len(plants), ctx.W))
    for r in t["production_capacity"].itertuples():
        cap[pidx[r.location_id], wpos[r.week_id]] = r.capacity_units
    planned = np.zeros_like(cap)
    required = np.zeros_like(cap)
    pp = t["production_plan"]
    for r in pp.itertuples():
        planned[pidx[r.location_id], wpos[r.week_id]] += r.planned_qty
        required[pidx[r.location_id], wpos[r.week_id]] += r.required_qty
    return dict(plants=plants, pidx=pidx, cap=cap, planned=planned, required=required)


def screen_constraints(st: PlanState, S: dict, PC: dict, sr: pd.DataFrame):
    """Flag suppliers/plants whose capacity binds: quantities were cut below what was requested/required,
    or utilisation stays very high for several weeks."""
    util = np.divide(S["load"], S["cap"], out=np.zeros_like(S["load"]), where=S["cap"] > 0)
    cut = sr[(sr.supplier_cut_base > 0) & sr.po_status.isin(["PLANNED", "CONFIRMED"])]
    cut_weeks = cut.groupby("supplier_id").ship_week_index.nunique().to_dict()
    cut_qty = cut.groupby("supplier_id").supplier_cut_base.sum().to_dict()
    for s, i in S["sidx"].items():
        weeks = np.flatnonzero(util[i] >= POLICY["constrained_supplier_util"])
        n_cut = int(cut_weeks.get(s, 0))
        if n_cut >= 1 or len(weeks) >= POLICY["constrained_supplier_min_weeks"]:
            add_issue(st, "CONSTRAINED_SUPPLIER", "LOW", "supplier", s, "FLAG_CONSTRAINED_SUPPLIER",
                      f"confirmed quantities cut by {int(cut_qty.get(s, 0))} units in {n_cut} ship week(s); "
                      f"utilisation >= {POLICY['constrained_supplier_util']:.0%} in {len(weeks)} week(s)",
                      sup=s, impact=int(cut_qty.get(s, 0)))
    putil = np.divide(PC["planned"], PC["cap"], out=np.zeros_like(PC["planned"]), where=PC["cap"] > 0)
    for p, i in PC["pidx"].items():
        gap_weeks = np.flatnonzero(PC["required"][i] > PC["planned"][i])
        weeks = np.flatnonzero(putil[i] >= POLICY["constrained_plant_util"])
        if len(gap_weeks) >= POLICY["constrained_plant_min_weeks"] or len(weeks) >= POLICY["constrained_plant_min_weeks"]:
            add_issue(st, "CONSTRAINED_PLANT", "LOW", "location", p, "FLAG_CONSTRAINED_PLANT",
                      f"planned production below requirement in {len(gap_weeks)} week(s) "
                      f"({int((PC['required'][i] - PC['planned'][i]).sum())} units); utilisation >= "
                      f"{POLICY['constrained_plant_util']:.0%} in {len(weeks)} week(s)",
                      loc=p, impact=int((PC["required"][i] - PC["planned"][i]).sum()))
    S["util"], PC["util"] = util, putil


# ============================================================ 7. shortages + causes
def lane_lead_time(t: dict, as_of: date) -> dict:
    lt = t["lead_time"]
    out = {}
    for r in lt.sort_values("version").itertuples():
        if _d(r.effective_from) <= as_of and (_none(r.effective_to) is None or as_of <= _d(r.effective_to)):
            out[(r.supplier_id, r.location_id)] = r._asdict()
    return out


def detect_shortages(st: PlanState, M: dict, sr: pd.DataFrame, S: dict, PC: dict, spike, spike_base):
    t, ctx = st.t, st.ctx
    sl, closing = M["sl"], M["closing"]
    W = ctx.W
    sku = t["sku"].set_index("sku_id")
    lanes = lane_lead_time(t, ctx.as_of)
    # evidence indexes
    sr_by = {}
    for r in sr.itertuples(index=False):
        sr_by.setdefault((r.sku_id, r.location_id), []).append(r)
    pp = t["production_plan"]
    bom = t["bom"]
    parents_of = bom.groupby("component_sku_id").parent_sku_id.apply(list).to_dict()
    pp_by = {k: g for k, g in pp.groupby(["sku_id", "location_id"])}
    episodes = []
    neg = closing < 0
    for i in np.flatnonzero(neg.any(axis=1)):
        w = 0
        row = neg[i]
        while w < W:
            if row[w]:
                s = w
                while w + 1 < W and row[w + 1]:
                    w += 1
                episodes.append((i, s, w))
            w += 1
    recs, causes = [], []
    for (i, s, e) in episodes:
        sku_id, loc = sl.sku_id.iat[i], sl.location_id.iat[i]
        info = sku.loc[sku_id]
        method = sl.planning_method.iat[i]
        seg = closing[i, s:e + 1]
        qty = int(-seg.min())
        peak_w = s + int(np.argmin(seg))
        if info.item_type == "COMPONENT":
            value = qty * float(info.unit_cost) * POLICY["component_value_multiplier"]
        else:
            value = qty * float(info.unit_price)
        prim = _none(sl.primary_supplier_id.iat[i])
        # first week a normal replenishment action can land: order today + lead time (purchase) or the end
        # of the frozen production fence (make). Shortages starting earlier are "within lead time".
        if method == "PRODUCTION":
            lt_weeks = POLICY["frozen_weeks"]
        else:
            lane = lanes.get((prim, loc))
            lt_weeks = ctx.widx(ctx.as_of + timedelta(days=int(lane["total_lead_days"]))) if lane else 0
        cum = lambda A, upto: int(A[i, :upto + 1].sum())
        O = int(M["O"][i])
        cs = []   # (code, qty, evidence_type, evidence_ids, explanation)
        # --- demand spike
        sw = [w for w in range(0, e + 1) if spike[i, w]]
        if sw:
            excess = int(sum(M["D"][i, w] - spike_base[i, w] for w in sw))
            cs.append(("DEMAND_SPIKE", min(qty, max(0, excess)), "forecast_demand",
                       "|".join(f"DEM-{sku_id}-{loc}-{ctx.week_ids[w]}" for w in sw),
                       f"forecast spike in {', '.join(ctx.week_ids[w] for w in sw)} adds {excess} units above the "
                       "local median"))
        lines = sr_by.get((sku_id, loc), [])
        # --- transport delay
        dl = [r for r in lines if r.counted_in_plan and r.transport_delay_days > 0 and r.promised_week <= e
              and r.receipt_week_index >= s and r.receipt_week_index > r.promised_week]
        if dl:
            q = sum(r.planning_base_qty for r in dl)
            cs.append(("TRANSPORT_DELAY", min(qty, q), "purchase_order", "|".join(sorted({r.po_id for r in dl})),
                       f"{len(dl)} inbound line(s) ({q} units) delayed past the shortage start by "
                       f"{max(r.transport_delay_days for r in dl)} days max"))
        # --- supplier capacity: confirmed < requested, or deferred by the engine's capacity check
        cut = [r for r in lines if r.counted_in_plan and r.supplier_cut_base > 0 and r.promised_week <= e]
        cd = [r for r in lines if "CAPACITY_DEFERRED" in _s(r.adjustment_codes)
              and r.receipt_week_index >= s]
        if cut or cd:
            q = sum(r.supplier_cut_base for r in cut) + sum(r.planning_base_qty for r in cd)
            parts = []
            if cut:
                parts.append(f"supplier confirmed {sum(r.supplier_cut_base for r in cut)} units less than requested "
                             f"on {len(cut)} line(s) (weekly capacity)")
            if cd:
                parts.append(f"{sum(r.planning_base_qty for r in cd)} units deferred because the supplier week was "
                             "over capacity")
            cs.append(("SUPPLIER_CAPACITY_CONSTRAINT", min(qty, q), "purchase_order_line",
                       "|".join(sorted({r.po_line_id for r in cut + cd})), "; ".join(parts)))
        # --- production capacity: planned < required
        if method == "PRODUCTION":
            gap = int((M["PREQ"][i, :e + 1] - M["P"][i, :e + 1]).sum())
            if gap > 0:
                pi = PC["pidx"][loc]
                weeks = [w for w in range(0, e + 1) if M["PREQ"][i, w] > M["P"][i, w]]
                cs.append(("PRODUCTION_CAPACITY_CONSTRAINT", min(qty, gap), "production_capacity",
                           "|".join(f"PCAP-{loc}-{ctx.week_ids[w]}" for w in weeks[:8]),
                           f"plant {loc} capacity cut planned production {gap} units below requirement in "
                           f"{len(weeks)} week(s)"))
        # --- dependent demand (components)
        if method == "DEPENDENT_PURCHASE":
            dd = int(M["DD"][i, s:e + 1].sum())
            ev = []
            for p in parents_of.get(sku_id, []):
                g = pp_by.get((p, loc))
                if g is not None:
                    ev += g[g.week_id.isin(ctx.week_ids[s:e + 1])].production_plan_id.tolist()
            cs.append(("DEPENDENT_DEMAND", min(qty, dd), "production_plan", "|".join(sorted(ev)[:20]),
                       f"BOM explosion of planned production consumes {dd} units in the shortage window"))
        # --- cancelled POs
        cx = [r for r in lines if r.po_status == "CANCELLED" and r.promised_week <= e]
        if cx:
            q = sum(r.source_base_qty for r in cx)
            cs.append(("PO_CANCELLED", min(qty, q), "purchase_order", "|".join(sorted({r.po_id for r in cx})),
                       f"{len(cx)} cancelled line(s) would have delivered {q} units"))
        # --- lead-time correction
        lc = [r for r in lines if "LEAD_TIME_RECALCULATED" in _s(r.adjustment_codes)
              and r.promised_week <= e and r.receipt_week_index >= s]
        if lc:
            q = sum(r.planning_base_qty for r in lc)
            cs.append(("LEAD_TIME_CORRECTION", min(qty, q), "purchase_order", "|".join(sorted({r.po_id for r in lc})),
                       f"{q} units recorded as arriving without lead time; recalculated arrival is later"))
        # --- UoM exclusion
        uc = [r for r in lines if "UOM_UNCONVERTIBLE_EXCLUDED" in _s(r.adjustment_codes)
              and r.promised_week <= e]
        if uc:
            q = sum(r.source_base_qty for r in uc)
            cs.append(("UOM_CORRECTION", min(qty, q), "purchase_order_line", "|".join(r.po_line_id for r in uc),
                       f"{q} units on lines with unconvertible units of measure were excluded"))
        # --- opening stock inside lead time
        if s < lt_weeks:
            gap = -int(closing[i, s])
            cs.append(("INSUFFICIENT_OPENING_STOCK", min(qty, gap), "inventory", None,
                       f"opening stock {O} cannot cover demand before a new order/production change can land "
                       f"(week index {lt_weeks})"))
        # --- no supply after start
        if int(M["R"][i, s:].sum() + M["P"][i, s:].sum()) == 0:
            cs.append(("NO_SCHEDULED_SUPPLY", qty, "purchase_order", None,
                       "no open purchase order or production is scheduled after the shortage starts"))
        cs.sort(key=lambda c: -c[1])
        base_expl = (f"through {ctx.week_ids[s]}: opening {O} + receipts {cum(M['R'], s)} + production "
                     f"{cum(M['P'], s)} - demand {cum(M['D'], s)} - dependent demand {cum(M['DD'], s)} = "
                     f"{int(closing[i, s])}; peak deficit {qty} in {ctx.week_ids[peak_w]}")
        cs.append(("DEMAND_EXCEEDS_SUPPLY", qty, "projected_balance",
                   "|".join(dict.fromkeys([f"PAB-{sku_id}-{loc}-{ctx.week_ids[s]}",
                                           f"PAB-{sku_id}-{loc}-{ctx.week_ids[peak_w]}"])),
                   "cumulative demand exceeds available supply: " + base_expl))
        primary = cs[0][0] if cs[0][1] > 0 or len(cs) == 1 else cs[-1][0]
        if cs[0][1] == 0:
            primary = "DEMAND_EXCEEDS_SUPPLY"
        summary = base_expl + ". Causes: " + "; ".join(f"{c[0]} ({c[1]})" for c in cs[:-1])
        if len(cs) == 1:
            summary = base_expl + ". Cause: demand exceeds scheduled supply"
        recs.append(dict(sl_index=i, sku_id=sku_id, location_id=loc, start_week_index=s, end_week_index=e,
                         start_week_id=ctx.week_ids[s], end_week_id=ctx.week_ids[e], duration_weeks=e - s + 1,
                         shortage_qty=qty, shortage_value=round(value, 2), lead_time_weeks=lt_weeks,
                         within_lead_time=bool(s < lt_weeks), abc=info.abc_class, primary_cause_code=primary,
                         cause_summary=summary))
        causes.append(cs)
    return recs, causes


def prioritise(recs: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(recs)
    if df.empty:
        return df
    vmax = np.log1p(df.shortage_value.max())
    value_n = np.log1p(df.shortage_value) / vmax if vmax > 0 else 0
    urgency = 1.0 / (1.0 + df.start_week_index / 4.0)
    abc_w = df.abc.map({"A": 1.0, "B": 0.6, "C": 0.3})
    dur = np.minimum(1.0, df.duration_weeks / 8.0)
    df["priority_score"] = (100 * (0.40 * value_n + 0.30 * urgency + 0.15 * abc_w + 0.15 * dur)).round(2)

    def tier(r):
        if (r.within_lead_time and r.abc in ("A", "B")) or r.priority_score >= 75:
            return "CRITICAL"
        if r.within_lead_time or r.priority_score >= 55:
            return "HIGH"
        if r.priority_score >= 35:
            return "MEDIUM"
        return "LOW"
    df["priority_tier"] = df.apply(tier, axis=1)
    df = df.sort_values(["priority_score", "start_week_index", "sku_id", "location_id"],
                        ascending=[False, True, True, True], kind="mergesort").reset_index()
    df = df.rename(columns={"index": "episode"})
    df["priority_rank"] = np.arange(1, len(df) + 1)
    return df


# ============================================================ driver
def run_planning(t: dict[str, pd.DataFrame]) -> PlanState:
    from .mitigation import generate_mitigations
    st = PlanState(ctx=make_ctx(t), t=t)
    ctx = st.ctx
    sr = build_scheduled_receipts(st)
    S = apply_supplier_capacity(st, sr)
    on_hand = screen_inventory(st, sr)
    screen_substitutes(st)
    M = build_matrices(st, sr, on_hand)
    spike, spike_base = detect_spikes(st, M["sl"], M["D"], M["active"])
    PC = plant_capacity(st, M)
    screen_constraints(st, S, PC, sr)
    recs, causes = detect_shortages(st, M, sr, S, PC, spike, spike_base)
    sh = prioritise(recs)
    cause_rows = []
    if len(sh):
        sh["shortage_id"] = [f"SHORT-{ctx.year}-{k:06d}" for k in sh.priority_rank]
        for r in sh.itertuples():
            for seq, c in enumerate(causes[r.episode], start=1):
                cause_rows.append(dict(shortage_cause_id=f"SC-{r.shortage_id}-{seq:02d}", shortage_id=r.shortage_id,
                                       cause_seq=seq, cause_code=c[0], contribution_qty=int(c[1]),
                                       evidence_record_type=c[2], evidence_record_ids=c[3], explanation=c[4]))
    st.out["shortage_cause"] = pd.DataFrame(cause_rows, columns=[
        "shortage_cause_id", "shortage_id", "cause_seq", "cause_code", "contribution_qty",
        "evidence_record_type", "evidence_record_ids", "explanation"])
    mit, rej, sh, S, PC = generate_mitigations(st, sh, M, sr, S, PC)
    st.out["mitigation_option"] = mit
    st.out["rejected_mitigation"] = rej
    st.out["shortage"] = sh
    st.out["projected_balance"] = projected_balance_table(st, M)
    st.out["scheduled_receipt"] = sr
    st.out["supplier_capacity_utilization"] = supplier_util_table(st, S)
    st.out["production_capacity_utilization"] = plant_util_table(st, PC)
    issues = pd.DataFrame(st.issues)
    order = {k: i for i, k in enumerate(["INBOUND_DOUBLE_COUNT", "SUBSTITUTE_NOT_APPROVED",
                                         "SUPPLIER_CAPACITY_EXCEEDED", "SHORTAGE_WITHOUT_LEAD_TIME",
                                         "UOM_MISMATCH", "DEMAND_SPIKE", "CONSTRAINED_SUPPLIER",
                                         "CONSTRAINED_PLANT"])}
    if len(issues):
        issues = issues.assign(_o=issues.issue_type.map(order)).sort_values(
            ["_o", "record_id"], kind="mergesort").drop(columns="_o").reset_index(drop=True)
        issues.insert(0, "issue_id", [f"ISS-{ctx.year}-{i + 1:06d}" for i in range(len(issues))])
    st.out["detected_issue"] = issues
    st.M, st.S, st.PC = M, S, PC
    return st


def supplier_util_table(st: PlanState, S: dict) -> pd.DataFrame:
    ctx = st.ctx
    rows = []
    for s, i in S["sidx"].items():
        for w in range(ctx.W):
            cap = S["cap"][i, w]
            res = S["reserved"][i, w]
            rows.append(dict(supplier_capacity_id=f"SCAP-{s}-{ctx.week_ids[w]}", supplier_id=s,
                             week_id=ctx.week_ids[w], capacity_units=int(cap),
                             source_committed_units=int(S["src_load"][i, w]),
                             planned_committed_units=int(S["load"][i, w]), mitigation_reserved_units=int(res),
                             utilization_pct=round(100 * (S["load"][i, w] + res) / cap, 2) if cap else 0.0,
                             source_over_capacity=bool(S["src_load"][i, w] > cap)))
    return pd.DataFrame(rows)


def plant_util_table(st: PlanState, PC: dict) -> pd.DataFrame:
    ctx = st.ctx
    rows = []
    for p, i in PC["pidx"].items():
        for w in range(ctx.W):
            cap = PC["cap"][i, w]
            res = PC["reserved"][i, w]
            rows.append(dict(production_capacity_id=f"PCAP-{p}-{ctx.week_ids[w]}", location_id=p,
                             week_id=ctx.week_ids[w], capacity_units=int(cap), planned_units=int(PC["planned"][i, w]),
                             mitigation_reserved_units=int(res),
                             utilization_pct=round(100 * (PC["planned"][i, w] + res) / cap, 2) if cap else 0.0))
    return pd.DataFrame(rows)
