-- Generated from src/supply_planning/schema.py
PRAGMA foreign_keys = ON;

CREATE TABLE calendar_week (
    week_id TEXT PRIMARY KEY,
    week_index INTEGER NOT NULL,
    week_start_date TEXT NOT NULL,
    week_end_date TEXT NOT NULL,
    is_holiday_week INTEGER NOT NULL
);

CREATE TABLE location (
    location_id TEXT PRIMARY KEY,
    location_name TEXT NOT NULL,
    location_type TEXT NOT NULL CHECK (location_type IS NULL OR location_type IN ('PLANT', 'DC')),
    region TEXT NOT NULL CHECK (region IS NULL OR region IN ('NORTH', 'SOUTH', 'EAST', 'WEST', 'CENTRAL')),
    status TEXT NOT NULL CHECK (status IS NULL OR status IN ('ACTIVE')),
    effective_from TEXT NOT NULL
);

CREATE TABLE supplier (
    supplier_id TEXT PRIMARY KEY,
    supplier_name TEXT NOT NULL,
    region TEXT NOT NULL CHECK (region IS NULL OR region IN ('NORTH', 'SOUTH', 'EAST', 'WEST', 'CENTRAL')),
    is_overseas INTEGER NOT NULL,
    supplier_tier TEXT NOT NULL CHECK (supplier_tier IS NULL OR supplier_tier IN ('STRATEGIC', 'PREFERRED', 'APPROVED')),
    supplier_role TEXT NOT NULL CHECK (supplier_role IS NULL OR supplier_role IN ('FINISHED_GOODS', 'COMPONENTS')),
    reliability_pct REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IS NULL OR status IN ('ACTIVE', 'ON_HOLD')),
    effective_from TEXT NOT NULL
);

CREATE TABLE sku (
    sku_id TEXT PRIMARY KEY,
    sku_name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IS NULL OR category IN ('ELECTRONICS', 'HOME_GOODS', 'PERSONAL_CARE', 'FOOD_BEVERAGE', 'APPAREL', 'HARDWARE', 'RAW_MATERIAL', 'PACKAGING', 'PARTS')),
    item_type TEXT NOT NULL CHECK (item_type IS NULL OR item_type IN ('FINISHED_GOOD', 'COMPONENT')),
    sourcing_type TEXT NOT NULL CHECK (sourcing_type IS NULL OR sourcing_type IN ('BUY', 'MAKE')),
    base_uom TEXT NOT NULL CHECK (base_uom IS NULL OR base_uom IN ('EA', 'KG', 'L')),
    units_per_case INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    unit_price REAL,
    abc_class TEXT NOT NULL CHECK (abc_class IS NULL OR abc_class IN ('A', 'B', 'C')),
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IS NULL OR lifecycle_status IN ('NEW', 'ACTIVE', 'PHASE_OUT')),
    effective_from TEXT NOT NULL,
    effective_to TEXT
);

CREATE TABLE sku_location (
    sku_location_id TEXT PRIMARY KEY,
    sku_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    planning_method TEXT NOT NULL CHECK (planning_method IS NULL OR planning_method IN ('PURCHASE', 'PRODUCTION', 'DEPENDENT_PURCHASE')),
    primary_supplier_id TEXT,
    safety_stock_qty INTEGER NOT NULL,
    effective_from TEXT NOT NULL,
    FOREIGN KEY (sku_id) REFERENCES sku (sku_id),
    FOREIGN KEY (location_id) REFERENCES location (location_id),
    FOREIGN KEY (primary_supplier_id) REFERENCES supplier (supplier_id)
);
CREATE UNIQUE INDEX ux_sku_location_nk ON sku_location (sku_id, location_id);

