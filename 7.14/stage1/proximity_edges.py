"""Helper: add distance-proximity edges."""

from __future__ import annotations

import math

import networkx as nx


def pair_distance(a: dict, b: dict) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def add_proximity_edges(graph: nx.Graph, max_distance: float) -> int:
    nodes = [nid for nid, data in graph.nodes(data=True) if data.get("node_kind") == "annotation"]
    added = 0
    for i, na in enumerate(nodes):
        da = graph.nodes[na]
        for nb in nodes[i + 1 :]:
            db = graph.nodes[nb]
            dist = pair_distance(da, db)
            if dist > max_distance:
                continue
            if graph.has_edge(na, nb):
                edge = graph.edges[na, nb]
                kinds = set(edge.get("edge_kinds", []))
                if "proximity" in kinds:
                    continue
                kinds.add("proximity")
                edge["edge_kinds"] = sorted(kinds)
                edge["distance"] = dist
            else:
                graph.add_edge(na, nb, edge_kinds=["proximity"], distance=dist)
            added += 1
    return added
