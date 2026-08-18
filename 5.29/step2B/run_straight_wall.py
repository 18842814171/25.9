"""
Step 2B straight wall: detect colinear chains, merge geometry, write PNG.

Merges along the Step 2A endpoint graph (angle + lateral only; no gap filter).
Short single-member groups go to residual (``short_length_scale × median width``).

Example:
  python step2B/run_straight_wall.py --stem part2-巷道
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage2.geometry import CorridorPipelineConfig
from stage2.graph_usage import info_list_from_endpoint_graph
from stage2.io import load_graph, load_json, save_json
from step2A.paths import (
  normalized_geometry_json,
  normalized_graph_pkl,
  resolve_step2a_artifacts_dir,
)
from step2B.paths import (
  residual_geometry_json,
  step2b_output_dir,
  straight_wall_geometry_json,
  straight_wall_png,
  wall_segment_json,
)
from step2B.straight_wall import (
  detect_wall_segments,
  merge_wall_segments_to_geometry,
  residual_geometry_to_json,
  straight_wall_geometry_to_json,
  wall_segments_to_json,
)
from step2B.config import StraightWallConfig
from step2B.visualize import visualize_straight_wall
from step2B.width_estimate import (
  estimate_corridor_width_median,
  estimate_mean_corridor_width,
  segments_from_endpoint_info,
)
from utils.scale import DEFAULT_MEDIAN_WIDTH

# Cap nearest-opposite sampling so large drawings (e.g. XJH) do not hang on O(n²).
_WIDTH_SAMPLE_CAP = 800


def _estimate_median_corridor_width(graph, info: list) -> float:
  if not info:
    return DEFAULT_MEDIAN_WIDTH
  if len(info) <= _WIDTH_SAMPLE_CAP:
    return estimate_mean_corridor_width(graph, info)
  sample = random.Random(0).sample(info, _WIDTH_SAMPLE_CAP)
  return estimate_corridor_width_median(segments_from_endpoint_info(sample))


def run_straight_wall(
  stem: str,
  *,
  step2a_dir: Path | None = None,
  output_dir: Path | None = None,
  cfg: StraightWallConfig | None = None,
  show_labels: bool = False,
  short_length_thresh: float | None = None,
  vis: bool = True,
) -> dict:
  step2a = resolve_step2a_artifacts_dir(step2a_dir or (_ROOT / "step2A" / "output"))
  out = step2b_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  graph_path = normalized_graph_pkl(stem, step2a)
  geo_path = normalized_geometry_json(stem, step2a)
  if not graph_path.is_file():
    raise FileNotFoundError(
      f"Missing {graph_path}; run step2A/build_normalized_graph.py first.",
    )
  if not geo_path.is_file():
    raise FileNotFoundError(
      f"Missing {geo_path}; run step2A/merge_normalized_geometry.py first.",
    )

  cfg = cfg or StraightWallConfig.from_pipeline(CorridorPipelineConfig())
  graph = load_graph(graph_path)
  geo_doc = load_json(geo_path)
  elements = list(geo_doc.get("elements") or [])
  prim_by_handle = {
    str(p["handle"]): p
    for p in elements
    if str(p.get("type", "")).upper() == "LINE"
  }

  info = info_list_from_endpoint_graph(graph)
  median_w = _estimate_median_corridor_width(graph, info)
  if short_length_thresh is None:
    short_length_thresh = float(cfg.short_length_scale) * float(median_w)

  segments = detect_wall_segments(graph, cfg)
  walls, residual = merge_wall_segments_to_geometry(
    segments,
    prim_by_handle,
    short_length_thresh=short_length_thresh,
  )

  seg_path = wall_segment_json(stem, out)
  walls_path = straight_wall_geometry_json(stem, out)
  residual_path = residual_geometry_json(stem, out)

  seg_doc = wall_segments_to_json(segments, source_stem=stem, cfg=cfg)
  save_json(seg_doc, seg_path)
  wall_doc = straight_wall_geometry_to_json(walls, source_stem=stem)
  residual_doc = residual_geometry_to_json(residual, source_stem=stem)
  save_json(wall_doc, walls_path)
  save_json(residual_doc, residual_path)

  paths = {
    "wall_segment_json": seg_path,
    "straight_wall_geometry_json": walls_path,
    "residual_geometry_json": residual_path,
  }
  if vis:
    png_path = straight_wall_png(stem, out, label=show_labels)
    visualize_straight_wall(
      wall_doc,
      residual_doc,
      png_path,
      prim_by_handle=prim_by_handle,
      show_handles=show_labels,
      title="Step 2B straight wall",
    )
    paths["straight_wall_png"] = png_path

  multi = sum(1 for s in segments if len(s["members"]) > 1)
  return {
    "segment_count": len(segments),
    "merged_groups": multi,
    "wall_count": len(walls),
    "residual_count": len(residual),
    "median_corridor_width": median_w,
    "short_length_thresh": short_length_thresh,
    "paths": paths,
  }


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 2B: straight wall detect + merge + PNG",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument("--step2a", type=Path, default=None)
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument("--continuity-angle-deg", type=float, default=None)
  parser.add_argument("--continuity-lateral-tol", type=float, default=None)
  parser.add_argument(
    "--short-length-scale",
    type=float,
    default=None,
    help="short single-member residual thresh = scale × median width (default 5)",
  )
  parser.add_argument(
    "--short-length-thresh",
    type=float,
    default=None,
    help="absolute short-length residual threshold (meters); overrides scale",
  )
  parser.add_argument(
    "--label",
    action="store_true",
    help="draw handle labels; output as lb_{stem}_straight_wall.png",
  )
  parser.add_argument("--no-vis", action="store_true", help="skip straight_wall PNG")
  args = parser.parse_args()

  cfg = StraightWallConfig.from_pipeline(CorridorPipelineConfig())
  if args.continuity_angle_deg is not None:
    cfg.continuity_angle_deg = args.continuity_angle_deg
  if args.continuity_lateral_tol is not None:
    cfg.continuity_lateral_tol = args.continuity_lateral_tol
  if args.short_length_scale is not None:
    cfg.short_length_scale = args.short_length_scale

  result = run_straight_wall(
    args.stem,
    step2a_dir=args.step2a,
    output_dir=args.output,
    cfg=cfg,
    show_labels=args.label,
    short_length_thresh=args.short_length_thresh,
    vis=not args.no_vis,
  )
  print(
    f"[step2B/straight_wall] segments={result['segment_count']} "
    f"merged_groups={result['merged_groups']} "
    f"walls={result['wall_count']} residual={result['residual_count']} "
    f"width_median={result['median_corridor_width']:.2f} "
    f"short_thresh={result['short_length_thresh']:.2f}",
  )
  for key, path in result["paths"].items():
    print(f"[step2B/straight_wall] → {path}")


if __name__ == "__main__":
  main()
