"""step1b graph I/O: stage-specific readable summary over shared utils.graph_io."""

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
    save_graph as _save_graph,
)

__all__ = ["load_graph", "save_graph", "graph_to_readable_dict"]


def _node_kind_counts(graph: nx.Graph) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for _, data in graph.nodes(data=True):
        if data.get("node_type") == "centerline":
            counts["centerline"] += 1
        elif data.get("node_type") == "structure":
            counts["structure"] += 1
        elif data.get("node_kind") == "cluster":
            counts[f"cluster:{data.get('cluster_type') or 'other'}"] += 1
        elif data.get("node_kind") == "annotation":
            key = str(data.get("attach_kind") or data.get("shape_type") or "annotation")
            counts[f"annotation:{key}"] += 1
        else:
            counts["other"] += 1
    return dict(sorted(counts.items()))


def _attachment_rows(graph: nx.Graph) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for u, v, data in graph.edges(data=True):
        if data.get("edge_kind") != "on-centerline":
            continue
        src = u
        dst = v
        if graph.nodes[u].get("node_type") == "centerline":
            src, dst = v, u
        src_data = graph.nodes[src]
        rows.append(
            jsonable(
                {
                    "source_id": str(src),
                    "centerline_id": str(dst),
                    "attach_kind": src_data.get("attach_kind")
                    or src_data.get("cluster_type")
                    or src_data.get("node_kind"),
                    "text": src_data.get("text") or src_data.get("label_text"),
                    "distance": data.get("distance"),
                    "t": data.get("t"),
                    "x": src_data.get("x"),
                    "y": src_data.get("y"),
                }
            )
        )
    rows.sort(key=lambda row: (str(row.get("attach_kind")), str(row.get("source_id"))))
    return rows


def graph_to_readable_dict(graph: nx.Graph) -> dict[str, Any]:
    return {
        "graph": jsonable(dict(graph.graph)),
        "summary": {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "node_kind_counts": _node_kind_counts(graph),
            "edge_kind_counts": edge_kind_counts(graph),
            "attachment_count": sum(
                1
                for _, _, d in graph.edges(data=True)
                if d.get("edge_kind") == "on-centerline"
            ),
        },
        "attachments": _attachment_rows(graph),
    }


def save_graph(graph: nx.Graph, pkl_path: Path, json_path: Path) -> None:
    _save_graph(graph, pkl_path, json_path, to_readable=graph_to_readable_dict)
