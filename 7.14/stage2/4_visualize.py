"""Script 4: visualize facility_graph and/or structure_graph_with_facilities."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from config import (
    Stage2Config,
    corridor_json,
    facility_graph_pkl,
    facility_graph_png,
    structure_graph_with_facilities_pkl,
    structure_graph_with_facilities_png,
)
from graph_io import load_graph
from visualize import (
    draw_facility_graph,
    draw_structure_graph_with_facilities,
    load_corridor_entities,
)

CFG = Stage2Config()


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize stage2 facility products")
    parser.add_argument("--stem", type=str, default=CFG.default_stem)
    parser.add_argument(
        "--which",
        choices=["facility", "structure", "both"],
        default="both",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="override product directory (default: stage2/output)",
    )
    parser.add_argument(
        "--corridor-json",
        type=str,
        default="",
        help="override corridor geometry JSON",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="",
        help="directory for corridor JSON when --corridor-json omitted",
    )
    args = parser.parse_args()
    out = args.output_dir or None
    in_dir = args.input_dir or None

    corridors = None
    corr_path = corridor_json(
        args.stem,
        CFG,
        base_dir=in_dir,
        path=args.corridor_json or None,
    )
    if corr_path.is_file():
        corridors = load_corridor_entities(corr_path)
        print(f"corridor: {corr_path} ({len(corridors)} entities)")
    else:
        print(f"corridor skipped (not found): {corr_path}")

    if args.which in {"facility", "both"}:
        g = load_graph(facility_graph_pkl(args.stem, out))
        png = facility_graph_png(args.stem, out)
        draw_facility_graph(g, png, CFG, corridors=corridors)
        print(f"facility_png: {png}")

    if args.which in {"structure", "both"}:
        path = structure_graph_with_facilities_pkl(args.stem, out)
        if not path.is_file():
            print(f"skip structure viz (missing): {path}")
            return
        g = load_graph(path)
        png = structure_graph_with_facilities_png(args.stem, out)
        draw_structure_graph_with_facilities(g, png, CFG, corridors=corridors)
        print(f"structure_png: {png}")


if __name__ == "__main__":
    main()
