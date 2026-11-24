# Evaluation report - `full`

Seed `20261022`. Engine outputs compared against `data/ground_truth/full/ground_truth.csv`.

## Exception detection vs ground truth

- Edge-case recall **100%**, precision **100%**, decision accuracy **100%**

| Issue type | Category | Labelled | Detected | TP | FP | FN | Precision | Recall | Decision accuracy |
|---|---|---|---|---|---|---|---|---|---|
| INBOUND_DOUBLE_COUNT | EDGE_CASE | 10 | 10 | 10 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| SUBSTITUTE_NOT_APPROVED | EDGE_CASE | 10 | 10 | 10 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| SUPPLIER_CAPACITY_EXCEEDED | EDGE_CASE | 10 | 10 | 10 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| SHORTAGE_WITHOUT_LEAD_TIME | EDGE_CASE | 10 | 10 | 10 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| UOM_MISMATCH | EDGE_CASE | 10 | 10 | 10 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| DEMAND_SPIKE | SCENARIO | 211 | 222 | 211 | 11 | 0 | 0.95 | 1.00 | 1.00 |
| CONSTRAINED_SUPPLIER | SCENARIO | 50 | 50 | 50 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CONSTRAINED_PLANT | SCENARIO | 1 | 1 | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |

## What a naive calculation would get wrong

