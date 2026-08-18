"""Augment residual_graph corridor-stub-touch edges with corridor_id."""

from __future__ import annotations

import networkx as nx

from step3B.residual_graph import EDGE_CORRIDOR_STUB_TOUCH


def augment_corridor_mapping(
  residual_graph: nx.Graph,
  cand_wall_to_id: dict[str, str],
) -> nx.Graph:
  """
  Write ``corridor_id`` onto ``corridor-stub-touch`` edges from wall → corridor map.

  Returns a copy with augmented edges (does not mutate the input graph).
  """
  graph = residual_graph.copy()
  mapped = 0
  for u, v, data in graph.edges(data=True):
    if str(data.get("edge_kind", "")) != EDGE_CORRIDOR_STUB_TOUCH:
      continue
    u_type = graph.nodes.get(u, {}).get("node_type")
    wall_id = str(v if u_type == "stub" else u)
    cid = cand_wall_to_id.get(wall_id)
    if cid is None:
      continue
    graph[u][v]["corridor_id"] = str(cid)
    mapped += 1

  graph.graph["corridor_mapping_augmented"] = True
  graph.graph["corridor_touch_edges_mapped"] = mapped
  return graph
