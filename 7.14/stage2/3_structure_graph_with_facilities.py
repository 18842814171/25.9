"""Script 3: 设施实例图挂接到文字+巷道融合图，并输出核对图。

用法（仓库根目录）：
  python stage2/3_structure_graph_with_facilities.py --stem 2026.1-1 ^
    --structure-pkl path/to/structure_graph_with_texts.pkl ^
    --output-dir path/to/714-stage2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from build_attach import build_structure_graph_with_facilities
from config import (
    Stage2Config,
    corridor_json,
    facility_graph_pkl,
    structure_graph_with_facilities_json,
    structure_graph_with_facilities_pkl,
    structure_graph_with_facilities_png,
)
from graph_io import load_graph, save_graph
from visualize import draw_structure_graph_with_facilities, load_corridor_entities

CFG = Stage2Config()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attach facilities onto structure_graph_with_texts and draw check PNG"
    )
    parser.add_argument("--stem", type=str, default=CFG.default_stem)
    parser.add_argument(
        "--structure-pkl",
        type=str,
        required=True,
        help="path to structure_graph_with_texts.pkl（须显式指定）",
    )
    parser.add_argument(
        "--facilities-pkl",
        type=str,
        default="",
        help="override path to facility_graph.pkl",
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
        help="override corridor geometry JSON for PNG",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="",
        help="directory for corridor JSON when --corridor-json omitted",
    )
    parser.add_argument(
        "--no-png",
        action="store_true",
        help="skip verification PNG (pkl/json only)",
    )
    args = parser.parse_args()
    out = args.output_dir or None
    in_dir = args.input_dir or None

    struct_path = Path(args.structure_pkl)
    if not struct_path.is_absolute():
        struct_path = (Path.cwd() / struct_path).resolve()
    fac_path = (
        Path(args.facilities_pkl)
        if args.facilities_pkl
        else facility_graph_pkl(args.stem, out)
    )
    if not struct_path.is_file():
        raise FileNotFoundError(f"structure not found: {struct_path}")
    if not fac_path.is_file():
        raise FileNotFoundError(f"facility_graph not found: {fac_path}")

    structure = load_graph(struct_path)
    facilities = load_graph(fac_path)
    fused = build_structure_graph_with_facilities(structure, facilities, CFG)
    fused.graph["stem"] = args.stem
    fused.graph["source_structure_pkl"] = str(struct_path)
    fused.graph["source_facility_pkl"] = str(fac_path)

    out_pkl = structure_graph_with_facilities_pkl(args.stem, out)
    out_json = structure_graph_with_facilities_json(args.stem, out)
    save_graph(fused, out_pkl, out_json)

    summary = fused.graph.get("facility_attach_summary") or {}
    print(f"structure: {struct_path}")
    print(f"facilities: {fac_path}")
    print(f"output: {out_pkl}")
    print(f"threshold: {fused.graph.get('facility_attach_threshold')}")
    print(f"attached: {summary.get('attached')}")
    print(f"skipped: {summary.get('skipped')}")

    if args.no_png:
        return

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

    out_png = structure_graph_with_facilities_png(args.stem, out)
    draw_structure_graph_with_facilities(fused, out_png, CFG, corridors=corridors)
    print(f"structure_png: {out_png}")


if __name__ == "__main__":
    main()
