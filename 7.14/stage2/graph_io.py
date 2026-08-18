"""stage2 graph I/O: stage-specific readable summary over shared utils.graph_io."""

from __future__ import annotations

import sys
from collections import Counter
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

__all__ = [
    "load_graph",
    "save_graph",
    "save_json_doc",
    "load_json_doc",
    "graph_to_readable_dict",
]


def _node_kind_counts(graph: nx.Graph) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for _, data in graph.nodes(data=True):
        if data.get("node_type") == "centerline":
            counts["centerline"] += 1
        elif data.get("node_type") == "structure":
            counts["structure"] += 1
        elif data.get("node_kind") == "facility":
            counts[f"facility:{data.get('facility_type') or 'other'}"] += 1
        elif data.get("node_kind") == "primitive":
            counts[f"primitive:{data.get('entity_type') or 'other'}"] += 1
        elif data.get("node_kind") == "cluster":
            counts[f"cluster:{data.get('cluster_type') or 'other'}"] += 1
        elif data.get("node_kind") == "annotation":
            key = str(data.get("attach_kind") or data.get("entity_type") or "annotation")
            counts[f"annotation:{key}"] += 1
        else:
            counts["other"] += 1
    return dict(sorted(counts.items()))


def graph_to_readable_dict(graph: nx.Graph) -> dict[str, Any]:
    facilities = []
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "facility":
            continue
        facilities.append(
            jsonable(
                {
                    "id": str(nid),
                    "facility_type": data.get("facility_type"),
                    "x": data.get("x"),
                    "y": data.get("y"),
                    "member_ids": data.get("member_ids"),
                    "block_names": data.get("block_names"),
                    "confidence": data.get("confidence"),
                    "attach_status": data.get("attach_status"),
                    "attached_centerline_id": data.get("attached_centerline_id"),
                }
            )
        )
    facilities.sort(key=lambda row: (str(row.get("facility_type")), str(row.get("id"))))
    return {
        "graph": jsonable(dict(graph.graph)),
        "summary": {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "node_kind_counts": _node_kind_counts(graph),
            "edge_kind_counts": edge_kind_counts(graph),
        },
        "facilities": facilities,
    }


def save_graph(graph: nx.Graph, pkl_path: Path, json_path: Path) -> None:
    _save_graph(graph, pkl_path, json_path, to_readable=graph_to_readable_dict)
