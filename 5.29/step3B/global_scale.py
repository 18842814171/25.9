"""Resolve Step 3B attach thresholds from drawing scale."""

from __future__ import annotations

from typing import Any

from step3B.config import AttachConfig
from utils.scale import DEFAULT_MEDIAN_WIDTH, global_scale_to_json as _global_scale_doc


def apply_attach_scale(cfg: AttachConfig, scale: dict[str, float]) -> AttachConfig:
  median_w = float(scale.get("median_corridor_width", DEFAULT_MEDIAN_WIDTH))
  cfg.median_corridor_width = median_w
  cfg.endpoint_link_gap = round(cfg.endpoint_link_gap_scale * median_w, 4)
  cfg.attach_tol = round(cfg.attach_tol_scale * median_w, 4)
  return cfg


def global_scale_to_json(
  scale: dict[str, float],
  *,
  source_stem: str,
  attach_config: AttachConfig | None = None,
) -> dict[str, Any]:
  return _global_scale_doc(
    scale,
    source_stem=source_stem,
    resolved_thresholds=attach_config.to_json() if attach_config is not None else None,
  )

