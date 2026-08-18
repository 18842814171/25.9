"""Drawing-relative scale defaults and width statistics."""

from __future__ import annotations

import statistics
from typing import Any

DEFAULT_MEDIAN_CORRIDOR_WIDTH = 5.4
DEFAULT_MEDIAN_WIDTH = DEFAULT_MEDIAN_CORRIDOR_WIDTH


def percentile(
  sorted_vals: list[float],
  p: float,
  *,
  default: float = DEFAULT_MEDIAN_CORRIDOR_WIDTH,
) -> float:
  if not sorted_vals:
    return default
  if len(sorted_vals) == 1:
    return sorted_vals[0]
  k = (len(sorted_vals) - 1) * p / 100.0
  f = int(k)
  c = min(f + 1, len(sorted_vals) - 1)
  if f == c:
    return sorted_vals[f]
  return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


def global_scale_to_json(
  scale: dict[str, float],
  *,
  source_stem: str,
  resolved_thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
  doc: dict[str, Any] = {
    "kind": "global_scale",
    "schema_version": 1,
    "source_stem": source_stem,
    **scale,
  }
  if resolved_thresholds is not None:
    doc["resolved_thresholds"] = resolved_thresholds
  return doc


def compute_global_scale(candidates: list[dict[str, Any]]) -> dict[str, float]:
  """Width statistics over corridor candidates (current drawing)."""
  widths = sorted(
    float(c.get("width", 0.0)) for c in candidates if float(c.get("width", 0.0)) > 0.0
  )
  if not widths:
    return {
      "median_corridor_width": DEFAULT_MEDIAN_CORRIDOR_WIDTH,
      "p25_width": DEFAULT_MEDIAN_CORRIDOR_WIDTH,
      "p75_width": DEFAULT_MEDIAN_CORRIDOR_WIDTH,
      "candidate_count": 0,
    }
  return {
    "median_corridor_width": round(statistics.median(widths), 4),
    "p25_width": round(percentile(widths, 25), 4),
    "p75_width": round(percentile(widths, 75), 4),
    "candidate_count": len(widths),
  }
