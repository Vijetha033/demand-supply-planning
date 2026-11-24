"""Generate the data dictionary (Markdown + JSON) and SQL DDL from schema.py."""
from __future__ import annotations

import json
from pathlib import Path

from .io import ddl_for
from .schema import TABLES

LAYER_TITLE = {"input": "Input (source) tables", "output": "Derived planning outputs",
               "ground_truth": "Ground truth (separate folder, never an input)"}


def _md_escape(s) -> str:
    return "" if s is None else str(s).replace("|", "\\|")


def data_dictionary_markdown() -> str:
    out = ["# Data dictionary", "",
           "Generated from `src/supply_planning/schema.py` (single source of truth used by the generator, "
           "validator and SQL exporter). Regenerate with `python -m supply_planning docs`.", "",
           "Conventions: dates are ISO-8601 `YYYY-MM-DD`; timestamps `YYYY-MM-DDTHH:MM:SS`; quantities are in "
           "the SKU base unit unless the unit column says otherwise; money is USD; booleans are `True/False`.", ""]
    for layer in ("input", "output", "ground_truth"):
        out += [f"## {LAYER_TITLE[layer]}", ""]
        for t in TABLES.values():
            if t.layer != layer:
                continue
            out += [f"### `{t.name}` - {t.entity}", "", t.description, "",
                    f"- **Grain:** {t.grain}", f"- **Primary key:** `{t.primary_key}`"]
            if t.natural_key:
                out.append(f"- **Natural key (unique):** `{', '.join(t.natural_key)}`")
            for fk in t.foreign_keys:
                opt = " (optional)" if fk.optional else ""
                note = f" - {fk.note}" if fk.note else ""
                out.append(f"- **FK** `{', '.join(fk.columns)}` -> `{fk.ref_table}({', '.join(fk.ref_columns)})` "
                           f"{fk.cardinality}{opt}{note}")
            if t.lifecycle:
                out.append(f"- **Lifecycle:** {t.lifecycle}")
            out += ["", "| Field | Type | Req. | Unique | Allowed values | Unit | Validation rule | Description |",
                    "|---|---|---|---|---|---|---|---|"]
            for f in t.fields:
                rule = [x for x in [f"pattern `{f.pattern}`" if f.pattern else None,
                                    f">= {f.min_value:g}" if f.min_value is not None else None,
                                    f"<= {f.max_value:g}" if f.max_value is not None else None, f.rule] if x]
                allowed = ", ".join(f.allowed) if f.allowed else ""
                pk = " (PK)" if f.name == t.primary_key else ""
                out.append(f"| `{f.name}`{pk} | {f.dtype} | {'yes' if f.required else 'no'} | "
                           f"{'yes' if f.unique or f.name == t.primary_key else 'no'} | {_md_escape(allowed)} | "
                           f"{_md_escape(f.unit or '')} | {_md_escape('; '.join(rule))} | {_md_escape(f.description)} |")
            out.append("")
    return "\n".join(out)


def data_dictionary_json() -> dict:
    res = {}
    for t in TABLES.values():
        res[t.name] = dict(
            entity=t.entity, layer=t.layer, description=t.description, grain=t.grain, primary_key=t.primary_key,
            natural_key=t.natural_key, lifecycle=t.lifecycle,
            foreign_keys=[dict(columns=fk.columns, ref_table=fk.ref_table, ref_columns=fk.ref_columns,
                               cardinality=fk.cardinality, optional=fk.optional) for fk in t.foreign_keys],
            fields=[dict(name=f.name, type=f.dtype, required=f.required, unique=f.unique or f.name == t.primary_key,
                         allowed_values=f.allowed, unit=f.unit, pattern=f.pattern, min=f.min_value, max=f.max_value,
                         rule=f.rule, description=f.description) for f in t.fields])
    return res


def schema_sql(tables: list[str]) -> str:
    head = ["-- Generated from src/supply_planning/schema.py", "PRAGMA foreign_keys = ON;", ""]
    return "\n".join(head + [ddl_for(TABLES[n]) + "\n" for n in tables])


def write_docs(docs_dir: Path) -> list[Path]:
    docs_dir.mkdir(parents=True, exist_ok=True)
    p1 = docs_dir / "data_dictionary.md"
    p1.write_text(data_dictionary_markdown())
    p2 = docs_dir / "data_dictionary.json"
    p2.write_text(json.dumps(data_dictionary_json(), indent=2))
    return [p1, p2]
