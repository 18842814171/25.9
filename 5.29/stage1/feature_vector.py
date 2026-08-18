"""Flatten per-layer feature records into numeric vectors for ML."""

from __future__ import annotations

from typing import Any

import numpy as np

FEATURE_NAMES = [
  "n_segments",
  "total_length",
  "mean_length",
  "std_length",
  "max_length",
  "parallel_pair_ratio",
  "long_segment_ratio",
  "dir_bin_0",
  "dir_bin_1",
  "dir_bin_2",
  "dir_bin_3",
  "dir_bin_4",
  "dir_bin_5",
  "dir_bin_6",
  "dir_bin_7",
  "entity_count",
  "text_count",
  "mean_text_height",
  "text_density",
  "dimension_count",
  "leader_count",
  "mean_leader_length",
  "line_ratio",
  "lwpolyline_ratio",
]


def layer_record_to_vector(record: dict[str, Any]) -> np.ndarray:
  g = record.get("geometry") or {}
  a = record.get("annotation") or {}
  hist = g.get("direction_hist") or [0.0] * 8
  if len(hist) < 8:
    hist = list(hist) + [0.0] * (8 - len(hist))

  type_counts = a.get("type_counts") or {}
  total_ent = max(a.get("entity_count", 0), 1)
  line_ratio = type_counts.get("LINE", 0) / total_ent
  lwp_ratio = type_counts.get("LWPOLYLINE", 0) / total_ent

  return np.array(
    [
      float(g.get("n_segments", 0)),
      float(g.get("total_length", 0)),
      float(g.get("mean_length", 0)),
      float(g.get("std_length", 0)),
      float(g.get("max_length", 0)),
      float(g.get("parallel_pair_ratio", 0)),
      float(g.get("long_segment_ratio", 0)),
      *[float(x) for x in hist[:8]],
      float(a.get("entity_count", 0)),
      float(a.get("text_count", 0)),
      float(a.get("mean_text_height", 0)),
      float(a.get("text_density", 0)),
      float(a.get("dimension_count", 0)),
      float(a.get("leader_count", 0)),
      float(a.get("mean_leader_length", 0)),
      line_ratio,
      lwp_ratio,
    ],
    dtype=np.float64,
  )


def build_matrix(
  layers: dict[str, dict[str, Any]],
) -> tuple[list[str], np.ndarray]:
  names = list(layers.keys())
  X = np.vstack([layer_record_to_vector(layers[n]) for n in names])
  return names, X
