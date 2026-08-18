"""
Step 3B: pick candidate corridor walls from residual_graph stubs.

Prerequisite:
  python step3B/build_residual_graph.py --stem {图名}
  python step3A/build_centerline_graph.py --stem {图名}

Example:
  python step3B/pick_corridor_wall_candidates.py --stem 2026.1-1part-巷道
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
from utils.centerline_graph import cand_wall_to_id_from_graph
from utils.scale import DEFAULT_MEDIAN_CORRIDOR_WIDTH
from step3B.corridor_mapping import augment_corridor_mapping
from step3B.corridor_wall_candidates import (
  candidate_corridor_walls_summary,
  detect_candidate_corridor_walls,
  tag_candidate_corridor_walls,
)
from step3B.paths import (
  centerline_graph_input_pkl,
  secondary_wall_candidates_json,
  secondary_wall_candidates_png,
  residual_graph_pkl,
  residual_graph_tagged_json,
  residual_graph_tagged_pkl,
  step3b_output_dir,
)
from step3B.visualize import visualize_secondary_wall_candidates


def pick_corridor_wall_candidates(
  stem: str,
  *,
  centerline_dir: Path | None = None,
  output_dir: Path | None = None,
  min_length_scale: float = 0.5,
  vis: bool = True,
) -> dict[str, Any]:
  """Augment corridor mapping, pick stubs, relabel graph, write outputs."""
  out = step3b_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  res_path = residual_graph_pkl(stem, out)
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

  augmented = augment_corridor_mapping(residual_graph, cand_wall_to_id)
  scale = centerline_graph.graph.get("global_scale") or {}
  median_w = float(
    scale.get("median_corridor_width")
    or residual_graph.graph.get("median_corridor_width")
    or DEFAULT_MEDIAN_CORRIDOR_WIDTH
  )
  min_length = min_length_scale * median_w

  candidates = detect_candidate_corridor_walls(augmented, min_length=min_length)
  tagged_graph = tag_candidate_corridor_walls(augmented, candidates)
  summary = candidate_corridor_walls_summary(
    source_stem=stem,
    candidates=candidates,
    min_length=min_length,
  )

  tagged_pkl = residual_graph_tagged_pkl(stem, out)
  tagged_json = residual_graph_tagged_json(stem, out)
  cand_json = secondary_wall_candidates_json(stem, out)
  save_graph(tagged_graph, tagged_pkl)
  save_json(graph_to_read_json(tagged_graph), tagged_json)
  save_json(summary, cand_json)

  paths: dict[str, Path | None] = {
    "residual_graph_tagged_pkl": tagged_pkl,
    "residual_graph_tagged_json": tagged_json,
    "secondary_wall_candidates_json": cand_json,
  }

  if vis:
    png_path = secondary_wall_candidates_png(stem, out)
    visualize_secondary_wall_candidates(
      tagged_graph,
      png_path,
      title=(
        f"Step 3B secondary wall candidates "
        f"n={len(candidates)}"
      ),
    )
    paths["secondary_wall_candidates_png"] = png_path

  return {
    "candidate_count": len(candidates),
    "candidates": candidates,
    "paths": paths,
  }


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 3B: pick candidate corridor walls from residual stubs",
  )
  parser.add_argument("--stem", required=True)
  
  parser.add_argument(
    "--centerline-dir",
    type=Path,
    default=None,
    help="directory containing {stem}_centerline_graph.pkl",
  )
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument("--min-length-scale", type=float, default=0.5)
  parser.add_argument("--no-vis", action="store_true")
  args = parser.parse_args()

  result = pick_corridor_wall_candidates(
    args.stem,
    centerline_dir=args.centerline_dir,
    output_dir=args.output,
    min_length_scale=args.min_length_scale,
    vis=not args.no_vis,
  )

  print(
    f"[step3B/secondary_wall_candidates] count={result.get('candidate_count', 0)}",
  )
  #for row in result.get("candidates") or []:
    
  for key, path in result["paths"].items():
    if path is not None:
      print(f"[step3B/secondary_wall_candidates] → {path}")


if __name__ == "__main__":
  main()
