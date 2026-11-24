"""Shared fixtures: run the full pipeline once at the tiny 'test' scale."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from supply_planning.config import load_config  # noqa: E402
from supply_planning.io import read_table  # noqa: E402
from supply_planning.pipeline import Paths, run_pipeline  # noqa: E402
from supply_planning.schema import INPUT_TABLES, OUTPUT_TABLES  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_config("test")


@pytest.fixture(scope="session")
def run(tmp_path_factory, cfg):
    root = tmp_path_factory.mktemp("pipeline")
    res = run_pipeline(cfg, root, log=lambda *a, **k: None)
    P = Paths(root, cfg.name)
    res["inputs"] = {n: read_table(P.raw, n) for n in INPUT_TABLES}
    res["outputs"] = {n: read_table(P.processed, n) for n in OUTPUT_TABLES}
    res["gt"] = read_table(P.gt, "ground_truth")
    res["root"] = root
    return res
