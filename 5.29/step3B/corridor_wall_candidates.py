"""Pick candidate corridor walls from residual_graph stubs."""

from __future__ import annotations

from typing import Any

import networkx as nx

from step3B.residual_graph import (
  EDGE_CORRIDOR_STUB_PARALLEL,
  EDGE_CORRIDOR_STUB_TOUCH,
  corridors_touching_stub,
  walls_touching_stub,
)

NODE_WALL = "wall"
NODE_STUB = "stub"
NODE_POSSIBLE_CORRIDOR_WALL = "possible_corridor_wall"


def _has_corridor_stub_parallel(residual_graph: nx.Graph, stub_id: str) -> bool:
  sid = str(stub_id)
  if not residual_graph.has_node(sid):
    return False
  for _nb, data in residual_graph[sid].items():
    if data.get("edge_kind") == EDGE_CORRIDOR_STUB_PARALLEL:
      return True
  return False


def is_candidate_corridor_wall(residual_graph: nx.Graph, stub_id: str) -> bool:
  """
  Two-class rule (no H_BRIDGE / CORRIDOR_WALL split):

  - touches >= 2 corridors via corridor-stub-touch, OR
  - touches >= 1 corridor AND has corridor-stub-parallel to a boundary wall
  """
  sid = str(stub_id)
  cids = corridors_touching_stub(residual_graph, sid)
  if len(cids) >= 2:
    return True
  if len(cids) >= 1 and _has_corridor_stub_parallel(residual_graph, sid):
    return True
  return False


def detect_candidate_corridor_walls(
  residual_graph: nx.Graph,
  *,
  min_length: float = 0.0,
) -> list[dict[str, Any]]:
  """Return candidate records for stubs promoted to possible_corridor_wall."""
  candidates: list[dict[str, Any]] = []
  for stub_id, data in sorted(residual_graph.nodes(data=True)):
    if data.get("node_type") != NODE_STUB:
      continue
    sid = str(stub_id)
    length = float(data.get("length", 0.0))
    if length < min_length:
      continue
    if not is_candidate_corridor_wall(residual_graph, sid):
      continue

    corridor_ids = sorted(corridors_touching_stub(residual_graph, sid))
    touch_walls = [
      str(row["wall_segment_id"])
      for row in walls_touching_stub(residual_graph, sid)
      if row.get("wall_segment_id")
    ]
    candidates.append({
      "candidate_id": f"CW{len(candidates) + 1:03d}",
      "residual_handle": sid,
      "node_type": NODE_POSSIBLE_CORRIDOR_WALL,
      "corridor_ids": corridor_ids,
      "touch_walls": sorted(set(touch_walls)),
      "has_parallel_wall": _has_corridor_stub_parallel(residual_graph, sid),
      "length": round(length, 4),
    })
  return candidates


def tag_candidate_corridor_walls(
  residual_graph: nx.Graph,
  candidates: list[dict[str, Any]],
) -> nx.Graph:
  """Copy graph; relabel picked stubs to ``possible_corridor_wall``."""
  tagged = residual_graph.copy()
  handles = {str(c["residual_handle"]) for c in candidates}
  for handle in handles:
    if not tagged.has_node(handle):
      continue
    tagged.nodes[handle]["node_type"] = NODE_POSSIBLE_CORRIDOR_WALL
    tagged.nodes[handle]["original_node_type"] = NODE_STUB

  tagged.graph["possible_corridor_wall_count"] = len(handles)
  tagged.graph["possible_corridor_wall_handles"] = sorted(handles)
  return tagged


def candidate_corridor_walls_summary(
  *,
  source_stem: str,
  candidates: list[dict[str, Any]],
  min_length: float,
) -> dict[str, Any]:
  return {
    "kind": "secondary_wall_candidates",
    "schema_version": 1,
    "source_stem": source_stem,
    "min_length": round(min_length, 4),
    "candidate_count": len(candidates),
    "candidates": candidates,
  }
