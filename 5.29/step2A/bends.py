"""
Step 2A bend detection and arc line normalization.

square_bend: record square corners only — no geometry rewrite.
arc_bend_detect: classify ARC as fillet or unknown — no geometry rewrite.
arc_normalize: clip adjacent LINE endpoints for confirmed fillets.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from step2A.bend_layer import (
  BendLayerConfig,
  _angle_deg,
  _best_line_pair_at_arc,
  _detect_square_markers,
  _fillet_tangent_intersection,
  _line_endpoint_dist_to_point,
  _lines_at_endpoint,
  fillet_arc_plausible_at_corner,
  is_small_fillet_arc,
)
from step2A.drawing_scale import DrawingScale, resolve_bend_config
from stage2.graph_usage import info_list_from_endpoint_graph

MIN_SEG_LEN = 1e-4
DEFAULT_FILLET_CONFIDENCE = 0.75

_FILLET_SIGNAL_WEIGHTS = {
  "localness": 0.20,
  "ix_near_arc": 0.25,
  "angle": 0.20,
  "corner_plausible": 0.15,
  "neighborhood": 0.10,
  "clip_ok": 0.10,
}


def _assign_bend_ids(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Deterministic Y numbering shared format for square / arc outputs."""
  ordered = sorted(
    records,
    key=lambda r: (
      float(r["bend_point"][0]),
      float(r["bend_point"][1]),
      str(r.get("line1", "")),
      str(r.get("line2", "")),
      str(r.get("source_arc") or ""),
    ),
  )
  out: list[dict[str, Any]] = []
  for idx, row in enumerate(ordered, start=1):
    item = dict(row)
    item["id"] = f"Y{idx:04d}"
    out.append(item)
  return out


def detect_square_bends(
  graph: Any,
  cfg: BendLayerConfig | None = None,
) -> list[dict[str, Any]]:
  """
  Detect square bends on init-graph; geometry is not modified.

  Uses the same endpoint rules as the legacy detector, but runs without
  fillet pair exclusion (square and arc scripts are independent).
  """
  cfg = cfg or BendLayerConfig()
  info = info_list_from_endpoint_graph(graph)
  raw_markers = _detect_square_markers(info, graph, set(), cfg)

  records: list[dict[str, Any]] = []
  for marker in raw_markers:
    lines = [
      m["handle"]
      for m in marker.get("members", [])
      if isinstance(m, dict) and m.get("role") == "line"
    ]
    if len(lines) != 2:
      continue
    anchor = marker.get("anchor", [])
    if len(anchor) < 2:
      continue
    records.append({
      "kind": "square",
      "bend_point": [float(anchor[0]), float(anchor[1])],
      "line1": str(lines[0]),
      "line2": str(lines[1]),
      "source_arc": None,
    })
  return _assign_bend_ids(records)


def _clip_line_at_endpoint(
  prim: dict[str, Any],
  ref_ep: np.ndarray,
  new_ep: np.ndarray,
) -> dict[str, Any] | None:
  """Move the endpoint nearest ``ref_ep`` to ``new_ep``."""
  row = dict(prim)
  attrs = dict(row.get("attributes") or {})
  start = np.asarray(attrs["start"], dtype=float)[:2]
  end = np.asarray(attrs["end"], dtype=float)[:2]
  ref = np.asarray(ref_ep, dtype=float)[:2]
  new = np.asarray(new_ep, dtype=float)[:2]
  d0 = float(np.linalg.norm(start - ref))
  d1 = float(np.linalg.norm(end - ref))
  if d0 <= d1:
    start = new
  else:
    end = new
  if float(np.linalg.norm(end - start)) < MIN_SEG_LEN:
    return None
  attrs["start"] = [float(start[0]), float(start[1]), 0.0]
  attrs["end"] = [float(end[0]), float(end[1]), 0.0]
  row["attributes"] = attrs
  return row


def _apply_clips_to_line(
  prim: dict[str, Any],
  clips: list[tuple[np.ndarray, np.ndarray]],
) -> dict[str, Any] | None:
  row: dict[str, Any] | None = dict(prim)
  for ref_ep, new_ep in clips:
    if row is None:
      return None
    row = _clip_line_at_endpoint(row, ref_ep, new_ep)
  return row


