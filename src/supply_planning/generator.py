"""Synthetic baseline generator (valid records only; edge cases are injected later).

Generation order (parents before children):
    calendar -> location -> supplier -> sku -> bom -> sku_location -> forecast_demand
    -> production_plan / production_capacity -> supplier_sku -> lead_time
    -> safety stock + ABC (derived) -> purchase_order(+lines, +events)
    -> supplier_capacity -> inventory -> sku_substitute

Hidden scenario drivers (demand spikes, constrained suppliers/plant) are
returned separately so they can only ever reach ground_truth.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from . import ids
from .calendar import as_of_date, week_id_for_date, week_start
from .config import ScaleConfig
from .schema import (BASE_UOMS, COMPONENT_CATEGORIES, FG_CATEGORIES, REGIONS, SUPPLIER_TIERS)

STAGES = {"locations": 1, "suppliers": 2, "skus": 3, "bom": 4, "demand": 5, "production": 6,
          "sourcing": 7, "lead_times": 8, "pos": 9, "events": 10, "capacity": 11,
          "inventory": 12, "substitutes": 13, "edge_cases": 14, "sku_locations": 15}

Z_BY_ABC = {"A": 1.65, "B": 1.28, "C": 0.84}
FORECAST_CV = 0.30              # assumed forecast-error coefficient of variation (safety stock rule)
FROZEN_WEEKS = 2                # production frozen fence
CATEGORY_DEMAND_LOG = {"ELECTRONICS": 2.3, "HOME_GOODS": 2.7, "PERSONAL_CARE": 3.3,
                       "FOOD_BEVERAGE": 3.6, "APPAREL": 2.8, "HARDWARE": 2.5}
CATEGORY_SEASON = {  # amplitude, peak week index
    "ELECTRONICS": (0.25, 47), "HOME_GOODS": (0.18, 20), "PERSONAL_CARE": (0.08, 26),
    "FOOD_BEVERAGE": (0.15, 50), "APPAREL": (0.35, 36), "HARDWARE": (0.25, 16)}
CATEGORY_COST_LOG = {"ELECTRONICS": 3.6, "HOME_GOODS": 2.8, "PERSONAL_CARE": 1.8, "FOOD_BEVERAGE": 1.3,
                     "APPAREL": 2.6, "HARDWARE": 2.4, "RAW_MATERIAL": 0.8, "PACKAGING": 0.0, "PARTS": 1.6}
NAME_A = ["Apex", "Bluefin", "Cedar", "Delta", "Ember", "Falcon", "Granite", "Harbor", "Iris", "Juniper",
          "Keystone", "Lumen", "Meridian", "Nova", "Orchid", "Pioneer", "Quartz", "Ridge", "Summit",
          "Tidal", "Unity", "Vertex", "Willow", "Zenith"]
NAME_B = ["Supply", "Industries", "Manufacturing", "Trading", "Components", "Works", "Materials", "Goods"]
SKU_ADJ = ["Compact", "Premium", "Classic", "Eco", "Pro", "Lite", "Max", "Core", "Plus", "Select"]
SKU_NOUN = {"ELECTRONICS": "Device", "HOME_GOODS": "Homeware", "PERSONAL_CARE": "Care Kit",
            "FOOD_BEVERAGE": "Pantry Pack", "APPAREL": "Garment", "HARDWARE": "Tool",
            "RAW_MATERIAL": "Resin", "PACKAGING": "Carton", "PARTS": "Assembly Part"}


def ts(d: date, hour: int = 9, minute: int = 0) -> str:
    return datetime(d.year, d.month, d.day, hour, minute).isoformat()


def dependent_demand_units(qty_x_per: float) -> int:
    """Rounding rule for BOM explosion (shared with planning/validation)."""
    return int(math.ceil(qty_x_per - 1e-9))


def select_lead_time_version(versions: list[dict], on: date) -> dict:
    """Version of a lane effective on a date (versions sorted by version)."""
    for v in reversed(versions):
        if date.fromisoformat(v["effective_from"]) <= on and (
                v["effective_to"] is None or on <= date.fromisoformat(v["effective_to"])):
            return v
    return versions[0]


def round_purchase_qty(base_needed: float, conv: float, moq: int, mult: int) -> int:
    """Smallest purchase-UoM quantity covering base_needed that respects MOQ and multiple."""
    pq = max(moq, math.ceil(base_needed / conv - 1e-9))
    return int(math.ceil(pq / mult) * mult)


class BaselineGenerator:
    def __init__(self, cfg: ScaleConfig):
        self.cfg = cfg
        self.year = cfg.plan_year
        self.W = cfg.n_weeks
        self.as_of = as_of_date(self.year)
        self.week_ids = [week_id_for_date(week_start(self.year, i)) for i in range(self.W)]
        self.t: dict[str, pd.DataFrame] = {}
        self.hidden: dict = {}

    def rng(self, stage: str) -> np.random.Generator:
        return np.random.default_rng([self.cfg.seed, STAGES[stage]])

    def ws(self, i: int) -> date:
        return week_start(self.year, i)

    def widx(self, d: date) -> int:
        return (d - self.as_of).days // 7

    # ------------------------------------------------------------------ run
    def run(self) -> tuple[dict[str, pd.DataFrame], dict]:
        self.gen_calendar()
        self.gen_locations()
        self.gen_suppliers()
        self.gen_skus()
        self.gen_bom()
        self.gen_sku_locations()
        self.gen_demand()
        self.gen_production()
        self.gen_sourcing()
        self.gen_lead_times()
        self.derive_abc_and_safety_stock()
        self.gen_purchase_orders()
        self.gen_supplier_capacity()
        self.finalize_purchase_orders()
        self.gen_inventory()
        self.gen_substitutes()
        return self.t, self.hidden

    # ------------------------------------------------------------------ calendar
    def gen_calendar(self):
        holidays = {0, self.W - 1} if self.W >= 52 else {0}
        rows = []
        for i in range(self.W):
            d = self.ws(i)
            rows.append(dict(week_id=self.week_ids[i], week_index=i, week_start_date=d.isoformat(),
                             week_end_date=(d + timedelta(days=6)).isoformat(), is_holiday_week=i in holidays))
        self.t["calendar_week"] = pd.DataFrame(rows)
        self.holiday = np.array([i in holidays for i in range(self.W)])

    # ------------------------------------------------------------------ locations
    def gen_locations(self):
        r = self.rng("locations")
        n, npl = self.cfg.n_locations, self.cfg.n_plants
        n_dc = n - npl
        dc_regions = list(r.permutation([REGIONS[j % 5] for j in range(n_dc)]))
        rows, counters = [], {}
        for i in range(n):
            ltype = "PLANT" if i < npl else "DC"
            region = REGIONS[i % 5] if ltype == "PLANT" else dc_regions[i - npl]
            key = (region, ltype)
            counters[key] = counters.get(key, 0) + 1
            name = f"{region.title()} {'Plant' if ltype == 'PLANT' else 'DC'} {counters[key]:02d}"
            eff = date(2015, 1, 1) + timedelta(days=int(r.integers(0, 3000)))
            rows.append(dict(location_id=ids.location_id(i + 1), location_name=name, location_type=ltype,
                             region=region, status="ACTIVE", effective_from=eff.isoformat()))
        loc = pd.DataFrame(rows)
        self.t["location"] = loc
        self.plants = loc.loc[loc.location_type == "PLANT", "location_id"].tolist()
        self.dcs = loc.loc[loc.location_type == "DC", "location_id"].tolist()
        self.loc_region = dict(zip(loc.location_id, loc.region))

    # ------------------------------------------------------------------ suppliers
    def gen_suppliers(self):
        r = self.rng("suppliers")
        c = self.cfg
        n = c.n_suppliers
        n_comp = max(2, round(n * c.share_component_suppliers))
        comp_idx = set(r.choice(n, n_comp, replace=False).tolist())
        rows = []
        for i in range(n):
            overseas = bool(r.random() < c.share_overseas_suppliers)
            rows.append(dict(
                supplier_id=ids.supplier_id(i + 1),
                supplier_name=f"{NAME_A[i % len(NAME_A)]} {NAME_B[(i // len(NAME_A)) % len(NAME_B)]} {i + 1:04d}",
                region=str(r.choice(REGIONS)), is_overseas=overseas,
                supplier_tier=str(r.choice(SUPPLIER_TIERS, p=[0.15, 0.35, 0.5])),
                supplier_role="COMPONENTS" if i in comp_idx else "FINISHED_GOODS",
                reliability_pct=round(float(r.uniform(84, 96) if overseas else r.uniform(90, 99.5)), 1),
                status="ACTIVE",
                effective_from=(date(2018, 1, 1) + timedelta(days=int(r.integers(0, 2700)))).isoformat()))
        sup = pd.DataFrame(rows)
        fg = sup.index[sup.supplier_role == "FINISHED_GOODS"].to_numpy()
        n_hold = max(1, round(0.03 * len(fg)))
        hold = r.choice(fg, n_hold, replace=False)
        sup.loc[hold, "status"] = "ON_HOLD"
        self.t["supplier"] = sup
        # Zipf-like popularity among active suppliers of each role
        self.sup_weights = {}
        for role in ["FINISHED_GOODS", "COMPONENTS"]:
            pool = sup[(sup.supplier_role == role) & (sup.status == "ACTIVE")].supplier_id.to_numpy()
            ranks = r.permutation(len(pool)) + 1
            w = 1.0 / ranks ** 0.7
            self.sup_weights[role] = (pool, w / w.sum())
        # served DCs for finished-goods suppliers
        self.served = {}
        for s in sup.itertuples():
            if s.supplier_role != "FINISHED_GOODS":
                continue
            home = [d for d in self.dcs if self.loc_region[d] == s.region]
            k = int(r.integers(1, min(3, len(self.dcs)) + 1))
            chosen = []
            for _ in range(k):
                pool = home if (home and r.random() < 0.75 and not s.is_overseas) else self.dcs
                pool = [d for d in pool if d not in chosen] or [d for d in self.dcs if d not in chosen]
                if pool:
                    chosen.append(str(r.choice(pool)))
            self.served[s.supplier_id] = sorted(chosen)
        self.sup_info = sup.set_index("supplier_id")

    # ------------------------------------------------------------------ skus
    def gen_skus(self):
        r = self.rng("skus")
        c = self.cfg
        n = c.n_skus
        n_make = max(3, round(n * c.share_make))
        n_comp = max(4, round(n * c.share_component))
        kinds = np.array(["MAKE"] * n_make + ["COMP"] * n_comp + ["BUY"] * (n - n_make - n_comp))
        kinds = r.permutation(kinds)
        rows = []
        for i, kind in enumerate(kinds):
            if kind == "COMP":
                cat = str(r.choice(COMPONENT_CATEGORIES, p=[0.4, 0.3, 0.3]))
                uom = str(r.choice(BASE_UOMS, p=[0.2, 0.5, 0.3])) if cat == "RAW_MATERIAL" else "EA"
            else:
                cat = str(r.choice(FG_CATEGORIES, p=[0.15, 0.2, 0.2, 0.2, 0.1, 0.15]))
                uom = str(r.choice(BASE_UOMS, p=[0.6, 0.25, 0.15])) if cat == "FOOD_BEVERAGE" else "EA"
            upc = int(r.choice({"EA": [6, 12, 24, 48], "KG": [10, 20, 25], "L": [4, 12, 20]}[uom]))
            cost = round(max(0.05, float(np.exp(r.normal(CATEGORY_COST_LOG[cat], 0.5)))), 2)
            price = round(cost * float(r.uniform(1.35, 2.3)), 2) if kind != "COMP" else None
            lifecycle, eff_from, eff_to = "ACTIVE", date(2021, 1, 1) + timedelta(days=int(r.integers(0, 1600))), None
            if kind == "BUY":
                u = r.random()
                if u < 0.08:
                    lifecycle = "NEW"
                    eff_from = self.ws(int(r.integers(4, self.W // 2)))
                elif u < 0.15:
                    lifecycle = "PHASE_OUT"
                    eff_to = self.ws(int(r.integers(self.W // 3, self.W - 4))) + timedelta(days=6)
            rows.append(dict(
                sku_id=ids.sku_id(i + 1),
                sku_name=f"{SKU_ADJ[i % len(SKU_ADJ)]} {SKU_NOUN[cat]} {i + 1:06d}",
                category=cat, item_type="COMPONENT" if kind == "COMP" else "FINISHED_GOOD",
                sourcing_type="MAKE" if kind == "MAKE" else "BUY", base_uom=uom, units_per_case=upc,
                unit_cost=cost, unit_price=price, abc_class=None, lifecycle_status=lifecycle,
                effective_from=eff_from.isoformat(), effective_to=eff_to.isoformat() if eff_to else None))
        self.t["sku"] = pd.DataFrame(rows)
        self.sku_info = self.t["sku"].set_index("sku_id")

    # ------------------------------------------------------------------ bom
    def gen_bom(self):
        r = self.rng("bom")
        sku = self.t["sku"]
        parents = sku[sku.sourcing_type == "MAKE"].sku_id.tolist()
        comps = sku[sku.item_type == "COMPONENT"].sku_id.tolist()
        target = {p: int(r.integers(2, 5)) for p in parents}
        links = {p: [] for p in parents}
        # every component used at least once
        for comp in r.permutation(comps):
            open_parents = [p for p in parents if len(links[p]) < 4] or parents
            p = str(r.choice(open_parents))
            links[p].append(str(comp))
        pop = r.dirichlet(np.ones(len(comps)) * 0.6)
        for p in parents:
            while len(links[p]) < target[p]:
                cand = str(r.choice(comps, p=pop))
                if cand not in links[p]:
                    links[p].append(cand)
        # plant per manufactured SKU
        self.make_plant = {p: str(r.choice(self.plants)) for p in parents}
        rows = []
        for p in parents:
            for comp in sorted(links[p]):
                uom = self.sku_info.at[comp, "base_uom"]
                qty = float(r.integers(1, 5)) if uom == "EA" else round(float(r.uniform(0.05, 2.0)), 3)
                rows.append(dict(parent_sku_id=p, component_sku_id=comp, qty_per=qty, component_uom=uom,
                                 effective_from="2025-01-01", effective_to=None))
        bom = pd.DataFrame(rows).sort_values(["parent_sku_id", "component_sku_id"]).reset_index(drop=True)
        bom.insert(0, "bom_id", [ids.seq_id("BOM", i + 1) for i in range(len(bom))])
        self.t["bom"] = bom

    # ------------------------------------------------------------------ sku-location + primary supplier
    def gen_sku_locations(self):
        r = self.rng("sku_locations")
        sku = self.t["sku"]
        bom = self.t["bom"]
        rows = []
        self.primary = {}
        for s in sku.itertuples():
            if s.sourcing_type == "MAKE":
                rows.append((s.sku_id, self.make_plant[s.sku_id], "PRODUCTION", None))
                continue
            role = "COMPONENTS" if s.item_type == "COMPONENT" else "FINISHED_GOODS"
            pool, w = self.sup_weights[role]
            sup = str(r.choice(pool, p=w))
            self.primary[s.sku_id] = sup
            if s.item_type == "COMPONENT":
                parents = bom.loc[bom.component_sku_id == s.sku_id, "parent_sku_id"]
                locs = sorted({self.make_plant[p] for p in parents})
                for loc in locs:
                    rows.append((s.sku_id, loc, "DEPENDENT_PURCHASE", sup))
            else:
                served = self.served[sup]
                k = int(r.choice(np.arange(1, len(served) + 1), p=self._k_probs(len(served))))
                for loc in sorted(r.choice(served, k, replace=False).tolist()):
                    rows.append((s.sku_id, loc, "PURCHASE", sup))
        sl = pd.DataFrame(rows, columns=["sku_id", "location_id", "planning_method", "primary_supplier_id"])
        sl = sl.sort_values(["sku_id", "location_id"]).reset_index(drop=True)
        sl.insert(0, "sku_location_id", [ids.seq_id("SL", i + 1) for i in range(len(sl))])
        eff = self.sku_info.loc[sl.sku_id, "effective_from"].to_numpy()
        sl["effective_from"] = np.where(eff > "2025-01-01", eff, "2025-01-01")
        sl["safety_stock_qty"] = 0
        self.t["sku_location"] = sl

    @staticmethod
    def _k_probs(m: int) -> np.ndarray:
        p = np.array([0.5, 0.3, 0.2][:m])
        return p / p.sum()

    # ------------------------------------------------------------------ demand
    def active_mask(self, sku_ids: np.ndarray) -> np.ndarray:
        """(n, W) boolean: week inside the SKU's effective window."""
        starts = np.array([self.ws(i) for i in range(self.W)], dtype="datetime64[D]")
        ef = pd.to_datetime(self.sku_info.loc[sku_ids, "effective_from"]).to_numpy().astype("datetime64[D]")
        et_raw = self.sku_info.loc[sku_ids, "effective_to"]
        et = pd.to_datetime(et_raw.fillna("2100-01-01")).to_numpy().astype("datetime64[D]")
        return (starts[None, :] >= ef[:, None]) & (starts[None, :] <= et[:, None])

    def gen_demand(self):
        r = self.rng("demand")
        sl = self.t["sku_location"]
        fg = sl[sl.planning_method != "DEPENDENT_PURCHASE"].reset_index(drop=True)
        n, W = len(fg), self.W
        cats = self.sku_info.loc[fg.sku_id, "category"].to_numpy()
        loc_factor = {l: float(np.exp(r.normal(0, 0.3))) for l in self.t["location"].location_id}
        mu = np.exp(np.array([r.normal(CATEGORY_DEMAND_LOG[cat], 0.8) for cat in cats]))
        mu *= np.array([loc_factor[l] for l in fg.location_id])
        mu *= np.where(fg.planning_method == "PRODUCTION", 3.0, 1.0)
        w = np.arange(W)
        amp = np.array([CATEGORY_SEASON[cat][0] for cat in cats]) * r.uniform(0.6, 1.4, n)
        peak = np.array([CATEGORY_SEASON[cat][1] for cat in cats]) + r.integers(-3, 4, n)
        season = 1 + amp[:, None] * np.cos(2 * np.pi * (w[None, :] - peak[:, None]) / 52.0)
        trend = 1 + r.normal(0.001, 0.003, n)[:, None] * w[None, :]
        expected = mu[:, None] * season * np.clip(trend, 0.5, None)
        mask = self.active_mask(fg.sku_id.to_numpy())
        bias = np.clip(r.normal(0, 0.05, n), -0.12, 0.12)
        plan_basis = expected * (1 + bias)[:, None] * mask
        noisy = expected * np.exp(r.normal(0, 0.12, (n, W)))
        fc = np.where(noisy < 5, r.poisson(noisy), np.round(noisy)).astype(np.int64)
        # demand spikes (hidden scenario driver; plan_basis does NOT include them)
        spikes = []
        n_spike = max(1, round(n * self.cfg.share_spike_sku_locations))
        for i in r.choice(n, n_spike, replace=False):
            active_weeks = np.flatnonzero(mask[i, 2:W - 2]) + 2
            if len(active_weeks) == 0:
                continue
            for wk in r.choice(active_weeks, min(len(active_weeks), int(r.integers(1, 3))), replace=False):
                mult = round(float(r.uniform(2.5, 4.5)), 2)
                base = max(int(fc[i, wk]), int(math.ceil(expected[i, wk])), 4)
                fc[i, wk] = int(round(base * mult))
                spikes.append((fg.sku_id[i], fg.location_id[i], int(wk), mult, base))
        fc = fc * mask
        self.fg_index = {(a, b): k for k, (a, b) in enumerate(zip(fg.sku_id, fg.location_id))}
        self.fg_rows = fg
        self.plan_basis = plan_basis
        self.forecast = fc
        self.fg_mask = mask
        self.hidden["spikes"] = spikes
        # long table
        ii, ww = np.nonzero(mask)
        skus = fg.sku_id.to_numpy()[ii]
        locs = fg.location_id.to_numpy()[ii]
        weeks = np.array(self.week_ids)[ww]
        uoms = self.sku_info.loc[skus, "base_uom"].to_numpy()
        dem = pd.DataFrame({
            "demand_id": [ids.demand_id(a, b, c) for a, b, c in zip(skus, locs, weeks)],
            "sku_id": skus, "location_id": locs, "week_id": weeks, "forecast_qty": fc[ii, ww],
            "uom": uoms, "forecast_version": "FV-2026-01"})
        self.t["forecast_demand"] = dem

    # ------------------------------------------------------------------ production
    def gen_production(self):
        r = self.rng("production")
        fg = self.fg_rows
        W = self.W
        # provisional ABC for finished goods (needed for MAKE safety stock)
        self.abc = {}
        fg_val = pd.Series(self.forecast.sum(axis=1) * self.sku_info.loc[fg.sku_id, "unit_cost"].to_numpy(),
                           index=fg.sku_id).groupby(level=0).sum()
        self.abc.update(pareto_abc(fg_val))
        make_rows = fg.index[fg.planning_method == "PRODUCTION"].to_numpy()
        prod = np.zeros((len(fg), W))
        self.make_opening, self.make_batch, self.make_ss = {}, {}, {}
        for i in make_rows:
            sku_id = fg.sku_id[i]
            D = self.plan_basis[i]
            mean = D.mean()
            ss = int(math.ceil(Z_BY_ABC[self.abc[sku_id]] * FORECAST_CV * mean * 1.0))
            batch = int(next((b for b in [100, 50, 25, 10] if b <= max(10.0, mean * 0.5)), 10))
            opening = int(round(mean * r.uniform(1.0, 2.5))) + ss
            proj = float(opening)
            for w in range(W):
                need = D[w] + ss - proj
                q = math.ceil(need / batch) * batch if need > 0 else 0
                prod[i, w] = q
                proj += q - D[w]
            self.make_opening[i], self.make_batch[i], self.make_ss[i] = opening, batch, ss
        plant_of = fg.location_id.to_numpy()
        loads = {p: prod[plant_of == p].sum(axis=0) for p in self.plants}
        constrained = self.plants[-1] if len(self.plants) >= 2 else None
        cap_rows = []
        for p in self.plants:
            load = loads[p]
            if p == constrained:
                base = load[load > 0].mean() * r.uniform(0.92, 1.0) if load.any() else 100.0
            else:
                base = (load.max() if load.any() else 100.0) * r.uniform(1.1, 1.35)
            caps = np.ceil(base * np.where(self.holiday, 0.75, 1.0) / 10) * 10
            rows_p = np.flatnonzero(plant_of == p)
            for w in range(W):
                if load[w] > caps[w]:
                    f = caps[w] / load[w]
                    for i in rows_p:
                        b = self.make_batch.get(i, 10)
                        prod[i, w] = math.floor(prod[i, w] * f / b) * b
            for w in range(W):
                cap_rows.append(dict(production_capacity_id=f"PCAP-{p}-{self.week_ids[w]}", location_id=p,
                                     week_id=self.week_ids[w], capacity_units=int(caps[w])))
        self.hidden["constrained_plant"] = constrained
        self.t["production_capacity"] = pd.DataFrame(cap_rows)
        self.production = prod
        rows = []
        for i in make_rows:
            for w in np.flatnonzero(prod[i] > 0):
                rows.append(dict(sku_id=fg.sku_id[i], location_id=fg.location_id[i], week_id=self.week_ids[w],
                                 week_index=int(w), planned_qty=int(prod[i, w]), batch_size=self.make_batch[i],
                                 status="FIRM" if w < FROZEN_WEEKS else "PLANNED"))
        pp = pd.DataFrame(rows).sort_values(["week_index", "location_id", "sku_id"]).reset_index(drop=True)
        pp.insert(0, "production_plan_id", [f"PP-{self.year}-{i + 1:06d}" for i in range(len(pp))])
        self.t["production_plan"] = pp.drop(columns="week_index")
        # dependent demand of components at plants
        bom = self.t["bom"]
        sl = self.t["sku_location"]
        comp_sl = sl[sl.planning_method == "DEPENDENT_PURCHASE"].reset_index(drop=True)
        self.comp_index = {(a, b): k for k, (a, b) in enumerate(zip(comp_sl.sku_id, comp_sl.location_id))}
        dep = np.zeros((len(comp_sl), W))
        for b in bom.itertuples():
            i = self.fg_index[(b.parent_sku_id, self.make_plant[b.parent_sku_id])]
            k = self.comp_index[(b.component_sku_id, self.make_plant[b.parent_sku_id])]
            dep[k] += prod[i] * b.qty_per
        self.comp_rows = comp_sl
        self.dependent = np.vectorize(dependent_demand_units)(dep) if dep.size else dep
        comp_val = pd.Series(self.dependent.sum(axis=1) * self.sku_info.loc[comp_sl.sku_id, "unit_cost"].to_numpy(),
                             index=comp_sl.sku_id).groupby(level=0).sum()
        self.abc.update(pareto_abc(comp_val))

    # ------------------------------------------------------------------ supplier_sku
    def gen_sourcing(self):
        r = self.rng("sourcing")
        sku = self.t["sku"]
        sup = self.t["supplier"]
        mean_req = {}
        for (s, _l), i in self.fg_index.items():
            mean_req[s] = mean_req.get(s, 0) + self.plan_basis[i].mean()
        for (s, _l), k in self.comp_index.items():
            mean_req[s] = mean_req.get(s, 0) + self.dependent[k].mean()
        rows = []
        for s in sku[sku.sourcing_type == "BUY"].itertuples():
            role = "COMPONENTS" if s.item_type == "COMPONENT" else "FINISHED_GOODS"
            suppliers = [self.primary[s.sku_id]]
            if r.random() < self.cfg.share_alternate_supplier:
                pool = sup[(sup.supplier_role == role) & (sup.supplier_id != suppliers[0])].supplier_id.to_numpy()
                n_alt = 2 if r.random() < 0.2 else 1
                suppliers += r.choice(pool, min(n_alt, len(pool)), replace=False).tolist()
            m = max(1.0, mean_req.get(s.sku_id, 1.0))
            for prio, sid in enumerate(suppliers, start=1):
                if r.random() < 0.6:
                    puom, conv = "CS", float(s.units_per_case)
                else:
                    puom, conv = s.base_uom, 1.0
                mult = 1 if puom == "CS" else int(r.choice([1, 5, 10]))
                moq_base = m * r.uniform(0.3, 1.5)
                moq = max(1, int(math.ceil(moq_base / conv)))
                moq = int(math.ceil(moq / mult) * mult)
                cost = s.unit_cost * (r.uniform(0.95, 1.05) if prio == 1 else r.uniform(1.03, 1.18))
                rows.append(dict(supplier_id=sid, sku_id=s.sku_id, supplier_priority=prio, purchase_uom=puom,
                                 uom_conversion_factor=conv, min_order_qty=moq, order_multiple=mult,
                                 unit_cost=round(float(cost), 4), approval_status="APPROVED",
                                 effective_from="2025-01-01", effective_to=None))
        ss = pd.DataFrame(rows).sort_values(["sku_id", "supplier_priority"]).reset_index(drop=True)
        ss.insert(0, "supplier_sku_id", [ids.seq_id("SS", i + 1) for i in range(len(ss))])
        self.t["supplier_sku"] = ss
        self.terms = {(a.supplier_id, a.sku_id): a._asdict() for a in ss.itertuples(index=False)}

    # ------------------------------------------------------------------ lead times
    def gen_lead_times(self):
        r = self.rng("lead_times")
        sl = self.t["sku_location"]
        ss = self.t["supplier_sku"]
        lanes = sorted(set(
            (row.supplier_id, loc) for row in ss.itertuples()
            for loc in sl.loc[sl.sku_id == row.sku_id, "location_id"]))
        prod_days = {s: int(r.integers(5, 22)) for s in self.t["supplier"].supplier_id}
        rows = []
        for sid, loc in lanes:
            info = self.sup_info.loc[sid]
            if info.is_overseas:
                mode, transit = "SEA", int(r.integers(18, 36))
                exp_t, prem = int(r.integers(3, 6)), round(float(r.uniform(25, 40)), 1)
            elif info.region == self.loc_region[loc]:
                mode, transit = "ROAD", int(r.integers(1, 5))
                exp_t, prem = max(1, transit // 2), round(float(r.uniform(8, 15)), 1)
            else:
                mode = str(r.choice(["ROAD", "RAIL"]))
                transit = int(r.integers(4, 11))
                exp_t, prem = max(1, transit // 2), round(float(r.uniform(8, 15)), 1)
            pdays = max(3, prod_days[sid] + int(r.integers(-2, 3)))
            v1 = dict(supplier_id=sid, location_id=loc, version=1, transport_mode=mode,
                      production_lead_days=pdays, transit_days=transit, total_lead_days=pdays + transit,
                      expedite_transit_days=exp_t, expedite_premium_pct=prem,
                      effective_from="2025-01-01", effective_to=None)
            rows.append(v1)
            if r.random() < self.cfg.share_lead_time_revision:
                start = self.ws(int(r.integers(8, self.W - 10)))
                delta = int(r.integers(3, 11)) if r.random() < 0.75 else -int(r.integers(1, 4))
                t2 = max(exp_t, transit + delta, 1)
                v1["effective_to"] = (start - timedelta(days=1)).isoformat()
                rows.append(dict(v1, version=2, transit_days=t2, total_lead_days=pdays + t2,
                                 effective_from=start.isoformat(), effective_to=None))
        lt = pd.DataFrame(rows).sort_values(["supplier_id", "location_id", "version"]).reset_index(drop=True)
        lt.insert(0, "lead_time_id", [ids.seq_id("LT", i + 1) for i in range(len(lt))])
        self.t["lead_time"] = lt
        self.lanes = {}
        for row in lt.astype(object).where(lt.notna(), None).to_dict("records"):
            self.lanes.setdefault((row["supplier_id"], row["location_id"]), []).append(row)

    # ------------------------------------------------------------------ ABC + safety stock
    def derive_abc_and_safety_stock(self):
        sku = self.t["sku"]
        sku["abc_class"] = sku.sku_id.map(self.abc).fillna("C")
        self.sku_info = sku.set_index("sku_id")
        sl = self.t["sku_location"]
        ss_vals = []
        for row in sl.itertuples():
            if row.planning_method == "PRODUCTION":
                i = self.fg_index[(row.sku_id, row.location_id)]
                mean, lt_weeks = self._mean_forecast(i), 1
            else:
                lane = select_lead_time_version(self.lanes[(row.primary_supplier_id, row.location_id)], self.as_of)
                lt_weeks = math.ceil(lane["total_lead_days"] / 7)
                if row.planning_method == "PURCHASE":
                    mean = self._mean_forecast(self.fg_index[(row.sku_id, row.location_id)])
                else:
                    mean = float(self.dependent[self.comp_index[(row.sku_id, row.location_id)]].mean())
            ss_vals.append(safety_stock(self.abc.get(row.sku_id, "C"), mean, lt_weeks))
        sl["safety_stock_qty"] = ss_vals
        self.ss = dict(zip(zip(sl.sku_id, sl.location_id), sl.safety_stock_qty))

    def _mean_forecast(self, i: int) -> float:
        m = self.fg_mask[i]
        return float(self.forecast[i][m].mean()) if m.any() else 0.0

    # ------------------------------------------------------------------ purchase orders
    def gen_purchase_orders(self):
        r = self.rng("pos")
        c = self.cfg
        W, H = self.W, c.history_weeks
        S = W + H
        sl = self.t["sku_location"]
        buy = sl[sl.planning_method != "PRODUCTION"]
        req = {}
        for row in buy.itertuples():
            key = (row.sku_id, row.location_id)
            req[key] = (self.plan_basis[self.fg_index[key]] if row.planning_method == "PURCHASE"
                        else self.dependent[self.comp_index[key]].astype(float))
        lane_skus: dict[tuple, list] = {}
        for row in buy.itertuples():
            lane_skus.setdefault((row.primary_supplier_id, row.location_id), []).append(row.sku_id)
        lane_keys = sorted(lane_skus)
        vol = np.array([sum(req[(s, l[1])].sum() * self.sku_info.at[s, "unit_cost"] for s in lane_skus[l])
                        for l in lane_keys])
        alloc = allocate_counts(c.n_purchase_orders, np.sqrt(vol) + 1.0, cap=S)
        headers, lines = [], []
        self.opening = {}
        for lane, k in zip(lane_keys, alloc):
            sid, loc = lane
            phase = r.random()
            receipt_weeks = sorted({-H + int(math.floor((j + phase) * S / k)) for j in range(k)})
            in_h = [w for w in receipt_weeks if w >= 0]
            lane_lines = {w: [] for w in receipt_weeks}
            for sku_id in sorted(lane_skus[lane]):
                R = req[(sku_id, loc)]
                ssq = self.ss[(sku_id, loc)]
                t = self.terms[(sid, sku_id)]
                conv, moq, mult = t["uom_conversion_factor"], t["min_order_qty"], t["order_multiple"]
                first = in_h[0] if in_h else W
                cover = R[:first].sum()
                if r.random() < 0.05:   # low-stock scenario
                    opening = int(round(cover * r.uniform(0.2, 0.6)))
                else:
                    opening = int(round(cover * r.uniform(0.9, 1.4) + ssq * r.uniform(0.4, 1.3)))
                self.opening[(sku_id, loc)] = opening
                proj = float(opening)
                consumed_to = 0
                for j, w in enumerate(receipt_weeks):
                    nxt = receipt_weeks[j + 1] if j + 1 < len(receipt_weeks) else W
                    if w < 0:   # history receipt (already in on-hand)
                        m = R[:8].mean()
                        if m <= 0:
                            continue
                        q = m * (nxt - w) * r.uniform(0.9, 1.1)
                    else:
                        proj -= R[consumed_to:w].sum()
                        consumed_to = w
                        q = ssq + R[w:nxt].sum() - proj
                    if q <= 0.5:
                        continue
                    pq = round_purchase_qty(q, conv, moq, mult)
                    if w >= 0:
                        proj += pq * conv
                    lane_lines[w].append((sku_id, pq))
            top_sku = max(lane_skus[lane], key=lambda s: req[(s, loc)].sum())
            for w in receipt_weeks:
                if not lane_lines[w]:
                    t = self.terms[(sid, top_sku)]
                    lane_lines[w].append((top_sku, round_purchase_qty(1, t["uom_conversion_factor"],
                                                                      t["min_order_qty"], t["order_multiple"])))
                promised = self.ws(w) + timedelta(days=int(r.integers(0, 5)))
                lt, order_date, promised = self._order_date_for(sid, loc, promised)
                headers.append(dict(lane=lane, supplier_id=sid, location_id=loc, lead_time_id=lt["lead_time_id"],
                                    order_date=order_date, ship_date=order_date + timedelta(
                                        days=lt["production_lead_days"]),
                                    promised_receipt_date=promised, transit_days=lt["transit_days"],
                                    lines=lane_lines[w]))
        headers.sort(key=lambda h: (h["order_date"], h["supplier_id"], h["location_id"], h["promised_receipt_date"]))
        po_rows, line_rows = [], []
        for n, h in enumerate(headers, start=1):
            pid = ids.po_id(self.year, n)
            h["po_id"] = pid
            for ln, (sku_id, pq) in enumerate(sorted(h["lines"]), start=1):
                t = self.terms[(h["supplier_id"], sku_id)]
                line_rows.append(dict(po_line_id=ids.po_line_id(pid, ln), po_id=pid, line_number=ln, sku_id=sku_id,
                                      supplier_sku_id=t["supplier_sku_id"], order_qty=int(pq),
                                      order_uom=t["purchase_uom"], uom_conversion_factor=t["uom_conversion_factor"],
                                      base_uom=self.sku_info.at[sku_id, "base_uom"], unit_cost=t["unit_cost"],
                                      min_order_qty=t["min_order_qty"], order_multiple=t["order_multiple"]))
            po_rows.append(h)
        self.po_headers = po_rows
        self.po_lines = pd.DataFrame(line_rows)
        self.gen_po_events()

    def _order_date_for(self, sid, loc, promised: date):
        versions = self.lanes[(sid, loc)]
        for v in reversed(versions):
            od = promised - timedelta(days=v["total_lead_days"])
            if date.fromisoformat(v["effective_from"]) <= od and (
                    v["effective_to"] is None or od <= date.fromisoformat(v["effective_to"])):
                return v, od, promised
        v = versions[-1]
        od = date.fromisoformat(v["effective_from"])
        return v, od, od + timedelta(days=v["total_lead_days"])

    # ------------------------------------------------------------------ PO events / lifecycle
    def gen_po_events(self):
        r = self.rng("events")
        c = self.cfg
        as_of = self.as_of
        as_of_dt = datetime(as_of.year, as_of.month, as_of.day)
        events = []
        for h in self.po_headers:
            pid, od, sd, prom = h["po_id"], h["order_date"], h["ship_date"], h["promised_receipt_date"]
            rel = self.sup_info.at[h["supplier_id"], "reliability_pct"]
            ev = []
            created = datetime(od.year, od.month, od.day, 9, int(r.integers(0, 60))) - timedelta(
                days=int(r.integers(1, 11)))
            latest_created = as_of_dt - timedelta(days=1 + int(r.integers(0, 14)), hours=int(r.integers(1, 10)))
            created = min(created, latest_created)
            ev.append(["CREATED", None, "PLANNED", created, "PLANNER", 0, None])
            status = "PLANNED"
            delay = 0
            confirm_dt = datetime(od.year, od.month, od.day, 10, 0) + timedelta(days=1)
            if confirm_dt < as_of_dt:
                ev.append(["CONFIRMED", "PLANNED", "CONFIRMED", confirm_dt, "SUPPLIER", 0, None])
                status = "CONFIRMED"
            ship_dt = datetime(sd.year, sd.month, sd.day, 14, 0)
            cancel = (status in ("PLANNED", "CONFIRMED") and ship_dt >= as_of_dt
                      and r.random() < c.share_cancelled * 1.4)
            if cancel:
                lo = max(ev[-1][3] + timedelta(hours=1), as_of_dt - timedelta(days=14))
                hi = as_of_dt - timedelta(hours=1)
                if lo < hi:
                    when = lo + (hi - lo) * float(r.random())
                    ev.append(["CANCELLED", status, "CANCELLED", when.replace(microsecond=0, second=0),
                               "PLANNER", 0, "Demand re-plan; order no longer required"])
                    status = "CANCELLED"
            if status != "CANCELLED":
                p_delay = c.share_transport_delay * float(np.clip((100 - rel) / 6.0, 0.3, 2.5))
                will_delay = r.random() < p_delay
                if ship_dt < as_of_dt:
                    ev.append(["SHIPPED", "CONFIRMED", "IN_TRANSIT", ship_dt, "CARRIER", 0, None])
                    status = "IN_TRANSIT"
                    if will_delay:
                        rep = ship_dt + timedelta(days=int(r.integers(1, max(2, h["transit_days"]))), hours=2)
                        if rep >= as_of_dt:
                            rep = as_of_dt - timedelta(hours=3)
                        if rep > ship_dt:
                            delay = int(r.integers(3, 22))
                            ev.append(["DELAY_REPORTED", "IN_TRANSIT", "IN_TRANSIT", rep, "CARRIER", delay,
                                       "Carrier reported transport delay"])
                    exp = prom + timedelta(days=delay)
                    rec_dt = datetime(exp.year, exp.month, exp.day, 16, 0)
                    if rec_dt < as_of_dt:
                        ev.append(["RECEIVED", "IN_TRANSIT", "RECEIVED", rec_dt, "WAREHOUSE_OPERATOR", 0, None])
                        status = "RECEIVED"
                elif status == "CONFIRMED" and will_delay:
                    rep = confirm_dt + timedelta(days=int(r.integers(1, 6)))
                    if rep >= as_of_dt:
                        rep = as_of_dt - timedelta(hours=2)
                    if rep > confirm_dt:
                        delay = int(r.integers(3, 22))
                        ev.append(["DELAY_REPORTED", "CONFIRMED", "CONFIRMED", rep, "SUPPLIER", delay,
                                   "Supplier reported production delay"])
            h["status"], h["delay"] = status, delay
            for seq, e in enumerate(ev, start=1):
                events.append(dict(po_id=pid, event_seq=seq, event_type=e[0], from_status=e[1], to_status=e[2],
                                   event_timestamp=e[3].isoformat(), actor=e[4], delay_days=e[5], note=e[6]))
        self.po_events = events

    # ------------------------------------------------------------------ supplier capacity
    def gen_supplier_capacity(self):
        r = self.rng("capacity")
        W = self.W
        hdr = pd.DataFrame([{k: h[k] for k in ("po_id", "supplier_id", "ship_date", "status")}
                            for h in self.po_headers])
        hdr["ship_w"] = [self.widx(d) for d in hdr.ship_date]
        lines = self.po_lines.assign(_li=self.po_lines.index).merge(hdr, on="po_id")
        live = lines[lines.status.isin(["PLANNED", "CONFIRMED"]) & (lines.ship_w >= 0) & (lines.ship_w < W)]
        sup_ids = self.t["supplier"].supplier_id.tolist()
        load = {s: np.zeros(W) for s in sup_ids}
        for row in live.itertuples():
            load[row.supplier_id][row.ship_w] += row.order_qty * row.uom_conversion_factor
        active = [s for s in sup_ids if load[s].any()]
        n_con = max(1, round(self.cfg.share_constrained_suppliers * len(sup_ids)))
        constrained = sorted(r.choice(active, min(n_con, len(active)), replace=False).tolist())
        typical = float(np.median([load[s].max() for s in active])) if active else 500.0
        line_idx = {k: g["_li"].tolist() for k, g in live.groupby(["supplier_id", "ship_w"])}
        rows = []
        for s in sup_ids:
            L = load[s]
            if s in constrained:
                base = L[L > 0].mean() * r.uniform(0.9, 1.0)
            elif L.any():
                base = L.max() * r.uniform(1.25, 2.0)
            else:
                base = typical * r.uniform(0.5, 1.5)
            caps = np.ceil(base * np.where(self.holiday, 0.75, 1.0) / 10) * 10
            for w in range(W):
                if L[w] > caps[w] and s in constrained:
                    f = caps[w] / L[w]
                    for li in line_idx.get((s, w), []):
                        row = self.po_lines.loc[li]
                        mult, moq = row.order_multiple, row.min_order_qty
                        new = max(moq, int(math.floor(row.order_qty * f / mult) * mult))
                        if new < row.order_qty:
                            self.po_lines.at[li, "order_qty"] = new
                    L[w] = sum(self.po_lines.at[li, "order_qty"] * self.po_lines.at[li, "uom_conversion_factor"]
                               for li in line_idx.get((s, w), []))
                if L[w] > caps[w]:
                    caps[w] = math.ceil(L[w])       # boundary case: exactly 100 % utilised
            for w in range(W):
                rows.append(dict(supplier_capacity_id=f"SCAP-{s}-{self.week_ids[w]}", supplier_id=s,
                                 week_id=self.week_ids[w], capacity_units=int(caps[w])))
        self.t["supplier_capacity"] = pd.DataFrame(rows)
        self.hidden["constrained_suppliers"] = constrained

    def finalize_purchase_orders(self):
        pl = self.po_lines
        pl["base_qty"] = (pl.order_qty * pl.uom_conversion_factor).round().astype(np.int64)
        pl["line_value"] = (pl.base_qty * pl.unit_cost).round(2)
        line_cols = ["po_line_id", "po_id", "line_number", "sku_id", "supplier_sku_id", "order_qty", "order_uom",
                     "uom_conversion_factor", "base_qty", "base_uom", "unit_cost", "line_value"]
        self.t["purchase_order_line"] = pl[line_cols].copy()
        agg = pl.groupby("po_id").agg(line_count=("po_line_id", "size"), total_base_qty=("base_qty", "sum"),
                                      total_value=("line_value", "sum"))
        ev = pd.DataFrame(self.po_events)
        created = ev[ev.event_type == "CREATED"].set_index("po_id").event_timestamp
        rows = []
        for h in self.po_headers:
            exp = h["promised_receipt_date"] + timedelta(days=h["delay"])
            a = agg.loc[h["po_id"]]
            rows.append(dict(po_id=h["po_id"], supplier_id=h["supplier_id"], location_id=h["location_id"],
                             lead_time_id=h["lead_time_id"], order_date=h["order_date"].isoformat(),
                             ship_date=h["ship_date"].isoformat(),
                             promised_receipt_date=h["promised_receipt_date"].isoformat(),
                             transport_delay_days=h["delay"], expected_receipt_date=exp.isoformat(),
                             actual_receipt_date=exp.isoformat() if h["status"] == "RECEIVED" else None,
                             status=h["status"], line_count=int(a.line_count), total_base_qty=int(a.total_base_qty),
                             total_value=round(float(a.total_value), 2), currency="USD",
                             created_at=created[h["po_id"]]))
        self.t["purchase_order"] = pd.DataFrame(rows)
        ev = ev.sort_values(["po_id", "event_seq"]).reset_index(drop=True)
        ev.insert(0, "event_id", [ids.seq_id("POE", i + 1, 7) for i in range(len(ev))])
        self.t["purchase_order_event"] = ev

    # ------------------------------------------------------------------ inventory
    def gen_inventory(self):
        r = self.rng("inventory")
        sl = self.t["sku_location"]
        rows = []
        for row in sl.itertuples():
            key = (row.sku_id, row.location_id)
            if row.planning_method == "PRODUCTION":
                qty = self.make_opening[self.fg_index[key]]
            else:
                qty = self.opening[key]
            uom = self.sku_info.at[row.sku_id, "base_uom"]
            rows.append((row.sku_id, row.location_id, 0, "ON_HAND", int(qty), uom, None))
            if r.random() < 0.03 and qty > 5:
                rows.append((row.sku_id, row.location_id, 1, "QUALITY_HOLD",
                             max(1, int(qty * r.uniform(0.05, 0.2))), uom, None))
        po = self.t["purchase_order"]
        intransit = self.t["purchase_order_line"].merge(po[po.status == "IN_TRANSIT"][["po_id", "location_id"]],
                                                        on="po_id")
        for row in intransit.itertuples():
            rows.append((row.sku_id, row.location_id, 2, "IN_TRANSIT", int(row.base_qty), row.base_uom,
                         row.po_line_id))
        inv = pd.DataFrame(rows, columns=["sku_id", "location_id", "_o", "stock_status", "quantity", "uom",
                                          "po_line_id"])
        inv = inv.sort_values(["sku_id", "location_id", "_o", "po_line_id"], na_position="first").reset_index(drop=True)
        inv.insert(0, "inventory_id", [ids.seq_id("INV", i + 1) for i in range(len(inv))])
        inv["snapshot_date"] = self.as_of.isoformat()
        self.t["inventory"] = inv.drop(columns="_o")

    # ------------------------------------------------------------------ substitutes
    def gen_substitutes(self):
        r = self.rng("substitutes")
        sku = self.sku_info
        sl = self.t["sku_location"]
        fg_sl = sl[sl.planning_method == "PURCHASE"]
        locs_of = fg_sl.groupby("sku_id").location_id.apply(set).to_dict()
        cands = sorted(locs_of)
        n = max(1, round(len(cands) * self.cfg.share_substitute))
        rows, used = [], set()
        for s in r.choice(cands, min(n, len(cands)), replace=False):
            pool = [t for t in cands if t != s and sku.at[t, "category"] == sku.at[s, "category"]
                    and sku.at[t, "base_uom"] == sku.at[s, "base_uom"] and locs_of[t] & locs_of[s]
                    and (s, t) not in used]
            if not pool:
                continue
            t = str(r.choice(pool))
            used.add((s, t))
            appr = date(2025, 1, 1) + timedelta(days=int(r.integers(0, 300)))
            rows.append(dict(sku_id=str(s), substitute_sku_id=t, conversion_ratio=1.0, approval_status="APPROVED",
                             approved_by=str(r.choice(["PLANNER", "OPERATIONS_MANAGER"])),
                             approval_date=appr.isoformat(), effective_from=appr.isoformat(),
                             effective_to=None, priority=1))
        sub = pd.DataFrame(rows, columns=["sku_id", "substitute_sku_id", "conversion_ratio", "approval_status",
                                          "approved_by", "approval_date", "effective_from", "effective_to", "priority"])
        sub = sub.sort_values(["sku_id", "substitute_sku_id"]).reset_index(drop=True)
        sub.insert(0, "substitution_id", [ids.seq_id("SUB", i + 1) for i in range(len(sub))])
        self.t["sku_substitute"] = sub


# ---------------------------------------------------------------------- helpers
def pareto_abc(values: pd.Series) -> dict:
    """A = top 80 % of value, B = next 15 %, C = rest (ties broken by id)."""
    v = values.sort_index().sort_values(ascending=False, kind="mergesort")
    total = v.sum()
    if total <= 0:
        return {k: "C" for k in v.index}
    cum = v.cumsum() / total
    prev = cum.shift(fill_value=0.0)
    return {k: ("A" if p < 0.80 else "B" if p < 0.95 else "C") for k, p in prev.items()}


def safety_stock(abc: str, mean_weekly: float, lead_time_weeks: int) -> int:
    return int(math.ceil(Z_BY_ABC[abc] * FORECAST_CV * mean_weekly * math.sqrt(max(1, lead_time_weeks)) - 1e-9))


def allocate_counts(total: int, weights: np.ndarray, cap: int) -> list[int]:
    """Largest-remainder allocation of an exact total, >=1 each, <= cap each."""
    n = len(weights)
    if n == 0:
        return []
    base_min = 2 if total >= 2 * n else 1
    alloc = np.full(n, base_min)
    remaining = total - alloc.sum()
    if remaining < 0:
        raise ValueError("not enough purchase orders for the number of lanes")
    w = weights / weights.sum()
    while remaining > 0:
        room = cap - alloc
        ww = np.where(room > 0, w, 0)
        if ww.sum() == 0:
            raise ValueError("purchase-order cap reached")
        ww = ww / ww.sum()
        raw = ww * remaining
        add = np.minimum(np.floor(raw).astype(int), room)
        alloc += add
        left = remaining - add.sum()
        if left > 0:
            frac = np.where(alloc < cap, raw - np.floor(raw), -1)
            for i in np.argsort(-frac, kind="mergesort")[:left]:
                if alloc[i] < cap:
                    alloc[i] += 1
        remaining = total - alloc.sum()
    return alloc.tolist()