CREATE TABLE supplier_sku (
    supplier_sku_id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    sku_id TEXT NOT NULL,
    supplier_priority INTEGER NOT NULL,
    purchase_uom TEXT NOT NULL CHECK (purchase_uom IS NULL OR purchase_uom IN ('EA', 'CS', 'KG', 'L')),
    uom_conversion_factor REAL NOT NULL,
    min_order_qty INTEGER NOT NULL,
    order_multiple INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    approval_status TEXT NOT NULL CHECK (approval_status IS NULL OR approval_status IN ('APPROVED')),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
    FOREIGN KEY (sku_id) REFERENCES sku (sku_id)
);
CREATE UNIQUE INDEX ux_supplier_sku_nk ON supplier_sku (supplier_id, sku_id);

CREATE TABLE lead_time (
    lead_time_id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    transport_mode TEXT NOT NULL CHECK (transport_mode IS NULL OR transport_mode IN ('ROAD', 'RAIL', 'SEA', 'AIR')),
    production_lead_days INTEGER NOT NULL,
    transit_days INTEGER NOT NULL,
    total_lead_days INTEGER NOT NULL,
    expedite_transit_days INTEGER NOT NULL,
    expedite_premium_pct REAL NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
    FOREIGN KEY (location_id) REFERENCES location (location_id)
);
CREATE UNIQUE INDEX ux_lead_time_nk ON lead_time (supplier_id, location_id, version);

CREATE TABLE supplier_capacity (
    supplier_capacity_id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    week_id TEXT NOT NULL,
    capacity_units INTEGER NOT NULL,
    FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
    FOREIGN KEY (week_id) REFERENCES calendar_week (week_id)
);
CREATE UNIQUE INDEX ux_supplier_capacity_nk ON supplier_capacity (supplier_id, week_id);

CREATE TABLE forecast_demand (
    demand_id TEXT PRIMARY KEY,
    sku_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    week_id TEXT NOT NULL,
    forecast_qty INTEGER NOT NULL,
    uom TEXT NOT NULL CHECK (uom IS NULL OR uom IN ('EA', 'KG', 'L')),
    forecast_version TEXT NOT NULL CHECK (forecast_version IS NULL OR forecast_version IN ('FV-2026-01')),
    FOREIGN KEY (sku_id) REFERENCES sku (sku_id),
    FOREIGN KEY (location_id) REFERENCES location (location_id),
    FOREIGN KEY (week_id) REFERENCES calendar_week (week_id),
    FOREIGN KEY (sku_id, location_id) REFERENCES sku_location (sku_id, location_id)
);
CREATE UNIQUE INDEX ux_forecast_demand_nk ON forecast_demand (sku_id, location_id, week_id);

