"""Script 1: `{stem}-图例.json` → facility_templates.json (endpoint components)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import networkx as nx

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.entity_json import exported_json_path, load_legend_facility_records
from utils.stats import median_char_height as _median_char_height

from cluster_facilities import (
    collect_legend_seeds,
    fingerprint_from_members,
    legend_symbol_members,
)
from config import Stage2Config, facility_templates_json
from dxf_primitives import median_facility_size
from endpoint_connect import add_endpoint_join_edges
from graph_io import save_json_doc

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


def build_legend_graph(primitives: list[dict], stem: str) -> nx.Graph:
    """Build a temporary endpoint-join graph from legend-only primitives."""
    graph = nx.Graph()
    med_h = _median_char_height(primitives, fallback=float(CFG.fallback_char_height))
    med_size = median_facility_size(primitives, CFG.template_layer)
    join_tol, orphan_tol = _join_tolerances(med_size, med_h)
    graph.graph.update(
        {
            "graph_name": "legend_primitives_graph",
            "stem": stem,
            "template_layer": CFG.template_layer,
            "facility_layer": CFG.facility_layer,
            "median_char_height": med_h,
            "median_facility_size": med_size,
            "endpoint_join_tol": join_tol,
            "orphan_near_tol": orphan_tol,
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
    add_endpoint_join_edges(graph, join_tol=join_tol, orphan_tol=orphan_tol)
    return graph


def extract_templates(graph: nx.Graph) -> dict:
    primitives = [
        dict(data)
        for _, data in graph.nodes(data=True)
        if data.get("node_kind") == "primitive"
    ]
    median_h = float(graph.graph.get("median_char_height") or CFG.fallback_char_height)
    med_fac = graph.graph.get("median_facility_size")
    probe = median_h * float(CFG.template_probe_norm)
    if med_fac is not None and float(med_fac) > 0:
        size_cap = max(
            float(med_fac) * float(CFG.template_symbol_size_cap_factor),
            median_h * float(CFG.template_symbol_size_cap_norm),
        )
    else:
        size_cap = median_h * float(CFG.template_symbol_size_cap_norm)
    seeds = collect_legend_seeds(primitives, CFG)
    seeds_ordered = sorted(
        seeds,
        key=lambda s: (float(s.get("x") or 0.0), float(s.get("y") or 0.0), str(s.get("id"))),
    )

    templates = []
    claimed: set[str] = set()
    for seed in seeds_ordered:
        sx, sy = float(seed["x"]), float(seed["y"])
        near = legend_symbol_members(
            graph,
            seed,
            probe=probe,
            size_cap=size_cap,
            cfg=CFG,
            exclude_ids=claimed,
        )
        if not near:
            templates.append(
                {
                    "facility_type": seed["facility_type"],
                    "caption_id": seed.get("id"),
                    "caption_text": seed.get("text"),
                    "caption_xy": [sx, sy],
                    "member_count": 0,
                    "type_hist": {},
                    "block_names": [],
                    "median_size": 0.0,
                    "median_length": 0.0,
                    "aspect_ratio": 1.0,
                    "texts": [],
                    "note": "no_nearby_endpoint_component",
                }
            )
            continue
        for m in near:
            claimed.add(str(m["id"]))
        fp = fingerprint_from_members(near)
        templates.append(
            {
                "facility_type": seed["facility_type"],
                "caption_id": seed.get("id"),
                "caption_text": seed.get("text"),
                "caption_xy": [sx, sy],
                "member_ids": [str(m["id"]) for m in near],
                **fp,
            }
        )

    merged: dict[str, dict] = {}
    for tmpl in templates:
        ftype = str(tmpl["facility_type"])
        if ftype not in merged:
            merged[ftype] = dict(tmpl)
            continue
        old = merged[ftype]
        blocks = sorted(set(old.get("block_names") or []) | set(tmpl.get("block_names") or []))
        hist: dict[str, int] = dict(old.get("type_hist") or {})
        for k, v in (tmpl.get("type_hist") or {}).items():
            hist[k] = max(int(hist.get(k, 0)), int(v))
        sizes = [
            float(old.get("median_size") or 0.0),
            float(tmpl.get("median_size") or 0.0),
        ]
        sizes = [s for s in sizes if s > 0]
        aspects = [
            float(old.get("aspect_ratio") or 0.0),
            float(tmpl.get("aspect_ratio") or 0.0),
        ]
        aspects = [a for a in aspects if a > 0]
        old["block_names"] = blocks
        old["type_hist"] = dict(sorted(hist.items()))
        old["median_size"] = sorted(sizes)[len(sizes) // 2] if sizes else 0.0
        old["aspect_ratio"] = sorted(aspects)[len(aspects) // 2] if aspects else 1.0
        old["member_count"] = int(old.get("member_count") or 0) + int(
            tmpl.get("member_count") or 0
        )
        merged[ftype] = old

    return {
        "stem": graph.graph.get("stem"),
        "median_char_height": median_h,
        "template_probe": probe,
        "symbol_size_cap": size_cap,
        "seed_count": len(seeds),
        "rotation_invariant": True,
        "templates": list(merged.values()),
        "raw_templates": templates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract facility legend templates from `{stem}-图例.json`"
    )
    parser.add_argument("--stem", type=str, default=CFG.default_stem)
    parser.add_argument(
        "--legend-json",
        type=str,
        default="",
        help="override path to legend export JSON",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="",
        help="directory of export JSON when --legend-json omitted",
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

    legend_path = (
        Path(args.legend_json)
        if args.legend_json
        else exported_json_path(args.stem, "legend", base_dir=in_dir)
    )
    primitives, source_path = load_legend_facility_records(
        args.stem,
        path=legend_path,
        types=CFG.primitive_entity_types,
    )
    if not primitives:
        raise RuntimeError(f"no legend primitives in {source_path}")

    graph = build_legend_graph(primitives, args.stem)
    doc = extract_templates(graph)
    doc["source_legend_json"] = str(source_path.as_posix())
    out_path = facility_templates_json(args.stem, out)
    save_json_doc(doc, out_path)

    print(f"stem: {args.stem}")
    print(f"input: {source_path}")
    print(f"output: {out_path}")
    print(f"seeds: {doc['seed_count']}")
    for tmpl in doc["templates"]:
        print(
            f"  {tmpl['facility_type']}: members={tmpl.get('member_count')} "
            f"blocks={tmpl.get('block_names')} hist={tmpl.get('type_hist')} "
            f"med_size={tmpl.get('median_size')} aspect={tmpl.get('aspect_ratio')}"
        )


if __name__ == "__main__":
    main()
