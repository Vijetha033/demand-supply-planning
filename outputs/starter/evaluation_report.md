# Evaluation report - `starter`

Seed `20261022`. Engine outputs compared against `data/ground_truth/starter/ground_truth.csv`.

## Exception detection vs ground truth

- Edge-case recall **100%**, precision **100%**, decision accuracy **100%**

| Issue type | Category | Labelled | Detected | TP | FP | FN | Precision | Recall | Decision accuracy |
|---|---|---|---|---|---|---|---|---|---|
| INBOUND_DOUBLE_COUNT | EDGE_CASE | 3 | 3 | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| SUBSTITUTE_NOT_APPROVED | EDGE_CASE | 3 | 3 | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| SUPPLIER_CAPACITY_EXCEEDED | EDGE_CASE | 3 | 3 | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| SHORTAGE_WITHOUT_LEAD_TIME | EDGE_CASE | 3 | 3 | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| UOM_MISMATCH | EDGE_CASE | 3 | 3 | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| DEMAND_SPIKE | SCENARIO | 23 | 26 | 23 | 3 | 0 | 0.88 | 1.00 | 1.00 |
| CONSTRAINED_SUPPLIER | SCENARIO | 5 | 5 | 5 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CONSTRAINED_PLANT | SCENARIO | 1 | 1 | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |

## What a naive calculation would get wrong

| GT | Issue | Record | Naive | Engine |
|---|---|---|---|---|
| GT-000001 | INBOUND_DOUBLE_COUNT | `INV-000630` | +48 phantom units of supply | excluded (counted once) |
| GT-000002 | INBOUND_DOUBLE_COUNT | `INV-000631` | +60 phantom units of supply | excluded (counted once) |
| GT-000003 | INBOUND_DOUBLE_COUNT | `INV-000632` | +65 phantom units of supply | excluded (counted once) |
| GT-000004 | SUBSTITUTE_NOT_APPROVED | `SUB-000012` | substitute stock would be offered as a mitigation | rejected in 7 shortage evaluation(s); used in 0 options |
| GT-000005 | SUBSTITUTE_NOT_APPROVED | `SUB-000013` | substitute stock would be offered as a mitigation | rejected in 4 shortage evaluation(s); used in 0 options |
| GT-000006 | SUBSTITUTE_NOT_APPROVED | `SUB-000014` | substitute stock would be offered as a mitigation | rejected in 4 shortage evaluation(s); used in 0 options |
| GT-000007 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0036-2026W45` | receipt 2026-11-08 (committed 3816 > capacity 2910) | receipt 2026-11-15 (CAPACITY_DEFERRED_1W) |
| GT-000008 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0013-2026W43` | receipt 2026-10-21 (committed 3032 > capacity 2330) | receipt 2026-11-11 (CAPACITY_DEFERRED_3W) |
| GT-000009 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0019-2026W28` | receipt 2026-07-10 (committed 758 > capacity 580) | receipt 2026-07-17 (CAPACITY_DEFERRED_1W) |
| GT-000010 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-001004` | receipt 2025-12-31 | receipt 2026-01-20 |
| GT-000011 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-001005` | receipt 2025-12-30 | receipt 2026-02-08 |
| GT-000012 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-001006` | receipt 2025-12-31 | receipt 2026-01-14 |
| GT-000013 | UOM_MISMATCH | `PO-2026-001007-L01` | 4 units | 96 units (UOM_CONVERTED) |
| GT-000014 | UOM_MISMATCH | `PO-2026-001008-L01` | 103 units | 0 units (UOM_UNCONVERTIBLE_EXCLUDED) |
| GT-000015 | UOM_MISMATCH | `PO-2026-001009-L01` | 6 units | 72 units (UOM_CONVERTED) |

## Planning KPIs