CREATE TABLE purchase_order (
    po_id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    lead_time_id TEXT NOT NULL,
    order_date TEXT NOT NULL,
    ship_date TEXT NOT NULL,
    promised_receipt_date TEXT NOT NULL,
    transport_delay_days INTEGER NOT NULL,
    expected_receipt_date TEXT NOT NULL,
    actual_receipt_date TEXT,
    status TEXT NOT NULL CHECK (status IS NULL OR status IN ('PLANNED', 'CONFIRMED', 'IN_TRANSIT', 'RECEIVED', 'CANCELLED')),
    line_count INTEGER NOT NULL,
    total_base_qty INTEGER NOT NULL,
    total_value REAL NOT NULL,
    currency TEXT NOT NULL CHECK (currency IS NULL OR currency IN ('USD')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
    FOREIGN KEY (location_id) REFERENCES location (location_id),
    FOREIGN KEY (lead_time_id) REFERENCES lead_time (lead_time_id)
);

CREATE TABLE purchase_order_line (
    po_line_id TEXT PRIMARY KEY,
    po_id TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    sku_id TEXT NOT NULL,
    supplier_sku_id TEXT NOT NULL,
    requested_qty INTEGER NOT NULL,
    order_qty INTEGER NOT NULL,
    order_uom TEXT NOT NULL CHECK (order_uom IS NULL OR order_uom IN ('EA', 'CS', 'KG', 'L')),
    uom_conversion_factor REAL NOT NULL,
    base_qty INTEGER NOT NULL,
    base_uom TEXT NOT NULL CHECK (base_uom IS NULL OR base_uom IN ('EA', 'KG', 'L')),
    unit_cost REAL NOT NULL,
    line_value REAL NOT NULL,
    FOREIGN KEY (po_id) REFERENCES purchase_order (po_id),
    FOREIGN KEY (sku_id) REFERENCES sku (sku_id),
    FOREIGN KEY (supplier_sku_id) REFERENCES supplier_sku (supplier_sku_id)
);
CREATE UNIQUE INDEX ux_purchase_order_line_nk ON purchase_order_line (po_id, sku_id);

CREATE TABLE inventory (
    inventory_id TEXT PRIMARY KEY,
    sku_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    stock_status TEXT NOT NULL CHECK (stock_status IS NULL OR stock_status IN ('ON_HAND', 'IN_TRANSIT', 'QUALITY_HOLD')),
    quantity INTEGER NOT NULL,
    uom TEXT NOT NULL CHECK (uom IS NULL OR uom IN ('EA', 'KG', 'L')),
    po_line_id TEXT,
    FOREIGN KEY (sku_id) REFERENCES sku (sku_id),
    FOREIGN KEY (location_id) REFERENCES location (location_id),
    FOREIGN KEY (po_line_id) REFERENCES purchase_order_line (po_line_id),
    FOREIGN KEY (sku_id, location_id) REFERENCES sku_location (sku_id, location_id)
);

CREATE TABLE purchase_order_event (
    event_id TEXT PRIMARY KEY,
    po_id TEXT NOT NULL,
    event_seq INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IS NULL OR event_type IN ('CREATED', 'CONFIRMED', 'SHIPPED', 'DELAY_REPORTED', 'RECEIVED', 'CANCELLED')),
    from_status TEXT CHECK (from_status IS NULL OR from_status IN ('PLANNED', 'CONFIRMED', 'IN_TRANSIT', 'RECEIVED', 'CANCELLED')),
    to_status TEXT NOT NULL CHECK (to_status IS NULL OR to_status IN ('PLANNED', 'CONFIRMED', 'IN_TRANSIT', 'RECEIVED', 'CANCELLED')),
    event_timestamp TEXT NOT NULL,
    actor TEXT NOT NULL CHECK (actor IS NULL OR actor IN ('PLANNER', 'SUPPLIER', 'CARRIER', 'WAREHOUSE_OPERATOR', 'OPERATIONS_MANAGER')),
    delay_days INTEGER NOT NULL,
    note TEXT,
    FOREIGN KEY (po_id) REFERENCES purchase_order (po_id)
);
CREATE UNIQUE INDEX ux_purchase_order_event_nk ON purchase_order_event (po_id, event_seq);

CREATE TABLE bom (
    bom_id TEXT PRIMARY KEY,
    parent_sku_id TEXT NOT NULL,
    component_sku_id TEXT NOT NULL,
    qty_per REAL NOT NULL,
    component_uom TEXT NOT NULL CHECK (component_uom IS NULL OR component_uom IN ('EA', 'KG', 'L')),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    FOREIGN KEY (parent_sku_id) REFERENCES sku (sku_id),
    FOREIGN KEY (component_sku_id) REFERENCES sku (sku_id)
);
CREATE UNIQUE INDEX ux_bom_nk ON bom (parent_sku_id, component_sku_id);

CREATE TABLE production_capacity (
    production_capacity_id TEXT PRIMARY KEY,
    location_id TEXT NOT NULL,
    week_id TEXT NOT NULL,
    capacity_units INTEGER NOT NULL,
    FOREIGN KEY (location_id) REFERENCES location (location_id),
    FOREIGN KEY (week_id) REFERENCES calendar_week (week_id)
);
CREATE UNIQUE INDEX ux_production_capacity_nk ON production_capacity (location_id, week_id);