| GT | Issue | Record | Naive | Engine |
|---|---|---|---|---|
| GT-000001 | INBOUND_DOUBLE_COUNT | `INV-005604` | +48 phantom units of supply | excluded (counted once) |
| GT-000002 | INBOUND_DOUBLE_COUNT | `INV-005605` | +90 phantom units of supply | excluded (counted once) |
| GT-000003 | INBOUND_DOUBLE_COUNT | `INV-005606` | +42 phantom units of supply | excluded (counted once) |
| GT-000004 | INBOUND_DOUBLE_COUNT | `INV-005607` | +186 phantom units of supply | excluded (counted once) |
| GT-000005 | INBOUND_DOUBLE_COUNT | `INV-005608` | +135 phantom units of supply | excluded (counted once) |
| GT-000006 | INBOUND_DOUBLE_COUNT | `INV-005609` | +36 phantom units of supply | excluded (counted once) |
| GT-000007 | INBOUND_DOUBLE_COUNT | `INV-005610` | +5856 phantom units of supply | excluded (counted once) |
| GT-000008 | INBOUND_DOUBLE_COUNT | `INV-005611` | +505 phantom units of supply | excluded (counted once) |
| GT-000009 | INBOUND_DOUBLE_COUNT | `INV-005612` | +576 phantom units of supply | excluded (counted once) |
| GT-000010 | INBOUND_DOUBLE_COUNT | `INV-005613` | +24 phantom units of supply | excluded (counted once) |
| GT-000011 | SUBSTITUTE_NOT_APPROVED | `SUB-000135` | substitute stock would be offered as a mitigation | rejected in 6 shortage evaluation(s); used in 0 options |
| GT-000012 | SUBSTITUTE_NOT_APPROVED | `SUB-000136` | substitute stock would be offered as a mitigation | rejected in 1 shortage evaluation(s); used in 0 options |
| GT-000013 | SUBSTITUTE_NOT_APPROVED | `SUB-000137` | substitute stock would be offered as a mitigation | rejected in 5 shortage evaluation(s); used in 0 options |
| GT-000014 | SUBSTITUTE_NOT_APPROVED | `SUB-000138` | substitute stock would be offered as a mitigation | rejected in 1 shortage evaluation(s); used in 0 options |
| GT-000015 | SUBSTITUTE_NOT_APPROVED | `SUB-000139` | substitute stock would be offered as a mitigation | rejected in 8 shortage evaluation(s); used in 0 options |
| GT-000016 | SUBSTITUTE_NOT_APPROVED | `SUB-000140` | substitute stock would be offered as a mitigation | rejected in 5 shortage evaluation(s); used in 0 options |
| GT-000017 | SUBSTITUTE_NOT_APPROVED | `SUB-000141` | substitute stock would be offered as a mitigation | rejected in 1 shortage evaluation(s); used in 0 options |
| GT-000018 | SUBSTITUTE_NOT_APPROVED | `SUB-000142` | substitute stock would be offered as a mitigation | rejected in 7 shortage evaluation(s); used in 0 options |
| GT-000019 | SUBSTITUTE_NOT_APPROVED | `SUB-000143` | substitute stock would be offered as a mitigation | rejected in 2 shortage evaluation(s); used in 0 options |
| GT-000020 | SUBSTITUTE_NOT_APPROVED | `SUB-000144` | substitute stock would be offered as a mitigation | rejected in 8 shortage evaluation(s); used in 0 options |
| GT-000021 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0299-2026W43` | receipt 2026-10-21 (committed 684 > capacity 520) | receipt 2026-10-28 (CAPACITY_DEFERRED_1W) |
| GT-000022 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0457-2026W26` | receipt 2026-07-01 (committed 672 > capacity 510) | receipt 2026-07-01 (CAPACITY_DEFERRED_BEYOND_HORIZON) |
| GT-000023 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0136-2026W05` | receipt 2026-02-06 (committed 1729 > capacity 1330) | receipt 2026-02-06 (CAPACITY_DEFERRED_BEYOND_HORIZON) |
| GT-000024 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0213-2026W12` | receipt 2026-04-08 (committed 1222 > capacity 940) | receipt 2026-04-08 (CAPACITY_DEFERRED_BEYOND_HORIZON) |
| GT-000025 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0220-2026W17` | receipt 2026-05-21 (committed 270 > capacity 190) | receipt 2026-05-21 (CAPACITY_DEFERRED_BEYOND_HORIZON) |
| GT-000026 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0264-2026W35` | receipt 2026-08-26 (committed 1188 > capacity 910) | receipt 2026-08-26 (CAPACITY_DEFERRED_BEYOND_HORIZON) |
| GT-000027 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0150-2026W39` | receipt 2026-10-18 (committed 1392 > capacity 1070) | receipt 2026-10-18 (CAPACITY_DEFERRED_BEYOND_HORIZON) |
| GT-000028 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0234-2026W34` | receipt 2026-08-22 (committed 360 > capacity 260) | receipt 2026-08-22 (CAPACITY_DEFERRED_BEYOND_HORIZON) |
| GT-000029 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0181-2026W45` | receipt 2026-12-07 (committed 3731 > capacity 2870) | receipt 2026-12-07 (CAPACITY_DEFERRED_BEYOND_HORIZON) |
| GT-000030 | SUPPLIER_CAPACITY_EXCEEDED | `SCAP-SUP-0071-2026W16` | receipt 2026-04-17 (committed 2370 > capacity 1820) | receipt 2026-04-17 (CAPACITY_DEFERRED_BEYOND_HORIZON) |
| GT-000031 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-010011` | receipt 2025-12-30 | receipt 2026-02-10 |
| GT-000032 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-010012` | receipt 2025-12-30 | receipt 2026-01-22 |
| GT-000033 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-010013` | receipt 2025-12-31 | receipt 2026-02-02 |
| GT-000034 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-010014` | receipt 2025-12-31 | receipt 2026-01-18 |
| GT-000035 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-010015` | receipt 2025-12-30 | receipt 2026-01-21 |
| GT-000036 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-010016` | receipt 2025-12-31 | receipt 2026-01-21 |
| GT-000037 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-010017` | receipt 2025-12-31 | receipt 2026-01-17 |
| GT-000038 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-010018` | receipt 2025-12-30 | receipt 2026-01-20 |
| GT-000039 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-010019` | receipt 2025-12-31 | receipt 2026-01-22 |
| GT-000040 | SHORTAGE_WITHOUT_LEAD_TIME | `PO-2026-010020` | receipt 2025-12-31 | receipt 2026-01-19 |
| GT-000041 | UOM_MISMATCH | `PO-2026-010021-L01` | 14 units | 168 units (UOM_CONVERTED) |
| GT-000042 | UOM_MISMATCH | `PO-2026-010022-L01` | 1 units | 0 units (UOM_UNCONVERTIBLE_EXCLUDED) |
| GT-000043 | UOM_MISMATCH | `PO-2026-010023-L01` | 2 units | 24 units (UOM_CONVERTED) |
| GT-000044 | UOM_MISMATCH | `PO-2026-010024-L01` | 4 units | 0 units (UOM_UNCONVERTIBLE_EXCLUDED) |
| GT-000045 | UOM_MISMATCH | `PO-2026-010025-L01` | 1 units | 12 units (UOM_CONVERTED) |
| GT-000046 | UOM_MISMATCH | `PO-2026-010026-L01` | 50 units | 0 units (UOM_UNCONVERTIBLE_EXCLUDED) |
| GT-000047 | UOM_MISMATCH | `PO-2026-010027-L01` | 2 units | 12 units (UOM_CONVERTED) |
| GT-000048 | UOM_MISMATCH | `PO-2026-010028-L01` | 1 units | 0 units (UOM_UNCONVERTIBLE_EXCLUDED) |
| GT-000049 | UOM_MISMATCH | `PO-2026-010029-L01` | 1 units | 12 units (UOM_CONVERTED) |
| GT-000050 | UOM_MISMATCH | `PO-2026-010030-L01` | 1 units | 0 units (UOM_UNCONVERTIBLE_EXCLUDED) |

## Planning KPIs

