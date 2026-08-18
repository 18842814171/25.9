"""
Step 2A square bend detection CLI.

Reads init-graph only; does not rewrite geometry.

Example:
  python step2A/square_bend.py --stem 2026.1-1part-巷道
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from step2A.bend_layer import BendLayerConfig
from stage2.io import load_graph, save_json
from step2A.bends import detect_square_bends, square_bends_to_json
from step2A.paths import init_graph_pkl, square_bend_json, step2a_output_dir, step2a_raw_dir


def export_square_bend(
  stem: str,
  *,
  raw_dir: Path | None = None,
  output_dir: Path | None = None,
  cfg: BendLayerConfig | None = None,
) -> dict:
  raw = step2a_raw_dir(raw_dir)
  out = step2a_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  graph_path = init_graph_pkl(stem, raw)
  if not graph_path.is_file():
    raise FileNotFoundError(
      f"Missing {graph_path}; run step2A/run_init_graph.py first.",
    )

  graph = load_graph(graph_path)
  cfg = cfg or BendLayerConfig()
  bends = detect_square_bends(graph, cfg)

  out_path = square_bend_json(stem, out)
  save_json(square_bends_to_json(bends, source_stem=stem), out_path)

  return {"bends": bends, "path": out_path}


def main() -> None:
  from stage2.geometry import CorridorPipelineConfig

  defaults = CorridorPipelineConfig()
  parser = argparse.ArgumentParser(
    description="Step 2A: init-graph → square_bend.json (no geometry rewrite)",
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
  args = parser.parse_args()

  cfg = BendLayerConfig(endpoint_link_gap=defaults.endpoint_link_gap)
  if args.endpoint_link_gap is not None:
    cfg.endpoint_link_gap = float(args.endpoint_link_gap)

  result = export_square_bend(
    args.stem,
    raw_dir=args.raw,
    output_dir=args.output,
    cfg=cfg,
  )
  print(f"[step2A/square_bend] bends={len(result['bends'])}")
  print(f"[step2A/square_bend] → {result['path']}")


if __name__ == "__main__":
  main()
