"""Step 2B threshold configs (from stage2.geometry.CorridorPipelineConfig)."""

from __future__ import annotations

from dataclasses import dataclass, field

from stage2.geometry import CorridorPipelineConfig
from step2B.width_estimate import apply_width_band


def _corridor_max_width(pipe: CorridorPipelineConfig) -> float:
  return max(pipe.max_width, 6.5)


@dataclass
class StraightWallConfig:
  """Straight-wall chain merge thresholds on the Step 2A endpoint graph.

  Gap filtering is not applied here: adjacency comes from the endpoint graph
  (built with ``endpoint_link_gap``). Only angle and lateral offset remain.

  Short single-member groups with length ≤ ``short_length_scale × median
  corridor width`` go to residual geometry instead of straight walls.
  """

  continuity_angle_deg: float = 5.0
  continuity_lateral_tol: float = 1.0
  short_length_scale: float = 5.0

  @classmethod
  def from_pipeline(cls, cfg: CorridorPipelineConfig | None = None) -> StraightWallConfig:
    pipe = cfg or CorridorPipelineConfig()
    return cls(
      continuity_angle_deg=pipe.continuity_angle_deg,
      continuity_lateral_tol=pipe.continuity_lateral_tol,
    )

  def to_json(self) -> dict[str, float]:
    return {
      "continuity_angle_deg": self.continuity_angle_deg,
      "continuity_lateral_tol": self.continuity_lateral_tol,
      "short_length_scale": self.short_length_scale,
    }


@dataclass
class ParallelGraphConfig:
  endpoint_link_gap: float = 1.0
  angle_th_deg: float = 5.0
  min_width: float = 1.0
  max_width: float = 6.5
  min_overlap_ratio: float = 0.4
  # Loose search radius for the first parallel-edge pass (not corridor scale).
  probe_min_width: float = 0.0
  probe_max_width: float = 20.0

  @classmethod
  def from_pipeline(cls, cfg: CorridorPipelineConfig | None = None) -> ParallelGraphConfig:
    pipe = cfg or CorridorPipelineConfig()
    return cls(
      endpoint_link_gap=pipe.endpoint_link_gap,
      angle_th_deg=pipe.angle_th_deg,
      min_width=pipe.min_width,
      max_width=_corridor_max_width(pipe),
      min_overlap_ratio=pipe.min_overlap_ratio,
    )

  def to_json(self) -> dict[str, float]:
    return {
      "endpoint_link_gap": self.endpoint_link_gap,
      "angle_th_deg": self.angle_th_deg,
      "min_width": self.min_width,
      "max_width": self.max_width,
      "min_overlap_ratio": self.min_overlap_ratio,
      "probe_min_width": self.probe_min_width,
      "probe_max_width": self.probe_max_width,
    }


@dataclass
class CenterlineGraphConfig(ParallelGraphConfig):
  """Parallel + endpoint graph on corridor centerlines."""

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


@dataclass
class CorridorNetworkConfig:
  """Scale factors multiply median_corridor_width; angles are absolute degrees."""

  continue_gap_scale: float = 1.5
  continue_angle_th: float = 5.0
  continue_lateral_scale: float = 0.5
  junction_tol_scale: float = 0.2
  junction_angle_th: float = 15.0

  median_corridor_width: float | None = None
  continue_gap_th: float = field(default=0.0, repr=False)
  continue_lateral_tol: float = field(default=0.0, repr=False)
  junction_tol: float = field(default=0.0, repr=False)

  def to_json(self) -> dict[str, float]:
    out: dict[str, float] = {
      "continue_gap_scale": self.continue_gap_scale,
      "continue_angle_th": self.continue_angle_th,
      "continue_lateral_scale": self.continue_lateral_scale,
      "junction_tol_scale": self.junction_tol_scale,
      "junction_angle_th": self.junction_angle_th,
    }
    if self.median_corridor_width is not None:
      out["median_corridor_width"] = self.median_corridor_width
    if self.continue_gap_th > 0:
      out["continue_gap_th"] = self.continue_gap_th
    if self.continue_lateral_tol > 0:
      out["continue_lateral_tol"] = self.continue_lateral_tol
    if self.junction_tol > 0:
      out["junction_tol"] = self.junction_tol
    return out


