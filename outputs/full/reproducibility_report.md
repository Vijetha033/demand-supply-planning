# Reproducibility report - `full`

Two independent runs with seed `20261022` in fresh temporary folders.

- Files compared: 56
- Identical (row count + SHA-256): 56
- **Reproducible: True**
- Control run with seed `20261023`: 53 of 56 files differ (expected: different seed -> different data)

| File | Rows A | Rows B | SHA-256 (A) | Identical |
|---|---|---|---|---|
| `data/exports/full/json/bom.json.gz` | - | - | `548360fc80773cdb...` | yes |
| `data/exports/full/json/calendar_week.json.gz` | - | - | `0f8e290a6c6d68a6...` | yes |
| `data/exports/full/json/detected_issue.json.gz` | - | - | `76b2a64a7d263ff5...` | yes |
| `data/exports/full/json/forecast_demand.json.gz` | - | - | `14548c7edd59647b...` | yes |
| `data/exports/full/json/inventory.json.gz` | - | - | `7bccf75b83273125...` | yes |
| `data/exports/full/json/lead_time.json.gz` | - | - | `4a78b70b2c68c8f7...` | yes |
| `data/exports/full/json/location.json.gz` | - | - | `7f63801dd2e08bd8...` | yes |
| `data/exports/full/json/mitigation_option.json.gz` | - | - | `b3ee8367acb985dd...` | yes |
| `data/exports/full/json/production_capacity.json.gz` | - | - | `4dba43fbe6ea17b9...` | yes |
| `data/exports/full/json/production_capacity_utilization.json.gz` | - | - | `b4f537562312fb98...` | yes |
| `data/exports/full/json/production_plan.json.gz` | - | - | `7cfee60c68347c48...` | yes |
| `data/exports/full/json/projected_balance.json.gz` | - | - | `27f550c0e5d07a96...` | yes |
| `data/exports/full/json/purchase_order.json.gz` | - | - | `f9aa63f876412a18...` | yes |
| `data/exports/full/json/purchase_order_event.json.gz` | - | - | `df63744e9a7d6e2b...` | yes |
| `data/exports/full/json/purchase_order_line.json.gz` | - | - | `f1d920186a868574...` | yes |
| `data/exports/full/json/rejected_mitigation.json.gz` | - | - | `3b6e9399ff716703...` | yes |
| `data/exports/full/json/scheduled_receipt.json.gz` | - | - | `87f071a1e6c52bd3...` | yes |
| `data/exports/full/json/shortage.json.gz` | - | - | `c085fb416a667df1...` | yes |
| `data/exports/full/json/shortage_cause.json.gz` | - | - | `f3a95712abdb5469...` | yes |
| `data/exports/full/json/sku.json.gz` | - | - | `23b29d95c368d32a...` | yes |
| `data/exports/full/json/sku_location.json.gz` | - | - | `cb5dd5195cc61727...` | yes |
| `data/exports/full/json/sku_substitute.json.gz` | - | - | `128a14946502eb0b...` | yes |
| `data/exports/full/json/supplier.json.gz` | - | - | `b1cd1fa8baeae593...` | yes |
| `data/exports/full/json/supplier_capacity.json.gz` | - | - | `cf37dac6ca42a6e9...` | yes |
| `data/exports/full/json/supplier_capacity_utilization.json.gz` | - | - | `3171e7a29aded780...` | yes |
| `data/exports/full/json/supplier_sku.json.gz` | - | - | `74bf85d5870f7a54...` | yes |
| `data/exports/full/sql/schema.sql` | - | - | `234a7d96f08c0455...` | yes |
| `data/exports/full/sql/seed.sql.gz` | - | - | `db038b27a4ddbf0b...` | yes |
| `data/ground_truth/full/ground_truth.csv` | 312 | 312 | `a816398af304df11...` | yes |
| `data/ground_truth/full/ground_truth.json` | - | - | `efad584287729c71...` | yes |
| `data/processed/full/detected_issue.csv.gz` | 323 | 323 | `d347df9872470d92...` | yes |
| `data/processed/full/mitigation_option.csv.gz` | 9046 | 9046 | `92108b9baa297570...` | yes |
| `data/processed/full/production_capacity_utilization.csv.gz` | 260 | 260 | `077cd213db9aaa9b...` | yes |
| `data/processed/full/projected_balance.csv.gz` | 218764 | 218764 | `2401a076a6d0d48f...` | yes |
| `data/processed/full/rejected_mitigation.csv.gz` | 1565 | 1565 | `8883b47e6fb5f719...` | yes |
| `data/processed/full/scheduled_receipt.csv.gz` | 44969 | 44969 | `798a392cebc275d6...` | yes |
| `data/processed/full/shortage.csv.gz` | 3025 | 3025 | `8acbb80bb28deece...` | yes |
| `data/processed/full/shortage_cause.csv.gz` | 5597 | 5597 | `f7edebc33e7e003b...` | yes |
| `data/processed/full/supplier_capacity_utilization.csv.gz` | 26000 | 26000 | `606fd64a4d7a4226...` | yes |
| `data/raw/full/bom.csv.gz` | 955 | 955 | `cc79ba693990d4f9...` | yes |
| `data/raw/full/calendar_week.csv.gz` | 52 | 52 | `0abc59485d7f18d0...` | yes |
| `data/raw/full/forecast_demand.csv.gz` | 170933 | 170933 | `cad134d0ed8c2382...` | yes |
| `data/raw/full/inventory.csv.gz` | 5613 | 5613 | `ae18a0876536eab1...` | yes |
| `data/raw/full/lead_time.csv.gz` | 2658 | 2658 | `d9e836f205360494...` | yes |
| `data/raw/full/location.csv.gz` | 50 | 50 | `d84f800218e7ee61...` | yes |
| `data/raw/full/production_capacity.csv.gz` | 260 | 260 | `344b470b531593ee...` | yes |
| `data/raw/full/production_plan.csv.gz` | 14821 | 14821 | `4e82857cfc548ca5...` | yes |
| `data/raw/full/purchase_order.csv.gz` | 10030 | 10030 | `8c6ed565a13ad74e...` | yes |
| `data/raw/full/purchase_order_event.csv.gz` | 15826 | 15826 | `a867e994c13019dd...` | yes |
| `data/raw/full/purchase_order_line.csv.gz` | 54955 | 54955 | `9989642500d7d057...` | yes |
| `data/raw/full/sku.csv.gz` | 3000 | 3000 | `46266d3bba91a5b6...` | yes |
| `data/raw/full/sku_location.csv.gz` | 4207 | 4207 | `2d79afd832516e4d...` | yes |
| `data/raw/full/sku_substitute.csv.gz` | 144 | 144 | `ab63b0498986fb40...` | yes |
| `data/raw/full/supplier.csv.gz` | 500 | 500 | `d2a124e962978b84...` | yes |
| `data/raw/full/supplier_capacity.csv.gz` | 26000 | 26000 | `03c5d25a12b6731d...` | yes |
| `data/raw/full/supplier_sku.csv.gz` | 3988 | 3988 | `e4962dbf98d568cf...` | yes |
