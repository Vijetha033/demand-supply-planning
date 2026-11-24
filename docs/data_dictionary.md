# Data dictionary

Generated from `src/supply_planning/schema.py` (single source of truth used by the generator, validator and SQL exporter). Regenerate with `python -m supply_planning docs`.

Conventions: dates are ISO-8601 `YYYY-MM-DD`; timestamps `YYYY-MM-DDTHH:MM:SS`; quantities are in the SKU base unit unless the unit column says otherwise; money is USD; booleans are `True/False`.

## Input (source) tables

### `calendar_week` - Calendar (supporting)

ISO planning weeks of the plan year. Week index 0 starts on the planning as-of date.

- **Grain:** one row per planning week
- **Primary key:** `week_id`

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `week_id` (PK) | string | yes | yes |  |  | pattern `^\d{4}W\d{2}$` | ISO week identifier |
| `week_index` | integer | yes | yes |  |  | >= 0 | 0-based week offset from the as-of date |
| `week_start_date` | date | yes | yes |  |  | ISO-8601 date YYYY-MM-DD | Monday of the ISO week |
| `week_end_date` | date | yes | no |  |  | = week_start_date + 6 days | Sunday of the ISO week |
| `is_holiday_week` | boolean | yes | no |  |  |  | Reduced supplier/plant capacity week |

### `location` - Location

Plants (production + stocking) and distribution centres.

- **Grain:** one row per location
- **Primary key:** `location_id`
- **Lifecycle:** ACTIVE (all synthetic locations are active in the horizon)

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `location_id` (PK) | string | yes | yes |  |  | pattern `^LOC-\d{3}$` | Location identifier |
| `location_name` | string | yes | yes |  |  |  | Synthetic display name |
| `location_type` | string | yes | no | PLANT, DC |  |  | Plant or distribution centre |
| `region` | string | yes | no | NORTH, SOUTH, EAST, WEST, CENTRAL |  |  | Planning region |
| `status` | string | yes | no | ACTIVE |  |  | Lifecycle status |
| `effective_from` | date | yes | no |  |  | ISO-8601 date YYYY-MM-DD | Date the location became active |

### `supplier` - Supplier

External suppliers. Capacity is in supplier_capacity; lanes and lead times in lead_time.

- **Grain:** one row per supplier
- **Primary key:** `supplier_id`
- **Lifecycle:** ACTIVE -> ON_HOLD (policy: no new POs while ON_HOLD)

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `supplier_id` (PK) | string | yes | yes |  |  | pattern `^SUP-\d{4}$` | Supplier identifier |
| `supplier_name` | string | yes | yes |  |  |  | Synthetic display name |
| `region` | string | yes | no | NORTH, SOUTH, EAST, WEST, CENTRAL |  |  | Home region |
| `is_overseas` | boolean | yes | no |  |  |  | Ships by sea from outside the network |
| `supplier_tier` | string | yes | no | STRATEGIC, PREFERRED, APPROVED |  |  | Commercial tier |
| `supplier_role` | string | yes | no | FINISHED_GOODS, COMPONENTS |  |  | What the supplier provides |
| `reliability_pct` | decimal | yes | no |  | percent | >= 0; <= 100 | Historical on-time delivery |
| `status` | string | yes | no | ACTIVE, ON_HOLD |  |  | ON_HOLD suppliers may not receive new purchase orders |
| `effective_from` | date | yes | no |  |  | ISO-8601 date YYYY-MM-DD | Onboarding date |

### `sku` - SKU

Stock-keeping units: purchased finished goods, manufactured finished goods and purchased components.

- **Grain:** one row per SKU
- **Primary key:** `sku_id`
- **Lifecycle:** NEW -> ACTIVE -> PHASE_OUT; no demand outside [effective_from, effective_to]

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `sku_id` (PK) | string | yes | yes |  |  | pattern `^SKU-\d{6}$` | SKU identifier |
| `sku_name` | string | yes | yes |  |  |  | Synthetic display name |
| `category` | string | yes | no | ELECTRONICS, HOME_GOODS, PERSONAL_CARE, FOOD_BEVERAGE, APPAREL, HARDWARE, RAW_MATERIAL, PACKAGING, PARTS |  |  | Product category |
| `item_type` | string | yes | no | FINISHED_GOOD, COMPONENT |  |  | Finished good or BOM component |
| `sourcing_type` | string | yes | no | BUY, MAKE |  | COMPONENT => BUY | BUY from suppliers or MAKE in a plant |
| `base_uom` | string | yes | no | EA, KG, L |  |  | Base (stocking) unit of measure |
| `units_per_case` | integer | yes | no |  |  | >= 1 | Base units in one case (CS) |
| `unit_cost` | decimal | yes | no |  | USD | >= 0.01 | Standard cost per base unit |
| `unit_price` | decimal | no | no |  | USD | required for FINISHED_GOOD; > unit_cost | Selling price per base unit (finished goods only) |
| `abc_class` | string | yes | no | A, B, C |  |  | Derived Pareto class on annual demand value (A=80%, B=15%, C=5%) |
| `lifecycle_status` | string | yes | no | NEW, ACTIVE, PHASE_OUT |  |  | Product lifecycle |
| `effective_from` | date | yes | no |  |  | ISO-8601 date YYYY-MM-DD | First date the SKU can be sold/planned |
| `effective_to` | date | no | no |  |  | required iff lifecycle_status = PHASE_OUT; >= effective_from | Last date (PHASE_OUT only) |

