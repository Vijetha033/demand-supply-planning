"""Single source of truth for every table: fields, types, keys, enums, rules.

Used by: the generator (column order), the validator (PK/FK/enum/pattern/
required checks), the data-dictionary generator and the SQL DDL exporter.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ids import PATTERNS

# --------------------------------------------------------------------- enums
REGIONS = ["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"]
LOCATION_TYPES = ["PLANT", "DC"]
SUPPLIER_TIERS = ["STRATEGIC", "PREFERRED", "APPROVED"]
SUPPLIER_ROLES = ["FINISHED_GOODS", "COMPONENTS"]
SUPPLIER_STATUS = ["ACTIVE", "ON_HOLD"]
FG_CATEGORIES = ["ELECTRONICS", "HOME_GOODS", "PERSONAL_CARE", "FOOD_BEVERAGE", "APPAREL", "HARDWARE"]
COMPONENT_CATEGORIES = ["RAW_MATERIAL", "PACKAGING", "PARTS"]
CATEGORIES = FG_CATEGORIES + COMPONENT_CATEGORIES
ITEM_TYPES = ["FINISHED_GOOD", "COMPONENT"]
SOURCING_TYPES = ["BUY", "MAKE"]
BASE_UOMS = ["EA", "KG", "L"]
PURCHASE_UOMS = ["EA", "CS", "KG", "L"]
ABC = ["A", "B", "C"]
SKU_LIFECYCLE = ["NEW", "ACTIVE", "PHASE_OUT"]
PLANNING_METHODS = ["PURCHASE", "PRODUCTION", "DEPENDENT_PURCHASE"]
APPROVAL = ["APPROVED", "PENDING", "REJECTED"]
TRANSPORT_MODES = ["ROAD", "RAIL", "SEA", "AIR"]
STOCK_STATUS = ["ON_HAND", "IN_TRANSIT", "QUALITY_HOLD"]
PO_STATUS = ["PLANNED", "CONFIRMED", "IN_TRANSIT", "RECEIVED", "CANCELLED"]
PO_EVENT_TYPES = ["CREATED", "CONFIRMED", "SHIPPED", "DELAY_REPORTED", "RECEIVED", "CANCELLED"]
ACTORS = ["PLANNER", "SUPPLIER", "CARRIER", "WAREHOUSE_OPERATOR", "OPERATIONS_MANAGER"]
PRODUCTION_STATUS = ["FIRM", "PLANNED"]
PRIORITY_TIERS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
SHORTAGE_STATUS = ["MITIGATION_PROPOSED", "PARTIALLY_MITIGATED", "UNMITIGATED"]
CAUSE_CODES = [
    "DEMAND_EXCEEDS_SUPPLY", "DEMAND_SPIKE", "INSUFFICIENT_OPENING_STOCK", "TRANSPORT_DELAY",
    "SUPPLIER_CAPACITY_CONSTRAINT", "PRODUCTION_CAPACITY_CONSTRAINT", "DEPENDENT_DEMAND",
    "PO_CANCELLED", "LEAD_TIME_CORRECTION", "UOM_CORRECTION", "NO_SCHEDULED_SUPPLY",
]
MITIGATION_TYPES = [
    "EXPEDITE_PO", "NEW_PO_PRIMARY", "NEW_PO_ALTERNATE", "STOCK_TRANSFER",
    "APPROVED_SUBSTITUTE", "INCREASE_PRODUCTION", "ACCEPT_BACKORDER",
]
REJECTION_REASONS = [
    "SUBSTITUTE_NOT_APPROVED", "SUBSTITUTE_NOT_EFFECTIVE", "SUPPLIER_ON_HOLD", "INSUFFICIENT_CAPACITY",
    "LEAD_TIME_TOO_LONG", "NO_SURPLUS", "NO_LANE", "BELOW_MOQ", "COMPONENT_SHORTAGE", "NO_BENEFIT",
]
ISSUE_TYPES = [
    "INBOUND_DOUBLE_COUNT", "SUBSTITUTE_NOT_APPROVED", "SUPPLIER_CAPACITY_EXCEEDED",
    "SHORTAGE_WITHOUT_LEAD_TIME", "UOM_MISMATCH", "DEMAND_SPIKE", "CONSTRAINED_SUPPLIER",
    "CONSTRAINED_PLANT",
]
EDGE_CASE_TYPES = ISSUE_TYPES[:5]
SEVERITY = ["HIGH", "MEDIUM", "LOW", "INFO"]
LABEL_CATEGORIES = ["EDGE_CASE", "SCENARIO"]


@dataclass
class Field:
    name: str
    dtype: str                    # string | integer | decimal | date | datetime | boolean
    description: str
    required: bool = True
    allowed: list | None = None
    unit: str | None = None
    unique: bool = False
    pattern: str | None = None
    rule: str | None = None       # human-readable validation rule
    min_value: float | None = None
    max_value: float | None = None


@dataclass
class ForeignKey:
    columns: list[str]
    ref_table: str
    ref_columns: list[str]
    cardinality: str              # e.g. "N:1"
    optional: bool = False
    note: str = ""


@dataclass
class Table:
    name: str
    entity: str
    layer: str                    # input | output | ground_truth
    description: str
    grain: str
    primary_key: str
    fields: list[Field]
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    natural_key: list[str] | None = None
    lifecycle: str | None = None

    @property
    def columns(self) -> list[str]:
        return [f.name for f in self.fields]

    def field(self, name: str) -> Field:
        return next(f for f in self.fields if f.name == name)


def F(name, dtype, description, **kw) -> Field:
    return Field(name, dtype, description, **kw)


def ID(name, description, pattern, **kw) -> Field:
    return Field(name, "string", description, unique=True, pattern=pattern, **kw)


def FKF(name, description, pattern=None, **kw) -> Field:
    return Field(name, "string", description, pattern=pattern, **kw)


DATE_RULE = "ISO-8601 date YYYY-MM-DD"
P = PATTERNS

TABLES: dict[str, Table] = {}


def _t(t: Table) -> None:
    TABLES[t.name] = t


# =========================================================== INPUT (source) layer
_t(Table(
    "calendar_week", "Calendar (supporting)", "input",
    "ISO planning weeks of the plan year. Week index 0 starts on the planning as-of date.",
    "one row per planning week", "week_id",
    [
        ID("week_id", "ISO week identifier", P["week_id"]),
        F("week_index", "integer", "0-based week offset from the as-of date", unique=True, min_value=0),
        F("week_start_date", "date", "Monday of the ISO week", unique=True, rule=DATE_RULE),
        F("week_end_date", "date", "Sunday of the ISO week", rule="= week_start_date + 6 days"),
        F("is_holiday_week", "boolean", "Reduced supplier/plant capacity week"),
    ],
))
_t(Table(
    "location", "Location", "input",
    "Plants (production + stocking) and distribution centres.",
    "one row per location", "location_id",
    [
        ID("location_id", "Location identifier", P["location_id"]),
        F("location_name", "string", "Synthetic display name", unique=True),
        F("location_type", "string", "Plant or distribution centre", allowed=LOCATION_TYPES),
        F("region", "string", "Planning region", allowed=REGIONS),
        F("status", "string", "Lifecycle status", allowed=["ACTIVE"]),
        F("effective_from", "date", "Date the location became active", rule=DATE_RULE),
    ],
    lifecycle="ACTIVE (all synthetic locations are active in the horizon)",
))
_t(Table(
    "supplier", "Supplier", "input",
    "External suppliers. Capacity is in supplier_capacity; lanes and lead times in lead_time.",
    "one row per supplier", "supplier_id",
    [
        ID("supplier_id", "Supplier identifier", P["supplier_id"]),
        F("supplier_name", "string", "Synthetic display name", unique=True),
        F("region", "string", "Home region", allowed=REGIONS),
        F("is_overseas", "boolean", "Ships by sea from outside the network"),
        F("supplier_tier", "string", "Commercial tier", allowed=SUPPLIER_TIERS),
        F("supplier_role", "string", "What the supplier provides", allowed=SUPPLIER_ROLES),
        F("reliability_pct", "decimal", "Historical on-time delivery", unit="percent", min_value=0, max_value=100),
        F("status", "string", "ON_HOLD suppliers may not receive new purchase orders", allowed=SUPPLIER_STATUS),
        F("effective_from", "date", "Onboarding date", rule=DATE_RULE),
    ],
    lifecycle="ACTIVE -> ON_HOLD (policy: no new POs while ON_HOLD)",
))
_t(Table(
    "sku", "SKU", "input",
    "Stock-keeping units: purchased finished goods, manufactured finished goods and purchased components.",
    "one row per SKU", "sku_id",
    [
        ID("sku_id", "SKU identifier", P["sku_id"]),
        F("sku_name", "string", "Synthetic display name", unique=True),
        F("category", "string", "Product category", allowed=CATEGORIES),
        F("item_type", "string", "Finished good or BOM component", allowed=ITEM_TYPES),
        F("sourcing_type", "string", "BUY from suppliers or MAKE in a plant", allowed=SOURCING_TYPES,
          rule="COMPONENT => BUY"),
        F("base_uom", "string", "Base (stocking) unit of measure", allowed=BASE_UOMS),
        F("units_per_case", "integer", "Base units in one case (CS)", min_value=1),
        F("unit_cost", "decimal", "Standard cost per base unit", unit="USD", min_value=0.01),
        F("unit_price", "decimal", "Selling price per base unit (finished goods only)", unit="USD",
          required=False, rule="required for FINISHED_GOOD; > unit_cost"),
        F("abc_class", "string", "Derived Pareto class on annual demand value (A=80%, B=15%, C=5%)", allowed=ABC),
        F("lifecycle_status", "string", "Product lifecycle", allowed=SKU_LIFECYCLE),
        F("effective_from", "date", "First date the SKU can be sold/planned", rule=DATE_RULE),
        F("effective_to", "date", "Last date (PHASE_OUT only)", required=False,
          rule="required iff lifecycle_status = PHASE_OUT; >= effective_from"),
    ],
    lifecycle="NEW -> ACTIVE -> PHASE_OUT; no demand outside [effective_from, effective_to]",
))
_t(Table(
    "sku_location", "SKU-Location (bridge)", "input",
    "Bridge resolving the N:M SKU<->Location relationship; holds stocking policy.",
    "one row per stocked SKU at a location", "sku_location_id",
    [
        ID("sku_location_id", "Bridge identifier", r"^SL-\d{6}$"),
        FKF("sku_id", "Stocked SKU", P["sku_id"]),
        FKF("location_id", "Stocking location", P["location_id"]),
        F("planning_method", "string", "How supply is planned", allowed=PLANNING_METHODS),
        FKF("primary_supplier_id", "Primary supplier for purchased items", P["supplier_id"], required=False,
            rule="required iff planning_method in (PURCHASE, DEPENDENT_PURCHASE)"),
        F("safety_stock_qty", "integer", "Derived: ceil(z(ABC) * 0.3 * mean weekly demand * sqrt(lead-time weeks))",
          unit="base_uom", min_value=0),
        F("effective_from", "date", "Start of stocking", rule=DATE_RULE),
    ],
    foreign_keys=[
        ForeignKey(["sku_id"], "sku", ["sku_id"], "N:1"),
        ForeignKey(["location_id"], "location", ["location_id"], "N:1"),
        ForeignKey(["primary_supplier_id"], "supplier", ["supplier_id"], "N:1", optional=True),
    ],
    natural_key=["sku_id", "location_id"],
))
_t(Table(
    "supplier_sku", "Supplier-SKU (bridge)", "input",
    "Bridge resolving N:M Supplier<->SKU; purchasing terms (UoM, MOQ, multiple, price).",
    "one row per supplier offering a SKU", "supplier_sku_id",
    [
        ID("supplier_sku_id", "Bridge identifier", r"^SS-\d{6}$"),
        FKF("supplier_id", "Supplier", P["supplier_id"]),
        FKF("sku_id", "SKU", P["sku_id"]),
        F("supplier_priority", "integer", "1 = primary, 2+ = alternate", min_value=1),
        F("purchase_uom", "string", "Unit the supplier sells in", allowed=PURCHASE_UOMS),
        F("uom_conversion_factor", "decimal", "Base units per purchase unit", unit="base_uom/purchase_uom",
          min_value=0.0001, rule="CS => sku.units_per_case; same-as-base => 1"),
        F("min_order_qty", "integer", "Minimum order quantity (MOQ)", unit="purchase_uom", min_value=1),
        F("order_multiple", "integer", "Order quantity must be a multiple of this", unit="purchase_uom", min_value=1),
        F("unit_cost", "decimal", "Price per base unit", unit="USD", min_value=0.01),
        F("approval_status", "string", "Sourcing approval", allowed=["APPROVED"]),
        F("effective_from", "date", "Start of agreement", rule=DATE_RULE),
        F("effective_to", "date", "End of agreement", required=False, rule=">= effective_from"),
    ],
    foreign_keys=[
        ForeignKey(["supplier_id"], "supplier", ["supplier_id"], "N:1"),
        ForeignKey(["sku_id"], "sku", ["sku_id"], "N:1"),
    ],
    natural_key=["supplier_id", "sku_id"],
))
_t(Table(
    "lead_time", "LeadTime", "input",
    "Effective-dated lead time per supplier->location lane. Revisions add a new version; history is kept.",
    "one row per lane per version", "lead_time_id",
    [
        ID("lead_time_id", "Lead-time version identifier", r"^LT-\d{6}$"),
        FKF("supplier_id", "Shipping supplier", P["supplier_id"]),
        FKF("location_id", "Receiving location", P["location_id"]),
        F("version", "integer", "Version number within the lane (1 = original)", min_value=1),
        F("transport_mode", "string", "Standard mode", allowed=TRANSPORT_MODES),
        F("production_lead_days", "integer", "Order -> ship", unit="days", min_value=0),
        F("transit_days", "integer", "Ship -> receipt", unit="days", min_value=1),
        F("total_lead_days", "integer", "Derived: production_lead_days + transit_days", unit="days", min_value=1),
        F("expedite_transit_days", "integer", "Transit if expedited (air/priority)", unit="days", min_value=1,
          rule="<= transit_days"),
        F("expedite_premium_pct", "decimal", "Expedite surcharge as % of line value", unit="percent", min_value=0),
        F("effective_from", "date", "Version start", rule=DATE_RULE),
        F("effective_to", "date", "Version end (null = open)", required=False,
          rule="versions of a lane do not overlap; v(n).effective_to = v(n+1).effective_from - 1 day"),
    ],
    foreign_keys=[
        ForeignKey(["supplier_id"], "supplier", ["supplier_id"], "N:1"),
        ForeignKey(["location_id"], "location", ["location_id"], "N:1"),
    ],
    natural_key=["supplier_id", "location_id", "version"],
))
_t(Table(
    "supplier_capacity", "SupplierCapacity", "input",
    "Weekly shipping capacity per supplier across all SKUs, in base units, measured on PO ship week.",
    "one row per supplier per planning week", "supplier_capacity_id",
    [
        ID("supplier_capacity_id", "Capacity identifier", r"^SCAP-SUP-\d{4}-\d{4}W\d{2}$"),
        FKF("supplier_id", "Supplier", P["supplier_id"]),
        FKF("week_id", "Planning week", P["week_id"]),
        F("capacity_units", "integer", "Maximum base units the supplier can ship in the week", unit="base units",
          min_value=0),
    ],
    foreign_keys=[
        ForeignKey(["supplier_id"], "supplier", ["supplier_id"], "N:1"),
        ForeignKey(["week_id"], "calendar_week", ["week_id"], "N:1"),
    ],
    natural_key=["supplier_id", "week_id"],
))
_t(Table(
    "forecast_demand", "ForecastDemand", "input",
    "Independent weekly forecast demand per SKU-location (finished goods only).",
    "one row per SKU, location and week within the SKU's effective window", "demand_id",
    [
        ID("demand_id", "DEM-<sku>-<location>-<week>", P["demand_id"]),
        FKF("sku_id", "SKU", P["sku_id"]),
        FKF("location_id", "Location", P["location_id"]),
        FKF("week_id", "Planning week", P["week_id"]),
        F("forecast_qty", "integer", "Forecast quantity", unit="base_uom", min_value=0),
        F("uom", "string", "Must equal sku.base_uom", allowed=BASE_UOMS),
        F("forecast_version", "string", "Forecast release", allowed=["FV-2026-01"]),
    ],
    foreign_keys=[
        ForeignKey(["sku_id"], "sku", ["sku_id"], "N:1"),
        ForeignKey(["location_id"], "location", ["location_id"], "N:1"),
        ForeignKey(["week_id"], "calendar_week", ["week_id"], "N:1"),
        ForeignKey(["sku_id", "location_id"], "sku_location", ["sku_id", "location_id"], "N:1",
                   note="demand only for stocked SKU-locations"),
    ],
    natural_key=["sku_id", "location_id", "week_id"],
))
_t(Table(
    "inventory", "Inventory", "input",
    "Inventory snapshot at the as-of date: on-hand, quality hold and in-transit (linked to the PO line).",
    "one row per SKU-location-stock status (in-transit: per PO line)", "inventory_id",
    [
        ID("inventory_id", "Inventory record identifier", r"^INV-\d{6}$"),
        FKF("sku_id", "SKU", P["sku_id"]),
        FKF("location_id", "Location", P["location_id"]),
        F("snapshot_date", "date", "As-of date of the snapshot", rule="= planning as-of date"),
        F("stock_status", "string", "Availability status", allowed=STOCK_STATUS),
        F("quantity", "integer", "Quantity", unit="base_uom", min_value=0),
        F("uom", "string", "Must equal sku.base_uom", allowed=BASE_UOMS),
        FKF("po_line_id", "Inbound PO line (IN_TRANSIT only)", P["po_line_id"], required=False,
            rule="required iff stock_status = IN_TRANSIT; at most one IN_TRANSIT row per PO line"),
    ],
    foreign_keys=[
        ForeignKey(["sku_id"], "sku", ["sku_id"], "N:1"),
        ForeignKey(["location_id"], "location", ["location_id"], "N:1"),
        ForeignKey(["po_line_id"], "purchase_order_line", ["po_line_id"], "N:1", optional=True),
        ForeignKey(["sku_id", "location_id"], "sku_location", ["sku_id", "location_id"], "N:1"),
    ],
))
_t(Table(
    "purchase_order", "PurchaseOrder", "input",
    "Inbound purchase order header (one supplier -> one receiving location). Status is derived from events.",
    "one row per purchase order", "po_id",
    [
        ID("po_id", "PO-<year>-<counter>", P["po_id"]),
        FKF("supplier_id", "Supplier", P["supplier_id"]),
        FKF("location_id", "Receiving location", P["location_id"]),
        FKF("lead_time_id", "Lead-time version effective at order_date", r"^LT-\d{6}$"),
        F("order_date", "date", "Date the order is (or will be) released to the supplier", rule=DATE_RULE),
        F("ship_date", "date", "Planned ship date = order_date + production_lead_days", rule=">= order_date"),
        F("promised_receipt_date", "date", "order_date + total_lead_days of lead_time_id", rule=">= ship_date"),
        F("transport_delay_days", "integer", "Derived: sum of DELAY_REPORTED event delays", unit="days", min_value=0),
        F("expected_receipt_date", "date", "Derived: promised_receipt_date + transport_delay_days"),
        F("actual_receipt_date", "date", "Receipt date (RECEIVED only)", required=False,
          rule="required iff status = RECEIVED; < as-of date"),
        F("status", "string", "Derived: to_status of the latest event", allowed=PO_STATUS),
        F("line_count", "integer", "Derived: number of lines", min_value=1),
        F("total_base_qty", "integer", "Derived: sum(line.base_qty)", unit="base units", min_value=1),
        F("total_value", "decimal", "Derived: sum(line.line_value)", unit="USD", min_value=0),
        F("currency", "string", "Currency", allowed=["USD"]),
        F("created_at", "datetime", "Timestamp of the CREATED event"),
    ],
    foreign_keys=[
        ForeignKey(["supplier_id"], "supplier", ["supplier_id"], "N:1"),
        ForeignKey(["location_id"], "location", ["location_id"], "N:1"),
        ForeignKey(["lead_time_id"], "lead_time", ["lead_time_id"], "N:1"),
    ],
    lifecycle="PLANNED -> CONFIRMED -> IN_TRANSIT -> RECEIVED; PLANNED|CONFIRMED -> CANCELLED",
))
_t(Table(
    "purchase_order_line", "PurchaseOrder line", "input",
    "PO line: one SKU, ordered in the supplier's purchase UoM.",
    "one row per PO line", "po_line_id",
    [
        ID("po_line_id", "<po_id>-L<nn>", P["po_line_id"]),
        FKF("po_id", "Parent PO", P["po_id"]),
        F("line_number", "integer", "Line number within PO", min_value=1),
        FKF("sku_id", "SKU", P["sku_id"]),
        FKF("supplier_sku_id", "Purchasing terms used", r"^SS-\d{6}$",
            rule="supplier_sku.supplier_id = purchase_order.supplier_id and supplier_sku.sku_id = sku_id"),
        F("requested_qty", "integer", "Quantity the planner requested", unit="order_uom", min_value=1),
        F("order_qty", "integer", "Quantity confirmed by the supplier (capacity-limited suppliers may cut it)",
          unit="order_uom", min_value=1, rule="<= requested_qty; >= MOQ and multiple of order_multiple"),
        F("order_uom", "string", "Unit ordered in", allowed=PURCHASE_UOMS),
        F("uom_conversion_factor", "decimal", "Base units per order unit", min_value=0.0001),
        F("base_qty", "integer", "Derived: order_qty * uom_conversion_factor", unit="base_uom", min_value=1),
        F("base_uom", "string", "SKU base unit", allowed=BASE_UOMS),
        F("unit_cost", "decimal", "Price per base unit", unit="USD", min_value=0.01),
        F("line_value", "decimal", "Derived: base_qty * unit_cost", unit="USD", min_value=0),
    ],
    foreign_keys=[
        ForeignKey(["po_id"], "purchase_order", ["po_id"], "N:1"),
        ForeignKey(["sku_id"], "sku", ["sku_id"], "N:1"),
        ForeignKey(["supplier_sku_id"], "supplier_sku", ["supplier_sku_id"], "N:1"),
    ],
    natural_key=["po_id", "sku_id"],
))
_t(Table(
    "purchase_order_event", "PurchaseOrder event (history)", "input",
    "Append-only state-change history of purchase orders. History is never overwritten.",
    "one row per state change", "event_id",
    [
        ID("event_id", "Event identifier", r"^POE-\d{7}$"),
        FKF("po_id", "Purchase order", P["po_id"]),
        F("event_seq", "integer", "1-based sequence within the PO", min_value=1),
        F("event_type", "string", "Event", allowed=PO_EVENT_TYPES),
        F("from_status", "string", "Status before (null for CREATED)", required=False, allowed=PO_STATUS),
        F("to_status", "string", "Status after", allowed=PO_STATUS),
        F("event_timestamp", "datetime", "When it happened", rule="strictly increasing per PO; < as-of date"),
        F("actor", "string", "Who recorded it", allowed=ACTORS),
        F("delay_days", "integer", "Delay reported (DELAY_REPORTED only)", unit="days", min_value=0),
        F("note", "string", "Free text", required=False),
    ],
    foreign_keys=[ForeignKey(["po_id"], "purchase_order", ["po_id"], "N:1")],
    natural_key=["po_id", "event_seq"],
))
_t(Table(
    "bom", "BOM (bridge)", "input",
    "Bill of materials: N:M bridge between manufactured SKUs and component SKUs.",
    "one row per parent-component pair", "bom_id",
    [
        ID("bom_id", "BOM line identifier", r"^BOM-\d{6}$"),
        FKF("parent_sku_id", "Manufactured SKU (MAKE)", P["sku_id"]),
        FKF("component_sku_id", "Component SKU", P["sku_id"]),
        F("qty_per", "decimal", "Component base units per parent unit", min_value=0.0001),
        F("component_uom", "string", "Must equal component sku.base_uom", allowed=BASE_UOMS),
        F("effective_from", "date", "Start", rule=DATE_RULE),
        F("effective_to", "date", "End", required=False),
    ],
    foreign_keys=[
        ForeignKey(["parent_sku_id"], "sku", ["sku_id"], "N:1"),
        ForeignKey(["component_sku_id"], "sku", ["sku_id"], "N:1"),
    ],
    natural_key=["parent_sku_id", "component_sku_id"],
))
_t(Table(
    "production_capacity", "Production capacity", "input",
    "Weekly production capacity per plant (all manufactured SKUs), in base units.",
    "one row per plant per week", "production_capacity_id",
    [
        ID("production_capacity_id", "Capacity identifier", r"^PCAP-LOC-\d{3}-\d{4}W\d{2}$"),
        FKF("location_id", "Plant", P["location_id"], rule="location.location_type = PLANT"),
        FKF("week_id", "Week", P["week_id"]),
        F("capacity_units", "integer", "Max units producible", unit="base units", min_value=0),
    ],
    foreign_keys=[
        ForeignKey(["location_id"], "location", ["location_id"], "N:1"),
        ForeignKey(["week_id"], "calendar_week", ["week_id"], "N:1"),
    ],
    natural_key=["location_id", "week_id"],
))
_t(Table(
    "production_plan", "ProductionPlan", "input",
    "Planned production of manufactured SKUs per plant and week.",
    "one row per SKU, plant and week with production", "production_plan_id",
    [
        ID("production_plan_id", "PP-<year>-<counter>", r"^PP-\d{4}-\d{6}$"),
        FKF("sku_id", "Manufactured SKU", P["sku_id"], rule="sku.sourcing_type = MAKE"),
        FKF("location_id", "Plant", P["location_id"]),
        FKF("week_id", "Production week", P["week_id"]),
        F("required_qty", "integer", "Unconstrained requirement (before plant capacity)", unit="base_uom",
          min_value=1),
        F("planned_qty", "integer", "Capacity-constrained planned quantity", unit="base_uom", min_value=0,
          rule="<= required_qty; multiple of batch_size; plant total <= production_capacity"),
        F("batch_size", "integer", "Batch multiple", min_value=1),
        F("status", "string", "FIRM inside the 2-week frozen fence, else PLANNED", allowed=PRODUCTION_STATUS),
    ],
    foreign_keys=[
        ForeignKey(["sku_id"], "sku", ["sku_id"], "N:1"),
        ForeignKey(["location_id"], "location", ["location_id"], "N:1"),
        ForeignKey(["week_id"], "calendar_week", ["week_id"], "N:1"),
        ForeignKey(["sku_id", "location_id"], "sku_location", ["sku_id", "location_id"], "N:1"),
    ],
    natural_key=["sku_id", "location_id", "week_id"],
    lifecycle="PLANNED -> FIRM (inside frozen fence)",
))
_t(Table(
    "sku_substitute", "SKU substitute (bridge)", "input",
    "N:M self-bridge on SKU: which SKU may replace another. Only APPROVED and effective links are usable.",
    "one row per SKU-substitute pair", "substitution_id",
    [
        ID("substitution_id", "Substitution identifier", r"^SUB-\d{6}$"),
        FKF("sku_id", "SKU being substituted", P["sku_id"]),
        FKF("substitute_sku_id", "Replacement SKU", P["sku_id"], rule="!= sku_id; same base_uom"),
        F("conversion_ratio", "decimal", "Substitute units per original unit", min_value=0.0001),
        F("approval_status", "string", "Approval state", allowed=APPROVAL),
        F("approved_by", "string", "Approver role", required=False, allowed=["PLANNER", "OPERATIONS_MANAGER"],
          rule="required iff APPROVED"),
        F("approval_date", "date", "Approval date", required=False, rule="required iff APPROVED"),
        F("effective_from", "date", "Start", rule=DATE_RULE),
        F("effective_to", "date", "End", required=False),
        F("priority", "integer", "Preference order", min_value=1),
    ],
    foreign_keys=[
        ForeignKey(["sku_id"], "sku", ["sku_id"], "N:1"),
        ForeignKey(["substitute_sku_id"], "sku", ["sku_id"], "N:1"),
    ],
    natural_key=["sku_id", "substitute_sku_id"],
    lifecycle="PENDING -> APPROVED | REJECTED",
))

# =========================================================== OUTPUT (derived) layer
_t(Table(
    "scheduled_receipt", "Scheduled receipt (derived)", "output",
    "Every open PO line as used by the plan, with any correction applied (source rows are never modified).",
    "one row per open PO line", "po_line_id",
    [
        ID("po_line_id", "PO line", P["po_line_id"]),
        FKF("po_id", "PO", P["po_id"]),
        FKF("sku_id", "SKU", P["sku_id"]),
        FKF("location_id", "Receiving location", P["location_id"]),
        FKF("supplier_id", "Supplier", P["supplier_id"]),
        F("po_status", "string", "PO status", allowed=PO_STATUS),
        F("source_base_qty", "integer", "base_qty as recorded on the line", min_value=0),
        F("planning_base_qty", "integer", "Quantity used in the plan after UoM correction", min_value=0),
        F("source_receipt_date", "date", "expected_receipt_date as recorded"),
        F("planning_receipt_date", "date", "Receipt date used after lead-time / capacity corrections"),
        F("ship_week_index", "integer", "Week index the supplier ships (capacity bucket)", required=False),
        F("receipt_week_index", "integer", "Week index of planning receipt"),
        F("adjustment_codes", "string", "Pipe-separated corrections applied", required=False),
        F("counted_in_plan", "boolean", "False if cancelled, outside horizon or unconvertible"),
    ],
    foreign_keys=[
        ForeignKey(["po_line_id"], "purchase_order_line", ["po_line_id"], "1:1"),
        ForeignKey(["po_id"], "purchase_order", ["po_id"], "N:1"),
    ],
))
_t(Table(
    "projected_balance", "Projected available balance (derived)", "output",
    "Week-by-week projected available balance (PAB). closing = opening + receipts + production - demand - dependent demand.",
    "one row per SKU-location-week", "pab_id",
    [
        ID("pab_id", "PAB-<sku>-<location>-<week>", r"^PAB-SKU-\d{6}-LOC-\d{3}-\d{4}W\d{2}$"),
        FKF("sku_id", "SKU", P["sku_id"]),
        FKF("location_id", "Location", P["location_id"]),
        FKF("week_id", "Week", P["week_id"]),
        F("week_index", "integer", "Week offset", min_value=0),
        F("opening_balance", "integer", "Previous closing (week 0: available on-hand)", unit="base_uom"),
        F("forecast_demand", "integer", "Independent demand", unit="base_uom", min_value=0),
        F("dependent_demand", "integer", "BOM-exploded demand from production", unit="base_uom", min_value=0),
        F("scheduled_receipts", "integer", "Sum of counted scheduled_receipt rows", unit="base_uom", min_value=0),
        F("planned_production", "integer", "Sum of production_plan", unit="base_uom", min_value=0),
        F("closing_balance", "integer", "Projected available balance; negative = backlog", unit="base_uom"),
        F("safety_stock_qty", "integer", "Safety stock", unit="base_uom", min_value=0),
        F("below_safety_stock", "boolean", "closing_balance < safety_stock_qty"),
        F("is_shortage", "boolean", "closing_balance < 0"),
    ],
    foreign_keys=[
        ForeignKey(["sku_id", "location_id"], "sku_location", ["sku_id", "location_id"], "N:1"),
        ForeignKey(["week_id"], "calendar_week", ["week_id"], "N:1"),
    ],
    natural_key=["sku_id", "location_id", "week_id"],
))
_t(Table(
    "shortage", "Shortage (derived)", "output",
    "Shortage episode: consecutive weeks with negative projected balance for a SKU-location.",
    "one row per shortage episode", "shortage_id",
    [
        ID("shortage_id", "SHORT-<year>-<counter>, numbered in priority order", P["shortage_id"]),
        FKF("sku_id", "SKU", P["sku_id"]),
        FKF("location_id", "Location", P["location_id"]),
        FKF("start_week_id", "First negative week", P["week_id"]),
        FKF("end_week_id", "Last negative week", P["week_id"]),
        F("start_week_index", "integer", "", min_value=0),
        F("end_week_index", "integer", "", min_value=0),
        F("duration_weeks", "integer", "end - start + 1", min_value=1),
        F("shortage_qty", "integer", "Peak deficit = -min(closing_balance) in the episode", unit="base_uom", min_value=1),
        F("shortage_value", "decimal", "shortage_qty * unit_price (components: 2 * unit_cost)", unit="USD"),
        F("lead_time_weeks", "integer", "First week index a normal action can land: week of (as-of + primary lane "
          "total_lead_days) for purchased items; frozen fence (2) for manufactured items", min_value=0),
        F("within_lead_time", "boolean", "start_week_index < lead_time_weeks: cannot be fixed by a normal order"),
        F("priority_score", "decimal", "0-100 weighted score (value, urgency, ABC, duration)", min_value=0, max_value=100),
        F("priority_rank", "integer", "1 = most urgent", min_value=1, unique=True),
        F("priority_tier", "string", "Tier", allowed=PRIORITY_TIERS),
        F("primary_cause_code", "string", "Largest-contribution cause", allowed=CAUSE_CODES),
        F("cause_summary", "string", "Human-readable explanation with reconciliation arithmetic"),
        F("status", "string", "Derived from mitigation coverage", allowed=SHORTAGE_STATUS),
    ],
    foreign_keys=[ForeignKey(["sku_id", "location_id"], "sku_location", ["sku_id", "location_id"], "N:1")],
))
_t(Table(
    "shortage_cause", "Shortage cause (derived)", "output",
    "Explainable causes of each shortage with quantified contribution and evidence record IDs.",
    "one row per cause per shortage", "shortage_cause_id",
    [
        ID("shortage_cause_id", "SC-<shortage_id>-<nn>", r"^SC-SHORT-\d{4}-\d{6}-\d{2}$"),
        FKF("shortage_id", "Shortage", P["shortage_id"]),
        F("cause_seq", "integer", "Order (1 = primary)", min_value=1),
        F("cause_code", "string", "Cause", allowed=CAUSE_CODES),
        F("contribution_qty", "integer", "Quantified effect on the deficit", unit="base_uom", min_value=0),
        F("evidence_record_type", "string", "Table holding the evidence"),
        F("evidence_record_ids", "string", "Pipe-separated record IDs", required=False),
        F("explanation", "string", "Plain-language explanation"),
    ],
    foreign_keys=[ForeignKey(["shortage_id"], "shortage", ["shortage_id"], "N:1")],
    natural_key=["shortage_id", "cause_seq"],
))
_t(Table(
    "mitigation_option", "MitigationOption (derived)", "output",
    "Feasible mitigation alternatives per shortage with cost / service trade-offs. All pass policy and capacity checks.",
    "one row per feasible option", "mitigation_id",
    [
        ID("mitigation_id", "MIT-<shortage_id>-<nn> (nn = option rank)", P["mitigation_id"]),
        FKF("shortage_id", "Shortage", P["shortage_id"]),
        F("option_rank", "integer", "1 = best net benefit", min_value=1),
        F("mitigation_type", "string", "Action", allowed=MITIGATION_TYPES),
        FKF("supplier_id", "Supplier used", P["supplier_id"], required=False),
        FKF("po_id", "PO expedited", P["po_id"], required=False),
        FKF("source_location_id", "Transfer source", P["location_id"], required=False),
        FKF("substitute_sku_id", "Substitute used", P["sku_id"], required=False),
        FKF("substitution_id", "Approved substitution link", r"^SUB-\d{6}$", required=False),
        F("proposed_qty", "integer", "Quantity moved/ordered", unit="base_uom", min_value=0),
        F("order_qty_purchase_uom", "integer", "Order quantity in purchase UoM (POs)", required=False),
        F("arrival_week_index", "integer", "Week the quantity becomes available", required=False),
        F("covered_qty", "integer", "min(proposed_qty, shortage_qty)", unit="base_uom", min_value=0),
        F("residual_shortage_qty", "integer", "shortage_qty - covered_qty", unit="base_uom", min_value=0),
        F("fill_rate_pct", "decimal", "covered / shortage", unit="percent", min_value=0, max_value=100),
        F("weeks_late", "integer", "max(0, arrival - start week)", min_value=0),
        F("service_score", "decimal", "fill_rate * max(0, 1 - 0.15 * weeks_late)", min_value=0, max_value=1),
        F("total_cost", "decimal", "Cash cost of the action", unit="USD", min_value=0),
        F("incremental_cost", "decimal", "Premium over normal replenishment (or lost margin for backorder)",
          unit="USD", min_value=0),
        F("net_benefit", "decimal", "service_score * shortage_value - incremental_cost", unit="USD"),
        F("capacity_available", "integer", "Capacity/surplus available before this option", required=False),
        F("capacity_consumed", "integer", "Capacity/surplus this option would use", required=False),
        F("lead_time_days", "integer", "Lead time applied", required=False),
        F("moq_check", "string", "PASS / N/A", allowed=["PASS", "N/A"]),
        F("lead_time_check", "string", "PASS / N/A", allowed=["PASS", "N/A"]),
        F("approval_check", "string", "PASS / N/A", allowed=["PASS", "N/A"]),
        F("capacity_check", "string", "PASS / N/A", allowed=["PASS", "N/A"]),
        F("is_recommended", "boolean", "Highest net benefit (capacity reserved)"),
        F("rationale", "string", "Explanation"),
    ],
    foreign_keys=[
        ForeignKey(["shortage_id"], "shortage", ["shortage_id"], "N:1"),
        ForeignKey(["supplier_id"], "supplier", ["supplier_id"], "N:1", optional=True),
        ForeignKey(["po_id"], "purchase_order", ["po_id"], "N:1", optional=True),
        ForeignKey(["source_location_id"], "location", ["location_id"], "N:1", optional=True),
        ForeignKey(["substitute_sku_id"], "sku", ["sku_id"], "N:1", optional=True),
        ForeignKey(["substitution_id"], "sku_substitute", ["substitution_id"], "N:1", optional=True),
    ],
))
_t(Table(
    "rejected_mitigation", "Rejected mitigation (derived, audit)", "output",
    "Candidates that were considered and rejected, with the policy or constraint that failed.",
    "one row per rejected candidate", "rejection_id",
    [
        ID("rejection_id", "REJ-<shortage_id>-<nn>", r"^REJ-SHORT-\d{4}-\d{6}-\d{2}$"),
        FKF("shortage_id", "Shortage", P["shortage_id"]),
        F("mitigation_type", "string", "Candidate type", allowed=MITIGATION_TYPES),
        F("candidate_ref", "string", "Supplier / location / substitution / PO considered"),
        F("reason_code", "string", "Failed rule", allowed=REJECTION_REASONS),
        F("detail", "string", "Explanation"),
    ],
    foreign_keys=[ForeignKey(["shortage_id"], "shortage", ["shortage_id"], "N:1")],
))
_t(Table(
    "detected_issue", "Detected data/plan issue (derived)", "output",
    "Exceptions detected by the planning engine's data-quality screen, with the decision taken.",
    "one row per detected issue", "issue_id",
    [
        ID("issue_id", "ISS-<year>-<counter>", r"^ISS-\d{4}-\d{6}$"),
        F("issue_type", "string", "Issue", allowed=ISSUE_TYPES),
        F("severity", "string", "Severity", allowed=SEVERITY),
        F("record_type", "string", "Table of the offending record"),
        F("record_id", "string", "Offending record ID"),
        F("related_record_ids", "string", "Pipe-separated related IDs", required=False),
        F("sku_id", "string", "SKU", required=False),
        F("location_id", "string", "Location", required=False),
        F("supplier_id", "string", "Supplier", required=False),
        F("week_id", "string", "Week", required=False),
        F("decision", "string", "Action taken by the engine"),
        F("impact_qty", "integer", "Quantity affected", required=False),
        F("detail", "string", "Explanation"),
    ],
))
_t(Table(
    "supplier_capacity_utilization", "Supplier capacity utilisation (derived)", "output",
    "Committed open-PO load and mitigation reservations versus supplier capacity per week.",
    "one row per supplier-week", "supplier_capacity_id",
    [
        ID("supplier_capacity_id", "Capacity row", r"^SCAP-SUP-\d{4}-\d{4}W\d{2}$"),
        FKF("supplier_id", "Supplier", P["supplier_id"]),
        FKF("week_id", "Week", P["week_id"]),
        F("capacity_units", "integer", "Capacity", min_value=0),
        F("source_committed_units", "integer", "Load as recorded in source POs", min_value=0),
        F("planned_committed_units", "integer", "Load after capacity deferral", min_value=0),
        F("mitigation_reserved_units", "integer", "Reserved by recommended mitigations", min_value=0),
        F("utilization_pct", "decimal", "(planned + reserved) / capacity", unit="percent", min_value=0),
        F("source_over_capacity", "boolean", "source_committed_units > capacity_units"),
    ],
    foreign_keys=[ForeignKey(["supplier_capacity_id"], "supplier_capacity", ["supplier_capacity_id"], "1:1")],
))
_t(Table(
    "production_capacity_utilization", "Production capacity utilisation (derived)", "output",
    "Planned production plus mitigation reservations versus plant capacity per week.",
    "one row per plant-week", "production_capacity_id",
    [
        ID("production_capacity_id", "Capacity row", r"^PCAP-LOC-\d{3}-\d{4}W\d{2}$"),
        FKF("location_id", "Plant", P["location_id"]),
        FKF("week_id", "Week", P["week_id"]),
        F("capacity_units", "integer", "Capacity", min_value=0),
        F("planned_units", "integer", "Planned production", min_value=0),
        F("mitigation_reserved_units", "integer", "Reserved by recommended mitigations", min_value=0),
        F("utilization_pct", "decimal", "(planned + reserved) / capacity", unit="percent", min_value=0),
    ],
    foreign_keys=[ForeignKey(["production_capacity_id"], "production_capacity", ["production_capacity_id"], "1:1")],
))

# =========================================================== GROUND TRUTH (separate)
_t(Table(
    "ground_truth", "Ground truth (separate, never an input)", "ground_truth",
    "Labels for injected edge cases and generator scenario drivers. Stored outside the input folder.",
    "one row per labelled record", "gt_id",
    [
        ID("gt_id", "Label identifier", r"^GT-\d{6}$"),
        F("label_category", "string", "Edge case or scenario driver", allowed=LABEL_CATEGORIES),
        F("issue_type", "string", "Label", allowed=ISSUE_TYPES),
        F("record_type", "string", "Table of the labelled record"),
        F("record_id", "string", "Labelled record ID"),
        F("related_record_ids", "string", "Pipe-separated traceability IDs", required=False),
        F("sku_id", "string", "SKU", required=False),
        F("location_id", "string", "Location", required=False),
        F("supplier_id", "string", "Supplier", required=False),
        F("week_id", "string", "Week", required=False),
        F("expected_decision", "string", "What a correct planner/engine must do"),
        F("expected_value", "string", "Expected corrected value", required=False),
        F("rule_reference", "string", "Documented rule (docs/edge_cases.md)"),
        F("description", "string", "Explanation"),
    ],
))

INPUT_TABLES = [n for n, t in TABLES.items() if t.layer == "input"]
OUTPUT_TABLES = [n for n, t in TABLES.items() if t.layer == "output"]
# Column names that must never appear in input tables (label leakage guard).
LEAKAGE_COLUMNS = {"issue_type", "ground_truth", "label", "is_anomaly", "expected_decision",
                   "label_category", "gt_id", "is_spike", "is_constrained"}
