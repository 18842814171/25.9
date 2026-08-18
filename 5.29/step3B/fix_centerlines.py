"""
Step 3B: promote possible corridor walls and fix centerline geometry.

Prerequisite:
  python step3B/pick_corridor_wall_candidates.py --stem {图名}
  upstream {stem}_centerline_graph.pkl

Example:
  python step3B/fix_centerlines.py --stem 2026.1-1part-巷道
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage2.io import graph_to_read_json, load_graph, save_graph, save_json
from step2B.config import CenterlineGraphConfig, ParallelGraphConfig
from step3B.centerline_synthesis import (
  SYNTHESIS_STATUS,
  apply_parallel_connector_synthesis,
)
from step3B.centerline_fix import apply_centerline_fixes, centerline_fix_summary
from step3B.corridor_mapping import augment_corridor_mapping
from step3B.paths import (
  centerline_fix_json,
  centerline_fix_png,
  centerline_graph_fixed_json,
  centerline_graph_fixed_pkl,
  centerline_graph_input_pkl,
  residual_graph_resolved_json,
  residual_graph_resolved_pkl,
  residual_graph_tagged_pkl,
  step3b_output_dir,
)
from step3B.visualize import visualize_centerline_fix
from step3B.wall_promotion import (
  apply_wall_promotions,
  evaluate_wall_promotions,
)
from utils.centerline_graph import cand_wall_to_id_from_graph
from utils.scale import DEFAULT_MEDIAN_CORRIDOR_WIDTH


def fix_centerlines(
  stem: str,
  *,
  centerline_dir: Path | None = None,
  output_dir: Path | None = None,
  width_tol_scale: float = 1.05,
  vis: bool = True,
) -> dict[str, Any]:
  """Promote qualified possible walls and extend corridor centerlines."""
  out = step3b_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  tagged_path = residual_graph_tagged_pkl(stem, out)
  cl_path = centerline_graph_input_pkl(stem, centerline_dir)
  if not tagged_path.is_file():
    raise FileNotFoundError(
      f"Missing {tagged_path}; run step3B/pick_corridor_wall_candidates.py first.",
    )
  if not cl_path.is_file():
    raise FileNotFoundError(f"Missing upstream centerline graph: {cl_path}")

  tagged_graph = load_graph(tagged_path)
  centerline_graph = load_graph(cl_path)
  augmented = augment_corridor_mapping(
    tagged_graph,
    cand_wall_to_id_from_graph(centerline_graph),
  )

  median_w = float(
    centerline_graph.graph.get("global_scale", {}).get("median_corridor_width")
    or augmented.graph.get("median_corridor_width")
    or DEFAULT_MEDIAN_CORRIDOR_WIDTH
  )
  width_tol = width_tol_scale * median_w

  para_raw = augmented.graph.get("parallel_config") or {}
  para_cfg = ParallelGraphConfig()
  for key in (
    "endpoint_link_gap",
    "angle_th_deg",
    "min_width",
    "max_width",
    "min_overlap_ratio",
  ):
    if key in para_raw:
      setattr(para_cfg, key, float(para_raw[key]))
  angle_th_deg = float(para_cfg.angle_th_deg)

  promotions, deferred = evaluate_wall_promotions(
    augmented,
    centerline_graph,
    width_tol=width_tol,
    angle_th_deg=angle_th_deg,
  )
  resolved_graph = apply_wall_promotions(augmented, promotions)
  fixed_graph, fixes = apply_centerline_fixes(
    centerline_graph,
    resolved_graph,
    promotions,
    para_cfg=para_cfg,
  )

  bridge_cfg = CenterlineGraphConfig()
  for key in (
    "endpoint_link_gap",
    "angle_th_deg",
    "min_width",
    "max_width",
    "min_overlap_ratio",
    "endpoint_link_gap_scale",
  ):
    if key in para_raw:
      setattr(bridge_cfg, key, float(para_raw[key]))
  bridge_cfg.apply_global_scale(
    centerline_graph.graph.get("global_scale")
    or {"median_corridor_width": median_w},
  )
  fixed_graph, syntheses = apply_parallel_connector_synthesis(
    fixed_graph,
    resolved_graph,
    para_cfg=bridge_cfg,
  )

  summary = centerline_fix_summary(
    source_stem=stem,
    promotions=promotions,
    deferred=deferred,
    fixes=fixes,
    syntheses=syntheses,
    endpoint_link_gap=float(bridge_cfg.endpoint_link_gap),
    width_tol=width_tol,
  )

  resolved_pkl = residual_graph_resolved_pkl(stem, out)
  resolved_json = residual_graph_resolved_json(stem, out)
  fixed_pkl = centerline_graph_fixed_pkl(stem, out)
  fixed_json = centerline_graph_fixed_json(stem, out)
  fix_json = centerline_fix_json(stem, out)

  save_graph(resolved_graph, resolved_pkl)
  save_json(graph_to_read_json(resolved_graph), resolved_json)
  save_graph(fixed_graph, fixed_pkl)
  save_json(graph_to_read_json(fixed_graph), fixed_json)
  save_json(summary, fix_json)

  paths: dict[str, Path | None] = {
    "residual_graph_resolved_pkl": resolved_pkl,
    "residual_graph_resolved_json": resolved_json,
    "centerline_graph_fixed_pkl": fixed_pkl,
    "centerline_graph_fixed_json": fixed_json,
    "centerline_fix_json": fix_json,
  }

  if vis:
    png_path = centerline_fix_png(stem, out)
    visualize_centerline_fix(
      resolved_graph,
      fixed_graph,
      promotions,
      png_path,
      syntheses=syntheses,
      title=(
        f"centerline fix promoted={len(promotions)} "
        f"deferred={len(deferred)} "
        f"synthesized={sum(1 for row in syntheses if row.get('status') == SYNTHESIS_STATUS)}"
      ),
    )
    paths["centerline_fix_png"] = png_path

  return {
    "promoted_count": len(promotions),
    "deferred_count": len(deferred),
    "fixes": fixes,
    "syntheses": syntheses,
    "paths": paths,
  }


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 3B: promote possible corridor walls and fix centerlines",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument(
    "--centerline-dir",
    type=Path,
    default=None,
    help="directory containing {stem}_centerline_graph.pkl",
  )
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument("--width-tol-scale", type=float, default=1.05)
  parser.add_argument("--no-vis", action="store_true")
  args = parser.parse_args()

  result = fix_centerlines(
    args.stem,
    centerline_dir=args.centerline_dir,
    output_dir=args.output,
    width_tol_scale=args.width_tol_scale,
    vis=not args.no_vis,
  )

  print(
    f"[step3B/centerline_fix] promoted={result.get('promoted_count', 0)} "
    f"deferred={result.get('deferred_count', 0)} "
    f"synthesized={sum(1 for row in result.get('syntheses') or [] if row.get('status') == SYNTHESIS_STATUS)}",
  )
  for row in result.get("fixes") or []:
    if row.get("status") != "applied":
      continue
    cids = [
      cf["corridor_id"]
      for cf in row.get("corridor_fixes") or []
      if cf.get("status") == "extended"
    ]
   # print(
      #f"  handle={row['residual_handle']} partner={row['partner_wall_id']} "
     # f"corridors={cids}",
    #)
  for row in result.get("syntheses") or []:
    if row.get("status") != SYNTHESIS_STATUS:
      continue
   # print(
   #   f"  synthesized={row['corridor_id']} component={row.get('component')} "
   #   f"left_walls={row.get('left_wall_ids')} right_walls={row.get('right_wall_ids')} "
    #  f"low={[a['corridor_id'] for a in row.get('low_attachments') or []]} "
    #  f"high={[a['corridor_id'] for a in row.get('high_attachments') or []]}",
   # )
  for key, path in result["paths"].items():
    if path is not None:
      print(f"[step3B/centerline_fix] → {path}")


if __name__ == "__main__":
  main()