### `sku_location` - SKU-Location (bridge)

Bridge resolving the N:M SKU<->Location relationship; holds stocking policy.

- **Grain:** one row per stocked SKU at a location
- **Primary key:** `sku_location_id`
- **Natural key (unique):** `sku_id, location_id`
- **FK** `sku_id` -> `sku(sku_id)` N:1
- **FK** `location_id` -> `location(location_id)` N:1
- **FK** `primary_supplier_id` -> `supplier(supplier_id)` N:1 (optional)

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `sku_location_id` (PK) | string | yes | yes |  |  | pattern `^SL-\d{6}$` | Bridge identifier |
| `sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | Stocked SKU |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$` | Stocking location |
| `planning_method` | string | yes | no | PURCHASE, PRODUCTION, DEPENDENT_PURCHASE |  |  | How supply is planned |
| `primary_supplier_id` | string | no | no |  |  | pattern `^SUP-\d{4}$`; required iff planning_method in (PURCHASE, DEPENDENT_PURCHASE) | Primary supplier for purchased items |
| `safety_stock_qty` | integer | yes | no |  | base_uom | >= 0 | Derived: ceil(z(ABC) * 0.3 * mean weekly demand * sqrt(lead-time weeks)) |
| `effective_from` | date | yes | no |  |  | ISO-8601 date YYYY-MM-DD | Start of stocking |

### `supplier_sku` - Supplier-SKU (bridge)

Bridge resolving N:M Supplier<->SKU; purchasing terms (UoM, MOQ, multiple, price).

- **Grain:** one row per supplier offering a SKU
- **Primary key:** `supplier_sku_id`
- **Natural key (unique):** `supplier_id, sku_id`
- **FK** `supplier_id` -> `supplier(supplier_id)` N:1
- **FK** `sku_id` -> `sku(sku_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `supplier_sku_id` (PK) | string | yes | yes |  |  | pattern `^SS-\d{6}$` | Bridge identifier |
| `supplier_id` | string | yes | no |  |  | pattern `^SUP-\d{4}$` | Supplier |
| `sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | SKU |
| `supplier_priority` | integer | yes | no |  |  | >= 1 | 1 = primary, 2+ = alternate |
| `purchase_uom` | string | yes | no | EA, CS, KG, L |  |  | Unit the supplier sells in |
| `uom_conversion_factor` | decimal | yes | no |  | base_uom/purchase_uom | >= 0.0001; CS => sku.units_per_case; same-as-base => 1 | Base units per purchase unit |
| `min_order_qty` | integer | yes | no |  | purchase_uom | >= 1 | Minimum order quantity (MOQ) |
| `order_multiple` | integer | yes | no |  | purchase_uom | >= 1 | Order quantity must be a multiple of this |
| `unit_cost` | decimal | yes | no |  | USD | >= 0.01 | Price per base unit |
| `approval_status` | string | yes | no | APPROVED |  |  | Sourcing approval |
| `effective_from` | date | yes | no |  |  | ISO-8601 date YYYY-MM-DD | Start of agreement |
| `effective_to` | date | no | no |  |  | >= effective_from | End of agreement |

### `lead_time` - LeadTime

Effective-dated lead time per supplier->location lane. Revisions add a new version; history is kept.

- **Grain:** one row per lane per version
- **Primary key:** `lead_time_id`
- **Natural key (unique):** `supplier_id, location_id, version`
- **FK** `supplier_id` -> `supplier(supplier_id)` N:1
- **FK** `location_id` -> `location(location_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `lead_time_id` (PK) | string | yes | yes |  |  | pattern `^LT-\d{6}$` | Lead-time version identifier |
| `supplier_id` | string | yes | no |  |  | pattern `^SUP-\d{4}$` | Shipping supplier |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$` | Receiving location |
| `version` | integer | yes | no |  |  | >= 1 | Version number within the lane (1 = original) |
| `transport_mode` | string | yes | no | ROAD, RAIL, SEA, AIR |  |  | Standard mode |
| `production_lead_days` | integer | yes | no |  | days | >= 0 | Order -> ship |
| `transit_days` | integer | yes | no |  | days | >= 1 | Ship -> receipt |
| `total_lead_days` | integer | yes | no |  | days | >= 1 | Derived: production_lead_days + transit_days |
| `expedite_transit_days` | integer | yes | no |  | days | >= 1; <= transit_days | Transit if expedited (air/priority) |
| `expedite_premium_pct` | decimal | yes | no |  | percent | >= 0 | Expedite surcharge as % of line value |
| `effective_from` | date | yes | no |  |  | ISO-8601 date YYYY-MM-DD | Version start |
| `effective_to` | date | no | no |  |  | versions of a lane do not overlap; v(n).effective_to = v(n+1).effective_from - 1 day | Version end (null = open) |

### `supplier_capacity` - SupplierCapacity

Weekly shipping capacity per supplier across all SKUs, in base units, measured on PO ship week.

