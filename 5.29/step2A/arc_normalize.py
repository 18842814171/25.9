"""
Step 2A arc normalization CLI.

Reads arc_bend.json from arc_bend_detect; clips geometry for high-confidence fillets.

Example:
  python step2A/arc_bend_detect.py --stem part2-巷道
  python step2A/arc_normalize.py --stem part2-巷道
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
  arc_line_normalize_to_json,
  normalize_arcs_from_detect,
  unmodified_elements_to_json,
)
from step2A.paths import (
  arc_bend_json,
  arc_line_normalize_json,
  init_graph_pkl,
  raw_geo_json,
  step2a_output_dir,
  step2a_raw_dir,
  unmodified_elements_json,
)


def export_arc_normalize(
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
  bend_path = arc_bend_json(stem, out)
  if not graph_path.is_file():
    raise FileNotFoundError(
      f"Missing {graph_path}; run step2A/run_init_graph.py first.",
    )
  if not geo_path.is_file():
    raise FileNotFoundError(
      f"Missing {geo_path}; run step2A/run_init_graph.py first.",
    )
  if not bend_path.is_file():
    raise FileNotFoundError(
      f"Missing {bend_path}; run step2A/arc_bend_detect.py first.",
    )

  graph = load_graph(graph_path)
  primitives = load_json(geo_path)
  if not isinstance(primitives, list):
    raise ValueError(f"Expected list JSON in {geo_path}")

  bend_doc = load_json(bend_path)
  # 图中无 ARC / 未检出圆角时 arcs 为空，按 0 处理，不中断流水线。
  arc_records = list(bend_doc.get("arcs") or [])

  cfg = cfg or BendLayerConfig()
  arc_lines, unmodified = normalize_arcs_from_detect(
    graph,
    primitives,
    arc_records,
    cfg,
    fillet_threshold=fillet_threshold,
  )

  lines_path = arc_line_normalize_json(stem, out)
  unmod_path = unmodified_elements_json(stem, out)

  save_json(arc_line_normalize_to_json(arc_lines, source_stem=stem), lines_path)
  save_json(unmodified_elements_to_json(unmodified, source_stem=stem), unmod_path)

  n_clip = sum(
    1 for r in arc_records
    if r.get("status") == "fillet"
    and float(r.get("confidence", 0.0)) >= fillet_threshold
    and float(r.get("signals", {}).get("clip_ok", 0.0)) >= 1.0
  )

  return {
    "arc_lines": arc_lines,
    "unmodified": unmodified,
    "normalized_arc_count": n_clip,
    "paths": {
      "arc_bend_json": bend_path,
      "arc_line_normalize_json": lines_path,
      "unmodified_elements_json": unmod_path,
    },
  }


def main() -> None:
  from stage2.geometry import CorridorPipelineConfig

  defaults = CorridorPipelineConfig()
  parser = argparse.ArgumentParser(
    description="Step 2A: arc_bend.json → arc_line_normalize + unmodified_elements",
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
    help="Must match arc_bend_detect threshold",
  )
  args = parser.parse_args()

  cfg = BendLayerConfig(endpoint_link_gap=defaults.endpoint_link_gap)
  if args.endpoint_link_gap is not None:
    cfg.endpoint_link_gap = float(args.endpoint_link_gap)

  result = export_arc_normalize(
    args.stem,
    raw_dir=args.raw,
    output_dir=args.output,
    cfg=cfg,
    fillet_threshold=args.fillet_threshold,
  )
  print(f"[step2A/arc_normalize] normalized_arcs={result['normalized_arc_count']}")
  print(f"[step2A/arc_normalize] clipped_lines={len(result['arc_lines'])}")
  print(f"[step2A/arc_normalize] unmodified={len(result['unmodified'])}")
  for key, path in result["paths"].items():
    print(f"[step2A/arc_normalize] → {path}")


if __name__ == "__main__":
  main()
