"""Step 2A init endpoint graph builder."""

from __future__ import annotations

from typing import Any

import networkx as nx

from stage2.geometry import (
  CorridorPipelineConfig,
  build_endpoint_graph,
  extract_primitive_info,
  filter_degenerate_segments,
  filter_spatial_outliers,
)

INIT_GRAPH_KIND = "init_graph"


def prepare_corridor_primitives(
  primitives: list[dict[str, Any]],
  cfg: CorridorPipelineConfig | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
  """Degenerate + optional spatial-outlier filter. Returns (kept, dropped)."""
  cfg = cfg or CorridorPipelineConfig()
  filtered = filter_degenerate_segments(
    primitives, min_length=cfg.min_length_filter,
  )
  dropped: list[dict[str, Any]] = []
  if cfg.spatial_outlier_filter:
    filtered, dropped = filter_spatial_outliers(
      filtered,
      percentile_low=cfg.spatial_outlier_percentile_low,
      percentile_high=cfg.spatial_outlier_percentile_high,
      pad_ratio=cfg.spatial_outlier_pad_ratio,
    )
  return filtered, dropped


def build_init_graph(
  primitives: list[dict[str, Any]],
  cfg: CorridorPipelineConfig | None = None,
) -> tuple[nx.Graph, list[dict[str, Any]]]:
  """Build init endpoint graph from original geometry JSON."""
  cfg = cfg or CorridorPipelineConfig()
  filtered, dropped = prepare_corridor_primitives(primitives, cfg)
  info = extract_primitive_info(filtered)
  graph = build_endpoint_graph(
    info,
    angle_th_deg=cfg.angle_th_deg,
    endpoint_tol=cfg.endpoint_tol,
    endpoint_link_gap=cfg.endpoint_link_gap,
  )
  graph.graph["kind"] = INIT_GRAPH_KIND
  graph.graph["schema_version"] = 1
  graph.graph["endpoint_link_gap"] = float(cfg.endpoint_link_gap)
  graph.graph["spatial_outlier_dropped"] = len(dropped)
  return graph, info
