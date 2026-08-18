"""
Step 4B: complete corridor centerlines and build tunnel logical graph.

Prerequisites:
  python step3B/fix_centerlines.py --stem {图名}
  python step4A/classify_attached_regions.py --stem {图名}
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
from stage4.corrected_centerlines import build_corrected_centerlines
from stage4.visualize import visualize_structure_graph
from step2B.config import CenterlineGraphConfig
try:
  from step4B.paths import (
    centerline_graph_fixed_pkl,
    step4A_residual_graph_semantic_pkl,
    step4B_output_dir,
    structure_graph_json,
    structure_graph_pkl,
    structure_graph_png,
  )
except ModuleNotFoundError:
  from paths import (  # type: ignore
    centerline_graph_fixed_pkl,
    step4A_residual_graph_semantic_pkl,
    step4B_output_dir,
    structure_graph_json,
    structure_graph_pkl,
    structure_graph_png,
  )
from utils.scale import DEFAULT_MEDIAN_CORRIDOR_WIDTH


def build_corrected_centerlines_artifacts(
  stem: str,
  *,
  step3b_dir: Path | None = None,
  step4A_dir: Path | None = None,
  output_dir: Path | None = None,
  width_tol_scale: float = 1.05,
  vis: bool = True,
  label: bool = False,
) -> dict[str, Any]:
  out = step4B_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  fixed_path = centerline_graph_fixed_pkl(stem, step3b_dir)
  semantic_path = step4A_residual_graph_semantic_pkl(stem, step4A_dir)
  if not fixed_path.is_file():
    raise FileNotFoundError(
      f"Missing {fixed_path}; run step3B/fix_centerlines.py first.",
    )
  if not semantic_path.is_file():
    raise FileNotFoundError(
      f"Missing {semantic_path}; run step4A/classify_attached_regions.py first.",
    )

  fixed_graph = load_graph(fixed_path)
  semantic_graph = load_graph(semantic_path)

  median_w = float(
    fixed_graph.graph.get("global_scale", {}).get("median_corridor_width")
    or semantic_graph.graph.get("median_corridor_width")
    or DEFAULT_MEDIAN_CORRIDOR_WIDTH,
  )
  width_tol = width_tol_scale * median_w

  para_cfg = CenterlineGraphConfig()
  para_raw = (
    fixed_graph.graph.get("parallel_config")
    or semantic_graph.graph.get("parallel_config")
    or {}
  )
  for key in (
    "endpoint_link_gap",
    "angle_th_deg",
    "min_width",
    "max_width",
    "min_overlap_ratio",
    "endpoint_link_gap_scale",
  ):
    if key in para_raw:
      setattr(para_cfg, key, float(para_raw[key]))
  para_cfg.apply_global_scale(
    fixed_graph.graph.get("global_scale")
    or {"median_corridor_width": median_w},
  )

  tunnel_graph, audit = build_corrected_centerlines(
    fixed_graph,
    semantic_graph,
    width_tol=width_tol,
    angle_th_deg=float(para_cfg.angle_th_deg),
    para_cfg=para_cfg,
  )
  tunnel_graph.graph["source_stem"] = stem
  tunnel_graph.graph["median_corridor_width"] = median_w

  struct_pkl = structure_graph_pkl(stem, out)
  struct_json = structure_graph_json(stem, out)
  save_graph(tunnel_graph, struct_pkl)
  save_json(graph_to_read_json(tunnel_graph), struct_json)

  paths: dict[str, Path | None] = {
    "structure_graph_pkl": struct_pkl,
    "structure_graph_json": struct_json,
  }

  if vis:
    roles = tunnel_graph.graph.get("role_counts") or {}
    struct_png = structure_graph_png(stem, out, label=label)
    visualize_structure_graph(
      tunnel_graph,
      struct_png,
      label=label,
      title=(
        "Step 4B structure graph"
        f"{' (labeled)' if label else ''} — "
        f"Corr={roles.get('corridor', 0)} "
        f"Aux={roles.get('auxiliary', 0)} "
        f"Ch={roles.get('niche', 0)} "
        f"Unc={roles.get('unclassified', 0)}"
      ),
    )
    paths["structure_graph_png"] = struct_png

  extensions = sum(
    1
    for row in audit.get("fixes") or []
    if row.get("status") == "applied"
    and any(
      cf.get("status") == "extended"
      for cf in row.get("corridor_fixes") or []
    )
  )
  synthesized = sum(
    1
    for row in audit.get("auxiliary_syntheses") or []
    if row.get("status") == "synthesized"
  )

  return {
    "centerline_count": tunnel_graph.graph.get("centerline_count"),
    "structure_count": tunnel_graph.graph.get("structure_count"),
    "edge_counts": tunnel_graph.graph.get("edge_counts"),
    "corridor_extensions": extensions,
    "auxiliary_synthesized": synthesized,
    "paths": paths,
  }


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 4B: build corrected centerlines tunnel graph",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument("--step3b", type=Path, default=None, help="step3B/output dir")
  parser.add_argument("--step4A", type=Path, default=None, help="step4A/output dir")
  parser.add_argument("--output", type=Path, default=None, help="step4B/output dir")
  parser.add_argument("--width-tol-scale", type=float, default=1.05)
  parser.add_argument("--no-vis", action="store_true")
  parser.add_argument(
    "--label",
    action="store_true",
    help="draw Aux/Ch labels; output as lb_{stem}_structure_graph.png",
  )
  args = parser.parse_args()

  result = build_corrected_centerlines_artifacts(
    args.stem,
    step3b_dir=args.step3b,
    step4A_dir=args.step4A,
    output_dir=args.output,
    width_tol_scale=args.width_tol_scale,
    vis=not args.no_vis,
    label=args.label,
  )

  print(
    f"[step4B/structure_graph] "
    f"CL={result.get('centerline_count')} "
    f"struct={result.get('structure_count')} "
    f"edges={result.get('edge_counts')} "
    f"extended={result.get('corridor_extensions')} "
    f"aux_synth={result.get('auxiliary_synthesized')}",
  )
  for key, path in result["paths"].items():
    if path is not None:
      print(f"[step4B/structure_graph] → {path}")


if __name__ == "__main__":
  main()

