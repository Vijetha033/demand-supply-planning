# Planning logic and business rules

Code: `src/supply_planning/planning.py` (screen, PAB, shortages, causes, priority) and
`src/supply_planning/mitigation.py` (options). The engine reads only `data/raw/<scale>/`.

## 0. Planning frame

* Horizon: 52 ISO weeks of 2026. Week index 0 = ISO 2026-W01, starting **2025-12-29** (the *as-of* date).
* Everything dated before the as-of date is history: received POs are already in on-hand stock, and all events are
  timestamped before it.
* Quantities are planned in each SKU's base unit (EA, KG or L).

## 1. Data-quality screen (exception path)

Source rows are never modified. Every correction is applied in `scheduled_receipt` (with `adjustment_codes`) and
logged in `detected_issue` together with the decision taken.

| Rule | Detection | Decision |
|---|---|---|
| R1 inbound counted once | more than one `IN_TRANSIT` inventory row for the same `po_line_id` | `EXCLUDE_DUPLICATE_INBOUND`. Opening stock = `ON_HAND` only; inbound supply comes **only** from open PO lines; `QUALITY_HOLD` is unavailable |
| R2 substitute approval | `sku_substitute.approval_status != APPROVED` | `REJECT_SUBSTITUTE_MITIGATION`. The link is never used, and every shortage that would have used it gets a `rejected_mitigation` row |
| R3 supplier capacity | sum of open (PLANNED/CONFIRMED) PO base quantity per supplier **ship week** > `capacity_units` | `DEFER_EXCESS_TO_NEXT_AVAILABLE_WEEK`. Lines in the week are taken in creation order; lines that no longer fit (latest-created first out) move to the next week with room, and their receipt date shifts by the same number of weeks (or falls beyond the horizon) |
| R4 lead time | `promised_receipt_date < order_date + lead_time.total_lead_days` | `RECALCULATE_RECEIPT_WITH_LEAD_TIME`. Ship = order + production lead; receipt = order + total lead + reported delay |
| R5 unit of measure | the line's conversion factor differs from the master factor (supplier terms if the order UoM matches the purchase UoM; 1 if it is the base UoM; `units_per_case` for CS; otherwise **unconvertible**) | `CONVERT_USING_MASTER_UOM` (planning qty = order_qty x master factor), or `EXCLUDE_UNCONVERTIBLE_LINE` (planning qty 0) |
| Demand spike | forecast >= 2.0 x median of the neighbouring active weeks (window 9) **and** excess >= max(8, 3 x sqrt(median)) | `FLAG_FOR_DEMAND_REVIEW` (informational; also used as a shortage cause) |
| Constrained supplier | confirmed < requested on at least one open line, **or** utilisation >= 90% in >= 3 weeks | `FLAG_CONSTRAINED_SUPPLIER` |
| Constrained plant | planned < required production in >= 3 weeks, **or** utilisation >= 95% in >= 3 weeks | `FLAG_CONSTRAINED_PLANT` |

## 2. Projected available balance (PAB)

For each SKU-location `i` and week `w`:

```
opening(i,0)   = sum(inventory.quantity where stock_status = ON_HAND)
receipts(i,w)  = sum(scheduled_receipt.planning_base_qty where counted_in_plan and receipt week = w)
production(i,w)= sum(production_plan.planned_qty)
demand(i,w)    = forecast_demand.forecast_qty                         (finished goods)
dependent(i,w) = ceil( sum over BOM parents p at the plant of planned_qty(p,w) x qty_per )   (components)
closing(i,w)   = opening(i,w) + receipts + production - demand - dependent
opening(i,w+1) = closing(i,w)
```

Negative balances are carried forward as a backlog, so the PAB reconciles exactly week by week. Validation
recomputes every term from source tables.

Counted receipts are lines of POs in status PLANNED, CONFIRMED or IN_TRANSIT, with planning quantity > 0 and receipt
week < 52. RECEIVED POs are already part of on-hand stock; CANCELLED POs are kept for cause analysis but not counted.

## 3. Shortages

A **shortage** is a maximal run of consecutive weeks with `closing < 0` for a SKU-location.

* `shortage_qty` = peak deficit = `-min(closing)` within the run (the quantity needed to clear it).
* `shortage_value` = `shortage_qty x unit_price` (components: `2 x unit_cost`, a proxy for stopping production).
* `lead_time_weeks` = first week a normal action can land: week of (as-of + primary lane total lead time) for
  purchased items, or the 2-week frozen fence for manufactured items. `within_lead_time = start < lead_time_weeks`.
  Such a shortage cannot be fixed by a normal order.

## 4. Explainable causes

Each shortage gets one or more rows in `shortage_cause`, each with a quantified `contribution_qty` (capped at the
shortage) and the evidence IDs. Specific causes are sorted by contribution, and the first one is the
`primary_cause_code`. `DEMAND_EXCEEDS_SUPPLY` is always appended with the reconciliation arithmetic, so every
shortage is explainable.