| KPI | Value |
|---|---|
| sku_locations | 4207 |
| sku_locations_with_shortage | 958 |
| shortage_episodes | 3025 |
| shortages_by_tier | {'MEDIUM': 1612, 'LOW': 801, 'HIGH': 473, 'CRITICAL': 139} |
| shortages_by_primary_cause | {'DEMAND_EXCEEDS_SUPPLY': 1123, 'SUPPLIER_CAPACITY_CONSTRAINT': 898, 'DEMAND_SPIKE': 419, 'PO_CANCELLED': 147, 'DEPENDENT_DEMAND': 123, 'INSUFFICIENT_OPENING_STOCK': 92, 'PRODUCTION_CAPACITY_CONSTRAINT': 90, 'NO_SCHEDULED_SUPPLY': 73, 'TRANSPORT_DELAY': 50, 'LEAD_TIME_CORRECTION': 7, 'UOM_CORRECTION': 3} |
| shortages_by_status | {'MITIGATION_PROPOSED': 2612, 'UNMITIGATED': 370, 'PARTIALLY_MITIGATED': 43} |
| total_shortage_qty | 817264 |
| total_shortage_value_usd | 8660243.96 |
| share_with_feasible_mitigation | 0.9345 |
| recommended_by_type | {'NEW_PO_PRIMARY': 2257, 'ACCEPT_BACKORDER': 370, 'EXPEDITE_PO': 267, 'NEW_PO_ALTERNATE': 74, 'STOCK_TRANSFER': 45, 'APPROVED_SUBSTITUTE': 11, 'INCREASE_PRODUCTION': 1} |
| recommended_value_protected_usd | 6413429.97 |
| recommended_incremental_cost_usd | 313710.87 |
| mean_recommended_fill_rate_pct | 87.11 |
| mitigation_options | 9046 |
| rejected_candidates_by_reason | {'NO_SURPLUS': 1076, 'LEAD_TIME_TOO_LONG': 182, 'COMPONENT_SHORTAGE': 129, 'INSUFFICIENT_CAPACITY': 76, 'SUPPLIER_ON_HOLD': 58, 'SUBSTITUTE_NOT_APPROVED': 44} |
| projected_service_level_pct | 90.69 |

## Coverage of normal / boundary / failure / exception scenarios

| Class | Scenario | Count |
|---|---|---|
| NORMAL | open PO lines received on promise (no delay) | 8,277 |
| NORMAL | SKU-location-weeks at or above safety stock | 193,943 |
| BOUNDARY | supplier-weeks at exactly 100 % source utilisation | 90 |
| BOUNDARY | SKU-location-weeks with projected balance exactly 0 | 489 |
| BOUNDARY | PO lines ordered at exactly MOQ | 17,745 |
| BOUNDARY | PO lines cut by supplier capacity (confirmed < requested) | 1,468 |
| BOUNDARY | lead-time lanes with a mid-horizon revision (version 2) | 239 |
| BOUNDARY | shortages starting inside replenishment lead time | 159 |
| FAILURE | cancelled purchase orders | 83 |
| FAILURE | transport/production delay events | 167 |
| FAILURE | rejected mitigation candidates | 1,565 |
| FAILURE | shortages left unmitigated (backorder recommended) | 370 |
| EXCEPTION | labelled edge cases injected | 50 |
| EXCEPTION | engine exceptions logged (detected_issue) | 323 |

## Distributions (realism)

```json
{
  "weekly_demand_per_sku_location_quantiles": {
    "0.05": 2.86,
    "0.25": 9.09,
    "0.5": 20.27,
    "0.75": 46.59,
    "0.95": 152.32
  },
  "demand_cv_quantiles": {
    "0.05": 0.13,
    "0.25": 0.16,
    "0.5": 0.19,
    "0.75": 0.27,
    "0.95": 0.63
  },
  "zero_demand_week_share": 0.0116,
  "sku_mix": {
    "item_type": {
      "FINISHED_GOOD": 2550,
      "COMPONENT": 450
    },
    "sourcing_type": {
      "BUY": 2700,
      "MAKE": 300
    },
    "abc_class": {
      "C": 1109,
      "A": 993,
      "B": 898
    },
    "lifecycle_status": {
      "ACTIVE": 2685,
      "NEW": 183,
      "PHASE_OUT": 132
    },
    "base_uom": {
      "EA": 2639,
      "KG": 224,
      "L": 137
    }
  },
  "unit_cost_quantiles": {
    "0.05": 1.46,
    "0.25": 4.08,
    "0.5": 8.29,
    "0.75": 17.01,
    "0.95": 45.57
  },
  "lead_time_days_quantiles": {
    "0.05": 9.0,
    "0.25": 15.0,
    "0.5": 21.0,
    "0.75": 28.0,
    "0.95": 45.0
  },
  "transport_mode_mix": {
    "ROAD": 1457,
    "RAIL": 659,
    "SEA": 542
  },
  "po_status_mix": {
    "PLANNED": 7849,
    "RECEIVED": 1612,
    "CONFIRMED": 263,
    "IN_TRANSIT": 223,
    "CANCELLED": 83
  },
  "po_lines_per_order_quantiles": {
    "0.05": 1.0,
    "0.25": 2.0,
    "0.5": 3.0,
    "0.75": 5.0,
    "0.95": 18.0
  },
  "po_delayed_share": 0.0167,
  "sku_location_weeks_short_share": 0.0931,
  "sku_location_weeks_below_safety_stock_share": 0.1135
}
```

## Ground-truth leakage audit

- Passed: **True**
- Engine modules referencing ground truth: {'planning.py': False, 'mitigation.py': False}
- Label columns found in inputs: none
