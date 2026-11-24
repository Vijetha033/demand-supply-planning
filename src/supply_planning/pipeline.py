"""End-to-end pipeline: generate -> inject edge cases -> export inputs + ground
truth -> plan (reading inputs back from disk) -> validate -> evaluate ->
JSON/SQL exports -> manifest.

Folder layout for a scale ``<s>`` under the project root:

    data/raw/<s>/                 input tables (CSV)            <- planning reads ONLY this
    data/ground_truth/<s>/        ground_truth.csv / .json      <- evaluation only
    data/processed/<s>/           planning outputs (CSV)
    data/exports/<s>/json/        every table as JSON
    data/exports/<s>/sql/         schema.sql + seed.sql (SQLite-compatible)
    outputs/<s>/                  manifest, validation summary, evaluation report
"""
from __future__ import annotations

import json
import platform
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .config import PROJECT_ROOT, ScaleConfig
from .docs_gen import schema_sql
from .edge_cases import inject_edge_cases
from .evaluation import evaluate
from .generator import BaselineGenerator
from .io import (count_rows, order_columns, read_table, sha256_file, sql_inserts, write_csv, write_json,
                 _write_bytes)
from .planning import run_planning
from .schema import INPUT_TABLES, OUTPUT_TABLES, TABLES
from .validation import Validator


@dataclass
class Paths:
    root: Path
    scale: str

    @property
    def raw(self): return self.root / "data" / "raw" / self.scale

    @property
    def gt(self): return self.root / "data" / "ground_truth" / self.scale

    @property
    def processed(self): return self.root / "data" / "processed" / self.scale

    @property
    def exports(self): return self.root / "data" / "exports" / self.scale

    @property
    def outputs(self): return self.root / "outputs" / self.scale

    def data_dirs(self):
        return [self.raw, self.gt, self.processed, self.exports]


def _fresh(d: Path):
    """Remove a previously *generated* folder for this scale (never anything else)."""
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)


def generator_command(cfg: ScaleConfig) -> str:
    return f"python -m supply_planning run --scale {cfg.name} --seed {cfg.seed}"


# ---------------------------------------------------------------------- stages
def build_inputs(cfg: ScaleConfig, log=print):
    t0 = time.time()
    tables, hidden = BaselineGenerator(cfg).run()
    log(f"  baseline generated in {time.time() - t0:.1f}s")
    baseline_state = run_planning(tables)
    log(f"  baseline plan: {len(baseline_state.out['shortage'])} shortages (used to target edge cases)")
    tables, gt = inject_edge_cases(tables, hidden, cfg, baseline_state)
    log(f"  injected {int((gt.label_category == 'EDGE_CASE').sum())} edge cases; "
        f"{int((gt.label_category == 'SCENARIO').sum())} scenario labels")
    return tables, gt


def write_tables(tables: dict, names: list[str], directory: Path, compress: bool) -> list[Path]:
    paths = []
    for n in names:
        paths.append(write_csv(order_columns(tables[n], n), directory / f"{n}.csv", compress))
    return paths


def export_json_sql(tables: dict, gt: pd.DataFrame, P: Paths, compress: bool) -> list[Path]:
    paths = []
    for n in INPUT_TABLES + OUTPUT_TABLES:
        paths.append(write_json(order_columns(tables[n], n), P.exports / "json" / f"{n}.json", compress))
    sql_dir = P.exports / "sql"
    sql_dir.mkdir(parents=True, exist_ok=True)
    order = dependency_order(INPUT_TABLES) + dependency_order(OUTPUT_TABLES)
    p = sql_dir / "schema.sql"
    p.write_text(schema_sql(order))
    paths.append(p)
    body = ["-- Seed data. Load after schema.sql (e.g. sqlite3 db < schema.sql; sqlite3 db < seed.sql)",
            "PRAGMA foreign_keys = ON;", "BEGIN;"]
    for n in order:
        body.append(sql_inserts(order_columns(tables[n], n), n))
    body.append("COMMIT;")
    paths.append(_write_bytes(sql_dir / "seed.sql", "\n".join(body).encode("utf-8"), compress))
    return paths


def dependency_order(names: list[str]) -> list[str]:
    deps = {n: {fk.ref_table for fk in TABLES[n].foreign_keys if fk.ref_table in names and fk.ref_table != n}
            for n in names}
    out, seen = [], set()

    def visit(n):
        if n in seen:
            return
        seen.add(n)
        for d in sorted(deps[n]):
            visit(d)
        out.append(n)
    for n in names:
        visit(n)
    return out


# ---------------------------------------------------------------------- reports
def _jsonable(o):
    if isinstance(o, pd.DataFrame):
        return o.astype(object).where(o.notna(), None).to_dict("records")
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(x) for x in o]
    return o


