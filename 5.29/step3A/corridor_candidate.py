"""Build corridor candidates from wall pairs and wall geometry."""

from __future__ import annotations

from typing import Any

import numpy as np

from utils.segment_geometry import (
  assign_left_right as _assign_left_right,
  overlap_centerline as _overlap_centerline,
  unit as _unit,
)


def _seg_from_wall_row(row: dict[str, Any]) -> dict[str, Any]:
  attrs = row.get("attributes") or {}
  start = np.asarray(attrs["start"], dtype=float)[:2]
  end = np.asarray(attrs["end"], dtype=float)[:2]
  vec = end - start
  length = float(np.linalg.norm(vec))
  direction = _unit(vec) if length >= 1e-12 else np.array([1.0, 0.0])
  ws_id = str(row.get("wall_segment_id", ""))
  return {
    "wall_id": ws_id,
    "start": start,
    "end": end,
    "mid": (start + end) / 2.0,
    "length": length,
    "direction": direction,
  }


def wall_index_from_geometry(wall_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
  out: dict[str, dict[str, Any]] = {}
  for row in wall_doc.get("walls") or []:
    ws_id = str(row.get("wall_segment_id", ""))
    if ws_id:
      out[ws_id] = _seg_from_wall_row(row)
  return out


def build_candidate_from_pair(
  pair: dict[str, Any],
  wall_index: dict[str, dict[str, Any]],
  *,
  corridor_id: str,
) -> dict[str, Any] | None:
  seg_a = wall_index.get(pair["wall_a"])
  seg_b = wall_index.get(pair["wall_b"])
  if seg_a is None or seg_b is None:
    return None

  centerline = _overlap_centerline(seg_a, seg_b)
  if centerline is None:
    return None

  left_id, right_id = _assign_left_right(
    pair["wall_a"],
    pair["wall_b"],
    seg_a,
    seg_b,
    centerline,
  )
  overlap_ratio = float(pair.get("overlap_ratio", 0.0))
  return {
    "corridor_id": corridor_id,
    "pair_id": str(pair["pair_id"]),
    "left_wall_id": left_id,
    "right_wall_id": right_id,
    "centerline": centerline,
    "corridor_length": centerline["length"],
    "width": round(float(pair.get("width", 0.0)), 4),
    "overlap_ratio": round(overlap_ratio, 4),
    "confidence": round(overlap_ratio, 4),
  }


def build_candidates_from_pairs(
  pairs: list[dict[str, Any]],
  wall_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
  candidates: list[dict[str, Any]] = []
  for idx, pair in enumerate(pairs, start=1):
    cand = build_candidate_from_pair(
      pair,
      wall_index,
      corridor_id=f"CC{idx:03d}",
    )
    if cand is not None:
      candidates.append(cand)
  return candidates


def deduplicate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Keep best candidate per normalized wall pair (by overlap_ratio)."""
  best: dict[tuple[str, str], dict[str, Any]] = {}
  for cand in candidates:
    left = str(cand["left_wall_id"])
    right = str(cand["right_wall_id"])
    key = tuple(sorted((left, right)))
    prev = best.get(key)
    if prev is None or float(cand["overlap_ratio"]) > float(prev["overlap_ratio"]):
      best[key] = cand

  out = list(best.values())
  out.sort(key=lambda c: (c["left_wall_id"], c["right_wall_id"]))
  for idx, cand in enumerate(out, start=1):
    cand["corridor_id"] = f"CC{idx:03d}"
  return out


def candidates_to_json(
  candidates: list[dict[str, Any]],
  *,
  source_stem: str,
  global_scale: dict[str, float] | None = None,
) -> dict[str, Any]:
  doc: dict[str, Any] = {
    "kind": "corridor_candidates",
    "schema_version": 1,
    "source_stem": source_stem,
    "candidates": candidates,
  }
  if global_scale is not None:
    doc["global_scale"] = global_scale
  return doc
