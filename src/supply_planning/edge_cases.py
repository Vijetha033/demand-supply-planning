"""Inject the five labelled edge cases into a *valid* baseline.

Every case adds new, clearly identifiable records (new IDs at the end of each
counter) instead of corrupting existing rows; the label lives only in the
ground-truth table, together with the IDs needed to trace it.

    INBOUND_DOUBLE_COUNT       duplicate IN_TRANSIT inventory row for a PO line already in transit
    SUBSTITUTE_NOT_APPROVED    PENDING/REJECTED substitute link for a short SKU whose substitute has stock
    SUPPLIER_CAPACITY_EXCEEDED new PO pushing a supplier-week above its capacity
    SHORTAGE_WITHOUT_LEAD_TIME new PO whose receipt date was computed without the lane lead time
    UOM_MISMATCH               new PO line ordered in cases but recorded as base units (A) or in an
                               unconvertible unit (B)

Targets are chosen with a baseline planning run so each case is meaningful
(e.g. the unapproved substitute would really have covered a shortage).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from . import ids
from .config import ScaleConfig
from .generator import STAGES, round_purchase_qty, select_lead_time_version

RULES = {
    "INBOUND_DOUBLE_COUNT": "R1: inbound supply is counted once, from the open PO line; at most one IN_TRANSIT "
                            "inventory row per PO line",
    "SUBSTITUTE_NOT_APPROVED": "R2: only APPROVED and effective sku_substitute links may be used in mitigations",
    "SUPPLIER_CAPACITY_EXCEEDED": "R3: committed open-PO quantity per supplier ship-week <= capacity_units; excess "
                                  "is deferred latest-created-first to the next week with capacity",
    "SHORTAGE_WITHOUT_LEAD_TIME": "R4: promised_receipt_date >= order_date + lead_time.total_lead_days; receipts "
                                  "violating this are recalculated before shortages are computed",
    "UOM_MISMATCH": "R5: base_qty = order_qty * conversion factor from supplier_sku (or sku.units_per_case); "
                    "unconvertible lines are excluded from supply",
    "DEMAND_SPIKE": "S1: generator multiplied forecast by 2.5-4.5x in this week (not in the PO planning basis)",
    "CONSTRAINED_SUPPLIER": "S2: generator set weekly capacity ~= mean load, cutting confirmed quantities",
    "CONSTRAINED_PLANT": "S3: generator set plant capacity ~= mean load, cutting planned production",
}


def _none_records(df: pd.DataFrame) -> list[dict]:
    return df.astype(object).where(df.notna(), None).to_dict("records")


class EdgeCaseInjector:
    def __init__(self, t: dict, hidden: dict, cfg: ScaleConfig, st):
        self.t, self.hidden, self.cfg, self.st = t, hidden, cfg, st
        self.r = np.random.default_rng([cfg.seed, STAGES["edge_cases"]])
        self.ctx = st.ctx
        self.as_of = st.ctx.as_of
        self.W = st.ctx.W
        self.n = cfg.edge_cases_per_type
        self.gt: list[dict] = []
        po = t["purchase_order"]
        self.next_po = int(po.po_id.str[-6:].astype(int).max()) + 1
        self.next_inv = int(t["inventory"].inventory_id.str[-6:].astype(int).max()) + 1
        self.next_ev = int(t["purchase_order_event"].event_id.str[-7:].astype(int).max()) + 1
        sub = t["sku_substitute"]
        self.next_sub = int(sub.substitution_id.str[-6:].astype(int).max()) + 1 if len(sub) else 1
        S = st.S
        self.sidx, self.cap = S["sidx"], S["cap"]
        self.load = S["load"].copy()          # planned (corrected) load
        self.src_load = S["src_load"].copy()  # as-recorded load
        self.lanes = {}
        for row in _none_records(t["lead_time"]):
            self.lanes.setdefault((row["supplier_id"], row["location_id"]), []).append(row)
        self.terms = {(row["supplier_id"], row["sku_id"]): row for row in _none_records(t["supplier_sku"])}
        self.sku = t["sku"].set_index("sku_id")
        self.sup = t["supplier"].set_index("supplier_id")
        self.used_suppliers: set[str] = set()
        self.new = {k: [] for k in ("purchase_order", "purchase_order_line", "purchase_order_event",
                                    "inventory", "sku_substitute")}

    # ------------------------------------------------------------------ helpers
    def label(self, issue_type, record_type, record_id, decision, description, related=None, sku=None,
              loc=None, sup=None, week=None, value=None, category="EDGE_CASE"):
        self.gt.append(dict(label_category=category, issue_type=issue_type, record_type=record_type,
                            record_id=record_id, related_record_ids=related, sku_id=sku, location_id=loc,
                            supplier_id=sup, week_id=week, expected_decision=decision,
                            expected_value=None if value is None else str(value),
                            rule_reference=RULES[issue_type], description=description))

    def rem(self, sid: str, w: int, source: bool = False) -> float:
        if not (0 <= w < self.W):
            return float("inf")
        L = self.src_load if source else self.load
        i = self.sidx[sid]
        return self.cap[i, w] - L[i, w]

    def add_load(self, sid, w_src, w_plan, base_src, base_plan):
        i = self.sidx[sid]
        if 0 <= w_src < self.W:
            self.src_load[i, w_src] += base_src
        if 0 <= w_plan < self.W:
            self.load[i, w_plan] += base_plan

    def make_po(self, sid, loc, sku_id, lt, order_date: date, ship_date: date, promised: date, order_qty: int,
                order_uom: str, factor: float, base_qty: int, note: str) -> tuple[str, str]:
        t = self.terms[(sid, sku_id)]
        pid = ids.po_id(self.ctx.year, self.next_po)
        self.next_po += 1
        lid = ids.po_line_id(pid, 1)
        created = datetime(self.as_of.year, self.as_of.month, self.as_of.day) - timedelta(minutes=30)
        value = round(base_qty * float(t["unit_cost"]), 2)
        self.new["purchase_order"].append(dict(
            po_id=pid, supplier_id=sid, location_id=loc, lead_time_id=lt["lead_time_id"],
            order_date=order_date.isoformat(), ship_date=ship_date.isoformat(),
            promised_receipt_date=promised.isoformat(), transport_delay_days=0,
            expected_receipt_date=promised.isoformat(), actual_receipt_date=None, status="PLANNED", line_count=1,
            total_base_qty=int(base_qty), total_value=value, currency="USD", created_at=created.isoformat()))
        self.new["purchase_order_line"].append(dict(
            po_line_id=lid, po_id=pid, line_number=1, sku_id=sku_id, supplier_sku_id=t["supplier_sku_id"],
            requested_qty=int(order_qty), order_qty=int(order_qty), order_uom=order_uom,
            uom_conversion_factor=float(factor), base_qty=int(base_qty), base_uom=self.sku.at[sku_id, "base_uom"],
            unit_cost=float(t["unit_cost"]), line_value=value))
        self.new["purchase_order_event"].append(dict(
            event_id=ids.seq_id("POE", self.next_ev, 7), po_id=pid, event_seq=1, event_type="CREATED",
            from_status=None, to_status="PLANNED", event_timestamp=created.isoformat(), actor="PLANNER",
            delay_days=0, note=note))
        self.next_ev += 1
        return pid, lid

    def supplier_lanes(self, sid):
        """(location, sku) pairs the supplier can ship that are stocked there."""
        sl = self.t["sku_location"]
        skus = {k[1] for k in self.terms if k[0] == sid}
        rows = sl[sl.sku_id.isin(skus)]
        return [(l, s) for s, l in zip(rows.sku_id, rows.location_id) if (sid, l) in self.lanes]

    # ------------------------------------------------------------------ 1
    def inbound_double_count(self):
        inv = self.t["inventory"]
        it = inv[inv.stock_status == "IN_TRANSIT"]
        if it.empty:
            return
        po_of = self.t["purchase_order_line"].set_index("po_line_id").po_id
        recv = self.t["purchase_order"].set_index("po_id")
        for k in sorted(self.r.choice(len(it), min(self.n, len(it)), replace=False)):
            row = it.iloc[int(k)].to_dict()
            orig = row["inventory_id"]
            row["inventory_id"] = ids.seq_id("INV", self.next_inv)
            self.next_inv += 1
            self.new["inventory"].append(row)
            pid = po_of[row["po_line_id"]]
            wk = self.ctx.wid(self.ctx.widx(recv.at[pid, "expected_receipt_date"]))
            self.label("INBOUND_DOUBLE_COUNT", "inventory", row["inventory_id"], "EXCLUDE_DUPLICATE_INBOUND",
                       f"In-transit record duplicates {orig}; naive on-hand + in-transit + open PO would count "
                       f"{row['quantity']} units two (or three) times",
                       related=f"{orig}|{row['po_line_id']}|{pid}", sku=row["sku_id"], loc=row["location_id"],
                       sup=recv.at[pid, "supplier_id"], week=wk, value=int(row["quantity"]))

    # ------------------------------------------------------------------ 2
    def substitute_not_approved(self):
        st, M = self.st, self.st.M
        sh = st.out["shortage"]
        if sh.empty:
            return
        sub = self.t["sku_substitute"]
        existing = set(zip(sub.sku_id, sub.substitute_sku_id))
        fg = self.sku[self.sku.item_type == "FINISHED_GOOD"]
        sl = M["sl"]
        by_loc = sl.groupby("location_id").sku_id.apply(list).to_dict()
        surplus = M["closing"] - M["SS"][:, None]
        cands = sh[sh.sku_id.isin(fg.index)].sort_values("priority_rank")
        order = self.r.permutation(len(cands))
        done, used_pairs = 0, set()
        for k in order:
            if done >= self.n:
                break
            r = cands.iloc[int(k)]
            if (r.sku_id, r.location_id) in used_pairs:
                continue
            best = None
            for s2 in by_loc.get(r.location_id, []):
                if s2 == r.sku_id or s2 not in fg.index or (r.sku_id, s2) in existing:
                    continue
                if fg.at[s2, "base_uom"] != fg.at[r.sku_id, "base_uom"]:
                    continue
                j = M["key"][(s2, r.location_id)]
                sp = int(surplus[j, int(r.start_week_index):].min())
                if sp > 0 and (best is None or sp > best[1]):
                    best = (s2, sp)
            if best is None:
                continue
            status = "PENDING" if done % 2 == 0 else "REJECTED"
            sid = ids.seq_id("SUB", self.next_sub)
            self.next_sub += 1
            self.new["sku_substitute"].append(dict(
                substitution_id=sid, sku_id=r.sku_id, substitute_sku_id=best[0], conversion_ratio=1.0,
                approval_status=status, approved_by=None, approval_date=None,
                effective_from=(self.as_of - timedelta(days=30)).isoformat(), effective_to=None, priority=1))
            existing.add((r.sku_id, best[0]))
            used_pairs.add((r.sku_id, r.location_id))
            self.label("SUBSTITUTE_NOT_APPROVED", "sku_substitute", sid, "REJECT_SUBSTITUTE_MITIGATION",
                       f"{best[0]} ({status}) would offer {best[1]} surplus units for the {r.sku_id} shortage at "
                       f"{r.location_id} starting {r.start_week_id}; it must not be proposed",
                       related=f"{best[0]}|{r.sku_id}|{r.location_id}", sku=r.sku_id, loc=r.location_id,
                       week=r.start_week_id, value=f"{best[0]} excluded")
            done += 1

    # ------------------------------------------------------------------ 3
    def supplier_capacity_exceeded(self):
        sups = [s for s in sorted(self.sidx) if self.sup.at[s, "status"] == "ACTIVE"]
        done = 0
        for s in self.r.permutation(sups):
            if done >= self.n:
                break
            s = str(s)
            pairs = self.supplier_lanes(s)
            if not pairs or s in self.used_suppliers:
                continue
            loc, sku_id = pairs[int(self.r.integers(len(pairs)))]
            versions = self.lanes[(s, loc)]
            weeks = list(range(4, self.W - 6))
            for w in self.r.permutation(weeks):
                w = int(w)
                ship = self.as_of + timedelta(weeks=w, days=1)
                lt = select_lead_time_version(versions, ship - timedelta(days=versions[0]["production_lead_days"]))
                order = ship - timedelta(days=lt["production_lead_days"])
                if order <= self.as_of or self.ctx.widx(ship) != w:
                    continue
                cap = self.cap[self.sidx[s], w]
                if cap <= 0 or self.load[self.sidx[s], w] > cap or self.src_load[self.sidx[s], w] > cap:
                    continue
                tm = self.terms[(s, sku_id)]
                conv = float(tm["uom_conversion_factor"])
                need = self.rem(s, w) + max(math.ceil(0.3 * cap), conv * tm["min_order_qty"])
                pq = round_purchase_qty(need, conv, int(tm["min_order_qty"]), int(tm["order_multiple"]))
                base = int(round(pq * conv))
                promised = order + timedelta(days=lt["total_lead_days"])
                pid, lid = self.make_po(s, loc, sku_id, lt, order, ship, promised, pq, tm["purchase_uom"], conv,
                                        base, "Rush order entered without capacity check")
                committed = int(self.load[self.sidx[s], w] + base)
                self.add_load(s, w, w, base, base)
                self.used_suppliers.add(s)
                wid = self.ctx.week_ids[w]
                self.label("SUPPLIER_CAPACITY_EXCEEDED", "supplier_capacity", f"SCAP-{s}-{wid}",
                           "DEFER_EXCESS_TO_NEXT_AVAILABLE_WEEK",
                           f"{pid} adds {base} units to {s} ship week {wid}: committed {committed} > capacity "
                           f"{int(cap)}", related=f"{pid}|{lid}", sku=sku_id, loc=loc, sup=s, week=wid,
                           value=f"committed {committed} > capacity {int(cap)}")
                done += 1
                break

    # ------------------------------------------------------------------ 4
    def shortage_without_lead_time(self):
        st = self.st
        sl = st.M["sl"]
        sh = st.out["shortage"]
        sh_keys = list(zip(sh.sku_id, sh.location_id)) if len(sh) else []
        pref = {k: i for i, k in enumerate(sh_keys)}
        cands = []
        for r in sl[sl.planning_method == "PURCHASE"].itertuples():
            sid = r.primary_supplier_id
            if sid in self.used_suppliers or self.sup.at[sid, "status"] != "ACTIVE":
                continue
            lt = select_lead_time_version(self.lanes[(sid, r.location_id)], self.as_of)
            if lt["total_lead_days"] < 14:
                continue
            cands.append((pref.get((r.sku_id, r.location_id), 10 ** 6), r.sku_id, r.location_id, sid))
        cands.sort()
        head = cands[:max(self.n * 3, 1)]
        done = 0
        for k in self.r.permutation(len(head)):
            if done >= self.n:
                break
            _, sku_id, loc, sid = head[int(k)]
            if sid in self.used_suppliers:
                continue
            order = self.as_of + timedelta(days=int(self.r.integers(1, 3)))
            lt = select_lead_time_version(self.lanes[(sid, loc)], order)
            tm = self.terms[(sid, sku_id)]
            conv = float(tm["uom_conversion_factor"])
            i = st.M["key"][(sku_id, loc)]
            need = max(1, int(st.M["D"][i, :3].sum()))
            pq = round_purchase_qty(need, conv, int(tm["min_order_qty"]), int(tm["order_multiple"]))
            base = int(round(pq * conv))
            w_naive = self.ctx.widx(order)
            correct_ship = order + timedelta(days=lt["production_lead_days"])
            w_corr = self.ctx.widx(correct_ship)
            if self.rem(sid, w_naive, source=True) < base or self.rem(sid, w_corr) < base:
                continue
            pid, lid = self.make_po(sid, loc, sku_id, lt, order, order, order, pq, tm["purchase_uom"], conv, base,
                                    "Receipt date keyed as order date")
            self.add_load(sid, w_naive, w_corr, base, base)
            self.used_suppliers.add(sid)
            correct = order + timedelta(days=lt["total_lead_days"])
            self.label("SHORTAGE_WITHOUT_LEAD_TIME", "purchase_order", pid, "RECALCULATE_RECEIPT_WITH_LEAD_TIME",
                       f"{pid} promises receipt on its order date {order}; lane {lt['lead_time_id']} needs "
                       f"{lt['total_lead_days']} days, so {base} units cannot arrive before {correct} "
                       f"({self.ctx.wid(self.ctx.widx(correct))})",
                       related=f"{lid}|{lt['lead_time_id']}", sku=sku_id, loc=loc, sup=sid,
                       week=self.ctx.wid(w_naive), value=correct.isoformat())
            done += 1

    # ------------------------------------------------------------------ 5
    def uom_mismatch(self):
        ss = self.t["supplier_sku"]
        sl = self.t["sku_location"]
        stocked = sl.groupby("sku_id").location_id.apply(list).to_dict()
        done = 0
        order_ss = ss.iloc[self.r.permutation(len(ss))]
        for tm in _none_records(order_ss):
            if done >= self.n:
                break
            sid, sku_id = tm["supplier_id"], tm["sku_id"]
            variant = "A" if done % 2 == 0 else "B"
            if sid in self.used_suppliers or self.sup.at[sid, "status"] != "ACTIVE":
                continue
            base_uom = self.sku.at[sku_id, "base_uom"]
            if variant == "A" and not (tm["purchase_uom"] == "CS" and tm["uom_conversion_factor"] > 1):
                continue
            if variant == "B" and not (base_uom == "EA" and tm["purchase_uom"] in ("EA", "CS")):
                continue
            locs = [l for l in stocked.get(sku_id, []) if (sid, l) in self.lanes]
            if not locs:
                continue
            loc = locs[0]
            k = int(self.r.integers(2, self.W - 12))
            promised = self.as_of + timedelta(weeks=k, days=2)
            lt = select_lead_time_version(self.lanes[(sid, loc)], promised - timedelta(
                days=self.lanes[(sid, loc)][0]["total_lead_days"]))
            order = promised - timedelta(days=lt["total_lead_days"])
            if order <= self.as_of:
                continue
            ship = order + timedelta(days=lt["production_lead_days"])
            w = self.ctx.widx(ship)
            pq = int(tm["min_order_qty"])
            if variant == "A":
                order_uom, recorded, correct = "CS", 1.0, int(round(pq * tm["uom_conversion_factor"]))
                if self.rem(sid, w, source=True) < pq or self.rem(sid, w) < correct:
                    continue
                decision, value = "CONVERT_USING_MASTER_UOM", correct
                desc = (f"{pq} CS recorded with factor 1 as {pq} {base_uom}; supplier terms say 1 CS = "
                        f"{tm['uom_conversion_factor']:g} {base_uom} -> {correct}")
                plan_base = correct
            else:
                order_uom, recorded = "KG", 1.0
                if self.rem(sid, w, source=True) < pq:
                    continue
                decision, value = "EXCLUDE_UNCONVERTIBLE_LINE", 0
                desc = (f"{pq} KG ordered for an EA-based SKU with no KG conversion in supplier terms "
                        f"({tm['purchase_uom']}); quantity cannot be trusted")
                plan_base = 0
            pid, lid = self.make_po(sid, loc, sku_id, lt, order, ship, promised, pq, order_uom, recorded, pq,
                                    f"Variant {variant}: unit of measure keyed incorrectly")
            self.add_load(sid, w, w, pq, plan_base)
            self.used_suppliers.add(sid)
            self.label("UOM_MISMATCH", "purchase_order_line", lid, decision, desc, related=pid, sku=sku_id, loc=loc,
                       sup=sid, week=self.ctx.wid(self.ctx.widx(promised)), value=value)
            done += 1

    # ------------------------------------------------------------------ scenario labels
    def scenario_labels(self):
        W = self.ctx.week_ids
        for s, l, w, mult, base in self.hidden.get("spikes", []):
            self.label("DEMAND_SPIKE", "forecast_demand", f"DEM-{s}-{l}-{W[w]}", "FLAG_FOR_DEMAND_REVIEW",
                       f"forecast multiplied {mult}x over a base of {base}", sku=s, loc=l, week=W[w], value=mult,
                       category="SCENARIO")
        for s in self.hidden.get("constrained_suppliers", []):
            self.label("CONSTRAINED_SUPPLIER", "supplier", s, "FLAG_CONSTRAINED_SUPPLIER",
                       "weekly capacity set close to mean load", sup=s, category="SCENARIO")
        p = self.hidden.get("constrained_plant")
        if p:
            self.label("CONSTRAINED_PLANT", "location", p, "FLAG_CONSTRAINED_PLANT",
                       "plant capacity set close to mean load", loc=p, category="SCENARIO")

    # ------------------------------------------------------------------ run
    def run(self) -> tuple[dict, pd.DataFrame]:
        self.inbound_double_count()
        self.substitute_not_approved()
        self.supplier_capacity_exceeded()
        self.shortage_without_lead_time()
        self.uom_mismatch()
        self.scenario_labels()
        t = dict(self.t)
        for name, rows in self.new.items():
            if rows:
                t[name] = pd.concat([t[name], pd.DataFrame(rows)], ignore_index=True)
        gt = pd.DataFrame(self.gt)
        gt.insert(0, "gt_id", [ids.seq_id("GT", i + 1) for i in range(len(gt))])
        return t, gt


def inject_edge_cases(t: dict, hidden: dict, cfg: ScaleConfig, baseline_state) -> tuple[dict, pd.DataFrame]:
    return EdgeCaseInjector(t, hidden, cfg, baseline_state).run()
