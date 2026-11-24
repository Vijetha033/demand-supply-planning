"""Ground truth is separate and never used as an input; same seed => identical files."""
import shutil
from pathlib import Path

import pandas as pd

from supply_planning.io import read_table, sha256_file
from supply_planning.pipeline import Paths, run_pipeline
from supply_planning.planning import run_planning
from supply_planning.schema import INPUT_TABLES, LEAKAGE_COLUMNS, OUTPUT_TABLES

SRC = Path(__file__).resolve().parents[1] / "src" / "supply_planning"


def test_ground_truth_stored_separately(run, cfg):
    P = Paths(run["root"], cfg.name)
    assert (P.gt / "ground_truth.csv").exists() and (P.gt / "ground_truth.json").exists()
    assert not any("ground_truth" in p.name for p in P.raw.iterdir())


def test_no_label_columns_in_inputs(run):
    for n in INPUT_TABLES:
        assert not (LEAKAGE_COLUMNS & set(run["inputs"][n].columns)), n


def test_engine_code_never_reads_ground_truth():
    for m in ["planning.py", "mitigation.py", "generator.py"]:
        assert "ground_truth" not in (SRC / m).read_text(), m


def test_plan_identical_without_ground_truth(run, cfg, tmp_path):
    P = Paths(run["root"], cfg.name)
    raw_copy = tmp_path / "raw"
    shutil.copytree(P.raw, raw_copy)
    st = run_planning({n: read_table(raw_copy, n) for n in INPUT_TABLES})
    for n in ["shortage", "mitigation_option", "detected_issue"]:
        a = st.out[n].reset_index(drop=True)
        b = run["outputs"][n]
        assert len(a) == len(b), n
    assert list(st.out["shortage"].sort_values("shortage_id").shortage_qty) == \
        list(run["outputs"]["shortage"].sort_values("shortage_id").shortage_qty)


def test_same_seed_identical_checksums(cfg, tmp_path):
    quiet = lambda *a, **k: None
    run_pipeline(cfg, tmp_path / "a", sqlite=False, log=quiet)
    run_pipeline(cfg, tmp_path / "b", sqlite=False, log=quiet)
    pa, pb = Paths(tmp_path / "a", cfg.name), Paths(tmp_path / "b", cfg.name)
    files = [p.relative_to(tmp_path / "a") for d in pa.data_dirs() for p in d.rglob("*") if p.is_file()]
    assert len(files) > 40
    for f in files:
        assert sha256_file(tmp_path / "a" / f) == sha256_file(tmp_path / "b" / f), f


def test_different_seed_differs(cfg, tmp_path):
    from dataclasses import replace
    quiet = lambda *a, **k: None
    run_pipeline(cfg, tmp_path / "a", sqlite=False, log=quiet)
    run_pipeline(replace(cfg, seed=cfg.seed + 1), tmp_path / "b", sqlite=False, log=quiet)
    f = Path("data/raw/test/forecast_demand.csv")
    assert sha256_file(tmp_path / "a" / f) != sha256_file(tmp_path / "b" / f)
