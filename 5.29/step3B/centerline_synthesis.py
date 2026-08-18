"""Synthesize corridor centerlines from qualified parallel residual components.

A connector centerline is created only when all of the following hold:

  parallel component
    + members sufficiently colinear
    + two distinct wall sides (each with at least one resolved ``wall`` node)
    + corridor topology attachment on both axial ends (or nearly)
  => centerline synthesis

This is not H-bar / crosscut handling (reserved for future work).
"""

from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np

from step2B.config import ParallelGraphConfig
from step3B.corridor_wall_candidates import NODE_WALL
from step3B.graph_inputs import _seg_from_parallel_node
from step3B.residual_graph import (
  EDGE_CORRIDOR_STUB_PARALLEL,
  EDGE_STUB_STUB_PARALLEL,
  walls_touching_stub,
)
from utils.segment_geometry import (
  acute_angle_deg,
  assign_left_right,
  clamp_point_to_segment,
  cross2,
  endpoint_gap,
  overlap_ratio,
  point_line_offset,
  projection_interval,
  unit,
)

SYNTHESIS_STATUS = "synthesized"


def _parallel_components(residual_graph: nx.Graph) -> list[list[str]]:
  para = nx.Graph()
  for u, v, data in residual_graph.edges(data=True):
    kind = str(data.get("edge_kind", ""))
    if kind not in (EDGE_STUB_STUB_PARALLEL, EDGE_CORRIDOR_STUB_PARALLEL):
      continue
    para.add_edge(str(u), str(v))
  return [sorted(comp) for comp in nx.connected_components(para)]


def _seg_from_node(residual_graph: nx.Graph, node_id: str) -> dict[str, Any]:
  seg = _seg_from_parallel_node(node_id, residual_graph.nodes[node_id])
  seg["wall_id"] = str(node_id)
  seg["node_type"] = str(residual_graph.nodes[node_id].get("node_type", ""))
  return seg


def _colinear_axis(
  segs: list[dict[str, Any]],
  angle_th_deg: float,
) -> tuple[bool, np.ndarray, np.ndarray]:
  if not segs:
    return False, np.zeros(2), np.array([1.0, 0.0])
  ref = max(segs, key=lambda s: float(s["length"]))
  axis = unit(np.asarray(ref["direction"], dtype=float)[:2])
  origin = np.asarray(ref["start"], dtype=float)[:2]
  for seg in segs:
    if acute_angle_deg(
      np.asarray(seg["direction"], dtype=float),
      axis,
    ) > angle_th_deg:
      return False, origin, axis
  return True, origin, axis