def _attach_arc_radius(
  info: list[dict[str, Any]],
  prim_by_handle: dict[str, dict[str, Any]],
) -> None:
  """Copy arc radius from raw primitives onto graph segment info."""
  for seg in info:
    if str(seg.get("type", "")).lower() != "arc":
      continue
    prim = prim_by_handle.get(str(seg["handle"]))
    if not prim or prim.get("type") != "ARC":
      continue
    radius = prim.get("attributes", {}).get("radius")
    if radius is not None:
      seg["radius"] = float(radius)


def _fillet_tangent_plausible(
  la: int,
  lb: int,
  arc_i: int,
  info: list[dict[str, Any]],
  intersection: np.ndarray,
  cfg: BendLayerConfig,
) -> bool:
  """Reject tangent intersections far from the arc / line endpoints."""
  seg = info[arc_i]
  arc_eps = [np.asarray(ep, dtype=float)[:2] for ep in seg["endpoints"]]
  line_eps = [
    np.asarray(p, dtype=float)[:2]
    for idx in (la, lb)
    for p in info[idx]["endpoints"]
  ]
  ix = np.asarray(intersection, dtype=float)[:2]
  ref_pt = np.mean(arc_eps, axis=0)
  chord = float(np.linalg.norm(arc_eps[1] - arc_eps[0]))
  if is_small_fillet_arc(arc_i, info, cfg):
    max_dist = max(
      chord * 3.0,
      cfg.endpoint_link_gap * cfg.ix_sanity_gap_scale,
      cfg.median_arc_chord * 2.0,
    )
  else:
    max_dist = max(
      cfg.ix_sanity_max_dist,
      cfg.endpoint_link_gap * 4.0,
      cfg.median_line_length * 2.0,
    )
  if float(np.linalg.norm(ix - ref_pt)) > max_dist:
    return False
  return min(float(np.linalg.norm(ix - p)) for p in line_eps) <= max_dist


def _line_far_endpoint_at_arc_junction(
  line_seg: dict[str, Any],
  arc_ep: np.ndarray,
) -> np.ndarray:
  """Endpoint of ``line_seg`` away from the arc junction."""
  eps = [
    np.asarray(line_seg["endpoints"][0], dtype=float)[:2],
    np.asarray(line_seg["endpoints"][1], dtype=float)[:2],
  ]
  arc_ep = np.asarray(arc_ep, dtype=float)[:2]
  d0 = float(np.linalg.norm(eps[0] - arc_ep))
  d1 = float(np.linalg.norm(eps[1] - arc_ep))
  return eps[1] if d0 <= d1 else eps[0]


def _max_corner_extension(
  arc_i: int,
  info: list[dict[str, Any]],
  cfg: BendLayerConfig,
) -> float:
  ep0 = np.asarray(info[arc_i]["endpoints"][0], dtype=float)[:2]
  ep1 = np.asarray(info[arc_i]["endpoints"][1], dtype=float)[:2]
  chord = float(np.linalg.norm(ep1 - ep0))
  radius = info[arc_i].get("radius")
  r = float(radius) if radius is not None else chord * 0.5
  return max(chord * 2.0, r * 3.0, cfg.median_arc_radius, cfg.median_arc_chord * 0.5)


def _clip_to_intersection_ok(
  near: np.ndarray,
  far: np.ndarray,
  ix: np.ndarray,
  line_length: float,
  max_extend: float,
  cfg: BendLayerConfig,
  *,
  lateral_tol: float | None = None,
  small_fillet: bool = False,
) -> bool:
  """
  True when ``ix`` lies on the wall-line through ``far``–``near`` and the clip
  only shortens the segment or extends slightly beyond ``near`` toward the corner.

  Short tangent legs on small fillet arcs may extend toward the corner.
  """
  near = np.asarray(near, dtype=float)[:2]
  far = np.asarray(far, dtype=float)[:2]
  ix = np.asarray(ix, dtype=float)[:2]
  wall = near - far
  wall_len = float(np.linalg.norm(wall))
  if wall_len < MIN_SEG_LEN:
    return False

  wall_u = wall / wall_len
  to_ix = ix - near
  along = float(np.dot(to_ix, wall_u))
  perp = abs(float(wall_u[0] * to_ix[1] - wall_u[1] * to_ix[0]))
  lat_tol = lateral_tol if lateral_tol is not None else cfg.clip_lateral_tol
  if perp > lat_tol:
    return False

  if along <= 0.0:
    return along >= -(wall_len - MIN_SEG_LEN)

  if small_fillet:
    return along <= max_extend

  min_len_for_extend = cfg.min_line_extend_len
  if min_len_for_extend <= 0.0:
    min_len_for_extend = cfg.endpoint_link_gap * 2.0
  if line_length < min_len_for_extend:
    return False
  return along <= max_extend


