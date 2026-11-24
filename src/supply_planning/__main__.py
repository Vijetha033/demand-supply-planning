"""Command-line interface.

    python -m supply_planning run   --scale starter            # generate, plan, validate, evaluate, export
    python -m supply_planning run   --scale full
    python -m supply_planning repro --scale starter            # same seed twice -> identical checksums
    python -m supply_planning validate --scale starter         # re-validate exported files
    python -m supply_planning docs                             # regenerate data dictionary
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import PROJECT_ROOT, load_config


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="supply_planning", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "repro", "validate"):
        p = sub.add_parser(name)
        p.add_argument("--scale", default="starter", help="test | starter | full (configs/<scale>.json)")
        p.add_argument("--config", help="path to a JSON config (overrides --scale preset)")
        p.add_argument("--seed", type=int)
        p.add_argument("--root", default=str(PROJECT_ROOT), help="project root for data/ and outputs/")
        for k in ("n_skus", "n_locations", "n_plants", "n_suppliers", "n_purchase_orders", "n_weeks",
                  "edge_cases_per_type"):
            p.add_argument(f"--{k.replace('_', '-')}", dest=k, type=int)
        p.add_argument("--compress", dest="compress", action="store_true", default=None,
                       help="gzip data files (default only for full)")
        p.add_argument("--no-compress", dest="compress", action="store_false")
        p.add_argument("--skip-sqlite", action="store_true", help="skip the SQLite foreign-key check")
    sub.add_parser("docs")
    a = ap.parse_args(argv)

    if a.cmd == "docs":
        from .docs_gen import write_docs
        for p in write_docs(PROJECT_ROOT / "docs"):
            print("wrote", p)
        return 0
    overrides = {k: getattr(a, k, None) for k in ("seed", "n_skus", "n_locations", "n_plants", "n_suppliers",
                                                  "n_purchase_orders", "n_weeks", "edge_cases_per_type")}
    cfg = load_config(a.scale, a.config, **overrides)
    root = Path(a.root)
    if a.cmd == "run":
        from .pipeline import run_pipeline
        res = run_pipeline(cfg, root, compress=a.compress, sqlite=not a.skip_sqlite)
        return 0 if res["summary"]["overall_status"] == "PASS" else 1
    if a.cmd == "repro":
        from .reproducibility import check_reproducibility
        rep = check_reproducibility(cfg, root / "outputs" / cfg.name)
        return 0 if rep["reproducible"] else 1
    if a.cmd == "validate":
        from .io import read_table
        from .pipeline import Paths, write_validation_report
        from .validation import validate_directory
        P = Paths(root, cfg.name)
        gt = read_table(P.gt, "ground_truth")
        s = validate_directory(P.raw, P.processed, gt, sqlite=not a.skip_sqlite)
        write_validation_report(s, P)
        print(f"{s['overall_status']}: {s['n_checks']} checks, {s['n_violations']} violations "
              f"({s['n_expected_labelled']} labelled, {s['n_unexpected']} unexpected)")
        return 0 if s["overall_status"] == "PASS" else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
