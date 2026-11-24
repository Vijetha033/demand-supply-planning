"""Deterministic, zero-padded, immutable identifiers (brief section 4)."""
from __future__ import annotations


def sku_id(n: int) -> str:
    return f"SKU-{n:06d}"


def location_id(n: int) -> str:
    return f"LOC-{n:03d}"


def supplier_id(n: int) -> str:
    return f"SUP-{n:04d}"


def demand_id(sku: str, loc: str, week: str) -> str:
    return f"DEM-{sku}-{loc}-{week}"


def po_id(year: int, n: int) -> str:
    return f"PO-{year}-{n:06d}"


def po_line_id(po: str, line: int) -> str:
    return f"{po}-L{line:02d}"


def shortage_id(year: int, n: int) -> str:
    return f"SHORT-{year}-{n:06d}"


def mitigation_id(shortage: str, n: int) -> str:
    return f"MIT-{shortage}-{n:02d}"


def seq_id(prefix: str, n: int, width: int = 6) -> str:
    return f"{prefix}-{n:0{width}d}"


# Regular expressions used by validation (single source of truth).
PATTERNS = {
    "sku_id": r"^SKU-\d{6}$",
    "location_id": r"^LOC-\d{3}$",
    "supplier_id": r"^SUP-\d{4}$",
    "week_id": r"^\d{4}W\d{2}$",
    "demand_id": r"^DEM-SKU-\d{6}-LOC-\d{3}-\d{4}W\d{2}$",
    "po_id": r"^PO-\d{4}-\d{6}$",
    "po_line_id": r"^PO-\d{4}-\d{6}-L\d{2}$",
    "shortage_id": r"^SHORT-\d{4}-\d{6}$",
    "mitigation_id": r"^MIT-SHORT-\d{4}-\d{6}-\d{2}$",
}
