"""Drawing-relative scale for Step 2A bend / fillet detection."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

import numpy as np

from step2A.bend_layer import BendLayerConfig
from utils.scale import percentile as _percentile

DEFAULT_MEDIAN_LINE = 12.0
DEFAULT_MEDIAN_CHORD = 4.24
DEFAULT_MEDIAN_RADIUS = 3.0
MIN_LINE_LEN = 0.01


@dataclass(frozen=True)
class DrawingScale:
  line_count: int
  arc_count: int
  median_line_length: float
  p10_line_length: float
  p25_line_length: float
  median_arc_chord: float
  p75_arc_chord: float
  median_arc_radius: float
  p75_arc_radius: float
  arc_chord_stub_max_len: float
  arc_endpoint_cluster_tol: float

  def to_json(self) -> dict[str, float | int]:
    return {
      "line_count": self.line_count,
      "arc_count": self.arc_count,
      "median_line_length": round(self.median_line_length, 4),
      "p10_line_length": round(self.p10_line_length, 4),
      "p25_line_length": round(self.p25_line_length, 4),
      "median_arc_chord": round(self.median_arc_chord, 4),
      "p75_arc_chord": round(self.p75_arc_chord, 4),
      "median_arc_radius": round(self.median_arc_radius, 4),
      "p75_arc_radius": round(self.p75_arc_radius, 4),
      "arc_chord_stub_max_len": round(self.arc_chord_stub_max_len, 4),
      "arc_endpoint_cluster_tol": round(self.arc_endpoint_cluster_tol, 4),
    }


def _arc_chord(seg: dict[str, Any]) -> float:
  ep0 = np.asarray(seg["endpoints"][0], dtype=float)[:2]
  ep1 = np.asarray(seg["endpoints"][1], dtype=float)[:2]
  return float(np.linalg.norm(ep1 - ep0))


def compute_drawing_scale(
  info: list[dict[str, Any]],
  *,
  prim_by_handle: dict[str, dict[str, Any]] | None = None,
  cfg: BendLayerConfig | None = None,
) -> DrawingScale:
  """Length / arc statistics on the current init-graph segment list."""
  cfg = cfg or BendLayerConfig()
  prim_by_handle = prim_by_handle or {}

  line_lengths = sorted(
    float(s.get("length", 0.0))
    for s in info
    if str(s.get("type", "")).lower() == "line"
    and float(s.get("length", 0.0)) > MIN_LINE_LEN
  )
  chords = sorted(
    _arc_chord(s)
    for s in info
    if str(s.get("type", "")).lower() == "arc"
  )
  radii: list[float] = []
  for s in info:
    if str(s.get("type", "")).lower() != "arc":
      continue
    r = s.get("radius")
    if r is not None:
      radii.append(float(r))
      continue
    prim = prim_by_handle.get(str(s.get("handle")))
    if prim and prim.get("type") == "ARC":
      pr = prim.get("attributes", {}).get("radius")
      if pr is not None:
        radii.append(float(pr))
  radii.sort()

  med_line = statistics.median(line_lengths) if line_lengths else DEFAULT_MEDIAN_LINE
  p10_line = _percentile(line_lengths, 10, default=med_line * 0.25) if line_lengths else med_line * 0.25
  p25_line = _percentile(line_lengths, 25, default=med_line * 0.4) if line_lengths else med_line * 0.4
  med_chord = statistics.median(chords) if chords else DEFAULT_MEDIAN_CHORD
  p75_chord = _percentile(chords, 75, default=med_chord) if chords else med_chord
  med_radius = statistics.median(radii) if radii else DEFAULT_MEDIAN_RADIUS
  p75_radius = _percentile(radii, 75, default=med_radius) if radii else med_radius

  stub_from_chord = med_chord * cfg.stub_chord_fraction
  stub_from_lines = p10_line * cfg.stub_p10_multiplier
  stub_max = min(stub_from_chord, stub_from_lines) if line_lengths and chords else max(stub_from_chord, stub_from_lines)
  cluster_tol = max(
    med_chord * cfg.endpoint_cluster_chord_scale,
    med_radius * cfg.endpoint_cluster_radius_scale,
    cfg.endpoint_cluster_floor,
  )

  return DrawingScale(
    line_count=len(line_lengths),
    arc_count=len(chords),
    median_line_length=float(med_line),
    p10_line_length=float(p10_line),
    p25_line_length=float(p25_line),
    median_arc_chord=float(med_chord),
    p75_arc_chord=float(p75_chord),
    median_arc_radius=float(med_radius),
    p75_arc_radius=float(p75_radius),
    arc_chord_stub_max_len=float(stub_max),
    arc_endpoint_cluster_tol=float(cluster_tol),
  )


def apply_drawing_scale(
  cfg: BendLayerConfig,
  scale: DrawingScale,
) -> BendLayerConfig:
  """Resolve absolute fillet thresholds from drawing statistics."""
  gap = cfg.endpoint_link_gap
  cfg.median_line_length = scale.median_line_length
  cfg.p10_line_length = scale.p10_line_length
  cfg.p25_line_length = scale.p25_line_length
  cfg.median_arc_chord = scale.median_arc_chord
  cfg.median_arc_radius = scale.median_arc_radius
  cfg.arc_chord_stub_max_len = scale.arc_chord_stub_max_len
  cfg.arc_endpoint_cluster_tol = scale.arc_endpoint_cluster_tol

  cfg.local_band_tol = gap * cfg.local_band_scale
  cfg.ix_sanity_max_dist = max(
    scale.median_arc_chord * cfg.ix_sanity_chord_scale,
    gap * cfg.ix_sanity_gap_scale,
  )
  cfg.clip_lateral_tol = max(
    scale.median_arc_radius * cfg.clip_lateral_radius_scale,
    scale.arc_endpoint_cluster_tol,
  )
  cfg.min_line_extend_len = scale.p25_line_length
  cfg.small_arc_chord_max = scale.p75_arc_chord * cfg.small_arc_chord_scale
  cfg.small_arc_radius_max = scale.p75_arc_radius * cfg.small_arc_radius_scale
  cfg.square_junction_tol = max(
    scale.median_arc_radius * cfg.junction_radius_scale,
    scale.arc_endpoint_cluster_tol,
  )
  return cfg


def resolve_bend_config(
  info: list[dict[str, Any]],
  cfg: BendLayerConfig | None = None,
  *,
  prim_by_handle: dict[str, dict[str, Any]] | None = None,
) -> tuple[BendLayerConfig, DrawingScale]:
  cfg = cfg or BendLayerConfig()
  scale = compute_drawing_scale(info, prim_by_handle=prim_by_handle, cfg=cfg)
  apply_drawing_scale(cfg, scale)
  return cfg, scale
