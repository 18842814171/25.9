"""Cluster facility primitives (endpoint components) into facility instances."""

from __future__ import annotations

from collections import Counter
from typing import Any

import networkx as nx

from config import Stage2Config
from endpoint_connect import connected_primitive_components

DEFAULT_FACILITY_TYPE = "通风设施"


def fingerprint_from_members(members: list[dict]) -> dict[str, Any]:
    type_hist = Counter(str(m.get("entity_type") or "") for m in members)
    blocks = sorted(
        {
            str(m["block_name"])
            for m in members
            if m.get("entity_type") == "INSERT" and m.get("block_name")
        }
    )
    sizes = [float(m.get("size") or 0.0) for m in members if float(m.get("size") or 0.0) > 0]
    lengths = [
        float(m.get("length") or 0.0) for m in members if float(m.get("length") or 0.0) > 0
    ]
    texts = sorted(
        {
            str(m.get("text") or "").strip()
            for m in members
            if m.get("entity_type") in {"TEXT", "MTEXT"} and str(m.get("text") or "").strip()
        }
    )
    sizes_sorted = sorted(sizes)
    lengths_sorted = sorted(lengths)
    med_size = sizes_sorted[len(sizes_sorted) // 2] if sizes_sorted else 0.0
    med_len = lengths_sorted[len(lengths_sorted) // 2] if lengths_sorted else 0.0
    xs = [float(m["x"]) for m in members if m.get("x") is not None]
    ys = [float(m["y"]) for m in members if m.get("y") is not None]
    cx = sum(xs) / len(xs) if xs else None
    cy = sum(ys) / len(ys) if ys else None
    if xs and ys:
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        long_side = max(bw, bh)
        short_side = min(bw, bh)
        if long_side <= 1e-9:
            aspect = 1.0
            bbox_long = med_size
        else:
            aspect = float(max(short_side, long_side * 0.05) / long_side)
            bbox_long = float(long_side)
    else:
        aspect = 1.0
        bbox_long = med_size
    if lengths_sorted and med_len > 1e-9:
        length_spectrum = [round(L / med_len, 3) for L in lengths_sorted]
    else:
        length_spectrum = []
    return {
        "type_hist": dict(sorted(type_hist.items())),
        "block_names": blocks,
        "median_size": med_size,
        "median_length": med_len,
        "aspect_ratio": aspect,
        "bbox_long": bbox_long,
        "length_spectrum": length_spectrum,
        "texts": texts,
        "member_count": len(members),
        "x": cx,
        "y": cy,
    }


def build_facility_graph(
    primitives_graph: nx.Graph,
    cfg: Stage2Config,
) -> nx.Graph:
    median_h = float(
        primitives_graph.graph.get("median_char_height") or cfg.fallback_char_height
    )
    med_fac = primitives_graph.graph.get("median_facility_size")
    facility_type = DEFAULT_FACILITY_TYPE

    graph = nx.Graph()
    graph.graph.update(
        {
            "graph_name": "facility_graph",
            "stem": primitives_graph.graph.get("stem"),
            "source_dxf": primitives_graph.graph.get("source_dxf"),
            "facility_layer": cfg.facility_layer,
            "median_char_height": median_h,
            "median_facility_size": med_fac,
            "endpoint_join_tol": primitives_graph.graph.get("endpoint_join_tol"),
            "cluster_mode": "endpoint_components",
            "stage2_config": cfg.to_json(),
        }
    )

    for nid, data in primitives_graph.nodes(data=True):
        if data.get("node_kind") != "primitive":
            continue
        if data.get("layer") != cfg.facility_layer:
            continue
        graph.add_node(str(nid), **dict(data))

    for u, v, edata in primitives_graph.edges(data=True):
        if u not in graph or v not in graph:
            continue
        kind = edata.get("edge_kind")
        if kind in {"endpoint-join", "orphan-near"}:
            graph.add_edge(u, v, **dict(edata))

    clusters = connected_primitive_components(graph, layer=cfg.facility_layer)
    expanded: list[list[dict]] = []
    for members in clusters:
        if len(members) > cfg.max_cluster_members:
            for m in members:
                expanded.append([m])
        else:
            expanded.append(members)
    clusters = expanded

    type_counts: Counter[str] = Counter()
    for idx, members in enumerate(clusters):
        fp = fingerprint_from_members(members)
        fid = f"facility_{idx:04d}"
        member_ids = [str(m["id"]) for m in members]
        graph.add_node(
            fid,
            node_kind="facility",
            facility_type=facility_type,
            member_ids=member_ids,
            block_names=list(fp.get("block_names") or []),
            type_hist=dict(fp.get("type_hist") or {}),
            aspect_ratio=float(fp.get("aspect_ratio") or 1.0),
            median_size=float(fp.get("median_size") or 0.0),
            x=fp.get("x"),
            y=fp.get("y"),
            label_text=facility_type,
            text=facility_type,
            attach_kind=facility_type,
        )
        for mid in member_ids:
            if mid in graph:
                graph.nodes[mid]["facility_id"] = fid
                graph.nodes[mid]["facility_type"] = facility_type
                graph.add_edge(fid, mid, edge_kind="member", edge_kinds=["member"])
        type_counts[facility_type] += 1

    graph.graph["facility_summary"] = {
        "facility_count": sum(type_counts.values()),
        "by_type": dict(sorted(type_counts.items())),
    }
    return graph
