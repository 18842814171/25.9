"""Promote possible_corridor_wall stubs when opposite side is a determined wall."""

from __future__ import annotations

from typing import Any

import networkx as nx

from utils.centerline_graph import cand_wall_to_id_from_graph
from utils.segment_geometry import acute_angle_deg, point_segment_distance
from step3B.corridor_wall_candidates import NODE_POSSIBLE_CORRIDOR_WALL, NODE_WALL
from step3B.graph_inputs import _seg_from_parallel_node
from step3B.residual_graph import (
  EDGE_CORRIDOR_STUB_PARALLEL,
  walls_touching_stub,
)

PROMOTION_PARALLEL_EDGE = "parallel_edge"
PROMOTION_GEOMETRIC = "geometric"
DEFER_NO_PARTNER = "no_determined_partner"


def _parallel_partner_walls(residual_graph: nx.Graph, stub_id: str) -> list[str]:
  sid = str(stub_id)
  partners: list[str] = []
  for nb, data in residual_graph[sid].items():
    if data.get("edge_kind") != EDGE_CORRIDOR_STUB_PARALLEL:
      continue
    if residual_graph.nodes.get(nb, {}).get("node_type") != NODE_WALL:
      continue
    partners.append(str(nb))
  return sorted(set(partners))


def _geometric_partner_walls(
  residual_graph: nx.Graph,
  stub_id: str,
  *,
  width_tol: float,
  angle_th_deg: float,
) -> list[str]:
  sid = str(stub_id)
  if not residual_graph.has_node(sid):
    return []
  stub = _seg_from_parallel_node(sid, residual_graph.nodes[sid])
  partners: list[str] = []
  for wall_id, data in residual_graph.nodes(data=True):
    if data.get("node_type") != NODE_WALL:
      continue
    wid = str(wall_id)
    wall = _seg_from_parallel_node(wid, data)
    if acute_angle_deg(stub["direction"], wall["direction"]) > angle_th_deg:
      continue
    d0 = point_segment_distance(stub["start"], wall["start"], wall["end"])
    d1 = point_segment_distance(stub["end"], wall["start"], wall["end"])
    if max(d0, d1) <= width_tol:
      partners.append(wid)
  return sorted(set(partners))


def determined_partner_walls(
  residual_graph: nx.Graph,
  stub_id: str,
  *,
  width_tol: float,
  angle_th_deg: float,
) -> tuple[list[str], str | None]:
  """Return partner wall ids and how they were matched."""
  parallel = _parallel_partner_walls(residual_graph, stub_id)
  if parallel:
    return parallel, PROMOTION_PARALLEL_EDGE

  geometric = _geometric_partner_walls(
    residual_graph,
    stub_id,
    width_tol=width_tol,
    angle_th_deg=angle_th_deg,
  )
  if geometric:
    return geometric, PROMOTION_GEOMETRIC
  return [], None


def target_corridor_ids(
  residual_graph: nx.Graph,
  centerline_graph: nx.Graph,
  cand_wall_to_id: dict[str, str],
  stub_id: str,
  partner_wall_ids: list[str],
) -> list[str]:
  """Corridors whose centerline may be extended from stub + partner wall."""
  targets: set[str] = set()
  for wid in partner_wall_ids:
    cid = cand_wall_to_id.get(wid)
    if cid and centerline_graph.has_node(cid):
      targets.add(str(cid))

  for row in walls_touching_stub(residual_graph, stub_id):
    cid = row.get("corridor_id")
    touch_wall = str(row.get("wall_segment_id", ""))
    if not cid or not centerline_graph.has_node(str(cid)):
      continue
    node = centerline_graph.nodes[str(cid)]
    if touch_wall in (
      str(node.get("left_wall_id", "")),
      str(node.get("right_wall_id", "")),
    ):
      targets.add(str(cid))
  return sorted(targets)


def evaluate_wall_promotions(
  residual_graph: nx.Graph,
  centerline_graph: nx.Graph,
  *,
  width_tol: float,
  angle_th_deg: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
  """
  Split possible_corridor_wall nodes into promote vs defer lists.

  Promote when a determined straight wall exists on the opposite side
  (corridor-stub-parallel edge, or endpoint-near + colinear geometry).
  """
  cand_wall_to_id = cand_wall_to_id_from_graph(centerline_graph)
  promoted: list[dict[str, Any]] = []
  deferred: list[dict[str, Any]] = []

  for nid, data in sorted(residual_graph.nodes(data=True)):
    if data.get("node_type") != NODE_POSSIBLE_CORRIDOR_WALL:
      continue
    sid = str(nid)
    partners, reason = determined_partner_walls(
      residual_graph,
      sid,
      width_tol=width_tol,
      angle_th_deg=angle_th_deg,
    )
    if not partners:
      deferred.append({
        "residual_handle": sid,
        "node_type": NODE_POSSIBLE_CORRIDOR_WALL,
        "reason": DEFER_NO_PARTNER,
      })
      continue

    corridor_ids = target_corridor_ids(
      residual_graph,
      centerline_graph,
      cand_wall_to_id,
      sid,
      partners,
    )
    promoted.append({
      "residual_handle": sid,
      "partner_wall_ids": partners,
      "promotion_reason": reason,
      "target_corridor_ids": corridor_ids,
      "length": round(float(data.get("length", 0.0)), 4),
    })

  return promoted, deferred


def apply_wall_promotions(
  residual_graph: nx.Graph,
  promotions: list[dict[str, Any]],
) -> nx.Graph:
  """Relabel promoted possible_corridor_wall nodes to ``wall``."""
  resolved = residual_graph.copy()
  handles = {str(row["residual_handle"]) for row in promotions}
  for handle in handles:
    if not resolved.has_node(handle):
      continue
    resolved.nodes[handle]["node_type"] = NODE_WALL
    resolved.nodes[handle]["original_node_type"] = NODE_POSSIBLE_CORRIDOR_WALL
    resolved.nodes[handle]["promoted_from_possible"] = True

  resolved.graph["promoted_wall_count"] = len(handles)
  resolved.graph["promoted_wall_handles"] = sorted(handles)
  deferred = [
    str(nid)
    for nid, data in resolved.nodes(data=True)
    if data.get("node_type") == NODE_POSSIBLE_CORRIDOR_WALL
  ]
  resolved.graph["deferred_possible_wall_count"] = len(deferred)
  resolved.graph["deferred_possible_wall_handles"] = sorted(deferred)
  return resolved
