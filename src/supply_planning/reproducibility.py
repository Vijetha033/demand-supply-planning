"""Fixed-seed reproducibility proof (brief step 10).

Generates the dataset twice into two fresh temporary roots with the same
seed, compares row counts and SHA-256 checksums of every data file, and (as a
control) once more with a different seed, which must differ.
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

from .config import ScaleConfig
from .pipeline import Paths, run_pipeline


def _snapshot(root: Path, scale: str) -> dict:
    P = Paths(root, scale)
    files = {}
    for d in P.data_dirs():
        for p in sorted(d.rglob("*")):
            if p.is_file():
                from .io import count_rows, sha256_file
                files[str(p.relative_to(root))] = dict(rows=count_rows(p), sha256=sha256_file(p))
    return files


def check_reproducibility(cfg: ScaleConfig, out_dir: Path, control_seed: int | None = None, log=print) -> dict:
    quiet = lambda *a, **k: None
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as c:
        log(f"run A (seed {cfg.seed})")
        run_pipeline(cfg, Path(a), sqlite=False, log=quiet)
        log(f"run B (seed {cfg.seed})")
        run_pipeline(cfg, Path(b), sqlite=False, log=quiet)
        sa, sb = _snapshot(Path(a), cfg.name), _snapshot(Path(b), cfg.name)
        ctrl_seed = control_seed if control_seed is not None else cfg.seed + 1
        log(f"control run C (seed {ctrl_seed})")
        run_pipeline(replace(cfg, seed=ctrl_seed), Path(c), sqlite=False, log=quiet)
        sc = _snapshot(Path(c), cfg.name)
    rows = []
    for f in sorted(set(sa) | set(sb)):
        x, y = sa.get(f), sb.get(f)
        rows.append(dict(file=f, rows_run_a=x and x["rows"], rows_run_b=y and y["rows"],
                         sha256_run_a=x and x["sha256"], sha256_run_b=y and y["sha256"],
                         identical=bool(x and y and x == y)))
    differing_control = sum(1 for f in sa if f in sc and sc[f]["sha256"] != sa[f]["sha256"])
    report = dict(scale=cfg.name, seed=cfg.seed, files_compared=len(rows),
                  identical_files=sum(r["identical"] for r in rows),
                  reproducible=all(r["identical"] for r in rows), control_seed=ctrl_seed,
                  control_files_differing=differing_control, files=rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reproducibility_report.json").write_text(json.dumps(report, indent=2))
    lines = [f"# Reproducibility report - `{cfg.name}`", "",
             f"Two independent runs with seed `{cfg.seed}` in fresh temporary folders.", "",
             f"- Files compared: {len(rows)}", f"- Identical (row count + SHA-256): {report['identical_files']}",
             f"- **Reproducible: {report['reproducible']}**",
             f"- Control run with seed `{ctrl_seed}`: {differing_control} of {len(sa)} files differ "
             "(expected: different seed -> different data)", "",
             "| File | Rows A | Rows B | SHA-256 (A) | Identical |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r['file']}` | {r['rows_run_a'] if r['rows_run_a'] is not None else '-'} | "
                     f"{r['rows_run_b'] if r['rows_run_b'] is not None else '-'} | `{(r['sha256_run_a'] or '')[:16]}...` | "
                     f"{'yes' if r['identical'] else 'NO'} |")
    (out_dir / "reproducibility_report.md").write_text("\n".join(lines) + "\n")
    log(f"reproducible={report['reproducible']} ({report['identical_files']}/{len(rows)} files identical); "
        f"control differs in {differing_control} files")
    return report
