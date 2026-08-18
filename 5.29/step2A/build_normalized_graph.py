"""
Step 2A normalized graph builder CLI.

Reads normalized_geometry.json; writes normalized_graph.pkl and .json.

Example:
  python step2A/build_normalized_graph.py --stem part2-巷道
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage2.geometry import CorridorPipelineConfig
from stage2.io import endpoint_graph_to_json, load_json, save_graph, save_json
from step2A.normalized_graph import build_normalized_graph
from step2A.paths import (
  normalized_geometry_json,
  normalized_graph_json,
  normalized_graph_pkl,
  step2a_output_dir,
)


def export_normalized_graph(
  stem: str,
  *,
  output_dir: Path | None = None,
  cfg: CorridorPipelineConfig | None = None,
) -> dict[str, Path]:
  out = step2a_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  geo_path = normalized_geometry_json(stem, out)
  if not geo_path.is_file():
    raise FileNotFoundError(
      f"Missing {geo_path}; run step2A/merge_normalized_geometry.py first.",
    )

  doc = load_json(geo_path)
  elements = list(doc.get("elements") or [])
  if not elements:
    raise ValueError(f"No elements[] in {geo_path}")

  cfg = cfg or CorridorPipelineConfig()
  graph, _info = build_normalized_graph(elements, cfg)

  pkl_path = normalized_graph_pkl(stem, out)
  json_path = normalized_graph_json(stem, out)
  save_graph(graph, pkl_path)
  save_json(endpoint_graph_to_json(graph), json_path)

  return {
    "normalized_geometry_json": geo_path,
    "normalized_graph_pkl": pkl_path,
    "normalized_graph_json": json_path,
  }


def main() -> None:
  defaults = CorridorPipelineConfig()
  parser = argparse.ArgumentParser(
    description="Step 2A: normalized_geometry.json → normalized_graph",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument(
    "--endpoint-link-gap",
    type=float,
    default=None,
    help=f"Override CorridorPipelineConfig.endpoint_link_gap (default {defaults.endpoint_link_gap})",
  )
  args = parser.parse_args()

  cfg = CorridorPipelineConfig()
  if args.endpoint_link_gap is not None:
    cfg.endpoint_link_gap = float(args.endpoint_link_gap)

  paths = export_normalized_graph(
    args.stem,
    output_dir=args.output,
    cfg=cfg,
  )
  print(f"[step2A/build_normalized_graph] stem={args.stem}")
  print(f"[step2A/build_normalized_graph] endpoint_link_gap={cfg.endpoint_link_gap}")
  print(f"[step2A/build_normalized_graph] → {paths['normalized_graph_pkl']}")
  print(f"[step2A/build_normalized_graph] → {paths['normalized_graph_json']}")


if __name__ == "__main__":
  main()
