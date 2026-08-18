"""
Step 4A: classify attached residual regions (crossbar / chamber / niche).

Prerequisites:
  python step3B/build_residual_graph.py --stem {图名}
  python step3A/build_centerline_graph.py --stem {图名}
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
from stage4.attached_regions import (
  annotate_residual_graph_semantic,
  attached_regions_summary,
  prepare_mapped_residual_graph,
)
from stage4.config import Stage4Config
from stage4.visualize import visualize_attached_regions
from utils.centerline_graph import cand_wall_to_id_from_graph
from utils.scale import DEFAULT_MEDIAN_CORRIDOR_WIDTH

try:
  from step4A.paths import (
    attached_regions_json,
    attached_regions_png,
    centerline_graph_input_pkl,
    residual_graph_semantic_json,
    residual_graph_semantic_pkl,
    step3b_residual_graph_pkl,
    step4A_output_dir,
  )
except ModuleNotFoundError:
  from paths import (  # type: ignore
    attached_regions_json,
    attached_regions_png,
    centerline_graph_input_pkl,
    residual_graph_semantic_json,
    residual_graph_semantic_pkl,
    step3b_residual_graph_pkl,
    step4A_output_dir,
  )


def classify_attached_regions(
  stem: str,
  *,
  step3b_dir: Path | None = None,
  centerline_dir: Path | None = None,
  output_dir: Path | None = None,
  cfg: Stage4Config | None = None,
  vis: bool = True,
  label: bool = False,
) -> dict[str, Any]:
  cfg = cfg or Stage4Config()
  out = step4A_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  res_path = step3b_residual_graph_pkl(stem, step3b_dir)
  cl_path = centerline_graph_input_pkl(stem, centerline_dir)
  if not res_path.is_file():
    raise FileNotFoundError(
      f"Missing {res_path}; run step3B/build_residual_graph.py first.",
    )
  if not cl_path.is_file():
    raise FileNotFoundError(
      f"Missing {cl_path}; run step3A/build_centerline_graph.py first.",
    )

  residual_graph = load_graph(res_path)
  centerline_graph = load_graph(cl_path)
  cand_wall_to_id = cand_wall_to_id_from_graph(centerline_graph)
  mapped = prepare_mapped_residual_graph(residual_graph, cand_wall_to_id)

  scale = centerline_graph.graph.get("global_scale") or {}
  median_w = float(
    scale.get("median_corridor_width")
    or mapped.graph.get("median_corridor_width")
    or DEFAULT_MEDIAN_CORRIDOR_WIDTH,
  )
  cfg.apply_global_scale({"median_corridor_width": median_w})

  semantic_graph, classified = annotate_residual_graph_semantic(
    mapped,
    cfg=cfg,
    median_corridor_width=median_w,
  )
  semantic_graph.graph["source_stem"] = stem
  semantic_graph.graph["median_corridor_width"] = median_w
  semantic_graph.graph["stage4_config"] = cfg.to_json()

  summary = attached_regions_summary(classified, source_stem=stem)

  pkl_path = residual_graph_semantic_pkl(stem, out)
  json_path = residual_graph_semantic_json(stem, out)
  summary_path = attached_regions_json(stem, out)
  save_graph(semantic_graph, pkl_path)
  save_json(graph_to_read_json(semantic_graph), json_path)
  save_json(summary, summary_path)

  paths: dict[str, Path | None] = {
    "residual_graph_semantic_pkl": pkl_path,
    "residual_graph_semantic_json": json_path,
    "attached_regions_json": summary_path,
  }

  if vis:
    png_path = attached_regions_png(stem, out, label=label)
    title = (
      "Step 4A attached regions"
      f"{' (handles)' if label else ''} — "
      f"{summary.get('semantic_counts', {})}"
    )
    visualize_attached_regions(
      semantic_graph,
      centerline_graph,
      png_path,
      label=label,
      title=title,
    )
    paths["attached_regions_png"] = png_path

  return {
    "stub_count": summary.get("stub_count", 0),
    "semantic_counts": summary.get("semantic_counts", {}),
    "rc_v1_count": semantic_graph.graph.get("rc_v1_count"),
    "rc_v2_count": semantic_graph.graph.get("rc_v2_count"),
    "median_corridor_width": median_w,
    "paths": paths,
  }


def main() -> None:
  default_cfg = Stage4Config()
  parser = argparse.ArgumentParser(
    description="Step 4A: classify attached residual regions",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument("--step3b", type=Path, default=None, help="step3B/output dir")
  parser.add_argument("--centerline", type=Path, default=None, help="step3A/output dir")
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument(
    "--parallel-length-scale",
    "--max-length-scale",
    type=float,
    default=None,
    dest="parallel_length_scale",
    help=f"default {default_cfg.parallel_length_scale}",
  )
  parser.add_argument("--no-vis", action="store_true")
  parser.add_argument(
    "--label",
    action="store_true",
    help="draw handle labels; output as lb_{stem}_attached_regions.png",
  )
  args = parser.parse_args()

  cfg = Stage4Config()
  if args.parallel_length_scale is not None:
    cfg.parallel_length_scale = args.parallel_length_scale

  step3b_dir = args.step3b
  if step3b_dir is not None:
    step3b_dir = Path(step3b_dir)

  result = classify_attached_regions(
    args.stem,
    step3b_dir=step3b_dir,
    centerline_dir=args.centerline,
    output_dir=args.output,
    cfg=cfg,
    vis=not args.no_vis,
    label=args.label,
  )

  counts = result.get("semantic_counts") or {}
  print(
    f"[step4A/classify] stubs={result.get('stub_count', 0)} "
    f"RC_v1={result.get('rc_v1_count')} RC_v2={result.get('rc_v2_count')} "
    f"sem={counts}",
  )
  for key, path in result["paths"].items():
    if path is not None:
      print(f"[step4A/classify] → {path}")


if __name__ == "__main__":
  main()

