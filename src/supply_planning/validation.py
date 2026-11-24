"""Validation suite (brief step 8 + acceptance criteria in section 7).

Runs on the exported files.  Checks: schema/type/required, ID patterns, enums,
ranges, primary-key uniqueness, natural-key duplicates, foreign-key integrity
(pandas and SQLite with enforced foreign keys), date ordering, arithmetic
reconciliation, lifecycle transitions, duplicate records, cross-entity rules,
label-leakage guard and planning-output reconciliation.

Each violation is classified as EXPECTED when it points at a record labelled
in ground truth (a deliberately injected edge case) and UNEXPECTED otherwise.
A run passes when there are zero unexpected violations.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .generator import FORECAST_CV, Z_BY_ABC, dependent_demand_units, pareto_abc, safety_stock
from .io import ddl_for, read_table
from .planning import OPEN_STATUSES, master_uom_factor
from .schema import INPUT_TABLES, LEAKAGE_COLUMNS, OUTPUT_TABLES, TABLES

ALLOWED_TRANSITIONS = {
    (None, "PLANNED"), ("PLANNED", "CONFIRMED"), ("CONFIRMED", "IN_TRANSIT"), ("IN_TRANSIT", "RECEIVED"),
    ("PLANNED", "CANCELLED"), ("CONFIRMED", "CANCELLED"), ("CONFIRMED", "CONFIRMED"), ("IN_TRANSIT", "IN_TRANSIT"),
}
EVENT_FOR = {"CREATED": (None, "PLANNED"), "CONFIRMED": ("PLANNED", "CONFIRMED"),
             "SHIPPED": ("CONFIRMED", "IN_TRANSIT"), "RECEIVED": ("IN_TRANSIT", "RECEIVED")}


class Validator:
    def __init__(self, t: dict[str, pd.DataFrame], gt: pd.DataFrame | None = None,
                 input_dir: Path | None = None):
        self.t = t
        self.v: list[dict] = []
        self.checks: dict[str, dict] = {}
        cal = t["calendar_week"].sort_values("week_index")
        self.as_of = date.fromisoformat(cal.week_start_date.iloc[0])
        self.W = len(cal)
        self.week_ids = cal.week_id.tolist()
        self.input_dir = input_dir
        self.gt = gt

    # ------------------------------------------------------------------ bookkeeping
    def check(self, name: str, category: str, description: str, rows: int):
        self.checks[name] = dict(check=name, category=category, description=description, rows_checked=int(rows))

    def fail(self, name: str, table: str, record_id, detail: str):
        self.v.append(dict(check=name, category=self.checks[name]["category"], table=table,
                           record_id=str(record_id), detail=detail))

    def fail_many(self, name, table, ids, detail_fn):
        for rid in ids:
            self.fail(name, table, rid, detail_fn(rid) if callable(detail_fn) else detail_fn)

    def widx(self, d) -> int:
        return (date.fromisoformat(str(d)[:10]) - self.as_of).days // 7

    # ------------------------------------------------------------------ generic schema checks
    def schema_checks(self, tables):
        for name in tables:
            spec, df = TABLES[name], self.t[name]
            pk = spec.primary_key
            n = f"schema:{name}"
            self.check(n, "schema", f"{name}: columns, required, types, patterns, enums, ranges", len(df))
            missing = [c for c in spec.columns if c not in df.columns]
            for c in missing:
                self.fail(n, name, "-", f"missing column {c}")
            for f in spec.fields:
                if f.name not in df.columns:
                    continue
                s = df[f.name]
                ids = df[pk] if pk in df.columns else df.index
                if f.required:
                    bad = s.isna()
                    self.fail_many(n, name, ids[bad], f"{f.name} is required")
                nn = s.notna()
                if f.pattern:
                    bad = nn & ~s.astype(str).str.match(f.pattern)
                    self.fail_many(n, name, ids[bad], lambda r, f=f: f"{f.name} does not match {f.pattern}")
                if f.allowed:
                    bad = nn & ~s.isin(f.allowed)
                    self.fail_many(n, name, ids[bad], lambda r, f=f: f"{f.name} not in allowed values")
                if f.dtype in ("integer", "decimal") and (f.min_value is not None or f.max_value is not None):
                    x = pd.to_numeric(s, errors="coerce")
                    bad = nn & (((x < f.min_value) if f.min_value is not None else False) |
                                ((x > f.max_value) if f.max_value is not None else False))
                    self.fail_many(n, name, ids[bad], lambda r, f=f: f"{f.name} out of range")
                if f.dtype == "date":
                    x = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
                    self.fail_many(n, name, ids[nn & x.isna()], lambda r, f=f: f"{f.name} not an ISO date")
                if f.unique and f.name != pk:
                    self.fail_many(n, name, ids[nn & s.duplicated(keep=False)], f"{f.name} not unique")
            # primary key
            k = f"pk:{name}"
            self.check(k, "primary_key", f"{name}.{pk} unique and not null", len(df))
            self.fail_many(k, name, df[pk][df[pk].duplicated()], "duplicate primary key")
            self.fail_many(k, name, df.index[df[pk].isna()], "null primary key")
            # natural key
            if spec.natural_key:
                k = f"duplicate:{name}"
                self.check(k, "duplicate", f"{name} natural key {spec.natural_key} unique", len(df))
                d = df[df.duplicated(spec.natural_key, keep="first")]
                self.fail_many(k, name, d[pk], f"duplicate natural key {spec.natural_key}")
            # foreign keys
            for fk in spec.foreign_keys:
                k = f"fk:{name}.{'+'.join(fk.columns)}->{fk.ref_table}"
                self.check(k, "foreign_key", f"{name}({', '.join(fk.columns)}) -> {fk.ref_table}", len(df))
                parent = self.t.get(fk.ref_table)
                if parent is None:
                    continue
                child = df[fk.columns].dropna()
                pkeys = set(map(tuple, parent[fk.ref_columns].astype(str).to_numpy()))
                ck = list(map(tuple, child.astype(str).to_numpy()))
                bad = [df.at[i, pk] for i, key in zip(child.index, ck) if key not in pkeys]
                self.fail_many(k, name, bad, f"orphan reference to {fk.ref_table}")

    # ------------------------------------------------------------------ input-specific checks
    def input_checks_basic(self):
        t = self.t
        sku = self._sku()
        cal = t["calendar_week"]
        # calendar
        n = "date:calendar"
        self.check(n, "date_ordering", "calendar weeks consecutive, end = start + 6", len(cal))
        for r in cal.itertuples():
            if date.fromisoformat(r.week_end_date) != date.fromisoformat(r.week_start_date) + timedelta(days=6) or \
                    date.fromisoformat(r.week_start_date) != self.as_of + timedelta(weeks=int(r.week_index)):
                self.fail(n, "calendar_week", r.week_id, "calendar dates inconsistent")
        # sku lifecycle
        n = "lifecycle:sku"
        self.check(n, "lifecycle", "PHASE_OUT iff effective_to; effective_to >= effective_from; NEW starts in horizon",
                   len(sku))
        for sid, r in sku.iterrows():
            has_to = isinstance(r.effective_to, str)
            if (r.lifecycle_status == "PHASE_OUT") != has_to or (has_to and r.effective_to < r.effective_from):
                self.fail(n, "sku", sid, "lifecycle/effective dates inconsistent")
            if r.lifecycle_status == "NEW" and r.effective_from < self.as_of.isoformat():
                self.fail(n, "sku", sid, "NEW SKU effective before as-of date")
            if r.item_type == "FINISHED_GOOD" and not (pd.notna(r.unit_price) and r.unit_price > r.unit_cost):
                self.fail(n, "sku", sid, "finished good needs unit_price > unit_cost")
            if r.item_type == "COMPONENT" and r.sourcing_type != "BUY":
                self.fail(n, "sku", sid, "components must be BUY")
        # demand inside effective window / FG only / uom
        fd = t["forecast_demand"]
        n = "date:demand_in_sku_window"
        self.check(n, "date_ordering", "forecast weeks inside SKU effective window; FG only; uom = base_uom", len(fd))
        ws = fd.week_id.map(cal.set_index("week_id").week_start_date)
        ef = fd.sku_id.map(sku.effective_from)
        et = fd.sku_id.map(sku.effective_to).fillna("9999-12-31")
        bad = (ws < ef) | (ws > et) | (fd.sku_id.map(sku.item_type) != "FINISHED_GOOD") | (
            fd.uom != fd.sku_id.map(sku.base_uom))
        self.fail_many(n, "forecast_demand", fd.demand_id[bad], "demand outside SKU window / not FG / wrong uom")
        # lead times
        lt = t["lead_time"]
        n = "arithmetic:lead_time"
        self.check(n, "arithmetic", "total = production + transit; expedite <= transit; versions contiguous", len(lt))
        bad = (lt.total_lead_days != lt.production_lead_days + lt.transit_days) | (
            lt.expedite_transit_days > lt.transit_days)
        self.fail_many(n, "lead_time", lt.lead_time_id[bad], "lead-time arithmetic")
        for _, g in lt.sort_values("version").groupby(["supplier_id", "location_id"]):
            rows = g.to_dict("records")
            if [r["version"] for r in rows] != list(range(1, len(rows) + 1)):
                self.fail(n, "lead_time", rows[0]["lead_time_id"], "version numbers not 1..n")
            for a, b in zip(rows, rows[1:]):
                if a["effective_to"] is None or date.fromisoformat(a["effective_to"]) + timedelta(days=1) != \
                        date.fromisoformat(b["effective_from"]):
                    self.fail(n, "lead_time", b["lead_time_id"], "lead-time versions overlap or leave a gap")
            if rows[-1]["effective_to"] is not None:
                self.fail(n, "lead_time", rows[-1]["lead_time_id"], "latest version must be open-ended")

    def po_checks(self, sku):
        t = self.t
        po, pol, ev = t["purchase_order"], t["purchase_order_line"], t["purchase_order_event"]
        lt = t["lead_time"].set_index("lead_time_id")
        ss = t["supplier_sku"].set_index("supplier_sku_id")
        as_of_s = self.as_of.isoformat()
        # dates
        n = "date:purchase_order"
        self.check(n, "date_ordering", "order <= ship <= promised; expected = promised + delay; actual iff RECEIVED "
                                       "and < as-of", len(po))
        for r in po.itertuples():
            od, sd, pd_, ed = (date.fromisoformat(x) for x in (r.order_date, r.ship_date, r.promised_receipt_date,
                                                               r.expected_receipt_date))
            if not (od <= sd <= pd_) or ed != pd_ + timedelta(days=int(r.transport_delay_days)):
                self.fail(n, "purchase_order", r.po_id, "date ordering / expected receipt arithmetic")
            has_actual = isinstance(r.actual_receipt_date, str)
            if (r.status == "RECEIVED") != has_actual or (has_actual and (
                    r.actual_receipt_date >= as_of_s or r.actual_receipt_date != r.expected_receipt_date)):
                self.fail(n, "purchase_order", r.po_id, "actual_receipt_date inconsistent with status")
        # lead-time rule
        n = "arithmetic:po_lead_time"
        self.check(n, "arithmetic", "PO uses the lane version effective at order_date; ship = order + production "
                                    "lead; promised = order + total lead", len(po))
        for r in po.itertuples():
            l = lt.loc[r.lead_time_id]
            od = date.fromisoformat(r.order_date)
            ok_lane = l.supplier_id == r.supplier_id and l.location_id == r.location_id
            ok_eff = date.fromisoformat(l.effective_from) <= od and (
                not isinstance(l.effective_to, str) or od <= date.fromisoformat(l.effective_to))
            ok_ship = date.fromisoformat(r.ship_date) == od + timedelta(days=int(l.production_lead_days))
            ok_prom = date.fromisoformat(r.promised_receipt_date) == od + timedelta(days=int(l.total_lead_days))
            if not (ok_lane and ok_eff and ok_ship and ok_prom):
                self.fail(n, "purchase_order", r.po_id,
                          f"lane_ok={ok_lane} effective_ok={ok_eff} ship_ok={ok_ship} promised_ok={ok_prom}")
        # line arithmetic + uom + terms
        n = "arithmetic:po_line"
        self.check(n, "arithmetic", "base_qty = order_qty * factor; line_value = base_qty * unit_cost; "
                                    "order_qty <= requested; MOQ and multiple", len(pol))
        n2 = "uom:po_line"
        self.check(n2, "uom", "order UoM and factor agree with supplier terms / SKU master", len(pol))
        n3 = "cross:po_line_terms"
        self.check(n3, "cross_entity", "line supplier_sku belongs to the PO supplier and the line SKU", len(pol))
        hdr_sup = po.set_index("po_id").supplier_id
        for r in pol.itertuples():
            if int(r.base_qty) != int(round(r.order_qty * r.uom_conversion_factor)) or \
                    abs(r.line_value - round(r.base_qty * r.unit_cost, 2)) > 0.011 or r.order_qty > r.requested_qty:
                self.fail(n, "purchase_order_line", r.po_line_id, "line arithmetic")
            term = ss.loc[r.supplier_sku_id]
            if r.order_qty < term.min_order_qty or r.order_qty % term.order_multiple:
                self.fail(n, "purchase_order_line", r.po_line_id, "MOQ / order multiple")
            s = sku.loc[r.sku_id]
            f = master_uom_factor(r.order_uom, term.purchase_uom, term.uom_conversion_factor, s.base_uom,
                                  s.units_per_case)
            if math.isnan(f) or abs(f - r.uom_conversion_factor) > 1e-9 or r.base_uom != s.base_uom:
                self.fail(n2, "purchase_order_line", r.po_line_id,
                          f"{r.order_qty} {r.order_uom} x {r.uom_conversion_factor} vs master factor {f}")
            if term.supplier_id != hdr_sup[r.po_id] or term.sku_id != r.sku_id:
                self.fail(n3, "purchase_order_line", r.po_line_id, "supplier_sku does not match PO supplier/SKU")
        # header totals
        n = "arithmetic:po_totals"
        self.check(n, "arithmetic", "header line_count / total_base_qty / total_value = sum of lines", len(po))
        agg = pol.groupby("po_id").agg(c=("po_line_id", "size"), q=("base_qty", "sum"), v=("line_value", "sum"))
        m = po.set_index("po_id").join(agg)
        bad = (m.line_count != m.c) | (m.total_base_qty != m.q) | ((m.total_value - m.v).abs() > 0.05)
        self.fail_many(n, "purchase_order", m.index[bad.fillna(True)], "header totals do not reconcile")
        # events / lifecycle
        n = "lifecycle:po_events"
        self.check(n, "lifecycle", "events start with CREATED, allowed transitions, chained statuses, increasing "
                                   "timestamps < as-of, status = last event, delay = sum of delays", len(po))
        ev = ev.sort_values(["po_id", "event_seq"])
        pos = po.set_index("po_id")
        for pid, g in ev.groupby("po_id", sort=False):
            rows = g.to_dict("records")
            prev_status, prev_ts, ok, delay = None, None, True, 0
            for k, e in enumerate(rows, start=1):
                fs = e["from_status"] if isinstance(e["from_status"], str) else None
                if e["event_seq"] != k or fs != prev_status or (fs, e["to_status"]) not in ALLOWED_TRANSITIONS:
                    ok = False
                if e["event_type"] in EVENT_FOR and EVENT_FOR[e["event_type"]] != (fs, e["to_status"]):
                    ok = False
                if prev_ts and e["event_timestamp"] <= prev_ts:
                    ok = False
                if e["event_timestamp"] >= as_of_s:
                    ok = False
                prev_status, prev_ts = e["to_status"], e["event_timestamp"]
                delay += int(e["delay_days"] or 0)
            h = pos.loc[pid]
            if rows[0]["event_type"] != "CREATED" or h.created_at != rows[0]["event_timestamp"]:
                ok = False
            if not ok or h.status != prev_status or int(h.transport_delay_days) != delay:
                self.fail(n, "purchase_order", pid, "event history inconsistent with PO")
        missing = set(po.po_id) - set(ev.po_id)
        self.fail_many(n, "purchase_order", sorted(missing), "PO without event history")
        # on-hold suppliers
        n = "policy:on_hold_supplier"
        self.check(n, "policy", "no open PO to an ON_HOLD supplier", len(po))
        held = set(t["supplier"].loc[t["supplier"].status == "ON_HOLD", "supplier_id"])
        bad = po.supplier_id.isin(held) & po.status.isin(["PLANNED", "CONFIRMED"])
        self.fail_many(n, "purchase_order", po.po_id[bad], "open PO to ON_HOLD supplier")

    def capacity_checks(self):
        t = self.t
        po, pol = t["purchase_order"], t["purchase_order_line"]
        cap = t["supplier_capacity"].set_index(["supplier_id", "week_id"]).capacity_units
        n = "capacity:supplier_source"
        self.check(n, "capacity", "sum(open PO base_qty by supplier ship week) <= capacity_units", len(cap))
        m = pol.merge(po[["po_id", "supplier_id", "ship_date", "status"]], on="po_id")
        m = m[m.status.isin(["PLANNED", "CONFIRMED"])]
        m = m.assign(w=[self.widx(d) for d in m.ship_date])
        m = m[(m.w >= 0) & (m.w < self.W)]
        load = m.groupby(["supplier_id", "w"]).base_qty.sum()
        for (s, w), q in load.items():
            c = cap.get((s, self.week_ids[w]))
            if c is not None and q > c:
                self.fail(n, "supplier_capacity", f"SCAP-{s}-{self.week_ids[w]}", f"committed {q} > capacity {c}")
        pp, pc = t["production_plan"], t["production_capacity"].set_index(["location_id", "week_id"]).capacity_units
        n = "capacity:production"
        self.check(n, "capacity", "production: planned <= required, multiple of batch, plant total <= capacity",
                   len(pp))
        bad = (pp.planned_qty > pp.required_qty) | (pp.planned_qty % pp.batch_size != 0)
        self.fail_many(n, "production_plan", pp.production_plan_id[bad], "planned qty rule")
        for (l, w), q in pp.groupby(["location_id", "week_id"]).planned_qty.sum().items():
            if q > pc.get((l, w), 0):
                self.fail(n, "production_capacity", f"PCAP-{l}-{w}", f"planned {q} > capacity")
        sku = t["sku"].set_index("sku_id")
        locs = t["location"].set_index("location_id").location_type
        bad = (pp.sku_id.map(sku.sourcing_type) != "MAKE") | (pp.location_id.map(locs) != "PLANT")
        self.fail_many(n, "production_plan", pp.production_plan_id[bad], "production of non-MAKE SKU or not at plant")
        bom = t["bom"]
        n = "cross:bom"
        self.check(n, "cross_entity", "BOM parent is MAKE, component is COMPONENT, uom = component base", len(bom))
        bad = (bom.parent_sku_id.map(sku.sourcing_type) != "MAKE") | (
            bom.component_sku_id.map(sku.item_type) != "COMPONENT") | (
            bom.component_uom != bom.component_sku_id.map(sku.base_uom))
        self.fail_many(n, "bom", bom.bom_id[bad], "invalid BOM line")

    def policy_checks(self, sku):
        sub = self.t["sku_substitute"]
        n = "policy:substitute_approval"
        self.check(n, "policy", "substitute links are APPROVED (with approver + date); not self; same base UoM",
                   len(sub))
        for r in sub.itertuples():
            if r.approval_status != "APPROVED":
                self.fail(n, "sku_substitute", r.substitution_id, f"substitute link is {r.approval_status}")
            elif not (isinstance(r.approved_by, str) and isinstance(r.approval_date, str)):
                self.fail(n, "sku_substitute", r.substitution_id, "approved without approver/date")
            if r.sku_id == r.substitute_sku_id or sku.at[r.sku_id, "base_uom"] != sku.at[r.substitute_sku_id, "base_uom"]:
                self.fail(n, "sku_substitute", r.substitution_id, "self-substitute or UoM mismatch")

    def derived_master_checks(self, sku):
        t = self.t
        sl = t["sku_location"]
        ss = t["supplier_sku"]
        n = "derived:primary_supplier"
        self.check(n, "derived", "sku_location.primary_supplier_id = supplier_sku priority 1", len(sl))
        prim = ss[ss.supplier_priority == 1].set_index("sku_id").supplier_id
        buy = sl[sl.planning_method != "PRODUCTION"]
        bad = buy.primary_supplier_id != buy.sku_id.map(prim)
        self.fail_many(n, "sku_location", buy.sku_location_id[bad], "primary supplier mismatch")
        bad = (sl.planning_method == "PRODUCTION") & sl.primary_supplier_id.notna()
        self.fail_many(n, "sku_location", sl.sku_location_id[bad], "production SKU-location has a supplier")
        # dependent demand + ABC + safety stock recomputation
        pp, bom = t["production_plan"], t["bom"]
        mm = pp.merge(bom, left_on="sku_id", right_on="parent_sku_id")
        dep = (mm.assign(q=mm.planned_qty * mm.qty_per).groupby(["component_sku_id", "location_id", "week_id"])
               .q.sum().map(dependent_demand_units))
        fd = t["forecast_demand"]
        fg_val = (fd.forecast_qty * fd.sku_id.map(sku.unit_cost)).groupby(fd.sku_id).sum()
        comp_val = (dep * dep.index.get_level_values(0).map(sku.unit_cost)).groupby(level=0).sum()
        abc = {}
        abc.update(pareto_abc(fg_val))
        abc.update(pareto_abc(comp_val))
        n = "derived:abc_class"
        self.check(n, "derived", "abc_class recomputed from annual demand value (Pareto 80/15/5)", len(sku))
        for sid, r in sku.iterrows():
            if r.abc_class != abc.get(sid, "C"):
                self.fail(n, "sku", sid, f"abc {r.abc_class} != recomputed {abc.get(sid, 'C')}")
        n = "derived:safety_stock"
        self.check(n, "derived", "safety_stock_qty = ceil(z(ABC) * 0.3 * mean weekly demand * sqrt(LT weeks))",
                   len(sl))
        fmean = fd.groupby(["sku_id", "location_id"]).forecast_qty.mean()
        dmean = dep.groupby(level=[0, 1]).sum() / self.W
        lanes = {}
        for r in t["lead_time"].itertuples():
            if date.fromisoformat(r.effective_from) <= self.as_of and (
                    not isinstance(r.effective_to, str) or self.as_of <= date.fromisoformat(r.effective_to)):
                lanes[(r.supplier_id, r.location_id)] = r.total_lead_days
        for r in sl.itertuples():
            key = (r.sku_id, r.location_id)
            if r.planning_method == "PRODUCTION":
                mean, ltw = float(fmean.get(key, 0.0)), 1
            else:
                ltw = math.ceil(lanes[(r.primary_supplier_id, r.location_id)] / 7)
                mean = float(fmean.get(key, 0.0)) if r.planning_method == "PURCHASE" else float(dmean.get(key, 0.0))
            exp = safety_stock(sku.at[r.sku_id, "abc_class"], mean, ltw)
            if exp != r.safety_stock_qty:
                self.fail(n, "sku_location", r.sku_location_id, f"safety stock {r.safety_stock_qty} != {exp}")

    def inventory_checks(self, sku):
        t = self.t
        inv = t["inventory"]
        po = t["purchase_order"].set_index("po_id")
        pol = t["purchase_order_line"].set_index("po_line_id")
        n = "duplicate:inventory_in_transit"
        self.check(n, "duplicate", "at most one IN_TRANSIT row per PO line; one ON_HAND row per SKU-location",
                   len(inv))
        it = inv[inv.stock_status == "IN_TRANSIT"].sort_values("inventory_id")
        self.fail_many(n, "inventory", it.inventory_id[it.duplicated("po_line_id")],
                       "PO line already has an in-transit record (inbound counted twice)")
        oh = inv[inv.stock_status == "ON_HAND"]
        self.fail_many(n, "inventory", oh.inventory_id[oh.duplicated(["sku_id", "location_id"])],
                       "duplicate ON_HAND record")
        n = "duplicate:exact_rows"
        self.check(n, "duplicate", "no two input rows identical apart from their primary key",
                   sum(len(self.t[x]) for x in INPUT_TABLES))
        for name in INPUT_TABLES:
            df = self.t[name]
            pk = TABLES[name].primary_key
            cols = [c for c in df.columns if c != pk]
            if name in ("calendar_week",):
                continue
            d = df[df.duplicated(cols, keep="first")]
            self.fail_many(n, name, d[pk], "row duplicates another record")
        n = "cross:inventory"
        self.check(n, "cross_entity", "snapshot = as-of; uom = base; IN_TRANSIT rows reference an IN_TRANSIT PO line "
                                      "for the same SKU and location", len(inv))
        for r in inv.itertuples():
            bad = r.snapshot_date != self.as_of.isoformat() or r.uom != sku.at[r.sku_id, "base_uom"]
            if r.stock_status == "IN_TRANSIT":
                if not isinstance(r.po_line_id, str) or r.po_line_id not in pol.index:
                    bad = True
                else:
                    line = pol.loc[r.po_line_id]
                    h = po.loc[line.po_id]
                    bad = bad or h.status != "IN_TRANSIT" or line.sku_id != r.sku_id or h.location_id != r.location_id \
                        or int(line.base_qty) != int(r.quantity)
            elif isinstance(r.po_line_id, str):
                bad = True
            if bad:
                self.fail(n, "inventory", r.inventory_id, "inventory record inconsistent")

    def leakage_checks(self):
        n = "leakage:ground_truth"
        self.check(n, "leakage", "no label columns in inputs; ground truth not stored with inputs",
                   len(INPUT_TABLES))
        for name in INPUT_TABLES:
            bad = LEAKAGE_COLUMNS & set(self.t[name].columns)
            if bad:
                self.fail(n, name, "-", f"label columns present: {sorted(bad)}")
        if self.input_dir is not None:
            for p in Path(self.input_dir).iterdir():
                if "ground_truth" in p.name:
                    self.fail(n, "ground_truth", p.name, "ground truth stored in the input folder")

    # ------------------------------------------------------------------ output checks
    def output_checks(self):
        t = self.t
        sr = t["scheduled_receipt"]
        pab = t["projected_balance"].sort_values(["sku_id", "location_id", "week_index"])
        W = self.W
        n = "reconciliation:pab_weekly"
        self.check(n, "reconciliation", "closing = opening + receipts + production - demand - dependent; "
                                        "opening(w) = closing(w-1); flags consistent", len(pab))
        calc = (pab.opening_balance + pab.scheduled_receipts + pab.planned_production - pab.forecast_demand
                - pab.dependent_demand)
        self.fail_many(n, "projected_balance", pab.pab_id[calc != pab.closing_balance], "PAB arithmetic")
        prev = pab.groupby(["sku_id", "location_id"]).closing_balance.shift()
        bad = prev.notna() & (prev != pab.opening_balance)
        self.fail_many(n, "projected_balance", pab.pab_id[bad], "opening != previous closing")
        bad = (pab.is_shortage != (pab.closing_balance < 0)) | (
            pab.below_safety_stock != (pab.closing_balance < pab.safety_stock_qty))
        self.fail_many(n, "projected_balance", pab.pab_id[bad], "flags inconsistent")
        # sources
        n = "reconciliation:pab_sources"
        self.check(n, "reconciliation", "PAB inputs reconcile to inventory, forecast, production, BOM explosion and "
                                        "counted scheduled receipts", len(pab))
        key = ["sku_id", "location_id", "week_id"]
        p = pab.set_index(key)
        inv = t["inventory"]
        oh = inv[inv.stock_status == "ON_HAND"].groupby(["sku_id", "location_id"]).quantity.sum()
        first = pab[pab.week_index == 0].set_index(["sku_id", "location_id"]).opening_balance
        diff = first.sub(oh.reindex(first.index).fillna(0))
        self.fail_many(n, "projected_balance", [f"PAB-{a}-{b}-{self.week_ids[0]}" for a, b in diff.index[diff != 0]],
                       "week-0 opening != ON_HAND inventory")
        fd = t["forecast_demand"].set_index(key).forecast_qty
        d = p.forecast_demand.sub(fd.reindex(p.index).fillna(0))
        self.fail_many(n, "projected_balance", p.pab_id[d != 0], "demand != forecast")
        pp = t["production_plan"].groupby(key).planned_qty.sum()
        d = p.planned_production.sub(pp.reindex(p.index).fillna(0))
        self.fail_many(n, "projected_balance", p.pab_id[d != 0], "production != production plan")
        mm = t["production_plan"].merge(t["bom"], left_on="sku_id", right_on="parent_sku_id")
        dep = (mm.assign(q=mm.planned_qty * mm.qty_per).groupby(["component_sku_id", "location_id", "week_id"]).q.sum()
               .map(dependent_demand_units))
        dep.index.names = key
        d = p.dependent_demand.sub(dep.reindex(p.index).fillna(0))
        self.fail_many(n, "projected_balance", p.pab_id[d != 0], "dependent demand != BOM explosion")
        c = sr[sr.counted_in_plan.astype(bool)]
        rc = c.assign(week_id=[self.week_ids[int(w)] for w in c.receipt_week_index]).groupby(key).planning_base_qty.sum()
        d = p.scheduled_receipts.sub(rc.reindex(p.index).fillna(0))
        self.fail_many(n, "projected_balance", p.pab_id[d != 0], "receipts != counted scheduled receipts")
        n = "reconciliation:scheduled_receipt"
        self.check(n, "reconciliation", "counted receipts are open PO lines; unadjusted lines keep source qty/date",
                   len(sr))
        bad = sr.counted_in_plan.astype(bool) & ~sr.po_status.isin(OPEN_STATUSES)
        plain = sr.adjustment_codes.isna()
        bad |= plain & ((sr.planning_base_qty != sr.source_base_qty) |
                        (sr.planning_receipt_date != sr.source_receipt_date))
        self.fail_many(n, "scheduled_receipt", sr.po_line_id[bad], "scheduled receipt inconsistent")
        self.shortage_checks(pab)
        self.mitigation_checks(pab)

    def shortage_checks(self, pab):
        t = self.t
        sh, sc = t["shortage"], t["shortage_cause"]
        n = "reconciliation:shortage"
        self.check(n, "reconciliation", "shortages = maximal runs of negative PAB; qty = peak deficit; ranks unique",
                   len(sh))
        expected = {}
        for (s, l), g in pab.groupby(["sku_id", "location_id"]):
            cb = g.closing_balance.to_numpy()
            w = 0
            while w < len(cb):
                if cb[w] < 0:
                    st = w
                    while w + 1 < len(cb) and cb[w + 1] < 0:
                        w += 1
                    expected[(s, l, st)] = (w, int(-cb[st:w + 1].min()))
                w += 1
        got = {(r.sku_id, r.location_id, int(r.start_week_index)): (int(r.end_week_index), int(r.shortage_qty),
                                                                    r.shortage_id) for r in sh.itertuples()}
        for k, v in got.items():
            if k not in expected or expected[k] != v[:2]:
                self.fail(n, "shortage", v[2], "shortage does not match projected balance")
        for k in set(expected) - set(got):
            self.fail(n, "shortage", f"{k}", "negative PAB run without shortage record")
        bad = (sh.duration_weeks != sh.end_week_index - sh.start_week_index + 1) | (
            sh.within_lead_time != (sh.start_week_index < sh.lead_time_weeks))
        self.fail_many(n, "shortage", sh.shortage_id[bad], "duration / within_lead_time")
        n = "explainability:shortage_causes"
        self.check(n, "explainability", "every shortage has >= 1 cause; contributions <= shortage qty; primary cause "
                                        "= cause 1 or DEMAND_EXCEEDS_SUPPLY", len(sh))
        g = sc.groupby("shortage_id")
        cnt = g.size()
        self.fail_many(n, "shortage", sh.shortage_id[~sh.shortage_id.isin(cnt.index)], "no cause recorded")
        m = sc.merge(sh[["shortage_id", "shortage_qty", "primary_cause_code"]], on="shortage_id")
        self.fail_many(n, "shortage_cause", m.shortage_cause_id[m.contribution_qty > m.shortage_qty],
                       "contribution exceeds shortage")
        first = m[m.cause_seq == 1]
        bad = (first.cause_code != first.primary_cause_code) & (first.primary_cause_code != "DEMAND_EXCEEDS_SUPPLY")
        self.fail_many(n, "shortage", first.shortage_id[bad], "primary cause mismatch")

    def mitigation_checks(self, pab):
        t = self.t
        mo, sh = t["mitigation_option"], t["shortage"].set_index("shortage_id")
        sku = t["sku"].set_index("sku_id")
        sup = t["supplier"].set_index("supplier_id")
        sub = t["sku_substitute"].set_index("substitution_id")
        terms = t["supplier_sku"].set_index(["supplier_id", "sku_id"])
        n = "policy:mitigation"
        self.check(n, "policy", "options respect approval, supplier status, MOQ/multiple, lead time, arrival before "
                                "shortage end; covered/residual/fill reconcile; one recommended per shortage",
                   len(mo))
        lanes = {}
        for r in t["lead_time"].itertuples():
            if date.fromisoformat(r.effective_from) <= self.as_of and (
                    not isinstance(r.effective_to, str) or self.as_of <= date.fromisoformat(r.effective_to)):
                lanes[(r.supplier_id, r.location_id)] = r
        for r in mo.itertuples():
            s = sh.loc[r.shortage_id]
            bad = []
            if r.covered_qty != min(r.proposed_qty, s.shortage_qty) or r.residual_shortage_qty != s.shortage_qty - \
                    r.covered_qty or abs(r.fill_rate_pct - round(100 * r.covered_qty / s.shortage_qty, 2)) > 0.01:
                bad.append("coverage arithmetic")
            if "FAIL" in (r.moq_check, r.lead_time_check, r.approval_check, r.capacity_check):
                bad.append("failed check")
            if r.mitigation_type != "ACCEPT_BACKORDER":
                if pd.isna(r.arrival_week_index) or int(r.arrival_week_index) > s.end_week_index:
                    bad.append("arrives after shortage ends")
            if r.mitigation_type in ("NEW_PO_PRIMARY", "NEW_PO_ALTERNATE"):
                tm = terms.loc[(r.supplier_id, s.sku_id)]
                lane = lanes.get((r.supplier_id, s.location_id))
                oq = int(r.order_qty_purchase_uom)
                if sup.at[r.supplier_id, "status"] != "ACTIVE" or tm.approval_status != "APPROVED":
                    bad.append("supplier not active/approved")
                if oq < tm.min_order_qty or oq % tm.order_multiple or int(round(oq * tm.uom_conversion_factor)) != \
                        r.proposed_qty:
                    bad.append("MOQ/multiple/UoM")
                if lane is None or int(r.lead_time_days) != int(lane.total_lead_days) or \
                        int(r.arrival_week_index) < self.widx(self.as_of + timedelta(days=int(lane.total_lead_days))):
                    bad.append("arrives earlier than lead time allows")
                if (r.mitigation_type == "NEW_PO_PRIMARY") != (tm.supplier_priority == 1):
                    bad.append("primary/alternate mislabelled")
            if r.mitigation_type == "APPROVED_SUBSTITUTE":
                link = sub.loc[r.substitution_id]
                if link.approval_status != "APPROVED" or link.sku_id != s.sku_id or \
                        link.substitute_sku_id != r.substitute_sku_id:
                    bad.append("substitute not approved for this SKU")
            if r.mitigation_type == "STOCK_TRANSFER" and r.source_location_id == s.location_id:
                bad.append("transfer from itself")
            if r.mitigation_type == "INCREASE_PRODUCTION" and sku.at[s.sku_id, "sourcing_type"] != "MAKE":
                bad.append("production for BUY SKU")
            if bad:
                self.fail(n, "mitigation_option", r.mitigation_id, "; ".join(bad))
        rec = mo[mo.is_recommended.astype(bool)]
        cnt = rec.groupby("shortage_id").size()
        self.fail_many(n, "shortage", sh.index[~sh.index.isin(cnt[cnt == 1].index)],
                       "shortage needs exactly one recommended option")
        self.fail_many(n, "mitigation_option", rec.mitigation_id[rec.option_rank != 1], "recommended is not rank 1")
        n = "explainability:tradeoffs"
        self.check(n, "explainability", "every shortage shows >= 2 alternatives with cost and service metrics, or "
                                        "backorder plus logged rejections explaining why nothing else is feasible",
                   len(sh))
        c = mo.groupby("shortage_id").size()
        rj = set(t["rejected_mitigation"].shortage_id)
        bad = [s_ for s_ in sh.index if c.get(s_, 0) < 2 and not (c.get(s_, 0) == 1 and s_ in rj)]
        self.fail_many(n, "shortage", bad, "no trade-off: fewer than 2 alternatives and no rejection log")
        # capacity after reservations
        n = "capacity:mitigation_supplier"
        self.check(n, "capacity", "planned load + mitigation reservations <= supplier capacity; reservations = "
                                  "recommended new-PO quantities", len(t["supplier_capacity_utilization"]))
        u = t["supplier_capacity_utilization"]
        bad = u.planned_committed_units + u.mitigation_reserved_units > u.capacity_units
        self.fail_many(n, "supplier_capacity_utilization", u.supplier_capacity_id[bad], "over capacity after plan")
        po_rec = rec[rec.mitigation_type.isin(["NEW_PO_PRIMARY", "NEW_PO_ALTERNATE"])]
        a = po_rec.groupby("supplier_id").proposed_qty.sum()
        b = u.groupby("supplier_id").mitigation_reserved_units.sum()
        b = b[b > 0]
        for s_ in set(a.index) | set(b.index):
            if int(a.get(s_, 0)) != int(b.get(s_, 0)):
                self.fail(n, "supplier", s_, "reserved capacity != recommended order quantities")
        n = "capacity:mitigation_plant"
        pu = t["production_capacity_utilization"]
        self.check(n, "capacity", "planned production + reservations <= plant capacity", len(pu))
        bad = pu.planned_units + pu.mitigation_reserved_units > pu.capacity_units
        self.fail_many(n, "production_capacity_utilization", pu.production_capacity_id[bad], "plant over capacity")
        n = "capacity:mitigation_stock"
        self.check(n, "capacity", "transfers and substitutes never take a source below safety stock", len(rec))
        res = defaultdict(list)
        for r in rec.itertuples():
            s = sh.loc[r.shortage_id]
            if r.mitigation_type == "STOCK_TRANSFER":
                res[(s.sku_id, r.source_location_id)].append((0, r.capacity_consumed))
            elif r.mitigation_type == "APPROVED_SUBSTITUTE":
                res[(r.substitute_sku_id, s.location_id)].append((int(s.start_week_index), r.capacity_consumed))
        if res:
            pk = pab.set_index(["sku_id", "location_id"])
            for (s_, l), items in res.items():
                g = pk.loc[(s_, l)].sort_values("week_index")
                cb = g.closing_balance.to_numpy().astype(float)
                ss_ = g.safety_stock_qty.to_numpy()
                for w0, q in items:
                    cb[w0:] -= q
                first_w = min(w for w, _ in items)
                if (cb[first_w:] < ss_[first_w:]).any():
                    self.fail(n, "sku_location", f"{s_}@{l}", "reservations take stock below safety stock")

    # ------------------------------------------------------------------ SQLite FK enforcement
    def sqlite_checks(self, tables):
        n = "fk:sqlite_enforced"
        self.check(n, "foreign_key", "load all tables into SQLite and run PRAGMA foreign_key_check",
                   sum(len(self.t[x]) for x in tables))
        con = sqlite3.connect(":memory:")
        for name in tables:
            con.executescript(ddl_for(TABLES[name]))
        for name in tables:
            df = self.t[name][TABLES[name].columns]
            rows = [tuple(None if (v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA)
                          else (int(v) if isinstance(v, (bool, np.bool_)) else
                                v.item() if hasattr(v, "item") else v) for v in r)
                    for r in df.itertuples(index=False, name=None)]
            ph = ",".join("?" * len(df.columns))
            con.executemany(f"INSERT INTO {name} VALUES ({ph})", rows)
        for tbl, rowid, parent, _ in con.execute("PRAGMA foreign_key_check").fetchall():
            self.fail(n, tbl, rowid, f"SQLite foreign key violation -> {parent}")
        con.close()

    # ------------------------------------------------------------------ run + classify
    def _safe(self, fn, *args):
        """Corrupted data must produce violations, never crash the validator."""
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001
            name = f"runtime:{fn.__name__}"
            self.check(name, "runtime", f"{fn.__name__} completed without error", 1)
            self.fail(name, "-", "-", f"check aborted on malformed data: {type(exc).__name__}: {exc}")

    def run(self, outputs: bool = True, sqlite: bool = True) -> dict:
        tables = INPUT_TABLES + (OUTPUT_TABLES if outputs else [])
        self._safe(self.schema_checks, tables)
        for fn in [self.input_checks_basic, self.po_checks_wrapped, self.capacity_checks,
                   self.policy_checks_wrapped, self.derived_master_checks_wrapped, self.inventory_checks_wrapped,
                   self.leakage_checks]:
            self._safe(fn)
        if outputs:
            self._safe(self.output_checks)
        if sqlite:
            self._safe(self.sqlite_checks, tables)
        return self.summary()

    def _sku(self):
        return self.t["sku"].drop_duplicates("sku_id").set_index("sku_id")

    def po_checks_wrapped(self):
        self.po_checks(self._sku())

    def policy_checks_wrapped(self):
        self.policy_checks(self._sku())

    def derived_master_checks_wrapped(self):
        self.derived_master_checks(self._sku())

    def inventory_checks_wrapped(self):
        self.inventory_checks(self._sku())

    def summary(self) -> dict:
        labelled = set()
        if self.gt is not None and len(self.gt):
            edge = self.gt[self.gt.label_category == "EDGE_CASE"]
            labelled |= set(edge.record_id)
            for rel in edge.related_record_ids.dropna():
                labelled |= set(str(rel).split("|"))
        viol = pd.DataFrame(self.v, columns=["check", "category", "table", "record_id", "detail"])
        viol["classification"] = np.where(viol.record_id.isin(labelled), "EXPECTED_LABELLED", "UNEXPECTED")
        rows = []
        for name, c in self.checks.items():
            sub = viol[viol.check == name]
            exp = int((sub.classification == "EXPECTED_LABELLED").sum())
            une = int((sub.classification == "UNEXPECTED").sum())
            status = "PASS" if len(sub) == 0 else ("PASS_WITH_LABELLED_EXCEPTIONS" if une == 0 else "FAIL")
            rows.append(dict(c, violations=len(sub), expected_labelled=exp, unexpected=une, status=status))
        checks = pd.DataFrame(rows)
        return dict(
            as_of=self.as_of.isoformat(), n_checks=len(checks), n_violations=len(viol),
            n_expected_labelled=int((viol.classification == "EXPECTED_LABELLED").sum()),
            n_unexpected=int((viol.classification == "UNEXPECTED").sum()),
            overall_status="PASS" if (viol.classification == "UNEXPECTED").sum() == 0 else "FAIL",
            checks=checks, violations=viol)


def validate_directory(input_dir: Path, output_dir: Path | None, gt: pd.DataFrame | None = None,
                       sqlite: bool = True) -> dict:
    t = {n: read_table(input_dir, n) for n in INPUT_TABLES}
    if output_dir is not None:
        t.update({n: read_table(output_dir, n) for n in OUTPUT_TABLES})
    return Validator(t, gt, input_dir).run(outputs=output_dir is not None, sqlite=sqlite)
