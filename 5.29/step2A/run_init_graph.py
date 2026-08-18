"""
Step 2A init-graph builder CLI.

Example:
  python step2A/run_init_graph.py --geo stage2/in/2026.1-1part-巷道.json
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
from step2A.init_graph import build_init_graph, prepare_corridor_primitives
from step2A.paths import init_graph_json, init_graph_pkl, raw_geo_json, step2a_raw_dir

DEFAULT_GEO = _ROOT / "stage2" / "in" / "2026.1-1tmp-巷道.json"


def export_init_graph(
  primitives: list[dict],
  stem: str,
  raw_dir: Path | None = None,
  *,
  cfg: CorridorPipelineConfig | None = None,
) -> dict[str, Path]:
  cfg = cfg or CorridorPipelineConfig()
  raw = step2a_raw_dir(raw_dir)
  raw.mkdir(parents=True, exist_ok=True)

  geo_path = raw_geo_json(stem, raw)
  pkl_path = init_graph_pkl(stem, raw)
  json_path = init_graph_json(stem, raw)

  kept, dropped = prepare_corridor_primitives(primitives, cfg)
  save_json(kept, geo_path)

  graph, _info = build_init_graph(kept, cfg)
  # build_init_graph 会再过滤一次；对已过滤输入 dropped 多为 0
  graph.graph["spatial_outlier_dropped"] = int(
    graph.graph.get("spatial_outlier_dropped") or 0
  ) + len(dropped)
  save_graph(graph, pkl_path)
  save_json(endpoint_graph_to_json(graph), json_path)

  return {
    "raw_geo_json": geo_path,
    "init_graph_pkl": pkl_path,
    "init_graph_json": json_path,
  }


def main() -> None:
  defaults = CorridorPipelineConfig()
  parser = argparse.ArgumentParser(
    description="Step 2A: original geometry JSON → init endpoint graph",
  )
  parser.add_argument("--geo", type=Path, default=DEFAULT_GEO, help="Input geometry JSON")
  parser.add_argument("--stem", default=None, help="Output stem (default: geo file stem)")
  parser.add_argument(
    "--raw",
    type=Path,
    default=None,
    help="Raw artefact directory (default: step2A/raw/)",
  )
  parser.add_argument(
    "--endpoint-link-gap",
    type=float,
    default=None,
    help=f"Override CorridorPipelineConfig.endpoint_link_gap (default {defaults.endpoint_link_gap})",
  )
  args = parser.parse_args()

  if not args.geo.is_file():
    raise FileNotFoundError(args.geo)

  stem = args.stem or args.geo.stem.replace(" ", "_")
  primitives = load_json(args.geo)
  if not isinstance(primitives, list):
    raise ValueError(f"Expected list JSON in {args.geo}")

  cfg = CorridorPipelineConfig()
  if args.endpoint_link_gap is not None:
    cfg.endpoint_link_gap = float(args.endpoint_link_gap)

  paths = export_init_graph(primitives, stem, args.raw, cfg=cfg)
  print(f"[step2A/init-graph] stem={stem}")
  print(f"[step2A/init-graph] endpoint_link_gap={cfg.endpoint_link_gap}")
  print(f"[step2A/init-graph] → {paths['raw_geo_json']}")
  print(f"[step2A/init-graph] → {paths['init_graph_pkl']}")
  print(f"[step2A/init-graph] → {paths['init_graph_json']}")


if __name__ == "__main__":
  main()
