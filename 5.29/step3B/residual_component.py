"""Legacy residual-component grouping for RC_v1 comparison."""

from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np


def _endpoint_gap(seg_a: dict[str, Any], seg_b: dict[str, Any]) -> float:
  best = float("inf")
  for key_a in ("start", "end"):
    for key_b in ("start", "end"):
      pa = np.asarray(seg_a[key_a], dtype=float)[:2]
      pb = np.asarray(seg_b[key_b], dtype=float)[:2]
      best = min(best, float(np.linalg.norm(pa - pb)))
  return best


def build_residual_components_from_stubs(
  stub_segments: dict[str, dict[str, Any]],
  endpoint_link_gap: float,
) -> list[dict[str, Any]]:
  """
  Connected components over stub segments linked by endpoint proximity.

  Reproduces the legacy RC partition used to validate ``residual_components_v1``.
  """
  handles = sorted(stub_segments)
  graph = nx.Graph()
  for handle in handles:
    graph.add_node(
      handle,
      length=float(stub_segments[handle].get("length", 0.0)),
    )

  for i in range(len(handles)):
    for j in range(i + 1, len(handles)):
      gap = _endpoint_gap(stub_segments[handles[i]], stub_segments[handles[j]])
      if gap <= endpoint_link_gap:
        graph.add_edge(handles[i], handles[j], gap=round(gap, 4))

  components: list[dict[str, Any]] = []
  for idx, comp in enumerate(nx.connected_components(graph), start=1):
    comp_handles = sorted(str(h) for h in comp)
    total_length = round(
      sum(float(graph.nodes[h].get("length", 0.0)) for h in comp_handles),
      4,
    )
    components.append({
      "rc_id": f"RC{idx:03d}",
      "rc_view": "legacy",
      "handles": comp_handles,
      "singleton": len(comp_handles) == 1,
      "handle_count": len(comp_handles),
      "total_length": total_length,
      "edge_count": graph.subgraph(comp_handles).number_of_edges(),
    })
  return components
