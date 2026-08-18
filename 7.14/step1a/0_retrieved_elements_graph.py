"""Script 0: `{stem}-文字.json` → retrieved_elements_graph.

Requires text export from utils/entity_export.py --mode text.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

STEP1A_DIR = Path(__file__).resolve().parent
_ROOT = STEP1A_DIR.parent
if str(STEP1A_DIR) not in sys.path:
    sys.path.insert(0, str(STEP1A_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.entity_json import exported_json_path

from config import (
    Step1aConfig,
    bind_chains_png,
    corridor_json,
    retrieved_elements_graph_json,
    retrieved_elements_graph_pkl,
)
from graph_io import save_graph
from graph_nodes import build_retrieved_elements_graph
from visualize_clusters import load_corridor_entities, visualize_bind_chains

CFG = Step1aConfig()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build annotation relationship graph from text export JSON "
            "(nodes + adjacent / proximity / bind edges); "
            "draw bind-chain check figure (no circle attach)"
        )
    )
    parser.add_argument("--stem", type=str, default=CFG.default_stem)
    parser.add_argument(
        "--text-json",
        type=str,
        default="",
        help="override path to text export JSON (default: root {stem}-文字.json)",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="",
        help="directory of export JSON when --text-json omitted (default: repo root)",
    )
    parser.add_argument(
        "--corridor-json",
        type=str,
        default="",
        help="optional corridor geometry JSON for bind-chain figure",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="override product directory (default: step1a/output)",
    )
    parser.add_argument(
        "--no-png",
        action="store_true",
        help="skip bind_chains verification PNG",
    )
    args = parser.parse_args()
    out = args.output_dir or None
    in_dir = args.input_dir or None

    text_path = (
        Path(args.text_json)
        if args.text_json
        else exported_json_path(args.stem, "text", base_dir=in_dir)
    )
    if not text_path.is_file():
        raise FileNotFoundError(
            f"text export not found: {text_path} "
            f"(run: python utils/entity_export.py --mode text)"
        )

    graph = build_retrieved_elements_graph(
        stem=args.stem,
        template_layer=CFG.template_layer,
        adjacency_radius_norm=CFG.adjacency_radius_norm,
        fallback_char_height=CFG.fallback_char_height,
        text_json_path=text_path,
    )
    graph.graph["step1a_config"] = CFG.to_json()

    out_pkl = retrieved_elements_graph_pkl(args.stem, out)
    out_json = retrieved_elements_graph_json(args.stem, out)
    save_graph(graph, out_pkl, out_json)

    print(f"stem: {args.stem}")
    print(f"input_text_json: {text_path}")
    print(f"output_pkl: {out_pkl}")
    print(f"nodes: {graph.number_of_nodes()}")
    print(f"excluded_layer_skipped: {graph.graph.get('excluded_layer_skipped')}")
    print(f"adjacent_edges: {graph.graph.get('adjacency_edge_count')}")
    print(f"text_proximity_edges: {graph.graph.get('text_proximity_edge_count')}")
    print(f"text_parallel_edges: {graph.graph.get('text_parallel_edge_count')}")
    print(f"bind_edges: {graph.graph.get('bind_edge_count')}")
    print(f"bind_groups: {graph.graph.get('bind_group_count')}")
    print(f"bind_line_bridges: {graph.graph.get('bind_line_bridge_count')}")
    print(f"bind_id_value_radius: {graph.graph.get('bind_id_value_radius')}")
    print(f"bind_value_value_radius: {graph.graph.get('bind_value_value_radius')}")
    print(f"bind_borehole_radius: {graph.graph.get('bind_borehole_radius')}")
    print(f"adjacency_radius: {graph.graph.get('adjacency_radius')}")

    if not args.no_png:
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

        out_png = bind_chains_png(args.stem, out)
        try:
            visualize_bind_chains(
                graph,
                out_png,
                corridors=corridors,
                title="bind_chains（测点字–值；钻孔同族联结）",
                cfg=CFG,
            )
            print(f"bind_chains_png: {out_png}")
        except Exception as exc:
            print(f"bind_chains visualize skipped: {exc}")


if __name__ == "__main__":
    main()
