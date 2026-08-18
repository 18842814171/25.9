"""Step 3A threshold configuration (relative to drawing scale)."""

from __future__ import annotations

from dataclasses import dataclass

from stage2.geometry import CorridorPipelineConfig
from step2B.config import ParallelGraphConfig
from step2B.width_estimate import apply_width_band


@dataclass
class CenterlineGraphConfig(ParallelGraphConfig):
  """Parallel + endpoint graph on corridor centerlines (Step 2B edge model)."""

  endpoint_link_gap_scale: float = 1.5

  @classmethod
  def from_pipeline(cls, cfg: CorridorPipelineConfig | None = None) -> CenterlineGraphConfig:
    base = ParallelGraphConfig.from_pipeline(cfg)
    return cls(
      endpoint_link_gap=base.endpoint_link_gap,
      angle_th_deg=base.angle_th_deg,
      min_width=base.min_width,
      max_width=base.max_width,
      min_overlap_ratio=base.min_overlap_ratio,
    )

  def apply_global_scale(self, scale: dict[str, float]) -> None:
    """Resolve width band and endpoint link gap from drawing median width."""
    median_w = float(scale.get("median_corridor_width", 5.4))
    apply_width_band(self, median_w)
    self.endpoint_link_gap = round(self.endpoint_link_gap_scale * median_w, 4)

  def to_json(self) -> dict[str, float]:
    out = super().to_json()
    out["endpoint_link_gap_scale"] = self.endpoint_link_gap_scale
    return out