CREATE TABLE production_plan (
    production_plan_id TEXT PRIMARY KEY,
    sku_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    week_id TEXT NOT NULL,
    required_qty INTEGER NOT NULL,
    planned_qty INTEGER NOT NULL,
    batch_size INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IS NULL OR status IN ('FIRM', 'PLANNED')),
    FOREIGN KEY (sku_id) REFERENCES sku (sku_id),
    FOREIGN KEY (location_id) REFERENCES location (location_id),
    FOREIGN KEY (week_id) REFERENCES calendar_week (week_id),
    FOREIGN KEY (sku_id, location_id) REFERENCES sku_location (sku_id, location_id)
);
CREATE UNIQUE INDEX ux_production_plan_nk ON production_plan (sku_id, location_id, week_id);

CREATE TABLE sku_substitute (
    substitution_id TEXT PRIMARY KEY,
    sku_id TEXT NOT NULL,
    substitute_sku_id TEXT NOT NULL,
    conversion_ratio REAL NOT NULL,
    approval_status TEXT NOT NULL CHECK (approval_status IS NULL OR approval_status IN ('APPROVED', 'PENDING', 'REJECTED')),
    approved_by TEXT CHECK (approved_by IS NULL OR approved_by IN ('PLANNER', 'OPERATIONS_MANAGER')),
    approval_date TEXT,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    priority INTEGER NOT NULL,
    FOREIGN KEY (sku_id) REFERENCES sku (sku_id),
    FOREIGN KEY (substitute_sku_id) REFERENCES sku (sku_id)
);
CREATE UNIQUE INDEX ux_sku_substitute_nk ON sku_substitute (sku_id, substitute_sku_id);

CREATE TABLE scheduled_receipt (
    po_line_id TEXT PRIMARY KEY,
    po_id TEXT NOT NULL,
    sku_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    supplier_id TEXT NOT NULL,
    po_status TEXT NOT NULL CHECK (po_status IS NULL OR po_status IN ('PLANNED', 'CONFIRMED', 'IN_TRANSIT', 'RECEIVED', 'CANCELLED')),
    source_base_qty INTEGER NOT NULL,
    planning_base_qty INTEGER NOT NULL,
    source_receipt_date TEXT NOT NULL,
    planning_receipt_date TEXT NOT NULL,
    ship_week_index INTEGER,
    receipt_week_index INTEGER NOT NULL,
    adjustment_codes TEXT,
    counted_in_plan INTEGER NOT NULL,
    FOREIGN KEY (po_line_id) REFERENCES purchase_order_line (po_line_id),
    FOREIGN KEY (po_id) REFERENCES purchase_order (po_id)
);

CREATE TABLE projected_balance (
    pab_id TEXT PRIMARY KEY,
    sku_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    week_id TEXT NOT NULL,
    week_index INTEGER NOT NULL,
    opening_balance INTEGER NOT NULL,
    forecast_demand INTEGER NOT NULL,
    dependent_demand INTEGER NOT NULL,
    scheduled_receipts INTEGER NOT NULL,
    planned_production INTEGER NOT NULL,
    closing_balance INTEGER NOT NULL,
    safety_stock_qty INTEGER NOT NULL,
    below_safety_stock INTEGER NOT NULL,
    is_shortage INTEGER NOT NULL,
    FOREIGN KEY (sku_id, location_id) REFERENCES sku_location (sku_id, location_id),
    FOREIGN KEY (week_id) REFERENCES calendar_week (week_id)
);
CREATE UNIQUE INDEX ux_projected_balance_nk ON projected_balance (sku_id, location_id, week_id);

