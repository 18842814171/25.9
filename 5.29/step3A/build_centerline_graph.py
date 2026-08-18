"""
Step 3A: corridor candidates → centerline logical graph.

Example:
  python step3A/build_centerline_graph.py --stem part1-巷道
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage2.geometry import CorridorPipelineConfig
from step3A.config import CenterlineGraphConfig
from step3A.pipeline import run_centerline_graph


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 3A: build centerline endpoint/parallel logical graph",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument("--no-auto-scale", action="store_true")
  parser.add_argument("--endpoint-link-gap", type=float, default=None)
  parser.add_argument("--angle-th-deg", type=float, default=None)
  parser.add_argument("--min-width", type=float, default=None)
  parser.add_argument("--max-width", type=float, default=None)
  parser.add_argument("--min-overlap-ratio", type=float, default=None)
  args = parser.parse_args()

  cfg = CenterlineGraphConfig.from_pipeline(CorridorPipelineConfig())
  auto_scale = not args.no_auto_scale
  if args.min_width is not None:
    cfg.min_width = args.min_width
    auto_scale = False
  if args.max_width is not None:
    cfg.max_width = args.max_width
    auto_scale = False
  if args.endpoint_link_gap is not None:
    cfg.endpoint_link_gap = args.endpoint_link_gap
  if args.angle_th_deg is not None:
    cfg.angle_th_deg = args.angle_th_deg
  if args.min_overlap_ratio is not None:
    cfg.min_overlap_ratio = args.min_overlap_ratio

  result = run_centerline_graph(
    args.stem,
    output_dir=args.output,
    cfg=cfg,
    auto_scale=auto_scale,
  )
  scale = result.get("global_scale") or {}
  w = scale.get("median_corridor_width")
  width_msg = f" width_median={w:.2f}" if w else ""
  print(
    f"[step3A/centerline_graph] corridors={result['corridor_count']} "
    f"edges={result['edge_count']} endpoint={result['endpoint_edge_count']} "
    f"parallel={result['parallel_edge_count']} "
    f"parallel_groups={result['parallel_group_count']}{width_msg}",
  )
  for key, path in result["paths"].items():
    if path is not None:
      print(f"[step3A/centerline_graph] → {path}")


if __name__ == "__main__":
  main()
