# Validation summary - `full`

- Overall status: **PASS**
- Checks run: 148
- Violations: 60 (60 expected - every one points at a labelled edge-case record; 0 unexpected)

Expected violations are the deliberately injected edge cases: the validator finds them and matches each to its `ground_truth` label. Any unexpected violation fails the run.

## By category

| Category | Checks | Rows checked | Violations | Expected (labelled) | Unexpected | Status |
|---|---|---|---|---|---|---|
| arithmetic | 4 | 77,673 | 10 | 10 | 0 | PASS_WITH_LABELLED_EXCEPTIONS |
| capacity | 5 | 70,106 | 10 | 10 | 0 | PASS_WITH_LABELLED_EXCEPTIONS |
| cross_entity | 3 | 61,523 | 0 | 0 | 0 | PASS |
| date_ordering | 3 | 181,015 | 0 | 0 | 0 | PASS |
| derived | 3 | 11,414 | 0 | 0 | 0 | PASS |
| duplicate | 15 | 838,713 | 20 | 20 | 0 | PASS_WITH_LABELLED_EXCEPTIONS |
| explainability | 2 | 6,050 | 0 | 0 | 0 | PASS |
| foreign_key | 50 | 2,298,610 | 0 | 0 | 0 | PASS |
| leakage | 1 | 17 | 0 | 0 | 0 | PASS |
| lifecycle | 2 | 13,030 | 0 | 0 | 0 | PASS |
| policy | 3 | 19,220 | 10 | 10 | 0 | PASS_WITH_LABELLED_EXCEPTIONS |
| primary_key | 26 | 623,541 | 0 | 0 | 0 | PASS |
| reconciliation | 4 | 485,522 | 0 | 0 | 0 | PASS |
| schema | 26 | 623,541 | 0 | 0 | 0 | PASS |
| uom | 1 | 54,955 | 10 | 10 | 0 | PASS_WITH_LABELLED_EXCEPTIONS |

## All checks

