# Labelled edge cases and ground truth

The generator first builds a **valid** baseline (all validation checks pass). A baseline planning run then picks
targets that make each case meaningful, and `src/supply_planning/edge_cases.py` injects the cases as **new records
with new IDs**. No existing row is modified (enforced by `tests/test_edge_cases.py::test_injection_does_not_modify_baseline_rows`).

Labels exist only in `data/ground_truth/<scale>/ground_truth.csv|json`, never as columns of an input table.

| # | issue_type | What is injected | Labelled record (`record_id`) | Traceability (`related_record_ids`) | Rule | Expected decision | Expected value |
|---|---|---|---|---|---|---|---|
| 1 | INBOUND_DOUBLE_COUNT | a second `IN_TRANSIT` inventory row for a PO line already in transit (same SKU, location, qty) | new `inventory_id` | original inventory row, `po_line_id`, `po_id` | R1 | EXCLUDE_DUPLICATE_INBOUND | phantom quantity |
| 2 | SUBSTITUTE_NOT_APPROVED | a PENDING or REJECTED `sku_substitute` link for a SKU that has a shortage, where the substitute has stock above safety stock at that location, so a naive planner would use it | new `substitution_id` | substitute SKU, short SKU, location | R2 | REJECT_SUBSTITUTE_MITIGATION | substitute excluded |
| 3 | SUPPLIER_CAPACITY_EXCEEDED | a "rush" PO (PLANNED) whose quantity pushes the supplier's ship week above `capacity_units` | `supplier_capacity_id` of that week | new `po_id`, `po_line_id` | R3 | DEFER_EXCESS_TO_NEXT_AVAILABLE_WEEK | committed > capacity |
| 4 | SHORTAGE_WITHOUT_LEAD_TIME | a PO whose ship and promised receipt dates equal the order date: the lane lead time was ignored, so a naive shortage calculation sees supply that cannot arrive in time | new `po_id` | `po_line_id`, `lead_time_id` | R4 | RECALCULATE_RECEIPT_WITH_LEAD_TIME | correct receipt date |
| 5 | UOM_MISMATCH | (A) a PO line ordered in cases (CS) but recorded with factor 1, so the base quantity is understated; (B) a line for an EA SKU ordered in KG, which cannot be converted | new `po_line_id` | `po_id` | R5 | (A) CONVERT_USING_MASTER_UOM, (B) EXCLUDE_UNCONVERTIBLE_LINE | (A) correct base qty, (B) 0 |

Counts: `edge_cases_per_type` per type (test 2, starter 3, full 10). Injected POs use suppliers and weeks with
spare capacity, so they don't trigger unrelated, unlabelled issues.

## Scenario labels (also in ground truth)

The generator also records the hidden drivers of realistic variation, so detection quality can be measured:

| issue_type | label_category | record | Meaning |
|---|---|---|---|
| DEMAND_SPIKE | SCENARIO | `demand_id` | the forecast was multiplied 2.5-4.5x after POs were planned |
| CONSTRAINED_SUPPLIER | SCENARIO | `supplier_id` | weekly capacity set close to mean load, so confirmed quantities were cut |
| CONSTRAINED_PLANT | SCENARIO | `location_id` | plant capacity set close to mean load, so planned production is below requirement |

## Ground-truth columns

`gt_id, label_category, issue_type, record_type, record_id, related_record_ids, sku_id, location_id, supplier_id,
week_id, expected_decision, expected_value, rule_reference, description`

## How the labels are used (and not used)

* **Planning engine**: never reads ground truth. A test asserts that `planning.py`, `mitigation.py` and
  `generator.py` contain no reference to it, and another re-plans from a copy of `data/raw` alone and gets identical
  results.
* **Validation**: violations whose record ID is labelled are classified `EXPECTED_LABELLED`; anything else is
  `UNEXPECTED` and fails the run.
* **Evaluation**: precision, recall and decision accuracy per issue type (`outputs/<scale>/evaluation_report.md`),
  plus a "naive vs engine" impact table for each edge case.
