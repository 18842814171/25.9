"""step1a graph I/O: stage-specific readable summary over shared utils.graph_io."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import networkx as nx

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.graph_io import (
    edge_kind_counts,
    jsonable,
    load_graph,
    load_json_doc,
    save_graph as _save_graph,
    save_json_doc,
)

# Re-export shared names expected by local scripts.
__all__ = [
    "load_graph",
    "save_graph",
    "save_json_doc",
    "load_json_doc",
    "graph_to_readable_dict",
]


def _member_row(nid: str, data: dict) -> dict[str, Any]:
    return jsonable(
        {
            "id": str(nid),
            "shape_type": data.get("shape_type"),
            "layer": data.get("layer"),
            "text": data.get("text"),
            "role": data.get("role"),
            "x": data.get("x"),
            "y": data.get("y"),
            "char_height": data.get("char_height"),
            "rotation": data.get("rotation"),
            "radius": data.get("radius"),
            "block_name": data.get("block_name"),
            "cluster_type": data.get("cluster_type"),
            "confidence": data.get("confidence"),
            "candidate_cluster_ids": data.get("candidate_cluster_ids"),
            "bind_group_id": data.get("bind_group_id"),
            "bind_value_ids": data.get("bind_value_ids"),
            "bind_id_ids": data.get("bind_id_ids"),
            "score_layer": data.get("score_layer"),
            "score_distance": data.get("score_distance"),
            "score_orientation": data.get("score_orientation"),
            "score_total": data.get("score_total"),
        }
    )


def _groups_by_cluster_type(graph: nx.Graph) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    cluster_nodes = [
        (nid, data)
        for nid, data in graph.nodes(data=True)
        if data.get("node_kind") == "cluster"
    ]
    cluster_nodes.sort(key=lambda item: str(item[0]))
    for cid, cdata in cluster_nodes:
        cluster_type = str(cdata.get("cluster_type") or "other")
        members = []
        for mid in cdata.get("member_ids") or []:
            if mid not in graph.nodes:
                continue
            members.append(_member_row(str(mid), graph.nodes[mid]))
        groups.setdefault(cluster_type, []).append(
            {
                "cluster_id": str(cid),
                "anchor_id": cdata.get("anchor_id"),
                "member_count": len(members),
                "confidence": cdata.get("confidence"),
                "members": members,
            }
        )
    return groups


def _groups_by_shape_type(graph: nx.Graph) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        key = str(data.get("shape_type") or data.get("cluster_type") or "other")
        groups.setdefault(key, []).append(_member_row(str(nid), data))
    for key in groups:
        groups[key].sort(key=lambda row: str(row.get("id", "")))
    return dict(sorted(groups.items()))


def graph_to_readable_dict(graph: nx.Graph) -> dict[str, Any]:
    has_clusters = any(
        data.get("node_kind") == "cluster" for _, data in graph.nodes(data=True)
    )
    if has_clusters:
        grouping = "cluster_type"
        groups = _groups_by_cluster_type(graph)
    else:
        grouping = "shape_type"
        groups = _groups_by_shape_type(graph)
    type_counts = {k: len(v) for k, v in groups.items()}
    return {
        "graph": jsonable(dict(graph.graph)),
        "summary": {
            "grouping": grouping,
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "edge_kind_counts": edge_kind_counts(graph),
            "group_counts": type_counts,
        },
        "groups": groups,
    }


def save_graph(graph: nx.Graph, pkl_path: Path, json_path: Path) -> None:
    _save_graph(graph, pkl_path, json_path, to_readable=graph_to_readable_dict)
