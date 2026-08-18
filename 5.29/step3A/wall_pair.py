"""Extract wall pairs from Step 2B parallel graph edges."""

from __future__ import annotations

from typing import Any

import networkx as nx


def _is_wall_parallel_edge(
  graph: nx.Graph,
  u: str,
  v: str,
  data: dict[str, Any],
) -> bool:
  if not data.get("is_parallel"):
    return False
  edge_kind = str(data.get("edge_kind", ""))
  if edge_kind not in ("is_parallel", "endpoint_parallel"):
    return False
  if graph.nodes[u].get("node_type") != "wall":
    return False
  if graph.nodes[v].get("node_type") != "wall":
    return False
  return True


def extract_wall_pairs(graph: nx.Graph) -> list[dict[str, Any]]:
  """Enumerate parallel wall-wall edges as normalized WallPair records."""
  pairs: list[dict[str, Any]] = []
  seen: set[tuple[str, str]] = set()

  for u, v, data in graph.edges(data=True):
    if not _is_wall_parallel_edge(graph, u, v, data):
      continue
    wall_a, wall_b = sorted((str(u), str(v)))
    key = (wall_a, wall_b)
    if key in seen:
      continue
    seen.add(key)
    pairs.append({
      "wall_a": wall_a,
      "wall_b": wall_b,
      "width": float(data.get("width", 0.0)),
      "overlap_ratio": float(data.get("overlap_ratio", 0.0)),
    })

  pairs.sort(key=lambda p: (p["wall_a"], p["wall_b"]))
  for idx, pair in enumerate(pairs, start=1):
    pair["pair_id"] = f"WP{idx:03d}"
  return pairs
