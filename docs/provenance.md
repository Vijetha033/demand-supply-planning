# Source manifest and lawful provenance

| Item | Value |
|---|---|
| Data origin | 100% synthetic, produced by `src/supply_planning/generator.py` |
| External datasets | **None used.** No data was downloaded, scraped or copied |
| Personal / confidential data | None. Supplier, SKU and location names are built from generic word lists and counters (e.g. `Apex Supply 0001`, `Compact Device 000123`, `North DC 01`) and do not refer to real organisations |
| Schema inspiration | General supply-planning concepts (MRP projected available balance, ABC classification, MOQ/order multiples, frozen fences) from common textbook practice; no proprietary schema was copied |
| License | MIT for code and generated data (see `LICENSE`) |
| Random generator | NumPy PCG64 via `numpy.random.default_rng([seed, stage_id])`; one independent stream per generation stage, so changing one stage does not shift the others |
| Fixed seed | `20261022` (configs/*.json) |
| Generator command | `python -m supply_planning run --scale starter` / `--scale full` |
| Per-run manifest | `outputs/<scale>/manifest.json`: config, seed, environment versions, and every data file with path, bytes, row count and SHA-256 |
| Reproducibility evidence | `outputs/<scale>/reproducibility_report.md|json` |

## Transformations and discarded fields

No external data was used, so there are no source transformations or discarded fields. Internal generator values
that are **deliberately not exported** as input features:

* the previous forecast release used to plan open POs and production (`plan_basis`),
* spike multipliers, and which suppliers and plant were configured as constrained.

These appear only as labels in `data/ground_truth/<scale>/`.

## Distributions used (synthetic, documented for review)

| Quantity | Distribution |
|---|---|
| Weekly demand level per SKU-location | log-normal by category (median ~10-40 units/week, sigma 1.0) x location size factor; x3 for manufactured SKUs |
| Seasonality | cosine with category-specific amplitude (8-35%) and peak week |
| Trend | linear, N(0.1%, 0.3%) per week |
| Weekly noise | log-normal sigma 0.12; Poisson rounding below 5 units |
| Demand spikes | 4% of SKU-locations, 1-2 weeks, x2.5-4.5 |
| Forecast revision since POs were planned | 20% of SKU-locations, N(0, 10%) |
| Unit cost | log-normal by category; price = cost x U(1.35, 2.3) |
| Lead times | production 3-23 days; road 1-4 (same region) / 4-10 days; sea 18-35 days; 10% of lanes revised mid-year |
| PO cadence | exactly `n_purchase_orders`, allocated to supplier-location lanes in proportion to sqrt(lane value) (largest remainder); order-up-to quantities rounded to MOQ / multiple |
| Transport delays | ~8% x (100 - reliability)/6 of shipped/confirmed POs, 3-21 days |
| Cancellations | 2% of small (<= 2 line) open POs |
| Supplier capacity | normal: 1.25-2.0 x peak load; constrained (10%): 0.95-1.1 x mean load with cuts; holiday weeks x 0.75 |
| Safety stock | ceil(z(ABC) x 0.3 x mean weekly demand x sqrt(lead-time weeks)), z = 1.65 / 1.28 / 0.84 |