def write_validation_report(summary: dict, P: Paths) -> None:
    P.outputs.mkdir(parents=True, exist_ok=True)
    checks, viol = summary["checks"], summary["violations"]
    (P.outputs / "validation_summary.json").write_text(json.dumps(_jsonable(
        {k: v for k, v in summary.items() if k != "violations"}), indent=2))
    write_csv(viol, P.outputs / "validation_violations.csv")
    lines = [f"# Validation summary - `{P.scale}`", "",
             f"- Overall status: **{summary['overall_status']}**",
             f"- Checks run: {summary['n_checks']}",
             f"- Violations: {summary['n_violations']} "
             f"({summary['n_expected_labelled']} expected - every one points at a labelled edge-case record; "
             f"{summary['n_unexpected']} unexpected)", "",
             "Expected violations are the deliberately injected edge cases: the validator finds them and "
             "matches each to its `ground_truth` label. Any unexpected violation fails the run.", "",
             "## By category", "", "| Category | Checks | Rows checked | Violations | Expected (labelled) | "
             "Unexpected | Status |", "|---|---|---|---|---|---|---|"]
    for cat, g in checks.groupby("category", sort=True):
        st = "FAIL" if g.unexpected.sum() else ("PASS_WITH_LABELLED_EXCEPTIONS" if g.violations.sum() else "PASS")
        lines.append(f"| {cat} | {len(g)} | {int(g.rows_checked.sum()):,} | {int(g.violations.sum())} | "
                     f"{int(g.expected_labelled.sum())} | {int(g.unexpected.sum())} | {st} |")
    lines += ["", "## All checks", "", "| Check | Category | Rows | Violations | Expected | Unexpected | Status | "
              "Description |", "|---|---|---|---|---|---|---|---|"]
    for r in checks.itertuples():
        lines.append(f"| `{r.check}` | {r.category} | {r.rows_checked:,} | {r.violations} | {r.expected_labelled} | "
                     f"{r.unexpected} | {r.status} | {r.description} |")
    if len(viol):
        lines += ["", "## Violations", "", "| Check | Table | Record | Classification | Detail |", "|---|---|---|---|---|"]
        for r in viol.head(200).itertuples():
            lines.append(f"| `{r.check}` | {r.table} | `{r.record_id}` | {r.classification} | {r.detail} |")
    (P.outputs / "validation_summary.md").write_text("\n".join(lines) + "\n")


