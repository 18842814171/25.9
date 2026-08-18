"""
Step 2A arc bend detection CLI.

Classify each ARC as fillet or unknown; write arc_bend.json before normalize.

Example:
  python step2A/arc_bend_detect.py --stem part2-巷道
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from step2A.bend_layer import BendLayerConfig
from stage2.io import load_graph, load_json, save_json
from step2A.bends import (
  DEFAULT_FILLET_CONFIDENCE,
  arc_bend_detect_to_json,
  detect_arc_bends,
)
from step2A.paths import arc_bend_json, init_graph_pkl, raw_geo_json, step2a_output_dir, step2a_raw_dir


def export_arc_bend_detect(
  stem: str,
  *,
  raw_dir: Path | None = None,
  output_dir: Path | None = None,
  cfg: BendLayerConfig | None = None,
  fillet_threshold: float = DEFAULT_FILLET_CONFIDENCE,
) -> dict:
  raw = step2a_raw_dir(raw_dir)
  out = step2a_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  graph_path = init_graph_pkl(stem, raw)
  geo_path = raw_geo_json(stem, raw)
  if not graph_path.is_file():
    raise FileNotFoundError(
      f"Missing {graph_path}; run step2A/run_init_graph.py first.",
    )
  if not geo_path.is_file():
    raise FileNotFoundError(
      f"Missing {geo_path}; run step2A/run_init_graph.py first.",
    )

  graph = load_graph(graph_path)
  primitives = load_json(geo_path)
  if not isinstance(primitives, list):
    raise ValueError(f"Expected list JSON in {geo_path}")

  cfg = cfg or BendLayerConfig()
  arc_records, scale = detect_arc_bends(
    graph, primitives, cfg, fillet_threshold=fillet_threshold,
  )

  out_path = arc_bend_json(stem, out)
  save_json(
    arc_bend_detect_to_json(
      arc_records,
      source_stem=stem,
      fillet_threshold=fillet_threshold,
      drawing_scale=scale.to_json(),
    ),
    out_path,
  )

  n_fillet = sum(1 for r in arc_records if r.get("status") == "fillet")
  n_unknown = len(arc_records) - n_fillet
  return {
    "arc_records": arc_records,
    "path": out_path,
    "fillet_count": n_fillet,
    "unknown_count": n_unknown,
  }


def main() -> None:
  from stage2.geometry import CorridorPipelineConfig

  defaults = CorridorPipelineConfig()
  parser = argparse.ArgumentParser(
    description="Step 2A: init-graph → arc_bend.json (detect only, no geometry rewrite)",
  )
  parser.add_argument("--stem", required=True, help="Dataset stem matching init-graph")
  parser.add_argument("--raw", type=Path, default=None, help="Raw directory (default: step2A/raw/)")
  parser.add_argument("--output", type=Path, default=None, help="Output directory (default: step2A/output/)")
  parser.add_argument(
    "--endpoint-link-gap",
    type=float,
    default=None,
    help=f"Override CorridorPipelineConfig.endpoint_link_gap (default {defaults.endpoint_link_gap})",
  )
  parser.add_argument(
    "--fillet-threshold",
    type=float,
    default=DEFAULT_FILLET_CONFIDENCE,
    help="Minimum confidence to label status=fillet",
  )
  args = parser.parse_args()

  cfg = BendLayerConfig(endpoint_link_gap=defaults.endpoint_link_gap)
  if args.endpoint_link_gap is not None:
    cfg.endpoint_link_gap = float(args.endpoint_link_gap)

  result = export_arc_bend_detect(
    args.stem,
    raw_dir=args.raw,
    output_dir=args.output,
    cfg=cfg,
    fillet_threshold=args.fillet_threshold,
  )
  print(
    f"[step2A/arc_bend_detect] arcs={len(result['arc_records'])} "
    f"fillet={result['fillet_count']} unknown={result['unknown_count']}",
  )
  print(f"[step2A/arc_bend_detect] → {result['path']}")


if __name__ == "__main__":
  main()
