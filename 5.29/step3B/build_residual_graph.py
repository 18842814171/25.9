"""
Step 3B: build residual_graph.pkl from parallel_graph.pkl.

Input: parallel_graph.pkl (wall + stub facts from Step 2B).
Output: residual_graph.pkl with stub-stub-touch, corridor-stub-touch,
        stub-stub-parallel, corridor-stub-parallel edges.

Example:
  python step3B/build_residual_graph.py --stem part1-巷道
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
from step2B.paths import parallel_graph_pkl, step2b_output_dir
from step2B.width_estimate import load_corridor_width_median
from step3B.config import AttachConfig
from step3B.global_scale import apply_attach_scale
from step3B.graph_inputs import load_from_parallel_graph
from step3B.paths import (
  residual_graph_json,
  residual_graph_pkl,
  residual_graph_png,
  residual_graph_summary_json,
  step3b_output_dir,
)
from step3B.residual_component import build_residual_components_from_stubs
from step3B.residual_graph import (
  build_residual_graph,
  compare_rc_v1_to_legacy,
  residual_components_v1,
  residual_graph_summary,
)
from step3B.visualize import visualize_residual_graph


def build_residual_graph_artifacts(
  stem: str,
  *,
  step2b_dir: Path | None = None,
  step2a_dir: Path | None = None,
  output_dir: Path | None = None,
  cfg: AttachConfig | None = None,
  auto_scale: bool = True,
  vis: bool = True,
  label: bool = False,
) -> dict[str, Any]:
  """Build residual_graph.pkl from parallel_graph.pkl only."""
  step2b = step2b_output_dir(step2b_dir)
  out = step3b_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)
  cfg = cfg or AttachConfig()

  pg_path = parallel_graph_pkl(stem, step2b)
  if not pg_path.is_file():
    raise FileNotFoundError(
      f"Missing {pg_path}; run step2B/build_parallel_graph.py first.",
    )

  parallel_graph = load_graph(pg_path)
  inputs = load_from_parallel_graph(parallel_graph)

  median_w = load_corridor_width_median(stem, step2b_dir)
  global_scale = {"median_corridor_width": median_w}
  if auto_scale:
    apply_attach_scale(cfg, global_scale)

  residual_graph = build_residual_graph(
    parallel_graph,
    stub_segments=inputs["stub_segments"],
    wall_index=inputs["wall_index"],
    cand_wall_to_id={},
    attach_tol=cfg.attach_tol,
    median_corridor_width=median_w,
    source_stem=stem,
  )
  residual_graph.graph["median_corridor_width"] = median_w

  para_cfg = residual_graph.graph.get("parallel_config") or {}
  endpoint_link_gap = float(para_cfg.get("endpoint_link_gap") or cfg.endpoint_link_gap)

  rc_v1 = residual_components_v1(residual_graph)
  legacy_rc = build_residual_components_from_stubs(
    inputs["stub_segments"],
    endpoint_link_gap,
  )
  rc_compare = compare_rc_v1_to_legacy(rc_v1, legacy_rc)

  summary_doc = residual_graph_summary(
    residual_graph,
    source_stem=stem,
    rc_v1=rc_v1,
    legacy_rc_compare=rc_compare,
  )

  pkl_path = residual_graph_pkl(stem, out)
  json_path = residual_graph_json(stem, out)
  summary_path = residual_graph_summary_json(stem, out)
  save_graph(residual_graph, pkl_path)
  save_json(graph_to_read_json(residual_graph), json_path)
  save_json(summary_doc, summary_path)

  paths: dict[str, Path | None] = {
    "residual_graph_pkl": pkl_path,
    "residual_graph_json": json_path,
    "residual_graph_summary_json": summary_path,
  }

  if vis:
    png_path = residual_graph_png(stem, out, label=label)
    visualize_residual_graph(
      residual_graph,
      png_path,
      label=label,
      title=(
        f"residual_graph RC_v1={len(rc_v1)} "
        f"legacy_RC={len(legacy_rc)} "
        f"match={rc_compare['identical_partitioning']}"
      ),
    )
    paths["residual_graph_png"] = png_path

  return {
    "stub_count": summary_doc.get("stub_count", 0),
    "edge_counts": summary_doc.get("edge_counts", {}),
    "rc_v1_count": len(rc_v1),
    "legacy_rc_count": len(legacy_rc),
    "rc_v1_legacy_match": rc_compare,
    "median_corridor_width": median_w,
    "paths": paths,
  }


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 3B: build residual_graph.pkl from parallel_graph.pkl",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument("--step2b", type=Path, default=None)
  parser.add_argument(
    "--step2a",
    type=Path,
    default=None,
    help="deprecated; width estimate now reads Step 2B straight wall geometry",
  )
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument("--no-vis", action="store_true")
  parser.add_argument("--no-auto-scale", action="store_true")
  parser.add_argument(
    "--label",
    action="store_true",
    help="draw touch junction labels; output as lb_{stem}_residual_graph.png",
  )
  parser.add_argument("--endpoint-link-gap-scale", type=float, default=None)
  parser.add_argument("--attach-tol-scale", type=float, default=None)
  parser.add_argument("--endpoint-link-gap", type=float, default=None)
  parser.add_argument("--attach-tol", type=float, default=None)
  args = parser.parse_args()

  cfg = AttachConfig()
  auto_scale = not args.no_auto_scale
  if args.endpoint_link_gap_scale is not None:
    cfg.endpoint_link_gap_scale = args.endpoint_link_gap_scale
  if args.attach_tol_scale is not None:
    cfg.attach_tol_scale = args.attach_tol_scale
  if args.endpoint_link_gap is not None:
    cfg.endpoint_link_gap = args.endpoint_link_gap
    auto_scale = False
  if args.attach_tol is not None:
    cfg.attach_tol = args.attach_tol
    auto_scale = False

  result = build_residual_graph_artifacts(
    args.stem,
    step2b_dir=args.step2b,
    step2a_dir=args.step2a,
    output_dir=args.output,
    cfg=cfg,
    auto_scale=auto_scale,
    vis=not args.no_vis,
    label=args.label,
  )

  match = result.get("rc_v1_legacy_match") or {}
  w = result.get("median_corridor_width")
  width_msg = f" width_median={w:.2f}" if w else ""
  print(
    f"[step3B/residual_graph] stubs={result.get('stub_count', 0)} "
    f"edges={result.get('edge_counts', {})}{width_msg}",
  )
  print(
    f"[step3B/RC_v1] count={result.get('rc_v1_count', 0)} "
    f"legacy={result.get('legacy_rc_count', 0)} "
    f"identical={match.get('identical_partitioning')} "
    f"matched_partitions={match.get('matched_partitions')}",
  )
  for key, path in result["paths"].items():
    if path is not None:
      print(f"[step3B/residual_graph] → {path}")


if __name__ == "__main__":
  main()