def _line_near_endpoint_at_arc_junction(
  line_seg: dict[str, Any],
  arc_ep: np.ndarray,
) -> np.ndarray:
  """Endpoint of ``line_seg`` at the arc junction."""
  eps = [
    np.asarray(line_seg["endpoints"][0], dtype=float)[:2],
    np.asarray(line_seg["endpoints"][1], dtype=float)[:2],
  ]
  arc_ep = np.asarray(arc_ep, dtype=float)[:2]
  d0 = float(np.linalg.norm(eps[0] - arc_ep))
  d1 = float(np.linalg.norm(eps[1] - arc_ep))
  return eps[0] if d0 <= d1 else eps[1]


def _neighborhood_factor(
  arc_i: int,
  info: list[dict[str, Any]],
  graph: Any,
  gap: float,
) -> float:
  """Reduce confidence when an arc endpoint has a busy LINE neighborhood."""
  deg0 = len(_lines_at_endpoint(arc_i, 0, info, graph, gap))
  deg1 = len(_lines_at_endpoint(arc_i, 1, info, graph, gap))
  if deg0 >= 3 or deg1 >= 3:
    return 0.5
  return 1.0


def _fillet_signal_scores(
  la: int,
  lb: int,
  arc_i: int,
  info: list[dict[str, Any]],
  graph: Any,
  ix: np.ndarray,
  cfg: BendLayerConfig,
) -> dict[str, float]:
  gap = cfg.endpoint_link_gap
  ep0 = np.asarray(info[arc_i]["endpoints"][0], dtype=float)[:2]
  ep1 = np.asarray(info[arc_i]["endpoints"][1], dtype=float)[:2]
  arc_mid = (ep0 + ep1) * 0.5
  d0 = _line_endpoint_dist_to_point(la, ep0, info)
  d1 = _line_endpoint_dist_to_point(lb, ep1, info)
  dist_ix = float(np.linalg.norm(ix - arc_mid))
  chord = float(np.linalg.norm(ep1 - ep0))
  radius = info[arc_i].get("radius")
  r = float(radius) if radius is not None else chord * 0.5
  ix_ref = max(chord * 2.0, r * 3.0, cfg.median_arc_radius, cfg.median_arc_chord * 0.5)

  ang = _angle_deg(info[la]["direction"], info[lb]["direction"])
  acute = min(ang, 180.0 - ang)

  max_extend = _max_corner_extension(arc_i, info, cfg)
  small = is_small_fillet_arc(arc_i, info, cfg)
  near0 = _line_near_endpoint_at_arc_junction(info[la], ep0)
  near1 = _line_near_endpoint_at_arc_junction(info[lb], ep1)
  far0 = _line_far_endpoint_at_arc_junction(info[la], ep0)
  far1 = _line_far_endpoint_at_arc_junction(info[lb], ep1)
  ok0 = _clip_to_intersection_ok(
    near0, far0, ix, float(info[la].get("length", 0.0)), max_extend, cfg,
    small_fillet=small,
  )
  ok1 = _clip_to_intersection_ok(
    near1, far1, ix, float(info[lb].get("length", 0.0)), max_extend, cfg,
    small_fillet=small,
  )

  return {
    "localness": max(0.0, 1.0 - (d0 + d1) / max(2.0 * gap, 1e-6)),
    "ix_near_arc": max(0.0, 1.0 - dist_ix / ix_ref),
    "angle": max(0.0, 1.0 - abs(acute - 90.0) / 90.0),
    "corner_plausible": 1.0 if fillet_arc_plausible_at_corner(
      la, lb, arc_i, info, junction_tol=cfg.square_junction_tol,
    ) else 0.0,
    "neighborhood": _neighborhood_factor(arc_i, info, graph, gap),
    "clip_ok": 1.0 if (ok0 and ok1) else 0.0,
  }


