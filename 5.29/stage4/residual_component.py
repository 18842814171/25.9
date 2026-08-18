"""RC_v1 / RC_v2 grouping for Stage 4."""

from __future__ import annotations

from typing import Any

import networkx as nx

from step3B.residual_graph import (
  EDGE_STUB_STUB_PARALLEL,
  EDGE_STUB_STUB_TOUCH,
  residual_components_v1,
)

RC_V2_EDGE_KINDS = frozenset({EDGE_STUB_STUB_TOUCH, EDGE_STUB_STUB_PARALLEL})


def _stub_subgraph(
  graph: nx.Graph,
  edge_kinds: frozenset[str],
) -> nx.Graph:
  sub = nx.Graph()
  for nid, data in graph.nodes(data=True):
    if data.get("node_type") != "stub":
      continue
    sub.add_node(
      str(nid),
      length=float(data.get("length", 0.0)),
      direction=list(data.get("direction") or [1.0, 0.0]),
    )
  for u, v, data in graph.edges(data=True):
    kind = str(data.get("edge_kind", ""))
    if kind not in edge_kinds:
      continue
    if sub.has_node(u) and sub.has_node(v):
      sub.add_edge(u, v, **{k: val for k, val in data.items() if k != "edge_kind"})
  return sub


def residual_components_v2(graph: nx.Graph) -> list[dict[str, Any]]:
  """RC_v2: connected components over touch + parallel stub edges."""
  sub = _stub_subgraph(graph, RC_V2_EDGE_KINDS)
  components: list[dict[str, Any]] = []
  for idx, comp in enumerate(nx.connected_components(sub), start=1):
    handles = sorted(str(h) for h in comp)
    total_length = round(
      sum(float(sub.nodes[h].get("length", 0.0)) for h in handles),
      4,
    )
    components.append({
      "rc_id": f"RC{idx:03d}",
      "rc_view": "RC_v2",
      "handles": handles,
      "singleton": len(handles) == 1,
      "handle_count": len(handles),
      "total_length": total_length,
      "edge_count": sub.subgraph(handles).number_of_edges(),
    })
  return components


def build_region_records(graph: nx.Graph) -> list[dict[str, Any]]:
  """
  Build RC_v2 region records (primary partition for Stage 4 semantics).

  RC_v1 list is included in graph metadata for validation only.
  """
  return residual_components_v2(graph)


def rc_v1_for_validation(graph: nx.Graph) -> list[dict[str, Any]]:
  """Expose RC_v1 list for summary / regression checks."""
  return residual_components_v1(graph)