CREATE TABLE shortage (
    shortage_id TEXT PRIMARY KEY,
    sku_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    start_week_id TEXT NOT NULL,
    end_week_id TEXT NOT NULL,
    start_week_index INTEGER NOT NULL,
    end_week_index INTEGER NOT NULL,
    duration_weeks INTEGER NOT NULL,
    shortage_qty INTEGER NOT NULL,
    shortage_value REAL NOT NULL,
    lead_time_weeks INTEGER NOT NULL,
    within_lead_time INTEGER NOT NULL,
    priority_score REAL NOT NULL,
    priority_rank INTEGER NOT NULL,
    priority_tier TEXT NOT NULL CHECK (priority_tier IS NULL OR priority_tier IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    primary_cause_code TEXT NOT NULL CHECK (primary_cause_code IS NULL OR primary_cause_code IN ('DEMAND_EXCEEDS_SUPPLY', 'DEMAND_SPIKE', 'INSUFFICIENT_OPENING_STOCK', 'TRANSPORT_DELAY', 'SUPPLIER_CAPACITY_CONSTRAINT', 'PRODUCTION_CAPACITY_CONSTRAINT', 'DEPENDENT_DEMAND', 'PO_CANCELLED', 'LEAD_TIME_CORRECTION', 'UOM_CORRECTION', 'NO_SCHEDULED_SUPPLY')),
    cause_summary TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IS NULL OR status IN ('MITIGATION_PROPOSED', 'PARTIALLY_MITIGATED', 'UNMITIGATED')),
    FOREIGN KEY (sku_id, location_id) REFERENCES sku_location (sku_id, location_id)
);

CREATE TABLE shortage_cause (
    shortage_cause_id TEXT PRIMARY KEY,
    shortage_id TEXT NOT NULL,
    cause_seq INTEGER NOT NULL,
    cause_code TEXT NOT NULL CHECK (cause_code IS NULL OR cause_code IN ('DEMAND_EXCEEDS_SUPPLY', 'DEMAND_SPIKE', 'INSUFFICIENT_OPENING_STOCK', 'TRANSPORT_DELAY', 'SUPPLIER_CAPACITY_CONSTRAINT', 'PRODUCTION_CAPACITY_CONSTRAINT', 'DEPENDENT_DEMAND', 'PO_CANCELLED', 'LEAD_TIME_CORRECTION', 'UOM_CORRECTION', 'NO_SCHEDULED_SUPPLY')),
    contribution_qty INTEGER NOT NULL,
    evidence_record_type TEXT NOT NULL,
    evidence_record_ids TEXT,
    explanation TEXT NOT NULL,
    FOREIGN KEY (shortage_id) REFERENCES shortage (shortage_id)
);
CREATE UNIQUE INDEX ux_shortage_cause_nk ON shortage_cause (shortage_id, cause_seq);

CREATE TABLE mitigation_option (
    mitigation_id TEXT PRIMARY KEY,
    shortage_id TEXT NOT NULL,
    option_rank INTEGER NOT NULL,
    mitigation_type TEXT NOT NULL CHECK (mitigation_type IS NULL OR mitigation_type IN ('EXPEDITE_PO', 'NEW_PO_PRIMARY', 'NEW_PO_ALTERNATE', 'STOCK_TRANSFER', 'APPROVED_SUBSTITUTE', 'INCREASE_PRODUCTION', 'ACCEPT_BACKORDER')),
    supplier_id TEXT,
    po_id TEXT,
    source_location_id TEXT,
    substitute_sku_id TEXT,
    substitution_id TEXT,
    proposed_qty INTEGER NOT NULL,
    order_qty_purchase_uom INTEGER,
    arrival_week_index INTEGER,
    covered_qty INTEGER NOT NULL,
    residual_shortage_qty INTEGER NOT NULL,
    fill_rate_pct REAL NOT NULL,
    weeks_late INTEGER NOT NULL,
    service_score REAL NOT NULL,
    total_cost REAL NOT NULL,
    incremental_cost REAL NOT NULL,
    net_benefit REAL NOT NULL,
    capacity_available INTEGER,
    capacity_consumed INTEGER,
    lead_time_days INTEGER,
    moq_check TEXT NOT NULL CHECK (moq_check IS NULL OR moq_check IN ('PASS', 'N/A')),
    lead_time_check TEXT NOT NULL CHECK (lead_time_check IS NULL OR lead_time_check IN ('PASS', 'N/A')),
    approval_check TEXT NOT NULL CHECK (approval_check IS NULL OR approval_check IN ('PASS', 'N/A')),
    capacity_check TEXT NOT NULL CHECK (capacity_check IS NULL OR capacity_check IN ('PASS', 'N/A')),
    is_recommended INTEGER NOT NULL,
    rationale TEXT NOT NULL,
    FOREIGN KEY (shortage_id) REFERENCES shortage (shortage_id),
    FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
    FOREIGN KEY (po_id) REFERENCES purchase_order (po_id),
    FOREIGN KEY (source_location_id) REFERENCES location (location_id),
    FOREIGN KEY (substitute_sku_id) REFERENCES sku (sku_id),
    FOREIGN KEY (substitution_id) REFERENCES sku_substitute (substitution_id)
);