def _confidence_from_signals(signals: dict[str, float]) -> float:
  total = 0.0
  weight_sum = 0.0
  for key, weight in _FILLET_SIGNAL_WEIGHTS.items():
    total += weight * float(signals.get(key, 0.0))
    weight_sum += weight
  return total / weight_sum if weight_sum > 0.0 else 0.0


def detect_arc_bends(
  graph: Any,
  primitives: list[dict[str, Any]],
  cfg: BendLayerConfig | None = None,
  *,
  fillet_threshold: float = DEFAULT_FILLET_CONFIDENCE,
) -> tuple[list[dict[str, Any]], DrawingScale]:
  """
  Classify each ARC as fillet (high confidence) or unknown.

  Detection only — no geometry rewrite.
  """
  cfg = cfg or BendLayerConfig()
  info = info_list_from_endpoint_graph(graph)
  prim_by_handle = {str(p["handle"]): p for p in primitives}
  _attach_arc_radius(info, prim_by_handle)
  cfg, scale = resolve_bend_config(info, cfg, prim_by_handle=prim_by_handle)

  records: list[dict[str, Any]] = []
  for arc_i, seg in enumerate(info):
    if str(seg.get("type", "")).lower() != "arc":
      continue
    arc_handle = str(seg["handle"])
    base: dict[str, Any] = {"arc_handle": arc_handle}

    pair = _best_line_pair_at_arc(
      arc_i, info, graph, cfg,
    )
    if pair is None:
      records.append({
        **base,
        "status": "unknown",
        "confidence": 0.0,
      })
      continue

    la, lb = pair
    intersection = _fillet_tangent_intersection(la, lb, arc_i, info, cfg)
    if intersection is None:
      records.append({
        **base,
        "status": "unknown",
        "confidence": 0.0,
        "line1": str(info[la]["handle"]),
        "line2": str(info[lb]["handle"]),
      })
      continue

    ix = np.asarray(intersection, dtype=float)[:2]
    if not _fillet_tangent_plausible(la, lb, arc_i, info, ix, cfg):
      records.append({
        **base,
        "status": "unknown",
        "confidence": 0.0,
        "line1": str(info[la]["handle"]),
        "line2": str(info[lb]["handle"]),
      })
      continue

    signals = _fillet_signal_scores(la, lb, arc_i, info, graph, ix, cfg)
    confidence = _confidence_from_signals(signals)
    row: dict[str, Any] = {
      **base,
      "confidence": round(confidence, 4),
      "bend_point": [float(ix[0]), float(ix[1])],
      "line1": str(info[la]["handle"]),
      "line2": str(info[lb]["handle"]),
      "signals": {k: round(v, 4) for k, v in signals.items()},
    }
    if confidence >= fillet_threshold:
      row["status"] = "fillet"
    else:
      row["status"] = "unknown"
    records.append(row)

  return records, scale


