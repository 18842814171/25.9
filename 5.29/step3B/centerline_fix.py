"""Extend corridor centerlines using promoted stub + determined partner walls."""

from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np

from step2B.config import ParallelGraphConfig
from utils.centerline_graph import cand_wall_to_id_from_graph
from utils.segment_geometry import (
  acute_angle_deg,
  assign_left_right,
  endpoint_gap,
  overlap_centerline,
)
from step3B.graph_inputs import _seg_from_parallel_node
from step3B.residual_graph import walls_touching_stub


def _seg_dict_from_node(node_id: str, data: dict[str, Any]) -> dict[str, Any]:
  seg = _seg_from_parallel_node(node_id, data)
  seg["wall_id"] = str(node_id)
  return seg


def _merge_centerlines(
  old_cl: dict[str, Any],
  new_cl: dict[str, Any],
) -> dict[str, Any]:
  """Union axial extent of two colinear centerlines."""
  origin = np.asarray(new_cl["start"], dtype=float)[:2]
  axis = np.asarray(new_cl["direction"], dtype=float)[:2]
  axis_len = float(np.linalg.norm(axis))
  if axis_len < 1e-12:
    return dict(new_cl)
  axis = axis / axis_len

  def interval(cl: dict[str, Any]) -> tuple[float, float]:
    ts = []
    for pt in (cl.get("start"), cl.get("end")):
      p = np.asarray(pt, dtype=float)[:2]
      ts.append(float(np.dot(p - origin, axis)))
    return min(ts), max(ts)

  a0, a1 = interval(old_cl)
  b0, b1 = interval(new_cl)
  t0, t1 = min(a0, b0), max(a1, b1)
  if t1 - t0 < 1e-6:
    return dict(new_cl)

  start = origin + axis * t0
  end = origin + axis * t1
  vec = end - start
  length = float(np.linalg.norm(vec))
  direction = vec / length if length >= 1e-12 else axis
  return {
    "start": [round(float(start[0]), 4), round(float(start[1]), 4)],
    "end": [round(float(end[0]), 4), round(float(end[1]), 4)],
    "direction": [round(float(direction[0]), 6), round(float(direction[1]), 6)],
    "length": round(length, 4),
  }


def _corridor_seg_from_node(node_id: str, data: dict[str, Any]) -> dict[str, Any]:
  start = np.asarray(data["start"], dtype=float)[:2]
  end = np.asarray(data["end"], dtype=float)[:2]
  direction = np.asarray(data.get("direction") or [1.0, 0.0], dtype=float)[:2]
  return {
    "node_id": str(node_id),
    "start": start,
    "end": end,
    "mid": (start + end) / 2.0,
    "length": float(data.get("length", 0.0)),
    "direction": direction,
    "endpoints": [start, end],
  }


def _add_endpoint_edge_if_needed(
  graph: nx.Graph,
  seg_a: dict[str, Any],
  seg_b: dict[str, Any],
  cfg: ParallelGraphConfig,
) -> dict[str, Any] | None:
  gap = endpoint_gap(seg_a, seg_b)
  if gap > cfg.endpoint_link_gap:
    return None
  angle = acute_angle_deg(seg_a["direction"], seg_b["direction"])
  u, v = str(seg_a["node_id"]), str(seg_b["node_id"])
  if graph.has_edge(u, v):
    return {"corridor_ids": [u, v], "status": "exists", "endpoint_gap": round(gap, 4)}
  graph.add_edge(
    u,
    v,
    edge_kind="endpoint",
    endpoint_gap=round(gap, 4),
    angle_deg=round(angle, 4),
    is_parallel=angle < cfg.angle_th_deg,
    is_ortho=abs(angle - 90.0) < cfg.angle_th_deg,
    source="centerline_fix",
  )
  return {"corridor_ids": [u, v], "status": "added", "endpoint_gap": round(gap, 4)}


def _touch_wall_for_corridor(
  residual_graph: nx.Graph,
  stub_id: str,
  corridor_id: str,
) -> str:
  for row in walls_touching_stub(residual_graph, stub_id):
    if str(row.get("corridor_id")) == str(corridor_id):
      wid = str(row.get("wall_segment_id", ""))
      if wid:
        return wid
  return ""