| KPI | Value |
|---|---|
| sku_locations | 408 |
| sku_locations_with_shortage | 115 |
| shortage_episodes | 322 |
| shortages_by_tier | {'MEDIUM': 159, 'LOW': 83, 'HIGH': 64, 'CRITICAL': 16} |
| shortages_by_primary_cause | {'SUPPLIER_CAPACITY_CONSTRAINT': 107, 'DEMAND_EXCEEDS_SUPPLY': 79, 'DEMAND_SPIKE': 45, 'PRODUCTION_CAPACITY_CONSTRAINT': 29, 'PO_CANCELLED': 29, 'TRANSPORT_DELAY': 14, 'NO_SCHEDULED_SUPPLY': 9, 'DEPENDENT_DEMAND': 6, 'INSUFFICIENT_OPENING_STOCK': 4} |
| shortages_by_status | {'MITIGATION_PROPOSED': 263, 'UNMITIGATED': 55, 'PARTIALLY_MITIGATED': 4} |
| total_shortage_qty | 80450 |
| total_shortage_value_usd | 1134310.79 |
| share_with_feasible_mitigation | 0.9006 |
| recommended_by_type | {'NEW_PO_PRIMARY': 221, 'ACCEPT_BACKORDER': 55, 'EXPEDITE_PO': 29, 'STOCK_TRANSFER': 11, 'NEW_PO_ALTERNATE': 6} |
| recommended_value_protected_usd | 882602.91 |
| recommended_incremental_cost_usd | 41300.04 |
| mean_recommended_fill_rate_pct | 82.51 |
| mitigation_options | 996 |
| rejected_candidates_by_reason | {'NO_SURPLUS': 116, 'COMPONENT_SHORTAGE': 29, 'LEAD_TIME_TOO_LONG': 28, 'SUBSTITUTE_NOT_APPROVED': 15, 'INSUFFICIENT_CAPACITY': 2, 'SUPPLIER_ON_HOLD': 1} |
| projected_service_level_pct | 89.3 |

## Coverage of normal / boundary / failure / exception scenarios

| Class | Scenario | Count |
|---|---|---|
| NORMAL | open PO lines received on promise (no delay) | 837 |
| NORMAL | SKU-location-weeks at or above safety stock | 18,438 |
| BOUNDARY | supplier-weeks at exactly 100 % source utilisation | 12 |
| BOUNDARY | SKU-location-weeks with projected balance exactly 0 | 46 |
| BOUNDARY | PO lines ordered at exactly MOQ | 970 |
| BOUNDARY | PO lines cut by supplier capacity (confirmed < requested) | 221 |
| BOUNDARY | lead-time lanes with a mid-horizon revision (version 2) | 17 |
| BOUNDARY | shortages starting inside replenishment lead time | 18 |
| FAILURE | cancelled purchase orders | 10 |
| FAILURE | transport/production delay events | 11 |
| FAILURE | rejected mitigation candidates | 191 |
| FAILURE | shortages left unmitigated (backorder recommended) | 55 |
| EXCEPTION | labelled edge cases injected | 15 |
| EXCEPTION | engine exceptions logged (detected_issue) | 47 |

## Distributions (realism)

```json
{
  "weekly_demand_per_sku_location_quantiles": {
    "0.05": 2.79,
    "0.25": 8.94,
    "0.5": 20.93,
    "0.75": 50.87,
    "0.95": 154.5
  },
  "demand_cv_quantiles": {
    "0.05": 0.12,
    "0.25": 0.15,
    "0.5": 0.19,
    "0.75": 0.27,
    "0.95": 0.65
  },
  "zero_demand_week_share": 0.0123,
  "sku_mix": {
    "item_type": {
      "FINISHED_GOOD": 255,
      "COMPONENT": 45
    },
    "sourcing_type": {
      "BUY": 270,
      "MAKE": 30
    },
    "abc_class": {
      "A": 107,
      "C": 106,
      "B": 87
    },
    "lifecycle_status": {
      "ACTIVE": 270,
      "NEW": 16,
      "PHASE_OUT": 14
    },
    "base_uom": {
      "EA": 269,
      "KG": 18,
      "L": 13
    }
  },
  "unit_cost_quantiles": {
    "0.05": 1.13,
    "0.25": 3.85,
    "0.5": 8.18,
    "0.75": 15.91,
    "0.95": 39.93
  },
  "lead_time_days_quantiles": {
    "0.05": 9.0,
    "0.25": 15.0,
    "0.5": 19.0,
    "0.75": 25.75,
    "0.95": 40.75
  },
  "transport_mode_mix": {
    "ROAD": 108,
    "RAIL": 66,
    "SEA": 32
  },
  "po_status_mix": {
    "PLANNED": 788,
    "RECEIVED": 156,
    "IN_TRANSIT": 31,
    "CONFIRMED": 24,
    "CANCELLED": 10
  },
  "po_lines_per_order_quantiles": {
    "0.05": 1.0,
    "0.25": 2.0,
    "0.5": 3.0,
    "0.75": 6.0,
    "0.95": 16.6
  },
  "po_delayed_share": 0.0109,
  "sku_location_weeks_short_share": 0.107,
  "sku_location_weeks_below_safety_stock_share": 0.1309
}
```

## Ground-truth leakage audit

- Passed: **True**
- Engine modules referencing ground truth: {'planning.py': False, 'mitigation.py': False}
- Label columns found in inputs: none