def _arc_records_to_bend_markers(
  arc_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  markers: list[dict[str, Any]] = []
  for rec in arc_records:
    if rec.get("status") != "fillet":
      continue
    bp = rec.get("bend_point")
    if not bp:
      continue
    markers.append({
      "kind": "fillet",
      "bend_point": bp,
      "line1": rec.get("line1"),
      "line2": rec.get("line2"),
      "source_arc": rec.get("arc_handle"),
      "confidence": rec.get("confidence"),
    })
  return _assign_bend_ids(markers)


def normalize_arcs_from_detect(
  graph: Any,
  primitives: list[dict[str, Any]],
  arc_records: list[dict[str, Any]],
  cfg: BendLayerConfig | None = None,
  *,
  fillet_threshold: float = DEFAULT_FILLET_CONFIDENCE,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
  """
  Apply geometry clips for fillet ARCs already classified by ``detect_arc_bends``.

  Returns ``(arc_line_normalize, unmodified_elements)``.
  """
  cfg = cfg or BendLayerConfig()
  info = info_list_from_endpoint_graph(graph)
  prim_by_handle = {str(p["handle"]): p for p in primitives}
  _attach_arc_radius(info, prim_by_handle)
  cfg, _scale = resolve_bend_config(info, cfg, prim_by_handle=prim_by_handle)
  handle_to_i = {str(seg["handle"]): i for i, seg in enumerate(info)}

  line_clips: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
  consumed_arcs: set[str] = set()

  for rec in arc_records:
    if rec.get("status") != "fillet":
      continue
    if float(rec.get("confidence", 0.0)) < fillet_threshold:
      continue
    if float(rec.get("signals", {}).get("clip_ok", 0.0)) < 1.0:
      continue

    arc_handle = str(rec["arc_handle"])
    arc_i = handle_to_i.get(arc_handle)
    if arc_i is None:
      continue
    line1_handle = str(rec.get("line1", ""))
    line2_handle = str(rec.get("line2", ""))
    la = handle_to_i.get(line1_handle)
    lb = handle_to_i.get(line2_handle)
    if la is None or lb is None:
      continue

    bp = rec.get("bend_point")
    if not bp:
      continue
    ix = np.asarray(bp, dtype=float)[:2]

    ep0 = np.asarray(info[arc_i]["endpoints"][0], dtype=float)[:2]
    ep1 = np.asarray(info[arc_i]["endpoints"][1], dtype=float)[:2]
    near0 = _line_near_endpoint_at_arc_junction(info[la], ep0)
    near1 = _line_near_endpoint_at_arc_junction(info[lb], ep1)
    if float(np.linalg.norm(near0 - ix)) < MIN_SEG_LEN:
      continue
    if float(np.linalg.norm(near1 - ix)) < MIN_SEG_LEN:
      continue

    line_clips.setdefault(line1_handle, []).append((near0, ix))
    line_clips.setdefault(line2_handle, []).append((near1, ix))
    consumed_arcs.add(arc_handle)

  modified_handles = set(line_clips)
  arc_lines: list[dict[str, Any]] = []
  for handle in sorted(modified_handles):
    prim = prim_by_handle.get(handle)
    if not prim or str(prim.get("type", "")).upper() != "LINE":
      continue
    clipped = _apply_clips_to_line(prim, line_clips[handle])
    if clipped is not None:
      arc_lines.append(clipped)

  unmodified: list[dict[str, Any]] = []
  for prim in primitives:
    handle = str(prim.get("handle", ""))
    typ = str(prim.get("type", "")).upper()
    if typ == "ARC" and handle in consumed_arcs:
      continue
    if typ == "LINE" and handle in modified_handles:
      continue
    unmodified.append(prim)

  return arc_lines, unmodified


def square_bends_to_json(
  bends: list[dict[str, Any]],
  *,
  source_stem: str,
) -> dict[str, Any]:
  return {
    "kind": "square_bend",
    "schema_version": 1,
    "source_stem": source_stem,
    "bends": bends,
  }


def arc_bend_detect_to_json(
  arc_records: list[dict[str, Any]],
  *,
  source_stem: str,
  fillet_threshold: float = DEFAULT_FILLET_CONFIDENCE,
  drawing_scale: dict[str, float | int] | None = None,
) -> dict[str, Any]:
  bends = _arc_records_to_bend_markers(arc_records)
  doc: dict[str, Any] = {
    "kind": "arc_bend",
    "schema_version": 2,
    "source_stem": source_stem,
    "fillet_threshold": fillet_threshold,
    "arcs": arc_records,
    "bends": bends,
  }
  if drawing_scale:
    doc["drawing_scale"] = drawing_scale
  return doc


def arc_line_normalize_to_json(
  lines: list[dict[str, Any]],
  *,
  source_stem: str,
) -> dict[str, Any]:
  return {
    "kind": "arc_line_normalize",
    "schema_version": 1,
    "source_stem": source_stem,
    "elements": lines,
  }


def unmodified_elements_to_json(
  elements: list[dict[str, Any]],
  *,
  source_stem: str,
) -> dict[str, Any]:
  return {
    "kind": "unmodified_elements",
    "schema_version": 1,
    "source_stem": source_stem,
    "elements": elements,
  }
