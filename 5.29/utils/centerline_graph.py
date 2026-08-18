"""Read-only helpers for centerline_graph.pkl nodes."""

from __future__ import annotations

import networkx as nx


def cand_wall_to_id_from_graph(graph: nx.Graph) -> dict[str, str]:
  """Map straight-wall segment id → corridor_id from centerline graph nodes."""
  mapping: dict[str, str] = {}
  for nid, data in graph.nodes(data=True):
    if data.get("node_type") != "corridor":
      continue
    cid = str(data.get("corridor_id") or nid)
    for wid in (data.get("left_wall_id"), data.get("right_wall_id")):
      if wid:
        mapping[str(wid)] = cid
  return mapping
