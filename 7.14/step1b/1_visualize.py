"""step1b-1：绘制 structure_graph_with_texts 核对图。

用法（在仓库根目录）：
  python step1b/1_visualize.py --stem 2026.1-1 --output-dir path/to/714-stage1 \\
    --corridor-json path/to/stem-巷道.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from config import (
    Step1bConfig,
    structure_graph_with_texts_pkl,
    structure_graph_with_texts_png,
)
from graph_io import load_graph
from visualize import draw_structure_graph_with_texts, load_corridor_entities

CFG = Step1bConfig()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize structure_graph_with_texts"
    )
    parser.add_argument("--stem", type=str, default=CFG.default_stem)
    parser.add_argument(
        "--pkl",
        type=str,
        default="",
        help="override path to structure_graph_with_texts.pkl",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="override product directory (default: step1b/output)",
    )
    parser.add_argument(
        "--corridor-json",
        type=str,
        default="",
        help="original corridor entities JSON (-巷道.json), drawn in black",
    )
    args = parser.parse_args()
    out = args.output_dir or None

    pkl_path = (
        Path(args.pkl) if args.pkl else structure_graph_with_texts_pkl(args.stem, out)
    )
    if not pkl_path.is_file():
        raise FileNotFoundError(f"graph not found: {pkl_path}")

    corridors = None
    if args.corridor_json:
        corr_path = Path(args.corridor_json)
        if not corr_path.is_file():
            raise FileNotFoundError(f"corridor json not found: {corr_path}")
        corridors = load_corridor_entities(corr_path)
        print(f"corridor: {corr_path} ({len(corridors)} entities)")

    graph = load_graph(pkl_path)
    out_png = structure_graph_with_texts_png(args.stem, out)
    draw_structure_graph_with_texts(graph, out_png, CFG, corridors=corridors)
    print(f"input:  {pkl_path}")
    print(f"output: {out_png}")


if __name__ == "__main__":
    main()