| Check | Category | Rows | Violations | Expected | Unexpected | Status | Description |
|---|---|---|---|---|---|---|---|
| `schema:calendar_week` | schema | 52 | 0 | 0 | 0 | PASS | calendar_week: columns, required, types, patterns, enums, ranges |
| `pk:calendar_week` | primary_key | 52 | 0 | 0 | 0 | PASS | calendar_week.week_id unique and not null |
| `schema:location` | schema | 50 | 0 | 0 | 0 | PASS | location: columns, required, types, patterns, enums, ranges |
| `pk:location` | primary_key | 50 | 0 | 0 | 0 | PASS | location.location_id unique and not null |
| `schema:supplier` | schema | 500 | 0 | 0 | 0 | PASS | supplier: columns, required, types, patterns, enums, ranges |
| `pk:supplier` | primary_key | 500 | 0 | 0 | 0 | PASS | supplier.supplier_id unique and not null |
| `schema:sku` | schema | 3,000 | 0 | 0 | 0 | PASS | sku: columns, required, types, patterns, enums, ranges |
| `pk:sku` | primary_key | 3,000 | 0 | 0 | 0 | PASS | sku.sku_id unique and not null |
| `schema:sku_location` | schema | 4,207 | 0 | 0 | 0 | PASS | sku_location: columns, required, types, patterns, enums, ranges |
| `pk:sku_location` | primary_key | 4,207 | 0 | 0 | 0 | PASS | sku_location.sku_location_id unique and not null |
| `duplicate:sku_location` | duplicate | 4,207 | 0 | 0 | 0 | PASS | sku_location natural key ['sku_id', 'location_id'] unique |
| `fk:sku_location.sku_id->sku` | foreign_key | 4,207 | 0 | 0 | 0 | PASS | sku_location(sku_id) -> sku |
| `fk:sku_location.location_id->location` | foreign_key | 4,207 | 0 | 0 | 0 | PASS | sku_location(location_id) -> location |
| `fk:sku_location.primary_supplier_id->supplier` | foreign_key | 4,207 | 0 | 0 | 0 | PASS | sku_location(primary_supplier_id) -> supplier |
| `schema:supplier_sku` | schema | 3,988 | 0 | 0 | 0 | PASS | supplier_sku: columns, required, types, patterns, enums, ranges |
| `pk:supplier_sku` | primary_key | 3,988 | 0 | 0 | 0 | PASS | supplier_sku.supplier_sku_id unique and not null |
| `duplicate:supplier_sku` | duplicate | 3,988 | 0 | 0 | 0 | PASS | supplier_sku natural key ['supplier_id', 'sku_id'] unique |
| `fk:supplier_sku.supplier_id->supplier` | foreign_key | 3,988 | 0 | 0 | 0 | PASS | supplier_sku(supplier_id) -> supplier |
| `fk:supplier_sku.sku_id->sku` | foreign_key | 3,988 | 0 | 0 | 0 | PASS | supplier_sku(sku_id) -> sku |
| `schema:lead_time` | schema | 2,658 | 0 | 0 | 0 | PASS | lead_time: columns, required, types, patterns, enums, ranges |
| `pk:lead_time` | primary_key | 2,658 | 0 | 0 | 0 | PASS | lead_time.lead_time_id unique and not null |
| `duplicate:lead_time` | duplicate | 2,658 | 0 | 0 | 0 | PASS | lead_time natural key ['supplier_id', 'location_id', 'version'] unique |
| `fk:lead_time.supplier_id->supplier` | foreign_key | 2,658 | 0 | 0 | 0 | PASS | lead_time(supplier_id) -> supplier |
| `fk:lead_time.location_id->location` | foreign_key | 2,658 | 0 | 0 | 0 | PASS | lead_time(location_id) -> location |
| `schema:supplier_capacity` | schema | 26,000 | 0 | 0 | 0 | PASS | supplier_capacity: columns, required, types, patterns, enums, ranges |
| `pk:supplier_capacity` | primary_key | 26,000 | 0 | 0 | 0 | PASS | supplier_capacity.supplier_capacity_id unique and not null |
| `duplicate:supplier_capacity` | duplicate | 26,000 | 0 | 0 | 0 | PASS | supplier_capacity natural key ['supplier_id', 'week_id'] unique |
| `fk:supplier_capacity.supplier_id->supplier` | foreign_key | 26,000 | 0 | 0 | 0 | PASS | supplier_capacity(supplier_id) -> supplier |
| `fk:supplier_capacity.week_id->calendar_week` | foreign_key | 26,000 | 0 | 0 | 0 | PASS | supplier_capacity(week_id) -> calendar_week |
| `schema:forecast_demand` | schema | 170,933 | 0 | 0 | 0 | PASS | forecast_demand: columns, required, types, patterns, enums, ranges |
| `pk:forecast_demand` | primary_key | 170,933 | 0 | 0 | 0 | PASS | forecast_demand.demand_id unique and not null |
| `duplicate:forecast_demand` | duplicate | 170,933 | 0 | 0 | 0 | PASS | forecast_demand natural key ['sku_id', 'location_id', 'week_id'] unique |
| `fk:forecast_demand.sku_id->sku` | foreign_key | 170,933 | 0 | 0 | 0 | PASS | forecast_demand(sku_id) -> sku |
| `fk:forecast_demand.location_id->location` | foreign_key | 170,933 | 0 | 0 | 0 | PASS | forecast_demand(location_id) -> location |
| `fk:forecast_demand.week_id->calendar_week` | foreign_key | 170,933 | 0 | 0 | 0 | PASS | forecast_demand(week_id) -> calendar_week |
| `fk:forecast_demand.sku_id+location_id->sku_location` | foreign_key | 170,933 | 0 | 0 | 0 | PASS | forecast_demand(sku_id, location_id) -> sku_location |
| `schema:inventory` | schema | 5,613 | 0 | 0 | 0 | PASS | inventory: columns, required, types, patterns, enums, ranges |
| `pk:inventory` | primary_key | 5,613 | 0 | 0 | 0 | PASS | inventory.inventory_id unique and not null |
| `fk:inventory.sku_id->sku` | foreign_key | 5,613 | 0 | 0 | 0 | PASS | inventory(sku_id) -> sku |
| `fk:inventory.location_id->location` | foreign_key | 5,613 | 0 | 0 | 0 | PASS | inventory(location_id) -> location |
| `fk:inventory.po_line_id->purchase_order_line` | foreign_key | 5,613 | 0 | 0 | 0 | PASS | inventory(po_line_id) -> purchase_order_line |
| `fk:inventory.sku_id+location_id->sku_location` | foreign_key | 5,613 | 0 | 0 | 0 | PASS | inventory(sku_id, location_id) -> sku_location |
| `schema:purchase_order` | schema | 10,030 | 0 | 0 | 0 | PASS | purchase_order: columns, required, types, patterns, enums, ranges |
| `pk:purchase_order` | primary_key | 10,030 | 0 | 0 | 0 | PASS | purchase_order.po_id unique and not null |
| `fk:purchase_order.supplier_id->supplier` | foreign_key | 10,030 | 0 | 0 | 0 | PASS | purchase_order(supplier_id) -> supplier |
| `fk:purchase_order.location_id->location` | foreign_key | 10,030 | 0 | 0 | 0 | PASS | purchase_order(location_id) -> location |
| `fk:purchase_order.lead_time_id->lead_time` | foreign_key | 10,030 | 0 | 0 | 0 | PASS | purchase_order(lead_time_id) -> lead_time |
| `schema:purchase_order_line` | schema | 54,955 | 0 | 0 | 0 | PASS | purchase_order_line: columns, required, types, patterns, enums, ranges |
| `pk:purchase_order_line` | primary_key | 54,955 | 0 | 0 | 0 | PASS | purchase_order_line.po_line_id unique and not null |
| `duplicate:purchase_order_line` | duplicate | 54,955 | 0 | 0 | 0 | PASS | purchase_order_line natural key ['po_id', 'sku_id'] unique |
| `fk:purchase_order_line.po_id->purchase_order` | foreign_key | 54,955 | 0 | 0 | 0 | PASS | purchase_order_line(po_id) -> purchase_order |
| `fk:purchase_order_line.sku_id->sku` | foreign_key | 54,955 | 0 | 0 | 0 | PASS | purchase_order_line(sku_id) -> sku |
| `fk:purchase_order_line.supplier_sku_id->supplier_sku` | foreign_key | 54,955 | 0 | 0 | 0 | PASS | purchase_order_line(supplier_sku_id) -> supplier_sku |
| `schema:purchase_order_event` | schema | 15,826 | 0 | 0 | 0 | PASS | purchase_order_event: columns, required, types, patterns, enums, ranges |
| `pk:purchase_order_event` | primary_key | 15,826 | 0 | 0 | 0 | PASS | purchase_order_event.event_id unique and not null |
| `duplicate:purchase_order_event` | duplicate | 15,826 | 0 | 0 | 0 | PASS | purchase_order_event natural key ['po_id', 'event_seq'] unique |
| `fk:purchase_order_event.po_id->purchase_order` | foreign_key | 15,826 | 0 | 0 | 0 | PASS | purchase_order_event(po_id) -> purchase_order |
| `schema:bom` | schema | 955 | 0 | 0 | 0 | PASS | bom: columns, required, types, patterns, enums, ranges |
| `pk:bom` | primary_key | 955 | 0 | 0 | 0 | PASS | bom.bom_id unique and not null |
| `duplicate:bom` | duplicate | 955 | 0 | 0 | 0 | PASS | bom natural key ['parent_sku_id', 'component_sku_id'] unique |
| `fk:bom.parent_sku_id->sku` | foreign_key | 955 | 0 | 0 | 0 | PASS | bom(parent_sku_id) -> sku |
| `fk:bom.component_sku_id->sku` | foreign_key | 955 | 0 | 0 | 0 | PASS | bom(component_sku_id) -> sku |
| `schema:production_capacity` | schema | 260 | 0 | 0 | 0 | PASS | production_capacity: columns, required, types, patterns, enums, ranges |
| `pk:production_capacity` | primary_key | 260 | 0 | 0 | 0 | PASS | production_capacity.production_capacity_id unique and not null |
| `duplicate:production_capacity` | duplicate | 260 | 0 | 0 | 0 | PASS | production_capacity natural key ['location_id', 'week_id'] unique |
| `fk:production_capacity.location_id->location` | foreign_key | 260 | 0 | 0 | 0 | PASS | production_capacity(location_id) -> location |
| `fk:production_capacity.week_id->calendar_week` | foreign_key | 260 | 0 | 0 | 0 | PASS | production_capacity(week_id) -> calendar_week |
| `schema:production_plan` | schema | 14,821 | 0 | 0 | 0 | PASS | production_plan: columns, required, types, patterns, enums, ranges |
| `pk:production_plan` | primary_key | 14,821 | 0 | 0 | 0 | PASS | production_plan.production_plan_id unique and not null |
| `duplicate:production_plan` | duplicate | 14,821 | 0 | 0 | 0 | PASS | production_plan natural key ['sku_id', 'location_id', 'week_id'] unique |
| `fk:production_plan.sku_id->sku` | foreign_key | 14,821 | 0 | 0 | 0 | PASS | production_plan(sku_id) -> sku |
| `fk:production_plan.location_id->location` | foreign_key | 14,821 | 0 | 0 | 0 | PASS | production_plan(location_id) -> location |
| `fk:production_plan.week_id->calendar_week` | foreign_key | 14,821 | 0 | 0 | 0 | PASS | production_plan(week_id) -> calendar_week |
| `fk:production_plan.sku_id+location_id->sku_location` | foreign_key | 14,821 | 0 | 0 | 0 | PASS | production_plan(sku_id, location_id) -> sku_location |
| `schema:sku_substitute` | schema | 144 | 0 | 0 | 0 | PASS | sku_substitute: columns, required, types, patterns, enums, ranges |
| `pk:sku_substitute` | primary_key | 144 | 0 | 0 | 0 | PASS | sku_substitute.substitution_id unique and not null |
| `duplicate:sku_substitute` | duplicate | 144 | 0 | 0 | 0 | PASS | sku_substitute natural key ['sku_id', 'substitute_sku_id'] unique |
| `fk:sku_substitute.sku_id->sku` | foreign_key | 144 | 0 | 0 | 0 | PASS | sku_substitute(sku_id) -> sku |
| `fk:sku_substitute.substitute_sku_id->sku` | foreign_key | 144 | 0 | 0 | 0 | PASS | sku_substitute(substitute_sku_id) -> sku |
| `schema:scheduled_receipt` | schema | 44,969 | 0 | 0 | 0 | PASS | scheduled_receipt: columns, required, types, patterns, enums, ranges |
| `pk:scheduled_receipt` | primary_key | 44,969 | 0 | 0 | 0 | PASS | scheduled_receipt.po_line_id unique and not null |
| `fk:scheduled_receipt.po_line_id->purchase_order_line` | foreign_key | 44,969 | 0 | 0 | 0 | PASS | scheduled_receipt(po_line_id) -> purchase_order_line |
| `fk:scheduled_receipt.po_id->purchase_order` | foreign_key | 44,969 | 0 | 0 | 0 | PASS | scheduled_receipt(po_id) -> purchase_order |
| `schema:projected_balance` | schema | 218,764 | 0 | 0 | 0 | PASS | projected_balance: columns, required, types, patterns, enums, ranges |
| `pk:projected_balance` | primary_key | 218,764 | 0 | 0 | 0 | PASS | projected_balance.pab_id unique and not null |
| `duplicate:projected_balance` | duplicate | 218,764 | 0 | 0 | 0 | PASS | projected_balance natural key ['sku_id', 'location_id', 'week_id'] unique |
| `fk:projected_balance.sku_id+location_id->sku_location` | foreign_key | 218,764 | 0 | 0 | 0 | PASS | projected_balance(sku_id, location_id) -> sku_location |
| `fk:projected_balance.week_id->calendar_week` | foreign_key | 218,764 | 0 | 0 | 0 | PASS | projected_balance(week_id) -> calendar_week |
| `schema:shortage` | schema | 3,025 | 0 | 0 | 0 | PASS | shortage: columns, required, types, patterns, enums, ranges |
| `pk:shortage` | primary_key | 3,025 | 0 | 0 | 0 | PASS | shortage.shortage_id unique and not null |
| `fk:shortage.sku_id+location_id->sku_location` | foreign_key | 3,025 | 0 | 0 | 0 | PASS | shortage(sku_id, location_id) -> sku_location |
| `schema:shortage_cause` | schema | 5,597 | 0 | 0 | 0 | PASS | shortage_cause: columns, required, types, patterns, enums, ranges |
| `pk:shortage_cause` | primary_key | 5,597 | 0 | 0 | 0 | PASS | shortage_cause.shortage_cause_id unique and not null |
| `duplicate:shortage_cause` | duplicate | 5,597 | 0 | 0 | 0 | PASS | shortage_cause natural key ['shortage_id', 'cause_seq'] unique |
| `fk:shortage_cause.shortage_id->shortage` | foreign_key | 5,597 | 0 | 0 | 0 | PASS | shortage_cause(shortage_id) -> shortage |
| `schema:mitigation_option` | schema | 9,046 | 0 | 0 | 0 | PASS | mitigation_option: columns, required, types, patterns, enums, ranges |
| `pk:mitigation_option` | primary_key | 9,046 | 0 | 0 | 0 | PASS | mitigation_option.mitigation_id unique and not null |
| `fk:mitigation_option.shortage_id->shortage` | foreign_key | 9,046 | 0 | 0 | 0 | PASS | mitigation_option(shortage_id) -> shortage |
| `fk:mitigation_option.supplier_id->supplier` | foreign_key | 9,046 | 0 | 0 | 0 | PASS | mitigation_option(supplier_id) -> supplier |
| `fk:mitigation_option.po_id->purchase_order` | foreign_key | 9,046 | 0 | 0 | 0 | PASS | mitigation_option(po_id) -> purchase_order |
| `fk:mitigation_option.source_location_id->location` | foreign_key | 9,046 | 0 | 0 | 0 | PASS | mitigation_option(source_location_id) -> location |
| `fk:mitigation_option.substitute_sku_id->sku` | foreign_key | 9,046 | 0 | 0 | 0 | PASS | mitigation_option(substitute_sku_id) -> sku |
| `fk:mitigation_option.substitution_id->sku_substitute` | foreign_key | 9,046 | 0 | 0 | 0 | PASS | mitigation_option(substitution_id) -> sku_substitute |
| `schema:rejected_mitigation` | schema | 1,565 | 0 | 0 | 0 | PASS | rejected_mitigation: columns, required, types, patterns, enums, ranges |
| `pk:rejected_mitigation` | primary_key | 1,565 | 0 | 0 | 0 | PASS | rejected_mitigation.rejection_id unique and not null |
| `fk:rejected_mitigation.shortage_id->shortage` | foreign_key | 1,565 | 0 | 0 | 0 | PASS | rejected_mitigation(shortage_id) -> shortage |
| `schema:detected_issue` | schema | 323 | 0 | 0 | 0 | PASS | detected_issue: columns, required, types, patterns, enums, ranges |
| `pk:detected_issue` | primary_key | 323 | 0 | 0 | 0 | PASS | detected_issue.issue_id unique and not null |
| `schema:supplier_capacity_utilization` | schema | 26,000 | 0 | 0 | 0 | PASS | supplier_capacity_utilization: columns, required, types, patterns, enums, ranges |
| `pk:supplier_capacity_utilization` | primary_key | 26,000 | 0 | 0 | 0 | PASS | supplier_capacity_utilization.supplier_capacity_id unique and not null |
| `fk:supplier_capacity_utilization.supplier_capacity_id->supplier_capacity` | foreign_key | 26,000 | 0 | 0 | 0 | PASS | supplier_capacity_utilization(supplier_capacity_id) -> supplier_capacity |
| `schema:production_capacity_utilization` | schema | 260 | 0 | 0 | 0 | PASS | production_capacity_utilization: columns, required, types, patterns, enums, ranges |
| `pk:production_capacity_utilization` | primary_key | 260 | 0 | 0 | 0 | PASS | production_capacity_utilization.production_capacity_id unique and not null |
| `fk:production_capacity_utilization.production_capacity_id->production_capacity` | foreign_key | 260 | 0 | 0 | 0 | PASS | production_capacity_utilization(production_capacity_id) -> production_capacity |
| `date:calendar` | date_ordering | 52 | 0 | 0 | 0 | PASS | calendar weeks consecutive, end = start + 6 |
| `lifecycle:sku` | lifecycle | 3,000 | 0 | 0 | 0 | PASS | PHASE_OUT iff effective_to; effective_to >= effective_from; NEW starts in horizon |
| `date:demand_in_sku_window` | date_ordering | 170,933 | 0 | 0 | 0 | PASS | forecast weeks inside SKU effective window; FG only; uom = base_uom |
| `arithmetic:lead_time` | arithmetic | 2,658 | 0 | 0 | 0 | PASS | total = production + transit; expedite <= transit; versions contiguous |
| `date:purchase_order` | date_ordering | 10,030 | 0 | 0 | 0 | PASS | order <= ship <= promised; expected = promised + delay; actual iff RECEIVED and < as-of |
| `arithmetic:po_lead_time` | arithmetic | 10,030 | 10 | 10 | 0 | PASS_WITH_LABELLED_EXCEPTIONS | PO uses the lane version effective at order_date; ship = order + production lead; promised = order + total lead |
| `arithmetic:po_line` | arithmetic | 54,955 | 0 | 0 | 0 | PASS | base_qty = order_qty * factor; line_value = base_qty * unit_cost; order_qty <= requested; MOQ and multiple |
| `uom:po_line` | uom | 54,955 | 10 | 10 | 0 | PASS_WITH_LABELLED_EXCEPTIONS | order UoM and factor agree with supplier terms / SKU master |
| `cross:po_line_terms` | cross_entity | 54,955 | 0 | 0 | 0 | PASS | line supplier_sku belongs to the PO supplier and the line SKU |
| `arithmetic:po_totals` | arithmetic | 10,030 | 0 | 0 | 0 | PASS | header line_count / total_base_qty / total_value = sum of lines |
| `lifecycle:po_events` | lifecycle | 10,030 | 0 | 0 | 0 | PASS | events start with CREATED, allowed transitions, chained statuses, increasing timestamps < as-of, status = last event, delay = sum of delays |
| `policy:on_hold_supplier` | policy | 10,030 | 0 | 0 | 0 | PASS | no open PO to an ON_HOLD supplier |
| `capacity:supplier_source` | capacity | 26,000 | 10 | 10 | 0 | PASS_WITH_LABELLED_EXCEPTIONS | sum(open PO base_qty by supplier ship week) <= capacity_units |
| `capacity:production` | capacity | 14,821 | 0 | 0 | 0 | PASS | production: planned <= required, multiple of batch, plant total <= capacity |
| `cross:bom` | cross_entity | 955 | 0 | 0 | 0 | PASS | BOM parent is MAKE, component is COMPONENT, uom = component base |
| `policy:substitute_approval` | policy | 144 | 10 | 10 | 0 | PASS_WITH_LABELLED_EXCEPTIONS | substitute links are APPROVED (with approver + date); not self; same base UoM |
| `derived:primary_supplier` | derived | 4,207 | 0 | 0 | 0 | PASS | sku_location.primary_supplier_id = supplier_sku priority 1 |
| `derived:abc_class` | derived | 3,000 | 0 | 0 | 0 | PASS | abc_class recomputed from annual demand value (Pareto 80/15/5) |
| `derived:safety_stock` | derived | 4,207 | 0 | 0 | 0 | PASS | safety_stock_qty = ceil(z(ABC) * 0.3 * mean weekly demand * sqrt(LT weeks)) |
| `duplicate:inventory_in_transit` | duplicate | 5,613 | 10 | 10 | 0 | PASS_WITH_LABELLED_EXCEPTIONS | at most one IN_TRANSIT row per PO line; one ON_HAND row per SKU-location |
| `duplicate:exact_rows` | duplicate | 313,992 | 10 | 10 | 0 | PASS_WITH_LABELLED_EXCEPTIONS | no two input rows identical apart from their primary key |
| `cross:inventory` | cross_entity | 5,613 | 0 | 0 | 0 | PASS | snapshot = as-of; uom = base; IN_TRANSIT rows reference an IN_TRANSIT PO line for the same SKU and location |
| `leakage:ground_truth` | leakage | 17 | 0 | 0 | 0 | PASS | no label columns in inputs; ground truth not stored with inputs |
| `reconciliation:pab_weekly` | reconciliation | 218,764 | 0 | 0 | 0 | PASS | closing = opening + receipts + production - demand - dependent; opening(w) = closing(w-1); flags consistent |
| `reconciliation:pab_sources` | reconciliation | 218,764 | 0 | 0 | 0 | PASS | PAB inputs reconcile to inventory, forecast, production, BOM explosion and counted scheduled receipts |
| `reconciliation:scheduled_receipt` | reconciliation | 44,969 | 0 | 0 | 0 | PASS | counted receipts are open PO lines; unadjusted lines keep source qty/date |
| `reconciliation:shortage` | reconciliation | 3,025 | 0 | 0 | 0 | PASS | shortages = maximal runs of negative PAB; qty = peak deficit; ranks unique |
| `explainability:shortage_causes` | explainability | 3,025 | 0 | 0 | 0 | PASS | every shortage has >= 1 cause; contributions <= shortage qty; primary cause = cause 1 or DEMAND_EXCEEDS_SUPPLY |
| `policy:mitigation` | policy | 9,046 | 0 | 0 | 0 | PASS | options respect approval, supplier status, MOQ/multiple, lead time, arrival before shortage end; covered/residual/fill reconcile; one recommended per shortage |
| `explainability:tradeoffs` | explainability | 3,025 | 0 | 0 | 0 | PASS | every shortage shows >= 2 alternatives with cost and service metrics, or backorder plus logged rejections explaining why nothing else is feasible |
| `capacity:mitigation_supplier` | capacity | 26,000 | 0 | 0 | 0 | PASS | planned load + mitigation reservations <= supplier capacity; reservations = recommended new-PO quantities |
| `capacity:mitigation_plant` | capacity | 260 | 0 | 0 | 0 | PASS | planned production + reservations <= plant capacity |
| `capacity:mitigation_stock` | capacity | 3,025 | 0 | 0 | 0 | PASS | transfers and substitutes never take a source below safety stock |
| `fk:sqlite_enforced` | foreign_key | 623,541 | 0 | 0 | 0 | PASS | load all tables into SQLite and run PRAGMA foreign_key_check |