def write_evaluation_report(ev: dict, P: Paths, cfg: ScaleConfig) -> None:
    (P.outputs / "evaluation_report.json").write_text(json.dumps(_jsonable(ev), indent=2))
    k = ev["planning_kpis"]
    d = ev["detection_metrics"]
    lines = [f"# Evaluation report - `{P.scale}`", "",
             f"Seed `{cfg.seed}`. Engine outputs compared against `data/ground_truth/{P.scale}/ground_truth.csv`.",
             "", "## Exception detection vs ground truth", "",
             f"- Edge-case recall **{ev['edge_case_recall']:.0%}**, precision **{ev['edge_case_precision']:.0%}**, "
             f"decision accuracy **{ev['edge_case_decision_accuracy']:.0%}**", "",
             "| Issue type | Category | Labelled | Detected | TP | FP | FN | Precision | Recall | Decision accuracy |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in d.itertuples():
        lines.append(f"| {r.issue_type} | {r.category} | {r.labelled} | {r.detected} | {r.true_positive} | "
                     f"{r.false_positive} | {r.false_negative} | {r.precision:.2f} | {r.recall:.2f} | "
                     f"{r.decision_accuracy:.2f} |")
    lines += ["", "## What a naive calculation would get wrong", "", "| GT | Issue | Record | Naive | Engine |",
              "|---|---|---|---|---|"]
    for r in ev["edge_case_impact"]:
        lines.append(f"| {r['gt_id']} | {r['issue_type']} | `{r['record_id']}` | {r['naive_effect']} | "
                     f"{r['engine_effect']} |")
    lines += ["", "## Planning KPIs", "", "| KPI | Value |", "|---|---|"]
    for key, v in k.items():
        lines.append(f"| {key} | {v} |")
    lines += ["", "## Coverage of normal / boundary / failure / exception scenarios", "",
              "| Class | Scenario | Count |", "|---|---|---|"]
    for r in ev["coverage_matrix"]:
        lines.append(f"| {r['coverage_class']} | {r['scenario']} | {r['count']:,} |")
    lines += ["", "## Distributions (realism)", "", "```json", json.dumps(_jsonable(ev["distribution"]), indent=2),
              "```", "", "## Ground-truth leakage audit", "",
              f"- Passed: **{ev['leakage_audit']['passed']}**",
              f"- Engine modules referencing ground truth: {ev['leakage_audit']['engine_modules_reference_ground_truth']}",
              f"- Label columns found in inputs: {ev['leakage_audit']['label_columns_in_inputs'] or 'none'}"]
    (P.outputs / "evaluation_report.md").write_text("\n".join(lines) + "\n")


def write_manifest(cfg: ScaleConfig, P: Paths) -> dict:
    files = []
    for d in P.data_dirs():
        for p in sorted(d.rglob("*")):
            if p.is_file():
                files.append(dict(path=str(p.relative_to(P.root)), bytes=p.stat().st_size, rows=count_rows(p),
                                  sha256=sha256_file(p)))
    manifest = {
        "dataset": f"ORYVA demand, inventory & supply planning - {cfg.name}",
        "generator": "supply_planning", "generator_version": __version__,
        "generator_command": generator_command(cfg), "seed": cfg.seed, "config": cfg.to_dict(),
        "as_of_date": str(pd.Timestamp.fromisocalendar(cfg.plan_year, 1, 1).date()),
        "provenance": {
            "data_origin": "100% synthetic, generated by this repository. No external, personal or confidential "
                           "data was used. Names are composed from generic word lists and counters.",
            "external_sources": [], "license": "MIT (code and generated data)",
            "random_generator": "numpy PCG64 via numpy.random.default_rng([seed, stage_id])"},
        "environment": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
        "ground_truth_location": str(P.gt.relative_to(P.root)),
        "input_tables": INPUT_TABLES, "output_tables": OUTPUT_TABLES, "files": files,
    }
    (P.outputs / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


# ---------------------------------------------------------------------- driver
def run_pipeline(cfg: ScaleConfig, root: Path = PROJECT_ROOT, compress: bool | None = None,
                 sqlite: bool = True, log=print) -> dict:
    compress = (cfg.name == "full") if compress is None else compress
    P = Paths(Path(root), cfg.name)
    timings = {}
    t0 = time.time()
    log(f"[1/6] generating '{cfg.name}' (seed {cfg.seed})")
    tables, gt = build_inputs(cfg, log)
    for d in P.data_dirs() + [P.outputs]:
        _fresh(d)
    write_tables(tables, INPUT_TABLES, P.raw, compress)
    write_csv(order_columns(gt, "ground_truth"), P.gt / "ground_truth.csv")
    write_json(order_columns(gt, "ground_truth"), P.gt / "ground_truth.json")
    timings["generate"] = round(time.time() - t0, 2)

    t1 = time.time()
    log("[2/6] planning from exported inputs only (data/raw)")
    t_in = {n: read_table(P.raw, n) for n in INPUT_TABLES}
    st = run_planning(t_in)
    write_tables(st.out, OUTPUT_TABLES, P.processed, compress)
    timings["plan"] = round(time.time() - t1, 2)

    t2 = time.time()
    log("[3/6] validating exported inputs and outputs")
    t_all = dict(t_in)
    t_all.update({n: read_table(P.processed, n) for n in OUTPUT_TABLES})
    gt_disk = read_table(P.gt, "ground_truth")
    summary = Validator(t_all, gt_disk, P.raw).run(outputs=True, sqlite=sqlite)
    write_validation_report(summary, P)
    timings["validate"] = round(time.time() - t2, 2)
    log(f"      {summary['overall_status']}: {summary['n_checks']} checks, {summary['n_violations']} violations "
        f"({summary['n_expected_labelled']} labelled, {summary['n_unexpected']} unexpected)")

    t3 = time.time()
    log("[4/6] evaluating against ground truth")
    out_disk = {n: t_all[n] for n in OUTPUT_TABLES}
    ev = evaluate(t_in, out_disk, gt_disk, Path(__file__).parent)
    write_evaluation_report(ev, P, cfg)
    timings["evaluate"] = round(time.time() - t3, 2)
    log(f"      edge cases: recall {ev['edge_case_recall']:.0%}, precision {ev['edge_case_precision']:.0%}, "
        f"decisions {ev['edge_case_decision_accuracy']:.0%}")

    t4 = time.time()
    log("[5/6] exporting JSON and SQL seed")
    export_json_sql(t_all, gt_disk, P, compress)
    timings["export"] = round(time.time() - t4, 2)

    log("[6/6] writing manifest with checksums")
    manifest = write_manifest(cfg, P)
    timings["total"] = round(time.time() - t0, 2)
    (P.outputs / "run_log.json").write_text(json.dumps({
        "command": generator_command(cfg), "timings_seconds": timings,
        "python": sys.version.split()[0], "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2))
    log(f"done in {timings['total']}s -> {P.outputs}")
    return dict(paths=P, summary=summary, evaluation=ev, manifest=manifest, timings=timings)
