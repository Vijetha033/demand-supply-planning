"""Candidate mitigations per shortage, respecting policy and capacity.

Shortages are processed in priority order.  For each shortage every candidate
is checked against MOQ / order multiples, lead time (orders are placed at the
as-of date), supplier status and sourcing approval, substitute approval,
supplier weekly capacity, plant capacity + frozen fence, component
availability and source-location surplus (stock must stay >= safety stock).
Feasible candidates become ``mitigation_option`` rows with cost and service
metrics; failed candidates are logged in ``rejected_mitigation``.  Capacity
and stock used by the *recommended* option are reserved before the next
shortage is evaluated, so recommendations never double-book capacity.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .generator import round_purchase_qty
from .planning import POLICY, _d, _none, lane_lead_time
from .schema import TABLES

COSTS = {
    "order_fee": 75.0,                  # admin cost of an unplanned PO
    "excess_holding_pct": 0.05,         # cost of MOQ overage, % of unit cost
    "transfer_same_region_pct": 0.03,
    "transfer_cross_region_pct": 0.06,
    "transfer_fixed": 50.0,
    "substitute_fee": 25.0,
    "overtime_premium_pct": 0.15,
    "lateness_penalty_per_week": 0.15,  # service-score reduction per week late
    "component_backorder_pct": 1.0,     # lost value of a component backorder, % of cost
}
TRANSFER_WEEKS = {True: 1, False: 2}    # same region / cross region
TYPE_ORDER = {"APPROVED_SUBSTITUTE": 0, "STOCK_TRANSFER": 1, "NEW_PO_PRIMARY": 2, "EXPEDITE_PO": 3,
              "NEW_PO_ALTERNATE": 4, "INCREASE_PRODUCTION": 5, "ACCEPT_BACKORDER": 6}


def _empty(table: str) -> pd.DataFrame:
    return pd.DataFrame(columns=TABLES[table].columns)


def generate_mitigations(st, sh: pd.DataFrame, M: dict, sr: pd.DataFrame, S: dict, PC: dict):
    t, ctx = st.t, st.ctx
    W, as_of = ctx.W, ctx.as_of
    S["reserved"] = np.zeros_like(S["cap"])
    PC["reserved"] = np.zeros_like(PC["cap"])
    if sh is None or sh.empty:
        cols = TABLES["shortage"].columns
        return _empty("mitigation_option"), _empty("rejected_mitigation"), pd.DataFrame(columns=cols), S, PC

    closing_res = M["closing"].astype(float).copy()
    SS, sl, key = M["SS"], M["sl"], M["key"]
    sku = t["sku"].set_index("sku_id")
    sup = t["supplier"].set_index("supplier_id")
    region = t["location"].set_index("location_id").region.to_dict()
    lanes = lane_lead_time(t, as_of)
    lt_by_id = t["lead_time"].set_index("lead_time_id")
    terms = {k: g.sort_values("supplier_priority").to_dict("records")
             for k, g in t["supplier_sku"].groupby("sku_id")}
    locs_by_sku = sl.groupby("sku_id").location_id.apply(list).to_dict()
    subs = {k: g.sort_values("priority").to_dict("records") for k, g in t["sku_substitute"].groupby("sku_id")}
    bom = t["bom"]
    bom_by_parent = {k: g.to_dict("records") for k, g in bom.groupby("parent_sku_id")}
    batch = t["production_plan"].groupby("sku_id").batch_size.first().to_dict()
    exp_lines = {}
    for r in sr[sr.counted_in_plan & sr.po_status.isin(["PLANNED", "CONFIRMED"])].itertuples(index=False):
        if r.ship_week_index is not None and not pd.isna(r.ship_week_index) and r.ship_week_index >= 0:
            exp_lines.setdefault((r.sku_id, r.location_id), []).append(r)

    def surplus(j: int, from_w: int) -> int:
        return int(math.floor(np.min(closing_res[j, from_w:] - SS[j]))) if from_w < W else 0

    mit_rows, rej_rows, status = [], [], {}
    for r in sh.itertuples():
        Q, s, e, V = int(r.shortage_qty), int(r.start_week_index), int(r.end_week_index), float(r.shortage_value)
        info = sku.loc[r.sku_id]
        loc = r.location_id
        opts, rejs = [], []

        def rej(mtype, ref, reason, detail):
            rejs.append(dict(mitigation_type=mtype, candidate_ref=ref, reason_code=reason, detail=detail))

        # ---------------------------------------------------- expedite an existing open PO line
        best = None
        for ln in exp_lines.get((r.sku_id, loc), []):
            if ln.receipt_week_index <= s:
                continue
            lt = lt_by_id.loc[ln.lead_time_id]
            ship = max(_d(ln.planning_ship_date), as_of)
            new_arr = ship + timedelta(days=int(lt.expedite_transit_days))
            a = ctx.widx(new_arr)
            if a >= ln.receipt_week_index or a > e:
                continue
            cand = (min(ln.planning_base_qty, Q), -a, ln)
            if best is None or cand[:2] > best[:2]:
                best = cand
        if best:
            ln = best[2]
            lt = lt_by_id.loc[ln.lead_time_id]
            a = -best[1]
            cost = ln.planning_base_qty * ln.unit_cost * float(lt.expedite_premium_pct) / 100
            opts.append(dict(mitigation_type="EXPEDITE_PO", supplier_id=ln.supplier_id, po_id=ln.po_id,
                             proposed_qty=int(ln.planning_base_qty), arrival_week_index=a, total_cost=cost,
                             incremental_cost=cost, lead_time_days=int(lt.expedite_transit_days),
                             moq_check="N/A", lead_time_check="PASS", approval_check="N/A", capacity_check="PASS",
                             rationale=f"expedite {ln.po_line_id} by {lt.expedite_transit_days}-day priority "
                                       f"transit: week {ln.receipt_week_index} -> {a}; supplier ship week unchanged",
                             reserve=[]))
        # ---------------------------------------------------- new purchase order (primary / alternate)
        if info.sourcing_type == "BUY":
            for tm in terms.get(r.sku_id, []):
                mtype = "NEW_PO_PRIMARY" if tm["supplier_priority"] == 1 else "NEW_PO_ALTERNATE"
                sid = tm["supplier_id"]
                if sup.at[sid, "status"] != "ACTIVE":
                    rej(mtype, sid, "SUPPLIER_ON_HOLD", f"{sid} is {sup.at[sid, 'status']}; no new orders allowed")
                    continue
                lane = lanes.get((sid, loc))
                if lane is None:
                    rej(mtype, sid, "NO_LANE", f"no effective lead-time lane {sid} -> {loc}")
                    continue
                total_lt, prod_lt = int(lane["total_lead_days"]), int(lane["production_lead_days"])
                a_min = ctx.widx(as_of + timedelta(days=total_lt))
                if a_min > e:
                    rej(mtype, sid, "LEAD_TIME_TOO_LONG",
                        f"order today arrives {ctx.wid(a_min)} ({total_lt} days) after the shortage "
                        f"ends {ctx.week_ids[e]}")
                    continue
                conv, moq, mult = float(tm["uom_conversion_factor"]), int(tm["min_order_qty"]), int(tm["order_multiple"])
                si = S["sidx"][sid]
                pq_full = round_purchase_qty(Q, conv, moq, mult)
                # Order as late as possible while still arriving by the shortage start (or now if inside
                # lead time); walk back towards today if that ship week lacks capacity.
                k_latest = 0
                while ctx.widx(as_of + timedelta(days=7 * (k_latest + 1) + total_lt)) <= s:
                    k_latest += 1
                choice, best_part = None, None
                for k in range(k_latest, -1, -1):
                    sw = ctx.widx(as_of + timedelta(days=7 * k + prod_lt))
                    if sw >= W:
                        continue
                    rem_k = int(S["cap"][si, sw] - S["load"][si, sw] - S["reserved"][si, sw])
                    if pq_full * conv <= rem_k:
                        choice = (k, sw, rem_k, pq_full)
                        break
                    part = int(math.floor(rem_k / conv / mult) * mult)
                    if part >= moq and (best_part is None or part > best_part[3]):
                        best_part = (k, sw, rem_k, part)
                choice = choice or best_part
                if choice is None:
                    rej(mtype, sid, "INSUFFICIENT_CAPACITY",
                        f"remaining capacity below MOQ {moq} {tm['purchase_uom']} in every ship week from today "
                        f"to the latest useful order week")
                    continue
                k, sw, rem, pq = choice
                a = ctx.widx(as_of + timedelta(days=7 * k + total_lt))
                base = int(round(pq * conv))
                price = float(tm["unit_cost"])
                total = base * price
                inc = (COSTS["order_fee"] + max(0.0, price - float(info.unit_cost)) * base
                       + COSTS["excess_holding_pct"] * float(info.unit_cost) * max(0, base - Q))
                opts.append(dict(mitigation_type=mtype, supplier_id=sid, proposed_qty=base,
                                 order_qty_purchase_uom=pq, arrival_week_index=a, total_cost=total,
                                 incremental_cost=inc, lead_time_days=int(lane["total_lead_days"]),
                                 capacity_available=rem, capacity_consumed=base, moq_check="PASS",
                                 lead_time_check="PASS", approval_check="PASS", capacity_check="PASS",
                                 rationale=f"order {pq} {tm['purchase_uom']} (MOQ {moq}, multiple {mult}) from {sid} "
                                           f"in {ctx.week_ids[k]}; ships {ctx.week_ids[sw]}, arrives {ctx.wid(a)} "
                                           f"({total_lt}-day lead time {lane['lead_time_id']})",
                                 reserve=[("sup", si, sw, base)]))
        # ---------------------------------------------------- stock transfer from another location
        others = [l for l in locs_by_sku.get(r.sku_id, []) if l != loc]
        best, checked = None, 0
        for src in others:
            same = region.get(src) == region.get(loc)
            a = TRANSFER_WEEKS[same]
            if a > e:
                continue
            checked += 1
            j = key[(r.sku_id, src)]
            sp = surplus(j, 0)
            if sp <= 0:
                continue
            q = min(sp, Q)
            cand = (q, same, src, j, a, sp)
            if best is None or cand[:2] > best[:2]:
                best = cand
        if best:
            q, same, src, j, a, sp = best
            pct = COSTS["transfer_same_region_pct" if same else "transfer_cross_region_pct"]
            cost = q * float(info.unit_cost) * pct + COSTS["transfer_fixed"]
            opts.append(dict(mitigation_type="STOCK_TRANSFER", source_location_id=src, proposed_qty=q,
                             arrival_week_index=a, total_cost=cost, incremental_cost=cost, lead_time_days=7 * a,
                             capacity_available=sp, capacity_consumed=q, moq_check="N/A", lead_time_check="PASS",
                             approval_check="N/A", capacity_check="PASS",
                             rationale=f"transfer {q} from {src} ({'same' if same else 'cross'}-region, {a} week); "
                                       f"source keeps >= safety stock {int(SS[j])} in every week",
                             reserve=[("stock", j, 0, q)]))
        elif checked:
            rej("STOCK_TRANSFER", "|".join(others), "NO_SURPLUS",
                f"{checked} other location(s) checked; none has stock above safety stock for the whole horizon")
        # ---------------------------------------------------- substitutes
        start_date = as_of + timedelta(weeks=s)
        for link in subs.get(r.sku_id, []):
            ref = f"{link['substitution_id']}:{link['substitute_sku_id']}"
            j = key.get((link["substitute_sku_id"], loc))
            sp = surplus(j, s) if j is not None else 0
            if link["approval_status"] != "APPROVED":
                rej("APPROVED_SUBSTITUTE", ref, "SUBSTITUTE_NOT_APPROVED",
                    f"substitution {link['substitution_id']} is {link['approval_status']}; would have offered "
                    f"{max(0, sp)} units at {loc} but policy forbids unapproved substitutes")
                continue
            eff_to = _none(link["effective_to"])
            if _d(link["effective_from"]) > start_date or (eff_to and _d(eff_to) < start_date):
                rej("APPROVED_SUBSTITUTE", ref, "SUBSTITUTE_NOT_EFFECTIVE",
                    f"link effective {link['effective_from']}..{eff_to or 'open'}, shortage starts {start_date}")
                continue
            if sp <= 0:
                rej("APPROVED_SUBSTITUTE", ref, "NO_SURPLUS",
                    f"{link['substitute_sku_id']} has no stock above safety stock at {loc} from {ctx.week_ids[s]}")
                continue
            ratio = float(link["conversion_ratio"])
            used = min(sp, int(math.ceil(Q * ratio)))
            covered = int(math.floor(used / ratio))
            sub_cost = float(sku.at[link["substitute_sku_id"], "unit_cost"])
            total = used * sub_cost
            inc = COSTS["substitute_fee"] + max(0.0, sub_cost * ratio - float(info.unit_cost)) * covered
            opts.append(dict(mitigation_type="APPROVED_SUBSTITUTE", substitute_sku_id=link["substitute_sku_id"],
                             substitution_id=link["substitution_id"], proposed_qty=covered, arrival_week_index=s,
                             total_cost=total, incremental_cost=inc, capacity_available=sp, capacity_consumed=used,
                             moq_check="N/A", lead_time_check="N/A", approval_check="PASS", capacity_check="PASS",
                             rationale=f"use {used} of approved substitute {link['substitute_sku_id']} "
                                       f"({link['substitution_id']}, approved by {link['approved_by']})",
                             reserve=[("stock", j, s, used)]))
        # ---------------------------------------------------- increase production
        if info.sourcing_type == "MAKE":
            fz = POLICY["frozen_weeks"]
            if e < fz:
                rej("INCREASE_PRODUCTION", loc, "LEAD_TIME_TOO_LONG",
                    f"shortage ends inside the {fz}-week frozen production fence")
            else:
                pi = PC["pidx"][loc]
                b = int(batch.get(r.sku_id, 1))
                need = int(math.ceil(Q / b) * b)
                plan = []
                for w in range(fz, e + 1):
                    room = PC["cap"][pi, w] - PC["planned"][pi, w] - PC["reserved"][pi, w]
                    take = int(min(room, need - sum(q for _, q in plan)) // b * b)
                    if take > 0:
                        plan.append((w, take))
                    if sum(q for _, q in plan) >= need:
                        break
                total_q = sum(q for _, q in plan)
                comp_res = []
                if total_q > 0:
                    w0 = plan[0][0]
                    limit = total_q
                    for c in bom_by_parent.get(r.sku_id, []):
                        cj = key.get((c["component_sku_id"], loc))
                        csp = surplus(cj, w0) if cj is not None else 0
                        limit = min(limit, int(math.floor(max(0, csp) / float(c["qty_per"]) / b) * b))
                    if limit < total_q:
                        trimmed, acc = [], 0
                        for w, q in plan:
                            q = min(q, limit - acc)
                            if q > 0:
                                trimmed.append((w, q))
                                acc += q
                        plan, total_q = trimmed, acc
                    if total_q > 0:
                        for c in bom_by_parent.get(r.sku_id, []):
                            cj = key[(c["component_sku_id"], loc)]
                            comp_res.append(("stock", cj, w0, int(math.ceil(total_q * float(c["qty_per"]) - 1e-9))))
                if total_q <= 0:
                    reason = "COMPONENT_SHORTAGE" if plan == [] and any(
                        PC["cap"][pi, w] - PC["planned"][pi, w] - PC["reserved"][pi, w] >= b
                        for w in range(fz, e + 1)) else "INSUFFICIENT_CAPACITY"
                    rej("INCREASE_PRODUCTION", loc, reason,
                        (f"plant {loc} has headroom but components lack stock above safety stock between "
                         if reason == "COMPONENT_SHORTAGE" else f"plant {loc} has no capacity headroom between ")
                        + f"{ctx.week_ids[fz]} and {ctx.week_ids[e]}")
                else:
                    a = plan[-1][0]
                    total = total_q * float(info.unit_cost)
                    opts.append(dict(mitigation_type="INCREASE_PRODUCTION", proposed_qty=total_q,
                                     arrival_week_index=a, total_cost=total,
                                     incremental_cost=total * COSTS["overtime_premium_pct"],
                                     capacity_available=int(sum(PC["cap"][pi, fz:e + 1] - PC["planned"][pi, fz:e + 1]
                                                                - PC["reserved"][pi, fz:e + 1])),
                                     capacity_consumed=total_q, moq_check="N/A", lead_time_check="PASS",
                                     approval_check="N/A", capacity_check="PASS",
                                     rationale="extra batches " + ", ".join(f"{ctx.week_ids[w]}:{q}" for w, q in plan)
                                               + f" outside the {fz}-week frozen fence; components reserved",
                                     reserve=[("plant", pi, w, q) for w, q in plan] + comp_res))
        # ---------------------------------------------------- accept backorder (do nothing)
        if info.item_type == "COMPONENT":
            lost = Q * float(info.unit_cost) * COSTS["component_backorder_pct"]
        else:
            lost = Q * (float(info.unit_price) - float(info.unit_cost))
        opts.append(dict(mitigation_type="ACCEPT_BACKORDER", proposed_qty=0, arrival_week_index=None,
                         total_cost=0.0, incremental_cost=lost, moq_check="N/A", lead_time_check="N/A",
                         approval_check="N/A", capacity_check="N/A",
                         rationale=f"no action: {Q} units back-ordered/lost; lost margin {lost:,.2f}", reserve=[]))
        # ---------------------------------------------------- score, rank, reserve
        scored = []
        for o in opts:
            covered = min(int(o["proposed_qty"]), Q)
            if o["mitigation_type"] != "ACCEPT_BACKORDER" and covered <= 0:
                rej(o["mitigation_type"], o.get("supplier_id") or o.get("source_location_id") or "-",
                    "NO_BENEFIT", "option covers no shortage quantity")
                continue
            a = o.get("arrival_week_index")
            late = max(0, int(a) - s) if a is not None else int(r.duration_weeks)
            fill = covered / Q
            service = fill * max(0.0, 1 - COSTS["lateness_penalty_per_week"] * late) if covered else 0.0
            o.update(covered_qty=covered, residual_shortage_qty=Q - covered, fill_rate_pct=round(100 * fill, 2),
                     weeks_late=late, service_score=round(service, 4),
                     total_cost=round(float(o["total_cost"]), 2), incremental_cost=round(float(o["incremental_cost"]), 2))
            o["net_benefit"] = round(service * V - o["incremental_cost"], 2)
            scored.append(o)
        scored.sort(key=lambda o: (-o["net_benefit"], o["incremental_cost"], TYPE_ORDER[o["mitigation_type"]]))
        for rank, o in enumerate(scored, start=1):
            o["option_rank"] = rank
            o["is_recommended"] = rank == 1
            o["mitigation_id"] = f"MIT-{r.shortage_id}-{rank:02d}"
            o["shortage_id"] = r.shortage_id
        top = scored[0]
        for kind, idx, w, q in top["reserve"]:
            if kind == "sup":
                S["reserved"][idx, w] += q
            elif kind == "plant":
                PC["reserved"][idx, w] += q
            else:
                closing_res[idx, w:] -= q
        cov = top["covered_qty"] if top["mitigation_type"] != "ACCEPT_BACKORDER" else 0
        status[r.shortage_id] = ("MITIGATION_PROPOSED" if cov >= Q else "PARTIALLY_MITIGATED" if cov > 0
                                 else "UNMITIGATED")
        mit_rows += scored
        for n, x in enumerate(rejs, start=1):
            rej_rows.append(dict(rejection_id=f"REJ-{r.shortage_id}-{n:02d}", shortage_id=r.shortage_id, **x))

    mit = pd.DataFrame(mit_rows)
    for c in TABLES["mitigation_option"].columns:
        if c not in mit.columns:
            mit[c] = None
    mit = mit[TABLES["mitigation_option"].columns]
    for c in ["order_qty_purchase_uom", "arrival_week_index", "capacity_available", "capacity_consumed",
              "lead_time_days"]:
        mit[c] = pd.array(mit[c].astype(object).where(mit[c].notna(), None), dtype="Int64")
    rej = pd.DataFrame(rej_rows, columns=TABLES["rejected_mitigation"].columns)
    sh = sh.copy()
    sh["status"] = sh.shortage_id.map(status)
    st.closing_reserved = closing_res
    return mit, rej, sh, S, PC