## Violations

| Check | Table | Record | Classification | Detail |
|---|---|---|---|---|
| `arithmetic:po_lead_time` | purchase_order | `PO-2026-010011` | EXPECTED_LABELLED | lane_ok=True effective_ok=True ship_ok=False promised_ok=False |
| `arithmetic:po_lead_time` | purchase_order | `PO-2026-010012` | EXPECTED_LABELLED | lane_ok=True effective_ok=True ship_ok=False promised_ok=False |
| `arithmetic:po_lead_time` | purchase_order | `PO-2026-010013` | EXPECTED_LABELLED | lane_ok=True effective_ok=True ship_ok=False promised_ok=False |
| `arithmetic:po_lead_time` | purchase_order | `PO-2026-010014` | EXPECTED_LABELLED | lane_ok=True effective_ok=True ship_ok=False promised_ok=False |
| `arithmetic:po_lead_time` | purchase_order | `PO-2026-010015` | EXPECTED_LABELLED | lane_ok=True effective_ok=True ship_ok=False promised_ok=False |
| `arithmetic:po_lead_time` | purchase_order | `PO-2026-010016` | EXPECTED_LABELLED | lane_ok=True effective_ok=True ship_ok=False promised_ok=False |
| `arithmetic:po_lead_time` | purchase_order | `PO-2026-010017` | EXPECTED_LABELLED | lane_ok=True effective_ok=True ship_ok=False promised_ok=False |
| `arithmetic:po_lead_time` | purchase_order | `PO-2026-010018` | EXPECTED_LABELLED | lane_ok=True effective_ok=True ship_ok=False promised_ok=False |
| `arithmetic:po_lead_time` | purchase_order | `PO-2026-010019` | EXPECTED_LABELLED | lane_ok=True effective_ok=True ship_ok=False promised_ok=False |
| `arithmetic:po_lead_time` | purchase_order | `PO-2026-010020` | EXPECTED_LABELLED | lane_ok=True effective_ok=True ship_ok=False promised_ok=False |
| `uom:po_line` | purchase_order_line | `PO-2026-010021-L01` | EXPECTED_LABELLED | 14 CS x 1.0 vs master factor 12.0 |
| `uom:po_line` | purchase_order_line | `PO-2026-010022-L01` | EXPECTED_LABELLED | 1 KG x 1.0 vs master factor nan |
| `uom:po_line` | purchase_order_line | `PO-2026-010023-L01` | EXPECTED_LABELLED | 2 CS x 1.0 vs master factor 12.0 |
| `uom:po_line` | purchase_order_line | `PO-2026-010024-L01` | EXPECTED_LABELLED | 4 KG x 1.0 vs master factor nan |
| `uom:po_line` | purchase_order_line | `PO-2026-010025-L01` | EXPECTED_LABELLED | 1 CS x 1.0 vs master factor 12.0 |
| `uom:po_line` | purchase_order_line | `PO-2026-010026-L01` | EXPECTED_LABELLED | 50 KG x 1.0 vs master factor nan |
| `uom:po_line` | purchase_order_line | `PO-2026-010027-L01` | EXPECTED_LABELLED | 2 CS x 1.0 vs master factor 6.0 |
| `uom:po_line` | purchase_order_line | `PO-2026-010028-L01` | EXPECTED_LABELLED | 1 KG x 1.0 vs master factor nan |
| `uom:po_line` | purchase_order_line | `PO-2026-010029-L01` | EXPECTED_LABELLED | 1 CS x 1.0 vs master factor 12.0 |
| `uom:po_line` | purchase_order_line | `PO-2026-010030-L01` | EXPECTED_LABELLED | 1 KG x 1.0 vs master factor nan |
| `capacity:supplier_source` | supplier_capacity | `SCAP-SUP-0071-2026W16` | EXPECTED_LABELLED | committed 2370 > capacity 1820 |
| `capacity:supplier_source` | supplier_capacity | `SCAP-SUP-0136-2026W05` | EXPECTED_LABELLED | committed 1729 > capacity 1330 |
| `capacity:supplier_source` | supplier_capacity | `SCAP-SUP-0150-2026W39` | EXPECTED_LABELLED | committed 1392 > capacity 1070 |
| `capacity:supplier_source` | supplier_capacity | `SCAP-SUP-0181-2026W45` | EXPECTED_LABELLED | committed 3731 > capacity 2870 |
| `capacity:supplier_source` | supplier_capacity | `SCAP-SUP-0213-2026W12` | EXPECTED_LABELLED | committed 1222 > capacity 940 |
| `capacity:supplier_source` | supplier_capacity | `SCAP-SUP-0220-2026W17` | EXPECTED_LABELLED | committed 270 > capacity 190 |
| `capacity:supplier_source` | supplier_capacity | `SCAP-SUP-0234-2026W34` | EXPECTED_LABELLED | committed 360 > capacity 260 |
| `capacity:supplier_source` | supplier_capacity | `SCAP-SUP-0264-2026W35` | EXPECTED_LABELLED | committed 1188 > capacity 910 |
| `capacity:supplier_source` | supplier_capacity | `SCAP-SUP-0299-2026W43` | EXPECTED_LABELLED | committed 684 > capacity 520 |
| `capacity:supplier_source` | supplier_capacity | `SCAP-SUP-0457-2026W26` | EXPECTED_LABELLED | committed 672 > capacity 510 |
| `policy:substitute_approval` | sku_substitute | `SUB-000135` | EXPECTED_LABELLED | substitute link is PENDING |
| `policy:substitute_approval` | sku_substitute | `SUB-000136` | EXPECTED_LABELLED | substitute link is REJECTED |
| `policy:substitute_approval` | sku_substitute | `SUB-000137` | EXPECTED_LABELLED | substitute link is PENDING |
| `policy:substitute_approval` | sku_substitute | `SUB-000138` | EXPECTED_LABELLED | substitute link is REJECTED |
| `policy:substitute_approval` | sku_substitute | `SUB-000139` | EXPECTED_LABELLED | substitute link is PENDING |
| `policy:substitute_approval` | sku_substitute | `SUB-000140` | EXPECTED_LABELLED | substitute link is REJECTED |
| `policy:substitute_approval` | sku_substitute | `SUB-000141` | EXPECTED_LABELLED | substitute link is PENDING |
| `policy:substitute_approval` | sku_substitute | `SUB-000142` | EXPECTED_LABELLED | substitute link is REJECTED |
| `policy:substitute_approval` | sku_substitute | `SUB-000143` | EXPECTED_LABELLED | substitute link is PENDING |
| `policy:substitute_approval` | sku_substitute | `SUB-000144` | EXPECTED_LABELLED | substitute link is REJECTED |
| `duplicate:inventory_in_transit` | inventory | `INV-005604` | EXPECTED_LABELLED | PO line already has an in-transit record (inbound counted twice) |
| `duplicate:inventory_in_transit` | inventory | `INV-005605` | EXPECTED_LABELLED | PO line already has an in-transit record (inbound counted twice) |
| `duplicate:inventory_in_transit` | inventory | `INV-005606` | EXPECTED_LABELLED | PO line already has an in-transit record (inbound counted twice) |
| `duplicate:inventory_in_transit` | inventory | `INV-005607` | EXPECTED_LABELLED | PO line already has an in-transit record (inbound counted twice) |
| `duplicate:inventory_in_transit` | inventory | `INV-005608` | EXPECTED_LABELLED | PO line already has an in-transit record (inbound counted twice) |
| `duplicate:inventory_in_transit` | inventory | `INV-005609` | EXPECTED_LABELLED | PO line already has an in-transit record (inbound counted twice) |
| `duplicate:inventory_in_transit` | inventory | `INV-005610` | EXPECTED_LABELLED | PO line already has an in-transit record (inbound counted twice) |
| `duplicate:inventory_in_transit` | inventory | `INV-005611` | EXPECTED_LABELLED | PO line already has an in-transit record (inbound counted twice) |
| `duplicate:inventory_in_transit` | inventory | `INV-005612` | EXPECTED_LABELLED | PO line already has an in-transit record (inbound counted twice) |
| `duplicate:inventory_in_transit` | inventory | `INV-005613` | EXPECTED_LABELLED | PO line already has an in-transit record (inbound counted twice) |
| `duplicate:exact_rows` | inventory | `INV-005604` | EXPECTED_LABELLED | row duplicates another record |
| `duplicate:exact_rows` | inventory | `INV-005605` | EXPECTED_LABELLED | row duplicates another record |
| `duplicate:exact_rows` | inventory | `INV-005606` | EXPECTED_LABELLED | row duplicates another record |
| `duplicate:exact_rows` | inventory | `INV-005607` | EXPECTED_LABELLED | row duplicates another record |
| `duplicate:exact_rows` | inventory | `INV-005608` | EXPECTED_LABELLED | row duplicates another record |
| `duplicate:exact_rows` | inventory | `INV-005609` | EXPECTED_LABELLED | row duplicates another record |
| `duplicate:exact_rows` | inventory | `INV-005610` | EXPECTED_LABELLED | row duplicates another record |
| `duplicate:exact_rows` | inventory | `INV-005611` | EXPECTED_LABELLED | row duplicates another record |
| `duplicate:exact_rows` | inventory | `INV-005612` | EXPECTED_LABELLED | row duplicates another record |
| `duplicate:exact_rows` | inventory | `INV-005613` | EXPECTED_LABELLED | row duplicates another record |
