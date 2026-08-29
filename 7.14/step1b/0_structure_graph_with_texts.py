"""step1b-0：将标注组与巷道文字关联到结构图，产出 structure_graph_with_texts。

用法（在仓库根目录）：
  python step1b/0_structure_graph_with_texts.py ^
    --structure-pkl path/to/structure_graph.pkl
  python step1b/0_structure_graph_with_texts.py ^
    --stem 2026.1-1 ^
    --structure-pkl path/to/structure_graph.pkl ^
    --output-dir path/to/714-stage1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from build_fusion import build_structure_graph_with_texts
from config import (
    Step1bConfig,
    final_cluster_pkl,
    structure_graph_with_texts_json,
    structure_graph_with_texts_pkl,
)
from graph_io import load_graph, save_graph

CFG = Step1bConfig()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attach final_cluster onto structure_graph → structure_graph_with_texts"
    )
    parser.add_argument("--stem", type=str, default=CFG.default_stem)
    parser.add_argument(
        "--structure-pkl",
        type=str,
        required=True,
        help="path to structure_graph.pkl（须在命令行显式指定，无默认跨目录路径）",
    )
    parser.add_argument(
        "--clusters-pkl",
        type=str,
        default="",
        help="override path to final_cluster.pkl",
    )
    parser.add_argument(
        "--step1a-output-dir",
        type=str,
        default="",
        help="directory of final_cluster when --clusters-pkl omitted",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="override product directory (default: step1b/output)",
    )
    args = parser.parse_args()
    out = args.output_dir or None
    step1a_out = args.step1a_output_dir or None

    struct_path = Path(args.structure_pkl)
    if not struct_path.is_absolute():
        struct_path = (Path.cwd() / struct_path).resolve()
    clusters_path = (
        Path(args.clusters_pkl)
        if args.clusters_pkl
        else final_cluster_pkl(args.stem, step1a_out=step1a_out)
    )
    if not struct_path.is_file():
        raise FileNotFoundError(f"structure_graph not found: {struct_path}")
    if not clusters_path.is_file():
        raise FileNotFoundError(f"final_cluster not found: {clusters_path}")

    structure = load_graph(struct_path)
    clusters = load_graph(clusters_path)
    fused = build_structure_graph_with_texts(structure, clusters, CFG)
    fused.graph["stem"] = args.stem
    fused.graph["source_structure_pkl"] = str(struct_path)
    fused.graph["source_clusters_pkl"] = str(clusters_path)

    out_pkl = structure_graph_with_texts_pkl(args.stem, out)
    out_json = structure_graph_with_texts_json(args.stem, out)
    save_graph(fused, out_pkl, out_json)

    summary = fused.graph.get("attach_summary") or {}
    print(f"structure: {struct_path}")
    print(f"clusters:  {clusters_path}")
    print(f"output:    {out_pkl}")
    print(f"threshold: {fused.graph.get('attach_threshold')}")
    print(f"nodes: {fused.number_of_nodes()}  edges: {fused.number_of_edges()}")
    print(f"attached: {summary.get('attached')}")
    print(f"skipped:  {summary.get('skipped')}")


if __name__ == "__main__":
    main()
