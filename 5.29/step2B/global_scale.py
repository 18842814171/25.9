"""Drawing-relative corridor width scale from corridor candidates."""

from __future__ import annotations

from typing import Any

from step2B.config import CorridorNetworkConfig
from utils.scale import (
  DEFAULT_MEDIAN_WIDTH,
  compute_global_scale,
  global_scale_to_json as _global_scale_doc,
)


def apply_global_scale(
  cfg: CorridorNetworkConfig,
  scale: dict[str, float],
) -> CorridorNetworkConfig:
  """Resolve absolute network thresholds from drawing median width."""
  median_w = float(scale.get("median_corridor_width", DEFAULT_MEDIAN_WIDTH))
  cfg.median_corridor_width = median_w
  cfg.continue_gap_th = round(cfg.continue_gap_scale * median_w, 4)
  cfg.junction_tol = round(cfg.junction_tol_scale * median_w, 4)
  cfg.continue_lateral_tol = round(cfg.continue_lateral_scale * median_w, 4)
  return cfg


def global_scale_to_json(
  scale: dict[str, float],
  *,
  source_stem: str,
  network_config: CorridorNetworkConfig | None = None,
) -> dict[str, Any]:
  return _global_scale_doc(
    scale,
    source_stem=source_stem,
    resolved_thresholds=network_config.to_json() if network_config is not None else None,
  )