def _opposite_wall_for_corridor(
  *,
  corridor_id: str,
  partner_wall_id: str,
  touch_wall_id: str,
  existing_left: str,
  existing_right: str,
  cand_wall_to_id: dict[str, str],
) -> str:
  """Pick the determined wall that pairs with the promoted stub for this corridor."""
  if partner_wall_id in (existing_left, existing_right):
    return partner_wall_id
  if touch_wall_id in (existing_left, existing_right):
    return touch_wall_id
  if cand_wall_to_id.get(partner_wall_id) == str(corridor_id):
    return partner_wall_id
  return touch_wall_id or partner_wall_id


def apply_centerline_fixes(
  centerline_graph: nx.Graph,
  residual_graph: nx.Graph,
  promotions: list[dict[str, Any]],
  *,
  para_cfg: ParallelGraphConfig | None = None,
) -> tuple[nx.Graph, list[dict[str, Any]]]:
  """
  For each promotion, extend target corridor centerlines using stub + partner wall.

  Returns a copied graph and per-fix records.
  """
  para_cfg = para_cfg or ParallelGraphConfig()
  fixed = centerline_graph.copy()
  fixes: list[dict[str, Any]] = []
  cand_wall_to_id = cand_wall_to_id_from_graph(centerline_graph)

  for promo in promotions:
    sid = str(promo["residual_handle"])
    if not residual_graph.has_node(sid):
      continue
    stub_seg = _seg_dict_from_node(sid, residual_graph.nodes[sid])
    partner_ids = list(promo.get("partner_wall_ids") or [])
    if not partner_ids:
      continue
    partner_id = partner_ids[0]

    corridor_fixes: list[dict[str, Any]] = []
    for cid in promo.get("target_corridor_ids") or []:
      if not fixed.has_node(str(cid)):
        corridor_fixes.append({
          "corridor_id": str(cid),
          "status": "skipped",
          "reason": "missing_corridor_node",
        })
        continue

      node = fixed.nodes[str(cid)]
      existing_left = str(node.get("left_wall_id", ""))
      existing_right = str(node.get("right_wall_id", ""))
      touch_wall = _touch_wall_for_corridor(residual_graph, sid, str(cid))
      opposite_id = _opposite_wall_for_corridor(
        corridor_id=str(cid),
        partner_wall_id=partner_id,
        touch_wall_id=touch_wall,
        existing_left=existing_left,
        existing_right=existing_right,
        cand_wall_to_id=cand_wall_to_id,
      )
      if not residual_graph.has_node(opposite_id):
        corridor_fixes.append({
          "corridor_id": str(cid),
          "status": "skipped",
          "reason": "missing_opposite_wall",
          "opposite_wall_id": opposite_id,
        })
        continue

      opposite_seg = _seg_dict_from_node(
        opposite_id,
        residual_graph.nodes[opposite_id],
      )
      pair_cl = overlap_centerline(stub_seg, opposite_seg)
      if pair_cl is None:
        corridor_fixes.append({
          "corridor_id": str(cid),
          "status": "skipped",
          "reason": "no_overlap_centerline",
          "opposite_wall_id": opposite_id,
        })
        continue

      old_cl = node.get("centerline") or {
        "start": list(node.get("start") or [0.0, 0.0]),
        "end": list(node.get("end") or [0.0, 0.0]),
        "direction": list(node.get("direction") or [1.0, 0.0]),
        "length": float(node.get("length", 0.0)),
      }
      if acute_angle_deg(
        np.asarray(old_cl["direction"], dtype=float),
        np.asarray(pair_cl["direction"], dtype=float),
      ) > para_cfg.angle_th_deg:
        corridor_fixes.append({
          "corridor_id": str(cid),
          "status": "skipped",
          "reason": "axis_mismatch",
          "opposite_wall_id": opposite_id,
        })
        continue

      merged = _merge_centerlines(old_cl, pair_cl)
      left_id, right_id = assign_left_right(
        sid,
        opposite_id,
        stub_seg,
        opposite_seg,
        pair_cl,
      )

      new_length = float(merged["length"])
      old_length = float(old_cl.get("length", 0.0))
      if new_length <= old_length + 1e-4:
        corridor_fixes.append({
          "corridor_id": str(cid),
          "status": "unchanged",
          "opposite_wall_id": opposite_id,
          "length": round(old_length, 4),
        })
        continue

      if opposite_id == existing_left:
        fixed.nodes[str(cid)]["right_wall_id"] = sid
      elif opposite_id == existing_right:
        fixed.nodes[str(cid)]["left_wall_id"] = sid
      else:
        fixed.nodes[str(cid)]["left_wall_id"] = str(left_id)
        fixed.nodes[str(cid)]["right_wall_id"] = str(right_id)

      fixed.nodes[str(cid)]["start"] = list(merged["start"])
      fixed.nodes[str(cid)]["end"] = list(merged["end"])
      fixed.nodes[str(cid)]["direction"] = list(merged["direction"])
      fixed.nodes[str(cid)]["length"] = float(merged["length"])
      fixed.nodes[str(cid)]["corridor_length"] = float(merged["length"])
      fixed.nodes[str(cid)]["centerline"] = merged

      corridor_fixes.append({
        "corridor_id": str(cid),
        "status": "extended",
        "opposite_wall_id": opposite_id,
        "old_length": round(float(old_cl.get("length", 0.0)), 4),
        "new_length": round(float(merged["length"]), 4),
        "left_wall_id": str(fixed.nodes[str(cid)]["left_wall_id"]),
        "right_wall_id": str(fixed.nodes[str(cid)]["right_wall_id"]),
      })

    fixes.append({
      "residual_handle": sid,
      "partner_wall_id": partner_id,
      "promotion_reason": promo.get("promotion_reason"),
      "status": "applied" if any(cf.get("status") == "extended" for cf in corridor_fixes) else "skipped",
      "corridor_fixes": corridor_fixes,
    })

  endpoint_links: list[dict[str, Any]] = []
  touched_cids: set[str] = set()
  for promo in promotions:
    for cid in promo.get("target_corridor_ids") or []:
      touched_cids.add(str(cid))

  touched = sorted(touched_cids)
  segs = {
    cid: _corridor_seg_from_node(cid, fixed.nodes[cid])
    for cid in touched
    if fixed.has_node(cid)
  }
  for i in range(len(touched)):
    for j in range(i + 1, len(touched)):
      row = _add_endpoint_edge_if_needed(
        fixed,
        segs[touched[i]],
        segs[touched[j]],
        para_cfg,
      )
      if row is not None:
        endpoint_links.append(row)

  fixed.graph["kind"] = "centerline_graph_fixed"
  fixed.graph["schema_version"] = 2
  fixed.graph["centerline_fix_count"] = sum(
    1
    for row in fixes
    if row.get("status") == "applied"
    and any(cf.get("status") == "extended" for cf in row.get("corridor_fixes") or [])
  )
  fixed.graph["centerline_endpoint_links_added"] = sum(
    1 for row in endpoint_links if row.get("status") == "added"
  )
  return fixed, fixes


def centerline_fix_summary(
  *,
  source_stem: str,
  promotions: list[dict[str, Any]],
  deferred: list[dict[str, Any]],
  fixes: list[dict[str, Any]],
  syntheses: list[dict[str, Any]] | None = None,
  endpoint_link_gap: float,
  width_tol: float,
) -> dict[str, Any]:
  extended = sum(
    len([cf for cf in row.get("corridor_fixes") or [] if cf.get("status") == "extended"])
    for row in fixes
  )
  synthesized = sum(
    1 for row in syntheses or [] if row.get("status") == "synthesized"
  )
  return {
    "kind": "centerline_fix",
    "schema_version": 1,
    "source_stem": source_stem,
    "promoted_count": len(promotions),
    "deferred_count": len(deferred),
    "corridor_extensions": extended,
    "corridor_synthesized": synthesized,
    "endpoint_link_gap": round(endpoint_link_gap, 4),
    "partner_width_tol": round(width_tol, 4),
    "promotions": promotions,
    "deferred": deferred,
    "fixes": fixes,
    "syntheses": syntheses or [],
  }