| Cause | Condition | Contribution | Evidence |
|---|---|---|---|
| DEMAND_SPIKE | spike weeks for this SKU-location up to the end week | sum of excess over local median | `demand_id`s |
| TRANSPORT_DELAY | counted line with delay > 0, promised <= end week, receipt >= start week | line quantities | `po_id`s |
| SUPPLIER_CAPACITY_CONSTRAINT | lines where confirmed < requested (promised <= end), or lines deferred by R3 | cut + deferred quantity | `po_line_id`s |
| PRODUCTION_CAPACITY_CONSTRAINT | `required_qty > planned_qty` up to the end week | sum of the gap | `production_capacity_id`s |
| DEPENDENT_DEMAND | component SKU-location | dependent demand in the run | `production_plan_id`s |
| PO_CANCELLED | cancelled lines promised <= end week | cancelled quantity | `po_id`s |
| LEAD_TIME_CORRECTION | lines recalculated by R4 that now land in or after the run | quantity | `po_id`s |
| UOM_CORRECTION | lines excluded by R5 | excluded quantity | `po_line_id`s |
| INSUFFICIENT_OPENING_STOCK | run starts inside the lead time | deficit at start | - |
| NO_SCHEDULED_SUPPLY | no receipt or production after the start week | shortage qty | - |
| DEMAND_EXCEEDS_SUPPLY | always | shortage qty | PAB rows (start, peak) |

## 5. Prioritisation

```
value_norm = ln(1 + shortage_value) / ln(1 + max shortage_value)
urgency    = 1 / (1 + start_week_index / 4)
abc_weight = A 1.0 | B 0.6 | C 0.3
duration   = min(1, duration_weeks / 8)
priority_score = 100 x (0.40 value_norm + 0.30 urgency + 0.15 abc_weight + 0.15 duration)
```

Tiers: **CRITICAL** = within lead time and ABC in (A, B), or score >= 75. **HIGH** = within lead time, or score >= 55.
**MEDIUM** = score >= 35. **LOW** otherwise. `priority_rank` orders by score; `shortage_id` counters follow rank
(SHORT-2026-000001 is the most urgent).

## 6. Mitigation options (policy + capacity)

Shortages are processed in rank order. Capacity or stock used by each **recommended** option is reserved before the
next shortage is evaluated, so recommendations never double-book a supplier week, plant week or surplus.

| Option | Feasibility rules | Cost model |
|---|---|---|
| EXPEDITE_PO | open, not-yet-shipped line for the SKU-location arriving after the start; new arrival = ship date + lane `expedite_transit_days`, earlier than now and <= end week; supplier ship week unchanged | `expedite_premium_pct` x line value |
| NEW_PO_PRIMARY / NEW_PO_ALTERNATE | supplier ACTIVE (else `SUPPLIER_ON_HOLD`); sourcing terms APPROVED; lane effective at the as-of date (else `NO_LANE`); order placed **no earlier than today**, arrival = order + `total_lead_days` <= end week (else `LEAD_TIME_TOO_LONG`). The order is placed as late as still covers the start week, walking back toward today when that ship week lacks capacity. Quantity is rounded up to MOQ and order multiple in purchase UoM and must fit remaining supplier capacity (planned load + reservations), otherwise it is reduced if still >= MOQ (partial) or rejected (`INSUFFICIENT_CAPACITY`) | total = qty x supplier price; incremental = 75 order fee + price premium over standard cost + 5% holding on MOQ overage |
| STOCK_TRANSFER | another location stocking the SKU; surplus = min over all weeks of (closing - safety stock) after earlier reservations; 1 week in-region, 2 weeks cross-region; arrival <= end week | 3% / 6% of value + 50 |
| APPROVED_SUBSTITUTE | link APPROVED and effective on the start date (else rejected with reason); substitute surplus at the same location from the start week, so it never goes below safety stock | substitute cost + 25 fee + any cost premium |
| INCREASE_PRODUCTION | MAKE SKUs only; weeks after the 2-week frozen fence up to the end week; plant headroom = capacity - planned - reserved; every BOM component must have surplus from the first production week (else `COMPONENT_SHORTAGE`); batch multiples | 15% overtime premium |
| ACCEPT_BACKORDER | always present as the "do nothing" baseline | lost margin `(price - cost) x qty` (components: cost x qty) |

Service and trade-off metrics for every option: `covered_qty = min(proposed, shortage)`, `residual`, `fill_rate_pct`,
`weeks_late = max(0, arrival - start)`, `service_score = fill x max(0, 1 - 0.15 x weeks_late)`,
`net_benefit = service_score x shortage_value - incremental_cost`. Options are ranked by net benefit; rank 1 is
recommended. The shortage status is derived from the recommended coverage. Candidates that fail a rule are written to
`rejected_mitigation` with the reason, so the trade-off is auditable even when only a backorder is feasible.

## 7. Policy parameters

All thresholds are named constants (`POLICY` in `planning.py`, `COSTS` in `mitigation.py`) so they can be reviewed
and tuned in one place.
