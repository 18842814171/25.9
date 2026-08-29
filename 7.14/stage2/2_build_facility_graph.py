"""Script 2: facility_primitives_graph → facility_graph."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from cluster_facilities import build_facility_graph
from config import (
    Stage2Config,
    facility_graph_json,
    facility_graph_pkl,
    facility_primitives_graph_pkl,
)
from graph_io import load_graph, save_graph

CFG = Stage2Config()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster facilities into instances")
    parser.add_argument("--stem", type=str, default=CFG.default_stem)
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="override product directory (default: stage2/output)",
    )
    parser.add_argument(
        "--primitives-pkl",
        type=str,
        default="",
        help="override facility_primitives_graph.pkl",
    )
    args = parser.parse_args()
    out = args.output_dir or None

    primitives = load_graph(
        Path(args.primitives_pkl)
        if args.primitives_pkl
        else facility_primitives_graph_pkl(args.stem, out)
    )
    graph = build_facility_graph(primitives, CFG)

    out_pkl = facility_graph_pkl(args.stem, out)
    out_json = facility_graph_json(args.stem, out)
    save_graph(graph, out_pkl, out_json)

    summary = graph.graph.get("facility_summary") or {}
    print(f"stem: {args.stem}")
    print(f"output: {out_pkl}")
    print(f"facilities: {summary.get('facility_count')}")
    print(f"by_type: {summary.get('by_type')}")


if __name__ == "__main__":
    main()
