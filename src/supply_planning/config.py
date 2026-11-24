"""Scale configuration.

Starter and full datasets are produced by the *same* generator; only the
parameters in :class:`ScaleConfig` differ.  Presets live in ``configs/*.json``
and can be overridden from the command line.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

DEFAULT_SEED = 20261022
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ScaleConfig:
    name: str
    n_skus: int
    n_locations: int
    n_plants: int
    n_suppliers: int
    n_purchase_orders: int
    n_weeks: int = 52
    edge_cases_per_type: int = 3
    seed: int = DEFAULT_SEED
    plan_year: int = 2026
    history_weeks: int = 10          # PO receipts before the as-of date (history)
    share_make: float = 0.10         # finished goods produced in-house
    share_component: float = 0.15    # purchased components consumed through BOMs
    share_component_suppliers: float = 0.15
    share_constrained_suppliers: float = 0.10
    share_overseas_suppliers: float = 0.20
    share_alternate_supplier: float = 0.40
    share_spike_sku_locations: float = 0.04
    share_transport_delay: float = 0.08
    share_cancelled: float = 0.02
    share_substitute: float = 0.06
    share_lead_time_revision: float = 0.10

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> None:
        if self.n_plants < 1 or self.n_plants >= self.n_locations:
            raise ValueError("need at least one plant and one DC")
        if self.n_weeks < 8 or self.n_weeks > 52:
            raise ValueError("n_weeks must be between 8 and 52 (one ISO plan year)")
        if self.n_purchase_orders < self.n_suppliers:
            raise ValueError("n_purchase_orders should be >= n_suppliers")
        if self.n_skus < 20:
            raise ValueError("n_skus must be >= 20")


PRESETS: dict[str, ScaleConfig] = {
    # tiny scale used by the automated tests (fast)
    "test": ScaleConfig(name="test", n_skus=80, n_locations=6, n_plants=2,
                        n_suppliers=16, n_purchase_orders=300, edge_cases_per_type=2),
    "starter": ScaleConfig(name="starter", n_skus=300, n_locations=10, n_plants=2,
                           n_suppliers=50, n_purchase_orders=1000, edge_cases_per_type=3),
    # baseline volume required by the brief
    "full": ScaleConfig(name="full", n_skus=3000, n_locations=50, n_plants=5,
                        n_suppliers=500, n_purchase_orders=10000, edge_cases_per_type=10),
}


def load_config(scale: str = "starter", config_file: str | None = None, **overrides) -> ScaleConfig:
    """Return a config from a preset name or a JSON file, with overrides applied."""
    if config_file:
        data = json.loads(Path(config_file).read_text())
        cfg = ScaleConfig(**data)
    else:
        preset_file = PROJECT_ROOT / "configs" / f"{scale}.json"
        if preset_file.exists():
            cfg = ScaleConfig(**json.loads(preset_file.read_text()))
        elif scale in PRESETS:
            cfg = PRESETS[scale]
        else:
            raise ValueError(f"unknown scale '{scale}'. Known: {sorted(PRESETS)}")
    valid = {f.name for f in fields(ScaleConfig)}
    clean = {k: v for k, v in overrides.items() if v is not None and k in valid}
    cfg = replace(cfg, **clean)
    cfg.validate()
    return cfg