def _split_sides(
  segs: list[dict[str, Any]],
  origin: np.ndarray,
  axis: np.ndarray,
  *,
  residual_graph: nx.Graph | None = None,
  member_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
  seg_by_id = {str(seg["wall_id"]): seg for seg in segs}
  ids = member_ids or sorted(seg_by_id)

  if residual_graph is not None and ids:
    para = nx.Graph()
    for nid in ids:
      para.add_node(str(nid))
    for u, v, data in residual_graph.edges(data=True):
      kind = str(data.get("edge_kind", ""))
      if kind not in (EDGE_STUB_STUB_PARALLEL, EDGE_CORRIDOR_STUB_PARALLEL):
        continue
      if str(u) in seg_by_id and str(v) in seg_by_id:
        para.add_edge(str(u), str(v))

    if para.number_of_edges() > 0:
      side_a_ids: set[str] = set()
      side_b_ids: set[str] = set()
      for comp in nx.connected_components(para):
        nodes = sorted(comp)
        if len(nodes) == 1:
          (only,) = nodes
          if not side_a_ids:
            side_a_ids.add(only)
          else:
            side_b_ids.add(only)
          continue
        color: dict[str, int] = {}
        start = nodes[0]
        color[start] = 0
        queue = [start]
        while queue:
          cur = queue.pop(0)
          for nb in para.neighbors(cur):
            expected = 1 - color[cur]
            if nb in color:
              if color[nb] != expected:
                color.clear()
                break
              continue
            color[nb] = expected
            queue.append(nb)
          if not color:
            break
        if color:
          for nid, ci in color.items():
            (side_a_ids if ci == 0 else side_b_ids).add(nid)
      if side_a_ids and side_b_ids:
        return (
          [seg_by_id[nid] for nid in sorted(side_a_ids)],
          [seg_by_id[nid] for nid in sorted(side_b_ids)],
        )

  signed: list[tuple[float, dict[str, Any]]] = []
  for seg in segs:
    cross = cross2(axis, np.asarray(seg["mid"], dtype=float)[:2] - origin)
    if abs(cross) < 1e-6:
      continue
    signed.append((cross, seg))

  if not signed:
    return None
  side_a = [seg for cross, seg in signed if cross < 0.0]
  side_b = [seg for cross, seg in signed if cross > 0.0]
  if not side_a or not side_b:
    return None
  return side_a, side_b


def _side_envelope_interval(
  segs: list[dict[str, Any]],
  origin: np.ndarray,
  axis: np.ndarray,
) -> tuple[float, float]:
  t0, t1 = float("inf"), float("-inf")
  for seg in segs:
    a0, a1 = projection_interval(
      np.asarray(seg["start"], dtype=float)[:2],
      np.asarray(seg["end"], dtype=float)[:2],
      origin,
      axis,
    )
    t0 = min(t0, a0)
    t1 = max(t1, a1)
  return t0, t1


def _closest_point_on_side(
  point: np.ndarray,
  segs: list[dict[str, Any]],
) -> np.ndarray:
  best_dist = float("inf")
  best_pt = np.asarray(segs[0]["start"], dtype=float)[:2]
  for seg in segs:
    start = np.asarray(seg["start"], dtype=float)[:2]
    end = np.asarray(seg["end"], dtype=float)[:2]
    pt = clamp_point_to_segment(point, start, end)
    dist = float(np.linalg.norm(point - pt))
    if dist < best_dist:
      best_dist = dist
      best_pt = pt
  return best_pt


def _centerline_between_sides(
  side_a: list[dict[str, Any]],
  side_b: list[dict[str, Any]],
  origin: np.ndarray,
  axis: np.ndarray,
) -> dict[str, Any] | None:
  a0, a1 = _side_envelope_interval(side_a, origin, axis)
  b0, b1 = _side_envelope_interval(side_b, origin, axis)
  t0 = max(a0, b0)
  t1 = min(a1, b1)
  if t1 - t0 < 1e-6:
    return None

  def midpoint_at(t: float) -> np.ndarray:
    p_axis = origin + axis * t
    pa = _closest_point_on_side(p_axis, side_a)
    pb = _closest_point_on_side(p_axis, side_b)
    return (pa + pb) / 2.0

  start = midpoint_at(t0)
  end = midpoint_at(t1)
  vec = end - start
  length = float(np.linalg.norm(vec))
  if length < 1e-6:
    return None
  direction = vec / length
  return {
    "start": [round(float(start[0]), 4), round(float(start[1]), 4)],
    "end": [round(float(end[0]), 4), round(float(end[1]), 4)],
    "direction": [round(float(direction[0]), 6), round(float(direction[1]), 6)],
    "length": round(length, 4),
    "t_low": round(t0, 4),
    "t_high": round(t1, 4),
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


def _angle_compatible(
  connector_dir: np.ndarray,
  corridor_dir: np.ndarray,
  angle_th_deg: float,
) -> bool:
  angle = acute_angle_deg(connector_dir, corridor_dir)
  return angle <= angle_th_deg or abs(angle - 90.0) <= angle_th_deg


def _touch_points_for_member(
  residual_graph: nx.Graph,
  member_id: str,
) -> list[tuple[np.ndarray, str]]:
  points: list[tuple[np.ndarray, str]] = []
  if not residual_graph.has_node(member_id):
    return points
  seg = _seg_from_node(residual_graph, member_id)
  for row in walls_touching_stub(residual_graph, member_id):
    cid = row.get("corridor_id")
    wall_id = row.get("wall_segment_id")
    if not cid or not wall_id or not residual_graph.has_node(str(wall_id)):
      continue
    wall = _seg_from_node(residual_graph, str(wall_id))
    best_dist = float("inf")
    best_pt = np.asarray(seg["start"], dtype=float)[:2]
    for pt in (seg["start"], seg["end"]):
      p = np.asarray(pt, dtype=float)[:2]
      dist = point_line_offset(
        p,
        np.asarray(wall["start"], dtype=float)[:2],
        np.asarray(wall["direction"], dtype=float)[:2],
      )
      if dist < best_dist:
        best_dist = dist
        best_pt = p
    points.append((best_pt, str(cid)))
  return points


def _assign_end_attachments(
  *,
  component_ids: list[str],
  residual_graph: nx.Graph,
  centerline_graph: nx.Graph,
  connector_cl: dict[str, Any],
  origin: np.ndarray,
  axis: np.ndarray,
  para_cfg: ParallelGraphConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
  t_low = float(connector_cl["t_low"])
  t_high = float(connector_cl["t_high"])
  connector_dir = np.asarray(connector_cl["direction"], dtype=float)[:2]
  assign_tol = float(para_cfg.endpoint_link_gap)
  low_pt = origin + axis * t_low
  high_pt = origin + axis * t_high

  low_rows: dict[str, dict[str, Any]] = {}
  high_rows: dict[str, dict[str, Any]] = {}

  def _record(
    bucket: dict[str, dict[str, Any]],
    cid: str,
    *,
    source: str,
    gap: float,
    axial_delta: float,
  ) -> None:
    row = bucket.get(cid)
    if row is None or gap < float(row["gap"]):
      bucket[cid] = {
        "corridor_id": cid,
        "source": source,
        "gap": round(gap, 4),
        "axial_delta": round(axial_delta, 4),
      }

  for cid, data in centerline_graph.nodes(data=True):
    if data.get("node_type") != "corridor":
      continue
    cseg = _corridor_seg_from_node(str(cid), data)
    if not _angle_compatible(connector_dir, cseg["direction"], para_cfg.angle_th_deg):
      continue
    for end_name, end_pt in (
      ("low", low_pt),
      ("high", high_pt),
    ):
      ep_gap = min(
        float(np.linalg.norm(end_pt - cseg["start"])),
        float(np.linalg.norm(end_pt - cseg["end"])),
      )
      if ep_gap > assign_tol:
        continue
      bucket = low_rows if end_name == "low" else high_rows
      _record(
        bucket,
        str(cid),
        source="geometry",
        gap=ep_gap,
        axial_delta=abs(ep_gap),
      )

  for member_id in component_ids:
    for pt, touch_cid in _touch_points_for_member(residual_graph, member_id):
      t = float(np.dot(pt - origin, axis))
      for end_name, t_end, end_pt in (
        ("low", t_low, low_pt),
        ("high", t_high, high_pt),
      ):
        axial_delta = abs(t - t_end)
        if axial_delta > assign_tol:
          continue
        gap = float(np.linalg.norm(pt - end_pt))
        if gap > assign_tol:
          continue
        if touch_cid and centerline_graph.has_node(touch_cid):
          bucket = low_rows if end_name == "low" else high_rows
          _record(
            bucket,
            touch_cid,
            source="touch",
            gap=gap,
            axial_delta=axial_delta,
          )

  return sorted(low_rows.values(), key=lambda r: r["corridor_id"]), sorted(
    high_rows.values(),
    key=lambda r: r["corridor_id"],
  )


def _side_wall_ids(side: list[dict[str, Any]]) -> list[str]:
  return sorted(str(seg["wall_id"]) for seg in side)


def _side_has_resolved_wall(
  residual_graph: nx.Graph,
  side: list[dict[str, Any]],
) -> bool:
  return any(
    str(residual_graph.nodes[str(seg["wall_id"])].get("node_type")) == NODE_WALL
    for seg in side
    if residual_graph.has_node(str(seg["wall_id"]))
  )


def _dominant_wall_member(side: list[dict[str, Any]]) -> dict[str, Any]:
  walls = [seg for seg in side if seg.get("node_type") == NODE_WALL]
  pool = walls or side
  return max(pool, key=lambda s: float(s["length"]))


def _next_corridor_id(graph: nx.Graph) -> str:
  max_n = 0
  for nid in graph.nodes:
    text = str(nid)
    if not text.startswith("CC"):
      continue
    try:
      max_n = max(max_n, int(text[2:]))
    except ValueError:
      continue
  return f"CC{max_n + 1:03d}"


def _has_parallel_attachment(
  attachments: list[dict[str, Any]],
  connector_dir: np.ndarray,
  centerline_graph: nx.Graph,
  angle_th_deg: float,
) -> bool:
  for row in attachments:
    cid = str(row["corridor_id"])
    if not centerline_graph.has_node(cid):
      continue
    cseg = _corridor_seg_from_node(cid, centerline_graph.nodes[cid])
    if acute_angle_deg(connector_dir, cseg["direction"]) <= angle_th_deg:
      return True
  return False


def _existing_covering_corridor(
  graph: nx.Graph,
  connector_cl: dict[str, Any],
  para_cfg: ParallelGraphConfig,
) -> str | None:
  connector_dir = np.asarray(connector_cl["direction"], dtype=float)[:2]
  probe = {
    "start": np.asarray(connector_cl["start"], dtype=float)[:2],
    "end": np.asarray(connector_cl["end"], dtype=float)[:2],
    "mid": (
      np.asarray(connector_cl["start"], dtype=float)[:2]
      + np.asarray(connector_cl["end"], dtype=float)[:2]
    ) / 2.0,
    "direction": connector_dir,
    "length": float(connector_cl["length"]),
    "endpoints": [
      np.asarray(connector_cl["start"], dtype=float)[:2],
      np.asarray(connector_cl["end"], dtype=float)[:2],
    ],
  }
  best_id = None
  best_overlap = 0.0
  for nid, data in graph.nodes(data=True):
    if data.get("node_type") != "corridor":
      continue
    cseg = _corridor_seg_from_node(str(nid), data)
    if acute_angle_deg(connector_dir, cseg["direction"]) > para_cfg.angle_th_deg:
      continue
    lateral = point_line_offset(
      cseg["mid"],
      probe["start"],
      connector_dir,
    )
    if lateral > para_cfg.max_width:
      continue
    ov = overlap_ratio(probe, cseg)
    if ov > best_overlap:
      best_overlap = ov
      best_id = str(nid)
  if best_overlap >= para_cfg.min_overlap_ratio:
    return best_id
  return None


def _link_connector_endpoints(
  graph: nx.Graph,
  connector_id: str,
  attachment_ids: list[str],
  para_cfg: ParallelGraphConfig,
) -> list[dict[str, Any]]:
  if not graph.has_node(connector_id):
    return []
  connector_seg = _corridor_seg_from_node(connector_id, graph.nodes[connector_id])
  rows: list[dict[str, Any]] = []
  for cid in attachment_ids:
    if not graph.has_node(cid):
      continue
    cseg = _corridor_seg_from_node(cid, graph.nodes[cid])
    gap = endpoint_gap(connector_seg, cseg)
    angle = acute_angle_deg(connector_seg["direction"], cseg["direction"])
    if graph.has_edge(connector_id, cid):
      rows.append({
        "corridor_id": cid,
        "status": "exists",
        "endpoint_gap": round(gap, 4),
      })
      continue
    graph.add_edge(
      connector_id,
      cid,
      edge_kind="endpoint",
      endpoint_gap=round(gap, 4),
      angle_deg=round(angle, 4),
      is_parallel=angle < para_cfg.angle_th_deg,
      is_ortho=abs(angle - 90.0) < para_cfg.angle_th_deg,
      source="centerline_synthesis",
    )
    rows.append({
      "corridor_id": cid,
      "status": "added",
      "endpoint_gap": round(gap, 4),
    })
  return rows


def apply_parallel_connector_synthesis(
  centerline_graph: nx.Graph,
  residual_graph: nx.Graph,
  *,
  para_cfg: ParallelGraphConfig | None = None,
) -> tuple[nx.Graph, list[dict[str, Any]]]:
  """
  Create connector corridors for parallel components that join existing topology.

  Returns a copied graph and per-component synthesis records.
  """
  para_cfg = para_cfg or ParallelGraphConfig()
  fixed = centerline_graph.copy()
  syntheses: list[dict[str, Any]] = []

  for component in _parallel_components(residual_graph):
    members = [nid for nid in component if residual_graph.has_node(nid)]
    if len(members) < 2:
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "too_few_members",
      })
      continue

    segs = [_seg_from_node(residual_graph, nid) for nid in members]
    ok_axis, origin, axis = _colinear_axis(segs, para_cfg.angle_th_deg)
    if not ok_axis:
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "not_colinear",
      })
      continue

    sides = _split_sides(
      segs,
      origin,
      axis,
      residual_graph=residual_graph,
      member_ids=members,
    )
    if sides is None:
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "not_two_sides",
      })
      continue
    side_a, side_b = sides

    if not _side_has_resolved_wall(residual_graph, side_a):
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "unresolved_wall_side",
        "side": "a",
        "side_wall_ids": _side_wall_ids(side_a),
      })
      continue
    if not _side_has_resolved_wall(residual_graph, side_b):
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "unresolved_wall_side",
        "side": "b",
        "side_wall_ids": _side_wall_ids(side_b),
      })
      continue

    width = point_line_offset(
      np.asarray(_dominant_wall_member(side_b)["mid"], dtype=float)[:2],
      np.asarray(_dominant_wall_member(side_a)["start"], dtype=float)[:2],
      axis,
    )
    if width < para_cfg.min_width or width > para_cfg.max_width:
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "width_out_of_band",
        "width": round(width, 4),
      })
      continue

    connector_cl = _centerline_between_sides(side_a, side_b, origin, axis)
    if connector_cl is None:
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "no_centerline_overlap",
      })
      continue

    existing = _existing_covering_corridor(
      fixed,
      connector_cl,
      para_cfg,
    )
    if existing is not None:
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "already_covered",
        "corridor_id": existing,
      })
      continue

    low_attach, high_attach = _assign_end_attachments(
      component_ids=members,
      residual_graph=residual_graph,
      centerline_graph=fixed,
      connector_cl=connector_cl,
      origin=origin,
      axis=axis,
      para_cfg=para_cfg,
    )
    if not low_attach or not high_attach:
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "open_end",
        "low_attachments": low_attach,
        "high_attachments": high_attach,
      })
      continue

    low_ids = {row["corridor_id"] for row in low_attach}
    high_ids = {row["corridor_id"] for row in high_attach}
    if low_ids & high_ids:
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "shared_corridor_both_ends",
        "shared_corridor_ids": sorted(low_ids & high_ids),
      })
      continue

    connector_dir = np.asarray(connector_cl["direction"], dtype=float)[:2]
    if not (
      _has_parallel_attachment(low_attach, connector_dir, fixed, para_cfg.angle_th_deg)
      or _has_parallel_attachment(high_attach, connector_dir, fixed, para_cfg.angle_th_deg)
    ):
      syntheses.append({
        "component": members,
        "status": "skipped",
        "reason": "no_parallel_attachment",
        "low_attachments": low_attach,
        "high_attachments": high_attach,
      })
      continue

    dom_a = _dominant_wall_member(side_a)
    dom_b = _dominant_wall_member(side_b)
    side_a_ids = _side_wall_ids(side_a)
    side_b_ids = _side_wall_ids(side_b)
    left_id, right_id = assign_left_right(
      dom_a["wall_id"],
      dom_b["wall_id"],
      dom_a,
      dom_b,
      connector_cl,
    )
    if left_id in side_a_ids:
      left_wall_ids, right_wall_ids = side_a_ids, side_b_ids
    else:
      left_wall_ids, right_wall_ids = side_b_ids, side_a_ids
    if right_id not in right_wall_ids:
      right_wall_ids = sorted(set(right_wall_ids) | {str(right_id)})
    connector_id = _next_corridor_id(fixed)
    start = connector_cl["start"]
    end = connector_cl["end"]
    direction = connector_cl["direction"]
    length = float(connector_cl["length"])
    centerline = {
      "start": list(start),
      "end": list(end),
      "direction": list(direction),
      "length": round(length, 4),
    }
    fixed.add_node(
      connector_id,
      node_type="corridor",
      corridor_id=connector_id,
      start=list(start),
      end=list(end),
      length=length,
      corridor_length=length,
      width=round(width, 4),
      direction=list(direction),
      pair_id="",
      left_wall_id=str(left_id),
      right_wall_id=str(right_id),
      left_wall_ids=left_wall_ids,
      right_wall_ids=right_wall_ids,
      centerline=centerline,
      overlap_ratio=1.0,
      confidence=0.5,
      source="centerline_synthesis",
      synthesis_component=members,
    )

    endpoint_links: list[dict[str, Any]] = []
    endpoint_links.extend(
      _link_connector_endpoints(fixed, connector_id, sorted(low_ids), para_cfg),
    )
    endpoint_links.extend(
      _link_connector_endpoints(fixed, connector_id, sorted(high_ids), para_cfg),
    )

    syntheses.append({
      "component": members,
      "status": SYNTHESIS_STATUS,
      "corridor_id": connector_id,
      "centerline": centerline,
      "width": round(width, 4),
      "left_wall_id": str(left_id),
      "right_wall_id": str(right_id),
      "left_wall_ids": left_wall_ids,
      "right_wall_ids": right_wall_ids,
      "low_attachments": low_attach,
      "high_attachments": high_attach,
      "endpoint_links": endpoint_links,
    })

  fixed.graph["centerline_synthesized_count"] = sum(
    1 for row in syntheses if row.get("status") == SYNTHESIS_STATUS
  )
  return fixed, syntheses


__all__ = ["SYNTHESIS_STATUS", "apply_parallel_connector_synthesis"]
