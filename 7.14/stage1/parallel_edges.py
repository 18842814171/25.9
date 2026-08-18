"""Helper: add parallel edges between text annotations."""

from __future__ import annotations

import math

import networkx as nx


def is_text_node(data: dict) -> bool:
    return data.get("entity_type") in {"TEXT", "MTEXT"}


def angle_difference_deg(a: float, b: float) -> float:
    diff = abs(a - b) % 180.0
    if diff > 90.0:
        diff = 180.0 - diff
    return diff


def pair_distance(a: dict, b: dict) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def add_parallel_edges(
    graph: nx.Graph,
    angle_tolerance: float,
    max_distance: float,
) -> int:
    texts = [
        nid
        for nid, data in graph.nodes(data=True)
        if data.get("node_kind") == "annotation" and is_text_node(data)
    ]
    added = 0
    for i, na in enumerate(texts):
        da = graph.nodes[na]
        for nb in texts[i + 1 :]:
            db = graph.nodes[nb]
            dist = pair_distance(da, db)
            if dist > max_distance:
                continue
            if angle_difference_deg(float(da["rotation"]), float(db["rotation"])) > angle_tolerance:
                continue
            if graph.has_edge(na, nb):
                edge = graph.edges[na, nb]
                kinds = set(edge.get("edge_kinds", []))
                if "parallel" in kinds:
                    continue
                kinds.add("parallel")
                edge["edge_kinds"] = sorted(kinds)
                if "distance" not in edge:
                    edge["distance"] = dist
            else:
                graph.add_edge(na, nb, edge_kinds=["parallel"], distance=dist)
            added += 1
    return added