- **Grain:** one row per supplier per planning week
- **Primary key:** `supplier_capacity_id`
- **Natural key (unique):** `supplier_id, week_id`
- **FK** `supplier_id` -> `supplier(supplier_id)` N:1
- **FK** `week_id` -> `calendar_week(week_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `supplier_capacity_id` (PK) | string | yes | yes |  |  | pattern `^SCAP-SUP-\d{4}-\d{4}W\d{2}$` | Capacity identifier |
| `supplier_id` | string | yes | no |  |  | pattern `^SUP-\d{4}$` | Supplier |
| `week_id` | string | yes | no |  |  | pattern `^\d{4}W\d{2}$` | Planning week |
| `capacity_units` | integer | yes | no |  | base units | >= 0 | Maximum base units the supplier can ship in the week |

### `forecast_demand` - ForecastDemand

Independent weekly forecast demand per SKU-location (finished goods only).

- **Grain:** one row per SKU, location and week within the SKU's effective window
- **Primary key:** `demand_id`
- **Natural key (unique):** `sku_id, location_id, week_id`
- **FK** `sku_id` -> `sku(sku_id)` N:1
- **FK** `location_id` -> `location(location_id)` N:1
- **FK** `week_id` -> `calendar_week(week_id)` N:1
- **FK** `sku_id, location_id` -> `sku_location(sku_id, location_id)` N:1 - demand only for stocked SKU-locations

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `demand_id` (PK) | string | yes | yes |  |  | pattern `^DEM-SKU-\d{6}-LOC-\d{3}-\d{4}W\d{2}$` | DEM-<sku>-<location>-<week> |
| `sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | SKU |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$` | Location |
| `week_id` | string | yes | no |  |  | pattern `^\d{4}W\d{2}$` | Planning week |
| `forecast_qty` | integer | yes | no |  | base_uom | >= 0 | Forecast quantity |
| `uom` | string | yes | no | EA, KG, L |  |  | Must equal sku.base_uom |
| `forecast_version` | string | yes | no | FV-2026-01 |  |  | Forecast release |

### `inventory` - Inventory

Inventory snapshot at the as-of date: on-hand, quality hold and in-transit (linked to the PO line).

- **Grain:** one row per SKU-location-stock status (in-transit: per PO line)
- **Primary key:** `inventory_id`
- **FK** `sku_id` -> `sku(sku_id)` N:1
- **FK** `location_id` -> `location(location_id)` N:1
- **FK** `po_line_id` -> `purchase_order_line(po_line_id)` N:1 (optional)
- **FK** `sku_id, location_id` -> `sku_location(sku_id, location_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `inventory_id` (PK) | string | yes | yes |  |  | pattern `^INV-\d{6}$` | Inventory record identifier |
| `sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | SKU |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$` | Location |
| `snapshot_date` | date | yes | no |  |  | = planning as-of date | As-of date of the snapshot |
| `stock_status` | string | yes | no | ON_HAND, IN_TRANSIT, QUALITY_HOLD |  |  | Availability status |
| `quantity` | integer | yes | no |  | base_uom | >= 0 | Quantity |
| `uom` | string | yes | no | EA, KG, L |  |  | Must equal sku.base_uom |
| `po_line_id` | string | no | no |  |  | pattern `^PO-\d{4}-\d{6}-L\d{2}$`; required iff stock_status = IN_TRANSIT; at most one IN_TRANSIT row per PO line | Inbound PO line (IN_TRANSIT only) |

### `purchase_order` - PurchaseOrder

Inbound purchase order header (one supplier -> one receiving location). Status is derived from events.

- **Grain:** one row per purchase order
- **Primary key:** `po_id`
- **FK** `supplier_id` -> `supplier(supplier_id)` N:1
- **FK** `location_id` -> `location(location_id)` N:1
- **FK** `lead_time_id` -> `lead_time(lead_time_id)` N:1
- **Lifecycle:** PLANNED -> CONFIRMED -> IN_TRANSIT -> RECEIVED; PLANNED|CONFIRMED -> CANCELLED

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `po_id` (PK) | string | yes | yes |  |  | pattern `^PO-\d{4}-\d{6}$` | PO-<year>-<counter> |
| `supplier_id` | string | yes | no |  |  | pattern `^SUP-\d{4}$` | Supplier |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$` | Receiving location |
| `lead_time_id` | string | yes | no |  |  | pattern `^LT-\d{6}$` | Lead-time version effective at order_date |
| `order_date` | date | yes | no |  |  | ISO-8601 date YYYY-MM-DD | Date the order is (or will be) released to the supplier |
| `ship_date` | date | yes | no |  |  | >= order_date | Planned ship date = order_date + production_lead_days |
| `promised_receipt_date` | date | yes | no |  |  | >= ship_date | order_date + total_lead_days of lead_time_id |
| `transport_delay_days` | integer | yes | no |  | days | >= 0 | Derived: sum of DELAY_REPORTED event delays |
| `expected_receipt_date` | date | yes | no |  |  |  | Derived: promised_receipt_date + transport_delay_days |
| `actual_receipt_date` | date | no | no |  |  | required iff status = RECEIVED; < as-of date | Receipt date (RECEIVED only) |
| `status` | string | yes | no | PLANNED, CONFIRMED, IN_TRANSIT, RECEIVED, CANCELLED |  |  | Derived: to_status of the latest event |
| `line_count` | integer | yes | no |  |  | >= 1 | Derived: number of lines |
| `total_base_qty` | integer | yes | no |  | base units | >= 1 | Derived: sum(line.base_qty) |
| `total_value` | decimal | yes | no |  | USD | >= 0 | Derived: sum(line.line_value) |
| `currency` | string | yes | no | USD |  |  | Currency |
| `created_at` | datetime | yes | no |  |  |  | Timestamp of the CREATED event |

### `purchase_order_line` - PurchaseOrder line

PO line: one SKU, ordered in the supplier's purchase UoM.

- **Grain:** one row per PO line
- **Primary key:** `po_line_id`
- **Natural key (unique):** `po_id, sku_id`
- **FK** `po_id` -> `purchase_order(po_id)` N:1
- **FK** `sku_id` -> `sku(sku_id)` N:1
- **FK** `supplier_sku_id` -> `supplier_sku(supplier_sku_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `po_line_id` (PK) | string | yes | yes |  |  | pattern `^PO-\d{4}-\d{6}-L\d{2}$` | <po_id>-L<nn> |
| `po_id` | string | yes | no |  |  | pattern `^PO-\d{4}-\d{6}$` | Parent PO |
| `line_number` | integer | yes | no |  |  | >= 1 | Line number within PO |
| `sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | SKU |
| `supplier_sku_id` | string | yes | no |  |  | pattern `^SS-\d{6}$`; supplier_sku.supplier_id = purchase_order.supplier_id and supplier_sku.sku_id = sku_id | Purchasing terms used |
| `requested_qty` | integer | yes | no |  | order_uom | >= 1 | Quantity the planner requested |
| `order_qty` | integer | yes | no |  | order_uom | >= 1; <= requested_qty; >= MOQ and multiple of order_multiple | Quantity confirmed by the supplier (capacity-limited suppliers may cut it) |
| `order_uom` | string | yes | no | EA, CS, KG, L |  |  | Unit ordered in |
| `uom_conversion_factor` | decimal | yes | no |  |  | >= 0.0001 | Base units per order unit |
| `base_qty` | integer | yes | no |  | base_uom | >= 1 | Derived: order_qty * uom_conversion_factor |
| `base_uom` | string | yes | no | EA, KG, L |  |  | SKU base unit |
| `unit_cost` | decimal | yes | no |  | USD | >= 0.01 | Price per base unit |
| `line_value` | decimal | yes | no |  | USD | >= 0 | Derived: base_qty * unit_cost |

### `purchase_order_event` - PurchaseOrder event (history)

Append-only state-change history of purchase orders. History is never overwritten.

- **Grain:** one row per state change
- **Primary key:** `event_id`
- **Natural key (unique):** `po_id, event_seq`
- **FK** `po_id` -> `purchase_order(po_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `event_id` (PK) | string | yes | yes |  |  | pattern `^POE-\d{7}$` | Event identifier |
| `po_id` | string | yes | no |  |  | pattern `^PO-\d{4}-\d{6}$` | Purchase order |
| `event_seq` | integer | yes | no |  |  | >= 1 | 1-based sequence within the PO |
| `event_type` | string | yes | no | CREATED, CONFIRMED, SHIPPED, DELAY_REPORTED, RECEIVED, CANCELLED |  |  | Event |
| `from_status` | string | no | no | PLANNED, CONFIRMED, IN_TRANSIT, RECEIVED, CANCELLED |  |  | Status before (null for CREATED) |
| `to_status` | string | yes | no | PLANNED, CONFIRMED, IN_TRANSIT, RECEIVED, CANCELLED |  |  | Status after |
| `event_timestamp` | datetime | yes | no |  |  | strictly increasing per PO; < as-of date | When it happened |
| `actor` | string | yes | no | PLANNER, SUPPLIER, CARRIER, WAREHOUSE_OPERATOR, OPERATIONS_MANAGER |  |  | Who recorded it |
| `delay_days` | integer | yes | no |  | days | >= 0 | Delay reported (DELAY_REPORTED only) |
| `note` | string | no | no |  |  |  | Free text |

### `bom` - BOM (bridge)

Bill of materials: N:M bridge between manufactured SKUs and component SKUs.

- **Grain:** one row per parent-component pair
- **Primary key:** `bom_id`
- **Natural key (unique):** `parent_sku_id, component_sku_id`
- **FK** `parent_sku_id` -> `sku(sku_id)` N:1
- **FK** `component_sku_id` -> `sku(sku_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `bom_id` (PK) | string | yes | yes |  |  | pattern `^BOM-\d{6}$` | BOM line identifier |
| `parent_sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | Manufactured SKU (MAKE) |
| `component_sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | Component SKU |
| `qty_per` | decimal | yes | no |  |  | >= 0.0001 | Component base units per parent unit |
| `component_uom` | string | yes | no | EA, KG, L |  |  | Must equal component sku.base_uom |
| `effective_from` | date | yes | no |  |  | ISO-8601 date YYYY-MM-DD | Start |
| `effective_to` | date | no | no |  |  |  | End |

### `production_capacity` - Production capacity

Weekly production capacity per plant (all manufactured SKUs), in base units.

- **Grain:** one row per plant per week
- **Primary key:** `production_capacity_id`
- **Natural key (unique):** `location_id, week_id`
- **FK** `location_id` -> `location(location_id)` N:1
- **FK** `week_id` -> `calendar_week(week_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `production_capacity_id` (PK) | string | yes | yes |  |  | pattern `^PCAP-LOC-\d{3}-\d{4}W\d{2}$` | Capacity identifier |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$`; location.location_type = PLANT | Plant |
| `week_id` | string | yes | no |  |  | pattern `^\d{4}W\d{2}$` | Week |
| `capacity_units` | integer | yes | no |  | base units | >= 0 | Max units producible |

### `production_plan` - ProductionPlan

Planned production of manufactured SKUs per plant and week.

- **Grain:** one row per SKU, plant and week with production
- **Primary key:** `production_plan_id`
- **Natural key (unique):** `sku_id, location_id, week_id`
- **FK** `sku_id` -> `sku(sku_id)` N:1
- **FK** `location_id` -> `location(location_id)` N:1
- **FK** `week_id` -> `calendar_week(week_id)` N:1
- **FK** `sku_id, location_id` -> `sku_location(sku_id, location_id)` N:1
- **Lifecycle:** PLANNED -> FIRM (inside frozen fence)

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `production_plan_id` (PK) | string | yes | yes |  |  | pattern `^PP-\d{4}-\d{6}$` | PP-<year>-<counter> |
| `sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$`; sku.sourcing_type = MAKE | Manufactured SKU |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$` | Plant |
| `week_id` | string | yes | no |  |  | pattern `^\d{4}W\d{2}$` | Production week |
| `required_qty` | integer | yes | no |  | base_uom | >= 1 | Unconstrained requirement (before plant capacity) |
| `planned_qty` | integer | yes | no |  | base_uom | >= 0; <= required_qty; multiple of batch_size; plant total <= production_capacity | Capacity-constrained planned quantity |
| `batch_size` | integer | yes | no |  |  | >= 1 | Batch multiple |
| `status` | string | yes | no | FIRM, PLANNED |  |  | FIRM inside the 2-week frozen fence, else PLANNED |

### `sku_substitute` - SKU substitute (bridge)

N:M self-bridge on SKU: which SKU may replace another. Only APPROVED and effective links are usable.

- **Grain:** one row per SKU-substitute pair
- **Primary key:** `substitution_id`
- **Natural key (unique):** `sku_id, substitute_sku_id`
- **FK** `sku_id` -> `sku(sku_id)` N:1
- **FK** `substitute_sku_id` -> `sku(sku_id)` N:1
- **Lifecycle:** PENDING -> APPROVED | REJECTED

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `substitution_id` (PK) | string | yes | yes |  |  | pattern `^SUB-\d{6}$` | Substitution identifier |
| `sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | SKU being substituted |
| `substitute_sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$`; != sku_id; same base_uom | Replacement SKU |
| `conversion_ratio` | decimal | yes | no |  |  | >= 0.0001 | Substitute units per original unit |
| `approval_status` | string | yes | no | APPROVED, PENDING, REJECTED |  |  | Approval state |
| `approved_by` | string | no | no | PLANNER, OPERATIONS_MANAGER |  | required iff APPROVED | Approver role |
| `approval_date` | date | no | no |  |  | required iff APPROVED | Approval date |
| `effective_from` | date | yes | no |  |  | ISO-8601 date YYYY-MM-DD | Start |
| `effective_to` | date | no | no |  |  |  | End |
| `priority` | integer | yes | no |  |  | >= 1 | Preference order |

## Derived planning outputs

### `scheduled_receipt` - Scheduled receipt (derived)

Every open PO line as used by the plan, with any correction applied (source rows are never modified).

- **Grain:** one row per open PO line
- **Primary key:** `po_line_id`
- **FK** `po_line_id` -> `purchase_order_line(po_line_id)` 1:1
- **FK** `po_id` -> `purchase_order(po_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `po_line_id` (PK) | string | yes | yes |  |  | pattern `^PO-\d{4}-\d{6}-L\d{2}$` | PO line |
| `po_id` | string | yes | no |  |  | pattern `^PO-\d{4}-\d{6}$` | PO |
| `sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | SKU |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$` | Receiving location |
| `supplier_id` | string | yes | no |  |  | pattern `^SUP-\d{4}$` | Supplier |
| `po_status` | string | yes | no | PLANNED, CONFIRMED, IN_TRANSIT, RECEIVED, CANCELLED |  |  | PO status |
| `source_base_qty` | integer | yes | no |  |  | >= 0 | base_qty as recorded on the line |
| `planning_base_qty` | integer | yes | no |  |  | >= 0 | Quantity used in the plan after UoM correction |
| `source_receipt_date` | date | yes | no |  |  |  | expected_receipt_date as recorded |
| `planning_receipt_date` | date | yes | no |  |  |  | Receipt date used after lead-time / capacity corrections |
| `ship_week_index` | integer | no | no |  |  |  | Week index the supplier ships (capacity bucket) |
| `receipt_week_index` | integer | yes | no |  |  |  | Week index of planning receipt |
| `adjustment_codes` | string | no | no |  |  |  | Pipe-separated corrections applied |
| `counted_in_plan` | boolean | yes | no |  |  |  | False if cancelled, outside horizon or unconvertible |

### `projected_balance` - Projected available balance (derived)

Week-by-week projected available balance (PAB). closing = opening + receipts + production - demand - dependent demand.

- **Grain:** one row per SKU-location-week
- **Primary key:** `pab_id`
- **Natural key (unique):** `sku_id, location_id, week_id`
- **FK** `sku_id, location_id` -> `sku_location(sku_id, location_id)` N:1
- **FK** `week_id` -> `calendar_week(week_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `pab_id` (PK) | string | yes | yes |  |  | pattern `^PAB-SKU-\d{6}-LOC-\d{3}-\d{4}W\d{2}$` | PAB-<sku>-<location>-<week> |
| `sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | SKU |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$` | Location |
| `week_id` | string | yes | no |  |  | pattern `^\d{4}W\d{2}$` | Week |
| `week_index` | integer | yes | no |  |  | >= 0 | Week offset |
| `opening_balance` | integer | yes | no |  | base_uom |  | Previous closing (week 0: available on-hand) |
| `forecast_demand` | integer | yes | no |  | base_uom | >= 0 | Independent demand |
| `dependent_demand` | integer | yes | no |  | base_uom | >= 0 | BOM-exploded demand from production |
| `scheduled_receipts` | integer | yes | no |  | base_uom | >= 0 | Sum of counted scheduled_receipt rows |
| `planned_production` | integer | yes | no |  | base_uom | >= 0 | Sum of production_plan |
| `closing_balance` | integer | yes | no |  | base_uom |  | Projected available balance; negative = backlog |
| `safety_stock_qty` | integer | yes | no |  | base_uom | >= 0 | Safety stock |
| `below_safety_stock` | boolean | yes | no |  |  |  | closing_balance < safety_stock_qty |
| `is_shortage` | boolean | yes | no |  |  |  | closing_balance < 0 |

### `shortage` - Shortage (derived)

Shortage episode: consecutive weeks with negative projected balance for a SKU-location.

- **Grain:** one row per shortage episode
- **Primary key:** `shortage_id`
- **FK** `sku_id, location_id` -> `sku_location(sku_id, location_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `shortage_id` (PK) | string | yes | yes |  |  | pattern `^SHORT-\d{4}-\d{6}$` | SHORT-<year>-<counter>, numbered in priority order |
| `sku_id` | string | yes | no |  |  | pattern `^SKU-\d{6}$` | SKU |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$` | Location |
| `start_week_id` | string | yes | no |  |  | pattern `^\d{4}W\d{2}$` | First negative week |
| `end_week_id` | string | yes | no |  |  | pattern `^\d{4}W\d{2}$` | Last negative week |
| `start_week_index` | integer | yes | no |  |  | >= 0 |  |
| `end_week_index` | integer | yes | no |  |  | >= 0 |  |
| `duration_weeks` | integer | yes | no |  |  | >= 1 | end - start + 1 |
| `shortage_qty` | integer | yes | no |  | base_uom | >= 1 | Peak deficit = -min(closing_balance) in the episode |
| `shortage_value` | decimal | yes | no |  | USD |  | shortage_qty * unit_price (components: 2 * unit_cost) |
| `lead_time_weeks` | integer | yes | no |  |  | >= 0 | First week index a normal action can land: week of (as-of + primary lane total_lead_days) for purchased items; frozen fence (2) for manufactured items |
| `within_lead_time` | boolean | yes | no |  |  |  | start_week_index < lead_time_weeks: cannot be fixed by a normal order |
| `priority_score` | decimal | yes | no |  |  | >= 0; <= 100 | 0-100 weighted score (value, urgency, ABC, duration) |
| `priority_rank` | integer | yes | yes |  |  | >= 1 | 1 = most urgent |
| `priority_tier` | string | yes | no | CRITICAL, HIGH, MEDIUM, LOW |  |  | Tier |
| `primary_cause_code` | string | yes | no | DEMAND_EXCEEDS_SUPPLY, DEMAND_SPIKE, INSUFFICIENT_OPENING_STOCK, TRANSPORT_DELAY, SUPPLIER_CAPACITY_CONSTRAINT, PRODUCTION_CAPACITY_CONSTRAINT, DEPENDENT_DEMAND, PO_CANCELLED, LEAD_TIME_CORRECTION, UOM_CORRECTION, NO_SCHEDULED_SUPPLY |  |  | Largest-contribution cause |
| `cause_summary` | string | yes | no |  |  |  | Human-readable explanation with reconciliation arithmetic |
| `status` | string | yes | no | MITIGATION_PROPOSED, PARTIALLY_MITIGATED, UNMITIGATED |  |  | Derived from mitigation coverage |

### `shortage_cause` - Shortage cause (derived)

Explainable causes of each shortage with quantified contribution and evidence record IDs.

- **Grain:** one row per cause per shortage
- **Primary key:** `shortage_cause_id`
- **Natural key (unique):** `shortage_id, cause_seq`
- **FK** `shortage_id` -> `shortage(shortage_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `shortage_cause_id` (PK) | string | yes | yes |  |  | pattern `^SC-SHORT-\d{4}-\d{6}-\d{2}$` | SC-<shortage_id>-<nn> |
| `shortage_id` | string | yes | no |  |  | pattern `^SHORT-\d{4}-\d{6}$` | Shortage |
| `cause_seq` | integer | yes | no |  |  | >= 1 | Order (1 = primary) |
| `cause_code` | string | yes | no | DEMAND_EXCEEDS_SUPPLY, DEMAND_SPIKE, INSUFFICIENT_OPENING_STOCK, TRANSPORT_DELAY, SUPPLIER_CAPACITY_CONSTRAINT, PRODUCTION_CAPACITY_CONSTRAINT, DEPENDENT_DEMAND, PO_CANCELLED, LEAD_TIME_CORRECTION, UOM_CORRECTION, NO_SCHEDULED_SUPPLY |  |  | Cause |
| `contribution_qty` | integer | yes | no |  | base_uom | >= 0 | Quantified effect on the deficit |
| `evidence_record_type` | string | yes | no |  |  |  | Table holding the evidence |
| `evidence_record_ids` | string | no | no |  |  |  | Pipe-separated record IDs |
| `explanation` | string | yes | no |  |  |  | Plain-language explanation |

### `mitigation_option` - MitigationOption (derived)

Feasible mitigation alternatives per shortage with cost / service trade-offs. All pass policy and capacity checks.

- **Grain:** one row per feasible option
- **Primary key:** `mitigation_id`
- **FK** `shortage_id` -> `shortage(shortage_id)` N:1
- **FK** `supplier_id` -> `supplier(supplier_id)` N:1 (optional)
- **FK** `po_id` -> `purchase_order(po_id)` N:1 (optional)
- **FK** `source_location_id` -> `location(location_id)` N:1 (optional)
- **FK** `substitute_sku_id` -> `sku(sku_id)` N:1 (optional)
- **FK** `substitution_id` -> `sku_substitute(substitution_id)` N:1 (optional)

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `mitigation_id` (PK) | string | yes | yes |  |  | pattern `^MIT-SHORT-\d{4}-\d{6}-\d{2}$` | MIT-<shortage_id>-<nn> (nn = option rank) |
| `shortage_id` | string | yes | no |  |  | pattern `^SHORT-\d{4}-\d{6}$` | Shortage |
| `option_rank` | integer | yes | no |  |  | >= 1 | 1 = best net benefit |
| `mitigation_type` | string | yes | no | EXPEDITE_PO, NEW_PO_PRIMARY, NEW_PO_ALTERNATE, STOCK_TRANSFER, APPROVED_SUBSTITUTE, INCREASE_PRODUCTION, ACCEPT_BACKORDER |  |  | Action |
| `supplier_id` | string | no | no |  |  | pattern `^SUP-\d{4}$` | Supplier used |
| `po_id` | string | no | no |  |  | pattern `^PO-\d{4}-\d{6}$` | PO expedited |
| `source_location_id` | string | no | no |  |  | pattern `^LOC-\d{3}$` | Transfer source |
| `substitute_sku_id` | string | no | no |  |  | pattern `^SKU-\d{6}$` | Substitute used |
| `substitution_id` | string | no | no |  |  | pattern `^SUB-\d{6}$` | Approved substitution link |
| `proposed_qty` | integer | yes | no |  | base_uom | >= 0 | Quantity moved/ordered |
| `order_qty_purchase_uom` | integer | no | no |  |  |  | Order quantity in purchase UoM (POs) |
| `arrival_week_index` | integer | no | no |  |  |  | Week the quantity becomes available |
| `covered_qty` | integer | yes | no |  | base_uom | >= 0 | min(proposed_qty, shortage_qty) |
| `residual_shortage_qty` | integer | yes | no |  | base_uom | >= 0 | shortage_qty - covered_qty |
| `fill_rate_pct` | decimal | yes | no |  | percent | >= 0; <= 100 | covered / shortage |
| `weeks_late` | integer | yes | no |  |  | >= 0 | max(0, arrival - start week) |
| `service_score` | decimal | yes | no |  |  | >= 0; <= 1 | fill_rate * max(0, 1 - 0.15 * weeks_late) |
| `total_cost` | decimal | yes | no |  | USD | >= 0 | Cash cost of the action |
| `incremental_cost` | decimal | yes | no |  | USD | >= 0 | Premium over normal replenishment (or lost margin for backorder) |
| `net_benefit` | decimal | yes | no |  | USD |  | service_score * shortage_value - incremental_cost |
| `capacity_available` | integer | no | no |  |  |  | Capacity/surplus available before this option |
| `capacity_consumed` | integer | no | no |  |  |  | Capacity/surplus this option would use |
| `lead_time_days` | integer | no | no |  |  |  | Lead time applied |
| `moq_check` | string | yes | no | PASS, N/A |  |  | PASS / N/A |
| `lead_time_check` | string | yes | no | PASS, N/A |  |  | PASS / N/A |
| `approval_check` | string | yes | no | PASS, N/A |  |  | PASS / N/A |
| `capacity_check` | string | yes | no | PASS, N/A |  |  | PASS / N/A |
| `is_recommended` | boolean | yes | no |  |  |  | Highest net benefit (capacity reserved) |
| `rationale` | string | yes | no |  |  |  | Explanation |

### `rejected_mitigation` - Rejected mitigation (derived, audit)

Candidates that were considered and rejected, with the policy or constraint that failed.

- **Grain:** one row per rejected candidate
- **Primary key:** `rejection_id`
- **FK** `shortage_id` -> `shortage(shortage_id)` N:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `rejection_id` (PK) | string | yes | yes |  |  | pattern `^REJ-SHORT-\d{4}-\d{6}-\d{2}$` | REJ-<shortage_id>-<nn> |
| `shortage_id` | string | yes | no |  |  | pattern `^SHORT-\d{4}-\d{6}$` | Shortage |
| `mitigation_type` | string | yes | no | EXPEDITE_PO, NEW_PO_PRIMARY, NEW_PO_ALTERNATE, STOCK_TRANSFER, APPROVED_SUBSTITUTE, INCREASE_PRODUCTION, ACCEPT_BACKORDER |  |  | Candidate type |
| `candidate_ref` | string | yes | no |  |  |  | Supplier / location / substitution / PO considered |
| `reason_code` | string | yes | no | SUBSTITUTE_NOT_APPROVED, SUBSTITUTE_NOT_EFFECTIVE, SUPPLIER_ON_HOLD, INSUFFICIENT_CAPACITY, LEAD_TIME_TOO_LONG, NO_SURPLUS, NO_LANE, BELOW_MOQ, COMPONENT_SHORTAGE, NO_BENEFIT |  |  | Failed rule |
| `detail` | string | yes | no |  |  |  | Explanation |

### `detected_issue` - Detected data/plan issue (derived)

Exceptions detected by the planning engine's data-quality screen, with the decision taken.

- **Grain:** one row per detected issue
- **Primary key:** `issue_id`

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `issue_id` (PK) | string | yes | yes |  |  | pattern `^ISS-\d{4}-\d{6}$` | ISS-<year>-<counter> |
| `issue_type` | string | yes | no | INBOUND_DOUBLE_COUNT, SUBSTITUTE_NOT_APPROVED, SUPPLIER_CAPACITY_EXCEEDED, SHORTAGE_WITHOUT_LEAD_TIME, UOM_MISMATCH, DEMAND_SPIKE, CONSTRAINED_SUPPLIER, CONSTRAINED_PLANT |  |  | Issue |
| `severity` | string | yes | no | HIGH, MEDIUM, LOW, INFO |  |  | Severity |
| `record_type` | string | yes | no |  |  |  | Table of the offending record |
| `record_id` | string | yes | no |  |  |  | Offending record ID |
| `related_record_ids` | string | no | no |  |  |  | Pipe-separated related IDs |
| `sku_id` | string | no | no |  |  |  | SKU |
| `location_id` | string | no | no |  |  |  | Location |
| `supplier_id` | string | no | no |  |  |  | Supplier |
| `week_id` | string | no | no |  |  |  | Week |
| `decision` | string | yes | no |  |  |  | Action taken by the engine |
| `impact_qty` | integer | no | no |  |  |  | Quantity affected |
| `detail` | string | yes | no |  |  |  | Explanation |

### `supplier_capacity_utilization` - Supplier capacity utilisation (derived)

Committed open-PO load and mitigation reservations versus supplier capacity per week.

- **Grain:** one row per supplier-week
- **Primary key:** `supplier_capacity_id`
- **FK** `supplier_capacity_id` -> `supplier_capacity(supplier_capacity_id)` 1:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `supplier_capacity_id` (PK) | string | yes | yes |  |  | pattern `^SCAP-SUP-\d{4}-\d{4}W\d{2}$` | Capacity row |
| `supplier_id` | string | yes | no |  |  | pattern `^SUP-\d{4}$` | Supplier |
| `week_id` | string | yes | no |  |  | pattern `^\d{4}W\d{2}$` | Week |
| `capacity_units` | integer | yes | no |  |  | >= 0 | Capacity |
| `source_committed_units` | integer | yes | no |  |  | >= 0 | Load as recorded in source POs |
| `planned_committed_units` | integer | yes | no |  |  | >= 0 | Load after capacity deferral |
| `mitigation_reserved_units` | integer | yes | no |  |  | >= 0 | Reserved by recommended mitigations |
| `utilization_pct` | decimal | yes | no |  | percent | >= 0 | (planned + reserved) / capacity |
| `source_over_capacity` | boolean | yes | no |  |  |  | source_committed_units > capacity_units |

### `production_capacity_utilization` - Production capacity utilisation (derived)

Planned production plus mitigation reservations versus plant capacity per week.

- **Grain:** one row per plant-week
- **Primary key:** `production_capacity_id`
- **FK** `production_capacity_id` -> `production_capacity(production_capacity_id)` 1:1

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `production_capacity_id` (PK) | string | yes | yes |  |  | pattern `^PCAP-LOC-\d{3}-\d{4}W\d{2}$` | Capacity row |
| `location_id` | string | yes | no |  |  | pattern `^LOC-\d{3}$` | Plant |
| `week_id` | string | yes | no |  |  | pattern `^\d{4}W\d{2}$` | Week |
| `capacity_units` | integer | yes | no |  |  | >= 0 | Capacity |
| `planned_units` | integer | yes | no |  |  | >= 0 | Planned production |
| `mitigation_reserved_units` | integer | yes | no |  |  | >= 0 | Reserved by recommended mitigations |
| `utilization_pct` | decimal | yes | no |  | percent | >= 0 | (planned + reserved) / capacity |

## Ground truth (separate folder, never an input)

### `ground_truth` - Ground truth (separate, never an input)

Labels for injected edge cases and generator scenario drivers. Stored outside the input folder.

- **Grain:** one row per labelled record
- **Primary key:** `gt_id`

| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |
|---|---|---|---|---|---|---|---|
| `gt_id` (PK) | string | yes | yes |  |  | pattern `^GT-\d{6}$` | Label identifier |
| `label_category` | string | yes | no | EDGE_CASE, SCENARIO |  |  | Edge case or scenario driver |
| `issue_type` | string | yes | no | INBOUND_DOUBLE_COUNT, SUBSTITUTE_NOT_APPROVED, SUPPLIER_CAPACITY_EXCEEDED, SHORTAGE_WITHOUT_LEAD_TIME, UOM_MISMATCH, DEMAND_SPIKE, CONSTRAINED_SUPPLIER, CONSTRAINED_PLANT |  |  | Label |
| `record_type` | string | yes | no |  |  |  | Table of the labelled record |
| `record_id` | string | yes | no |  |  |  | Labelled record ID |
| `related_record_ids` | string | no | no |  |  |  | Pipe-separated traceability IDs |
| `sku_id` | string | no | no |  |  |  | SKU |
| `location_id` | string | no | no |  |  |  | Location |
| `supplier_id` | string | no | no |  |  |  | Supplier |
| `week_id` | string | no | no |  |  |  | Week |
| `expected_decision` | string | yes | no |  |  |  | What a correct planner/engine must do |
| `expected_value` | string | no | no |  |  |  | Expected corrected value |
| `rule_reference` | string | yes | no |  |  |  | Documented rule (docs/edge_cases.md) |
| `description` | string | yes | no |  |  |  | Explanation |
