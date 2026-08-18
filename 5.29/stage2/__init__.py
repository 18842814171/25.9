"""Stage 2: shared I/O, geometry primitives, and visualization."""

from stage2.geometry import (
  CorridorPipelineConfig,
  build_endpoint_graph,
  extract_primitive_info,
  filter_degenerate_segments,
  wall_lines_to_info,
)
from stage2.graph_usage import collect_used_handles, isolated_stubs_from_graph
from stage2.io import load_graph, load_json, save_graph, save_json

__all__ = [
  "CorridorPipelineConfig",
  "build_endpoint_graph",
  "collect_used_handles",
  "extract_primitive_info",
  "filter_degenerate_segments",
  "isolated_stubs_from_graph",
  "load_graph",
  "load_json",
  "save_graph",
  "save_json",
  "wall_lines_to_info",
]