CREATE TABLE rejected_mitigation (
    rejection_id TEXT PRIMARY KEY,
    shortage_id TEXT NOT NULL,
    mitigation_type TEXT NOT NULL CHECK (mitigation_type IS NULL OR mitigation_type IN ('EXPEDITE_PO', 'NEW_PO_PRIMARY', 'NEW_PO_ALTERNATE', 'STOCK_TRANSFER', 'APPROVED_SUBSTITUTE', 'INCREASE_PRODUCTION', 'ACCEPT_BACKORDER')),
    candidate_ref TEXT NOT NULL,
    reason_code TEXT NOT NULL CHECK (reason_code IS NULL OR reason_code IN ('SUBSTITUTE_NOT_APPROVED', 'SUBSTITUTE_NOT_EFFECTIVE', 'SUPPLIER_ON_HOLD', 'INSUFFICIENT_CAPACITY', 'LEAD_TIME_TOO_LONG', 'NO_SURPLUS', 'NO_LANE', 'BELOW_MOQ', 'COMPONENT_SHORTAGE', 'NO_BENEFIT')),
    detail TEXT NOT NULL,
    FOREIGN KEY (shortage_id) REFERENCES shortage (shortage_id)
);

CREATE TABLE detected_issue (
    issue_id TEXT PRIMARY KEY,
    issue_type TEXT NOT NULL CHECK (issue_type IS NULL OR issue_type IN ('INBOUND_DOUBLE_COUNT', 'SUBSTITUTE_NOT_APPROVED', 'SUPPLIER_CAPACITY_EXCEEDED', 'SHORTAGE_WITHOUT_LEAD_TIME', 'UOM_MISMATCH', 'DEMAND_SPIKE', 'CONSTRAINED_SUPPLIER', 'CONSTRAINED_PLANT')),
    severity TEXT NOT NULL CHECK (severity IS NULL OR severity IN ('HIGH', 'MEDIUM', 'LOW', 'INFO')),
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    related_record_ids TEXT,
    sku_id TEXT,
    location_id TEXT,
    supplier_id TEXT,
    week_id TEXT,
    decision TEXT NOT NULL,
    impact_qty INTEGER,
    detail TEXT NOT NULL
);

CREATE TABLE supplier_capacity_utilization (
    supplier_capacity_id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    week_id TEXT NOT NULL,
    capacity_units INTEGER NOT NULL,
    source_committed_units INTEGER NOT NULL,
    planned_committed_units INTEGER NOT NULL,
    mitigation_reserved_units INTEGER NOT NULL,
    utilization_pct REAL NOT NULL,
    source_over_capacity INTEGER NOT NULL,
    FOREIGN KEY (supplier_capacity_id) REFERENCES supplier_capacity (supplier_capacity_id)
);

CREATE TABLE production_capacity_utilization (
    production_capacity_id TEXT PRIMARY KEY,
    location_id TEXT NOT NULL,
    week_id TEXT NOT NULL,
    capacity_units INTEGER NOT NULL,
    planned_units INTEGER NOT NULL,
    mitigation_reserved_units INTEGER NOT NULL,
    utilization_pct REAL NOT NULL,
    FOREIGN KEY (production_capacity_id) REFERENCES production_capacity (production_capacity_id)
);
