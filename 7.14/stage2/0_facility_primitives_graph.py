"""Script 0: `{stem}-设施.json` → facility_primitives_graph.

Requires root facility export from utils/entity_export.py --mode facility.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import networkx as nx

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.entity_json import exported_json_path, load_facility_records

from config import (
    Stage2Config,
    facility_primitives_graph_json,
    facility_primitives_graph_pkl,
)
from dxf_primitives import median_char_height, median_facility_size
from endpoint_connect import add_endpoint_join_edges
from graph_io import save_graph

CFG = Stage2Config()


def _join_tolerances(med_size: float | None, med_h: float) -> tuple[float, float]:
    base = float(med_size) if med_size is not None and float(med_size) > 0 else float(med_h)
    join_tol = max(
        base * float(CFG.endpoint_join_tol_factor),
        float(CFG.endpoint_join_tol_floor),
    )
    orphan_tol = max(
        base * float(CFG.orphan_near_tol_factor),
        float(CFG.orphan_near_tol_floor),
    )
    return join_tol, orphan_tol


def build_primitives_graph(
    primitives: list[dict],
    stem: str,
    *,
    source_facility_json: str = "",
) -> nx.Graph:
    graph = nx.Graph()
    med_h = median_char_height(primitives, CFG)
    med_size = median_facility_size(primitives, CFG.facility_layer)
    join_tol, orphan_tol = _join_tolerances(med_size, med_h)
    type_counts = Counter(p["entity_type"] for p in primitives)
    layer_counts = Counter(p["layer"] for p in primitives)
    graph.graph.update(
        {
            "graph_name": "facility_primitives_graph",
            "stem": stem,
            "source_facility_json": source_facility_json,
            "facility_layer": CFG.facility_layer,
            "template_layer": CFG.template_layer,
            "median_char_height": med_h,
            "median_facility_size": med_size,
            "endpoint_join_tol": join_tol,
            "orphan_near_tol": orphan_tol,
            "entity_type_counts": dict(sorted(type_counts.items())),
            "layer_counts": dict(sorted(layer_counts.items())),
            "stage2_config": CFG.to_json(),
        }
    )
    for p in primitives:
        nid = str(p["id"])
        graph.add_node(
            nid,
            node_kind="primitive",
            id=nid,
            entity_type=p.get("entity_type"),
            layer=p.get("layer"),
            text=p.get("text"),
            x=p.get("x"),
            y=p.get("y"),
            char_height=p.get("char_height"),
            rotation=p.get("rotation"),
            radius=p.get("radius"),
            block_name=p.get("block_name"),
            length=p.get("length"),
            size=p.get("size"),
            vertex_count=p.get("vertex_count"),
            closed=p.get("closed"),
            pattern_name=p.get("pattern_name"),
            scale_x=p.get("scale_x"),
            scale_y=p.get("scale_y"),
            endpoints=list(p.get("endpoints") or []),
            path_points=list(p.get("path_points") or []),
            arc_start_angle=p.get("arc_start_angle"),
            arc_end_angle=p.get("arc_end_angle"),
        )
    edge_stats = add_endpoint_join_edges(
        graph, join_tol=join_tol, orphan_tol=orphan_tol
    )
    graph.graph["endpoint_edge_stats"] = edge_stats
    return graph


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build facility primitives graph from facility export JSON"
    )
    parser.add_argument("--stem", type=str, default=CFG.default_stem)
    parser.add_argument(
        "--facility-json",
        type=str,
        default="",
        help="override path to facility export JSON (default: root {stem}-设施.json)",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="",
        help="directory of export JSON when --facility-json omitted",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="override product directory (default: stage2/output)",
    )
    args = parser.parse_args()
    out = args.output_dir or None
    in_dir = args.input_dir or None

    facility_path = (
        Path(args.facility_json)
        if args.facility_json
        else exported_json_path(args.stem, "facility", base_dir=in_dir)
    )
    if not facility_path.is_file():
        raise FileNotFoundError(
            f"facility export not found: {facility_path} "
            f"(run: python utils/entity_export.py --mode facility)"
        )

    layers = [CFG.facility_layer]
    primitives, _ = load_facility_records(
        args.stem,
        path=facility_path,
        types=CFG.primitive_entity_types,
        layers=layers,
    )
    graph = build_primitives_graph(
        primitives,
        args.stem,
        source_facility_json=str(facility_path.as_posix()),
    )

    out_pkl = facility_primitives_graph_pkl(args.stem, out)
    out_json = facility_primitives_graph_json(args.stem, out)
    save_graph(graph, out_pkl, out_json)

    print(f"stem: {args.stem}")
    print(f"input_facility_json: {facility_path}")
    print(f"output_pkl: {out_pkl}")
    print(f"nodes: {graph.number_of_nodes()}")
    print(f"median_char_height: {graph.graph.get('median_char_height')}")
    print(f"median_facility_size: {graph.graph.get('median_facility_size')}")
    print(f"endpoint_join_tol: {graph.graph.get('endpoint_join_tol')}")
    print(f"orphan_near_tol: {graph.graph.get('orphan_near_tol')}")
    print(f"endpoint_edge_stats: {graph.graph.get('endpoint_edge_stats')}")
    print(f"entity_type_counts: {graph.graph.get('entity_type_counts')}")
    print(f"layer_counts: {graph.graph.get('layer_counts')}")


if __name__ == "__main__":
    main()
