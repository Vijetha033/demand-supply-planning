"""Deterministic table I/O (CSV / JSON / SQL) and checksums.

Determinism rules: stable row order (sorted by primary key at write time),
'\n' line endings, gzip with mtime=0 and no embedded filename, no timestamps
inside data files.  Same seed => byte-identical files.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
from pathlib import Path

import pandas as pd

from .schema import TABLES, Table


# --------------------------------------------------------------------- helpers
def _open_write(path: Path, compress: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    if compress:
        raw = open(str(path) + ".gz", "wb")
        return gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0), raw
    return open(path, "wb"), None


def _write_bytes(path: Path, data: bytes, compress: bool) -> Path:
    fh, raw = _open_write(path, compress)
    fh.write(data)
    fh.close()
    if raw is not None:
        raw.close()
        return Path(str(path) + ".gz")
    return path


def order_columns(df: pd.DataFrame, table: str) -> pd.DataFrame:
    spec = TABLES[table]
    missing = [c for c in spec.columns if c not in df.columns]
    if missing:
        raise ValueError(f"{table}: missing columns {missing}")
    out = df[spec.columns]
    return out.sort_values(spec.primary_key, kind="mergesort").reset_index(drop=True)


def _clean_value(v):
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v):
            return None
        return round(v, 4)
    if hasattr(v, "item"):          # numpy scalar
        return _clean_value(v.item())
    if v is pd.NA:
        return None
    return v


def to_records(df: pd.DataFrame) -> list[dict]:
    cols = list(df.columns)
    out = []
    for row in df.itertuples(index=False, name=None):
        out.append({c: _clean_value(v) for c, v in zip(cols, row)})
    return out


# --------------------------------------------------------------------- writers
def write_csv(df: pd.DataFrame, path: Path, compress: bool = False) -> Path:
    buf = io.StringIO()
    df.to_csv(buf, index=False, lineterminator="\n")
    return _write_bytes(path, buf.getvalue().encode("utf-8"), compress)


def write_json(df: pd.DataFrame, path: Path, compress: bool = False) -> Path:
    data = json.dumps(to_records(df), ensure_ascii=False, separators=(",", ":"))
    return _write_bytes(path, data.encode("utf-8"), compress)


SQL_TYPES = {"string": "TEXT", "integer": "INTEGER", "decimal": "REAL", "date": "TEXT",
             "datetime": "TEXT", "boolean": "INTEGER"}


def ddl_for(table: Table) -> str:
    lines = []
    for f in table.fields:
        col = f"    {f.name} {SQL_TYPES[f.dtype]}"
        if f.name == table.primary_key:
            col += " PRIMARY KEY"
        elif f.required:
            col += " NOT NULL"
        if f.allowed and f.dtype == "string":
            vals = ", ".join("'" + a + "'" for a in f.allowed)
            col += f" CHECK ({f.name} IS NULL OR {f.name} IN ({vals}))"
        lines.append(col)
    for fk in table.foreign_keys:
        if fk.ref_table not in TABLES:
            continue
        ref = TABLES[fk.ref_table]
        # SQLite requires the parent key to be the PK or have a UNIQUE index.
        if fk.ref_columns != [ref.primary_key] and not ref.natural_key == fk.ref_columns:
            continue
        lines.append(f"    FOREIGN KEY ({', '.join(fk.columns)}) REFERENCES {fk.ref_table} "
                     f"({', '.join(fk.ref_columns)})")
    body = ",\n".join(lines)
    stmt = f"CREATE TABLE {table.name} (\n{body}\n);"
    if table.natural_key:
        stmt += (f"\nCREATE UNIQUE INDEX ux_{table.name}_nk ON {table.name} "
                 f"({', '.join(table.natural_key)});")
    return stmt


def _sql_literal(v) -> str:
    v = _clean_value(v)
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def sql_inserts(df: pd.DataFrame, table: str, batch: int = 500) -> str:
    cols = ", ".join(df.columns)
    rows = [f"({', '.join(_sql_literal(v) for v in r)})" for r in df.itertuples(index=False, name=None)]
    parts = []
    for i in range(0, len(rows), batch):
        parts.append(f"INSERT INTO {table} ({cols}) VALUES\n" + ",\n".join(rows[i:i + batch]) + ";")
    return "\n".join(parts)


# --------------------------------------------------------------------- readers
def find_file(directory: Path, name: str, ext: str = "csv") -> Path | None:
    for cand in (directory / f"{name}.{ext}", directory / f"{name}.{ext}.gz"):
        if cand.exists():
            return cand
    return None


def read_table(directory: Path, name: str) -> pd.DataFrame:
    path = find_file(Path(directory), name)
    if path is None:
        raise FileNotFoundError(f"{name}.csv not found in {directory}")
    spec = TABLES.get(name)
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    if spec is None:
        return df
    for f in spec.fields:
        if f.name not in df.columns:
            continue
        s = df[f.name]
        if f.dtype == "integer":
            df[f.name] = pd.to_numeric(s).astype("Int64")
        elif f.dtype == "decimal":
            df[f.name] = pd.to_numeric(s).astype(float)
        elif f.dtype == "boolean":
            df[f.name] = s.map({"True": True, "False": False, "1": True, "0": False}).astype("boolean")
        else:
            df[f.name] = s.astype(object).where(s.notna(), None)
    return df


def read_tables(directory: Path, names: list[str]) -> dict[str, pd.DataFrame]:
    return {n: read_table(directory, n) for n in names}


# --------------------------------------------------------------------- checksums
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_rows(path: Path) -> int | None:
    name = path.name
    if name.endswith(".csv") or name.endswith(".csv.gz"):
        opener = gzip.open if name.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as fh:
            return max(0, sum(1 for _ in fh) - 1)
    return None
