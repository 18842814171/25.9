"""
Step 2B: build logical graph (wall + stub) with endpoint and parallel edges.

Example:
  python step2B/build_parallel_graph.py --stem part1-巷道
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage2.geometry import CorridorPipelineConfig
from stage2.io import graph_to_read_json, load_json, save_graph, save_json
from step2B.parallel_graph import (
  build_parallel_graph,
  parallel_graph_summary,
  parallel_wall_groups,
  refine_parallel_edges_by_width_percentile,
)
from step2B.config import ParallelGraphConfig
from step2B.paths import (
  parallel_graph_json,
  parallel_graph_pkl,
  parallel_graph_png,
  parallel_graph_summary_json,
  residual_geometry_json,
  step2b_output_dir,
  straight_wall_geometry_json,
)
from step2B.visualize import visualize_parallel_graph


def run_build_parallel_graph(
  stem: str,
  *,
  output_dir: Path | None = None,
  step2a_dir: Path | None = None,
  cfg: ParallelGraphConfig | None = None,
  vis: bool = True,
  auto_width: bool = True,
  show_labels: bool = False,
) -> dict:
  del step2a_dir  # reserved for CLI compatibility
  out = step2b_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  walls_path = straight_wall_geometry_json(stem, out)
  residual_path = residual_geometry_json(stem, out)
  if not walls_path.is_file():
    raise FileNotFoundError(
      f"Missing {walls_path}; run step2B/run_straight_wall.py first.",
    )
  if not residual_path.is_file():
    raise FileNotFoundError(
      f"Missing {residual_path}; run step2B/run_straight_wall.py first.",
    )

  wall_doc = load_json(walls_path)
  residual_doc = load_json(residual_path)

  cfg = cfg or ParallelGraphConfig.from_pipeline(CorridorPipelineConfig())
  estimated_width: float | None = None

  if auto_width:
    # Pass 1: near-parallel + overlap inside a loose probe radius.
    graph = build_parallel_graph(wall_doc, residual_doc, cfg)
    # Pass 2: median of proposed edge widths → band → drop far/near edges.
    estimated_width = refine_parallel_edges_by_width_percentile(graph, cfg)
  else:
    # Manual / fixed band: search directly with cfg.min_width / max_width.
    graph = build_parallel_graph(
      wall_doc,
      residual_doc,
      cfg,
      search_min_width=float(cfg.min_width),
      search_max_width=float(cfg.max_width),
    )

  groups = parallel_wall_groups(graph)
  graph.graph["parallel_groups"] = groups

  pkl_path = parallel_graph_pkl(stem, out)
  pjson_path = parallel_graph_json(stem, out)
  png_path = parallel_graph_png(stem, out, label=show_labels)
  summary_path = parallel_graph_summary_json(stem, out)

  save_graph(graph, pkl_path)
  save_json(graph_to_read_json(graph), pjson_path)
  summary_doc = parallel_graph_summary(
    graph,
    source_stem=stem,
    cfg=cfg,
    estimated_corridor_width=estimated_width,
  )
  save_json(summary_doc, summary_path)

  if vis:
    width_note = f", width~{estimated_width:.1f}m" if estimated_width else ""
    visualize_parallel_graph(
      graph,
      groups,
      png_path,
      show_wall_ids=show_labels,
      title=f"parallel groups={len(groups)}{width_note}",
    )

  n_wall = summary_doc["wall_count"]
  n_stub = summary_doc["stub_count"]
  n_edge = summary_doc["edge_count"]
  return {
    "wall_count": n_wall,
    "stub_count": n_stub,
    "edge_count": n_edge,
    "parallel_group_count": len(groups),
    "estimated_corridor_width": estimated_width,
    "paths": {
      "parallel_graph_pkl": pkl_path,
      "parallel_graph_json": pjson_path,
      "parallel_graph_summary_json": summary_path,
      "parallel_graph_png": png_path if vis else None,
    },
  }


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 2B: wall/stub logical graph with endpoint and parallel edges",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument("--step2a", type=Path, default=None)
  parser.add_argument(
    "--no-auto-width",
    action="store_true",
    help="skip probe→percentile refine; use cfg/min/max width as search band",
  )
  parser.add_argument("--no-vis", action="store_true")
  parser.add_argument(
    "--label",
    action="store_true",
    help="draw WS*** wall labels; output as lb_{stem}_parallel_graph.png",
  )
  parser.add_argument("--endpoint-link-gap", type=float, default=None)
  parser.add_argument("--angle-th-deg", type=float, default=None)
  parser.add_argument("--min-width", type=float, default=None)
  parser.add_argument("--max-width", type=float, default=None)
  parser.add_argument("--min-overlap-ratio", type=float, default=None)
  parser.add_argument("--probe-max-width", type=float, default=None)
  args = parser.parse_args()

  cfg = ParallelGraphConfig.from_pipeline(CorridorPipelineConfig())
  auto_width = not args.no_auto_width
  if args.min_width is not None:
    cfg.min_width = args.min_width
    auto_width = False
  if args.max_width is not None:
    cfg.max_width = args.max_width
    auto_width = False
  if args.endpoint_link_gap is not None:
    cfg.endpoint_link_gap = args.endpoint_link_gap
  if args.angle_th_deg is not None:
    cfg.angle_th_deg = args.angle_th_deg
  if args.min_overlap_ratio is not None:
    cfg.min_overlap_ratio = args.min_overlap_ratio
  if args.probe_max_width is not None:
    cfg.probe_max_width = args.probe_max_width

  result = run_build_parallel_graph(
    args.stem,
    output_dir=args.output,
    step2a_dir=args.step2a,
    cfg=cfg,
    vis=not args.no_vis,
    auto_width=auto_width,
    show_labels=args.label,
  )
  width_msg = ""
  if result.get("estimated_corridor_width") is not None:
    w = result["estimated_corridor_width"]
    width_msg = f" width_median={w:.2f} band=[{cfg.min_width:.2f},{cfg.max_width:.2f}]"
  print(
    f"[step2B/parallel_graph] walls={result['wall_count']} "
    f"stubs={result['stub_count']} edges={result['edge_count']} "
    f"parallel_groups={result['parallel_group_count']}{width_msg}",
  )
  for key, path in result["paths"].items():
    if path is not None:
      print(f"[step2B/parallel_graph] → {path}")


if __name__ == "__main__":
  main()
