# Demand, Inventory & Supply Planning: ORYVA AI Student Technical Assignment

An end-to-end, reproducible Python solution that generates a synthetic planning dataset, matches weekly forecast
demand to inventory, supplier capacity, lead times and production constraints, then **identifies, explains,
prioritises and mitigates shortages**. Five labelled edge cases are injected and checked against a separate
ground-truth file that the planning engine never reads.

```
generate (fixed seed) -> inject labelled edge cases -> export inputs + ground truth (separately)
   -> plan from exported inputs only -> validate -> evaluate vs ground truth -> CSV / JSON / SQL + manifest
```

## Results at a glance (seed 20261022)

| | starter | full (brief volume) |
|---|---:|---:|
| SKUs / locations / suppliers / weeks | 300 / 10 / 50 / 52 | **3,000 / 50 / 500 / 52** |
| Inbound purchase orders (baseline + labelled) | 1,000 + 9 | **10,000** + 30 |
| PO lines / demand rows / PAB rows | 4,846 / 17,366 / 21,216 | 54,955 / 170,933 / 218,764 |
| Shortage episodes (CRITICAL / HIGH / MEDIUM / LOW) | 322 (16 / 64 / 159 / 83) | 3,025 (139 / 473 / 1,612 / 801) |
| Shortages with a feasible mitigation | 90.1% | 93.5% |
| Mitigation options evaluated / rejected candidates logged | 996 / 191 | 9,046 / 1,565 |
| Projected service level (SKU-location-weeks not short) | 89.3% | 90.7% |
| Validation | **PASS**: 148 checks, 0 unexpected violations | **PASS**: 148 checks, 0 unexpected |
| Edge-case detection (recall / precision / correct decision) | 100% / 100% / 100% | 100% / 100% / 100% |
| Same-seed regeneration | 56/56 files byte-identical | 56/56 files byte-identical |
| Runtime (Apple-silicon laptop) | ~2 s | ~30 s |

## Install

Requires Python >= 3.10 (developed on 3.14) with numpy, pandas and pytest.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# optional: .venv/bin/pip install -e .   (then `supply-planning ...` works without PYTHONPATH)
```

## Run

```bash
export PYTHONPATH=src                                   # or use `make`, which sets it
.venv/bin/python -m supply_planning run --scale starter # generate + plan + validate + evaluate + export
.venv/bin/python -m supply_planning run --scale full    # 3,000 SKUs, 50 locations, 500 suppliers, 10,000 POs
.venv/bin/python -m supply_planning repro --scale full  # regenerate twice, compare row counts + SHA-256
.venv/bin/python -m supply_planning validate --scale starter   # re-validate exported files only
.venv/bin/python -m supply_planning docs                # regenerate docs/data_dictionary.md
.venv/bin/python -m pytest -q                           # 47 automated tests
make all                                                # docs + starter + full + repro + tests
```

### Configure

Scale presets live in `configs/{test,starter,full}.json`. Starter and full use **the same generator**; only these
parameters differ. Any field can be overridden:

```bash
python -m supply_planning run --scale starter --seed 7 --n-skus 500 --n-purchase-orders 2000
python -m supply_planning run --config my_config.json      # a full custom ScaleConfig
python -m supply_planning run --scale full --no-compress   # full-scale files are gzipped by default
```

The planning-policy thresholds (`POLICY` in `planning.py`) and cost assumptions (`COSTS` in `mitigation.py`) are
named constants in one place each.

## Repository layout

```
configs/                 scale presets (seed 20261022)
src/supply_planning/
  config.py              ScaleConfig + presets
  schema.py              single source of truth: 28 tables, fields, PK/FK, enums, rules
  generator.py           baseline synthetic data in dependency order
  edge_cases.py          injects the 5 labelled edge cases + writes ground-truth labels
  planning.py            data-quality screen, scheduled receipts, PAB, shortages, causes, priority
  mitigation.py          constrained mitigation options, trade-offs, rejections, reservations
  validation.py          PK/FK/enum/date/arithmetic/lifecycle/duplicate/policy/leakage checks + SQLite FK check
  evaluation.py          precision/recall vs ground truth, KPIs, distributions, coverage, leakage audit
  pipeline.py            orchestration + CSV/JSON/SQL export + manifest
  reproducibility.py     double-run checksum proof
data/raw/<scale>/        INPUT tables (the planning engine reads only this folder)
data/ground_truth/<scale>/ground_truth.csv|json   labels, kept separate
data/processed/<scale>/  planning outputs
data/exports/<scale>/    json/ (every table) and sql/ (schema.sql + seed.sql, SQLite-compatible)
outputs/<scale>/         manifest.json, validation_summary.md|json, validation_violations.csv,
                         evaluation_report.md|json, reproducibility_report.md|json, run_log.json
