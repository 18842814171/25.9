"""Step 2A normalized endpoint graph (LINE-only, post arc normalize)."""

from __future__ import annotations

from typing import Any

import networkx as nx

from stage2.geometry import (
  CorridorPipelineConfig,
  build_endpoint_graph,
  extract_primitive_info,
  filter_degenerate_segments,
)

NORMALIZED_GRAPH_KIND = "normalized_graph"


def build_normalized_graph(
  primitives: list[dict[str, Any]],
  cfg: CorridorPipelineConfig | None = None,
) -> tuple[nx.Graph, list[dict[str, Any]]]:
  """Build endpoint graph from normalized LINE geometry only."""
  cfg = cfg or CorridorPipelineConfig()
  lines = [
    p for p in primitives
    if str(p.get("type", "")).upper() == "LINE"
  ]
  filtered = filter_degenerate_segments(
    lines, min_length=cfg.min_length_filter,
  )
  info = extract_primitive_info(filtered)
  graph = build_endpoint_graph(
    info,
    angle_th_deg=cfg.angle_th_deg,
    endpoint_tol=cfg.endpoint_tol,
    endpoint_link_gap=cfg.endpoint_link_gap,
  )
  graph.graph["kind"] = NORMALIZED_GRAPH_KIND
  graph.graph["schema_version"] = 1
  return graph, info