docs/                    data_dictionary.md|json, data_model.md, planning_logic.md, edge_cases.md, provenance.md
tests/                   47 pytest tests
```

Full-scale data files are written as `.csv.gz` / `.json.gz` / `.sql.gz` (deterministic gzip) to keep the repository
small. `pandas.read_csv("....csv.gz")` reads them directly.

## Data model (summary)

Core entities from the brief: **SKU, Location, ForecastDemand, Inventory, Supplier, SupplierCapacity, LeadTime,
PurchaseOrder, ProductionPlan, Shortage, MitigationOption**. They are supported by bridge tables for the N:M
relationships (`sku_location`, `supplier_sku`, `bom`, `sku_substitute`), PO lines, an append-only PO event history,
production capacity and a planning calendar. Each table has a primary key and FKs for every relationship, including
composite FKs (e.g. demand -> `sku_location`). Cardinality, optionality, effective dates and lifecycle states are in
[docs/data_model.md](docs/data_model.md); every field is in [docs/data_dictionary.md](docs/data_dictionary.md).

IDs follow the brief exactly and are zero-padded, immutable and consistent across CSV, JSON and SQL:
`SKU-000001`, `DEM-SKU-000001-LOC-001-2026W01`, `PO-2026-000001`, `SHORT-2026-000001`,
`MIT-SHORT-2026-000001-01`.

## How planning works (summary; full rules in [docs/planning_logic.md](docs/planning_logic.md))

1. **Data-quality screen.** Duplicate in-transit records, unapproved substitutes, supplier-week over-commitment,
   receipt dates that ignore lead time, and UoM mismatches are detected. A documented decision is applied in a
   derived layer (`scheduled_receipt.adjustment_codes`) and logged in `detected_issue`. Source rows are never
   overwritten.
2. **Projected available balance** per SKU-location-week:
   `closing = opening + scheduled receipts + planned production - forecast - BOM-dependent demand`. It reconciles
   exactly week by week, and validation recomputes every term from source.
3. **Shortages** are maximal runs of negative PAB. Each carries peak deficit, value, duration and whether it starts
   inside the lead time (when a normal order can't fix it).
4. **Explainable causes.** Each shortage gets quantified causes with evidence IDs (spike, transport delay, supplier
   capacity cut/deferral, plant capacity, BOM dependent demand, cancelled PO, lead-time/UoM correction, opening
   stock, no supply), plus the reconciliation arithmetic.
5. **Priority.** A 0-100 score combines value at risk, urgency, ABC class and duration. Tiers are
   CRITICAL / HIGH / MEDIUM / LOW, and IDs are numbered in priority order.
6. **Mitigations.** Expedite, new PO (primary or alternate), stock transfer, approved substitute, extra production
   or backorder. Each is checked against MOQ/multiples, lead time (no order before today), supplier status and
   approval, weekly supplier capacity, plant capacity plus frozen fence, component availability, and source surplus
   above safety stock. Every option shows cost (total and incremental) and service (fill rate, weeks late, net
   benefit). The recommended option's capacity is reserved before the next shortage is evaluated. Failed
   candidates are logged with the rule that failed.

Example (`data/processed/starter/`): `SHORT-2026-000002` is component `SKU-000277` at plant `LOC-002`, CRITICAL.
*"through 2026W02: opening 498 + receipts 0 + production 0 - demand 0 - dependent demand 2000 = -1502"*. Its causes
are TRANSPORT_DELAY 1502 (PO with a carrier-reported delay), DEPENDENT_DEMAND 1502 and SUPPLIER_CAPACITY_CONSTRAINT
1104 (confirmed < requested), each with source IDs. Trade-off: `MIT-SHORT-2026-000002-01` expedites the delayed
PO (100% fill, 0 weeks late, incremental cost $2,838, recommended). `-02` accepts the backorder (0% fill, lost
margin $11,265).

## The five required edge cases ([docs/edge_cases.md](docs/edge_cases.md))

| Edge case | How it is injected (new records only) | Engine decision |
|---|---|---|
| Inbound inventory counted twice | duplicate IN_TRANSIT inventory row for an in-transit PO line | EXCLUDE_DUPLICATE_INBOUND |
| Substitute SKU not approved | PENDING/REJECTED substitute that has stock for a short SKU | REJECT_SUBSTITUTE_MITIGATION (+ rejection log) |
| Supplier capacity exceeded | rush PO pushing a supplier ship-week over capacity | DEFER_EXCESS_TO_NEXT_AVAILABLE_WEEK |
| Shortage calculated without lead time | PO whose receipt date = order date | RECALCULATE_RECEIPT_WITH_LEAD_TIME |
| Units-of-measure mismatch | cases recorded as units (A) / unconvertible unit (B) | CONVERT_USING_MASTER_UOM / EXCLUDE_UNCONVERTIBLE_LINE |

Each case is labelled in `data/ground_truth/<scale>/ground_truth.csv` with `issue_type`, `record_id`,
`related_record_ids` (traceability), `expected_decision`, `expected_value` and `rule_reference`. The file also labels
scenario drivers (demand spikes, constrained suppliers, constrained plant) so their detection can be measured.

## Ground truth is never an input feature

* Stored in its own folder (`data/ground_truth/`); the validator fails if a ground-truth file appears in
  `data/raw/` or if any input table has a label-like column.
* The planning engine (`planning.py`, `mitigation.py`) has no code path to it. The pipeline plans by **re-reading
  the exported inputs from disk**, and a test re-plans from a copy of `data/raw/` alone and gets the same result.
* Only `evaluation.py` and the validator's final classification step read it.

## Validation (brief step 8, acceptance criteria section 7)

`outputs/<scale>/validation_summary.md` lists 148 checks: schema/types/required/patterns, PK uniqueness,
natural-key duplicates, FK integrity (pandas **and** SQLite with `PRAGMA foreign_key_check`), allowed enums, date
ordering, arithmetic reconciliation (PO lines/totals, lead-time sums, derived ABC and safety stock, PAB week by week,
receipts to PO lines, dependent demand to BOM), lifecycle transitions from the event log, duplicate records,
cross-entity rules, mitigation policy and capacity, explainability, and leakage. Violations that point at a labelled
record are `EXPECTED_LABELLED`; anything else fails the run.

## Reproducibility (brief step 10)

`python -m supply_planning repro --scale full` runs the whole pipeline twice in fresh temporary folders with seed
20261022 and compares every data file's row count and SHA-256 (`outputs/<scale>/reproducibility_report.md`). Result:
56/56 identical at both scales. A control run with seed 20261023 changes 53/56 files (the calendar, location and DDL
files are seed-independent by design). Determinism comes from one PCG64 stream per generation stage, stable sort
orders, `\n` line endings and gzip with `mtime=0`; data files contain no timestamps (`run_log.json` holds the
timings).

## Requirement traceability

| Brief requirement | Where |
|---|---|
| Master data first, dependent records next | `generator.py` run order; FK checks |
| SKU-location demand by week; on-hand + inbound; supplier capacity, MOQ, lead times; production capacity + BOM | `forecast_demand`, `inventory`, `purchase_order(_line)`, `supplier_capacity`, `supplier_sku`, `lead_time`, `production_capacity`, `production_plan`, `bom` |
| Projected available balance; shortages; candidate mitigations | `projected_balance`, `shortage`, `shortage_cause`, `mitigation_option`, `rejected_mitigation` |
| Preserve history, don't overwrite | `purchase_order_event`, lead-time versions, `scheduled_receipt` corrections |
| Outcomes and labels from documented rules | derived fields + `docs/planning_logic.md`; labels from injection rules R1-R5 |
| PK for every entity, FK for every relationship, bridge tables, cardinality, effective dates, lifecycle | `schema.py`, `docs/data_model.md` |
| Anomalies labelled, not silent corruption | `edge_cases.py`, `ground_truth`, no-mutation test |
| ID conventions | `ids.py`, `tests/test_integrity.py` |
| Step 1 data dictionary | `docs/data_dictionary.md` / `.json` |
| Step 4 volume + variation + fixed seed + parameterised scale | `configs/full.json`; spikes, constrained suppliers/plant, substitutes, transport delays, cancellations, lead-time revisions |
| Step 6 derived values | ABC, safety stock, PO totals, status/delay from events, PAB, scores |
| Step 7 separate ground truth | `data/ground_truth/` |
| Step 8 validation | `validation.py`, `outputs/*/validation_summary.md` |
| Step 9 CSV/JSON/SQL + README + dictionary + command + seed + manifest + summary | `data/raw`, `data/exports`, `outputs/*/manifest.json`, `docs/` |
| Step 10 reproducibility | `outputs/*/reproducibility_report.md` |
| Evaluation focus A-G | `outputs/*/evaluation_report.md` (distributions, joins, lifecycle, reconciliation, coverage matrix, leakage audit, provenance) |
| Lawful provenance | `docs/provenance.md`; 100% synthetic, no external data |

## Assumptions and limitations

* Each SKU is stocked at 1-3 locations, not all 50 (about 4,200 SKU-locations at full scale). See
  `docs/data_model.md`.
* Supplier capacity is one weekly figure in base units across all of a supplier's SKUs, measured on ship week.
* Transfers use fixed transit times (1 week in-region, 2 weeks cross-region); there is no transport-capacity model.
* Mitigations are single actions per shortage (no combinations); residual quantity is reported.
* About 20% of SKU-locations carry a forecast revision made after their POs were placed. The engine can't see the
  old forecast, so these shortages are honestly explained as `DEMAND_EXCEEDS_SUPPLY` with the reconciliation
  arithmetic.
