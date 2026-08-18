"""Load and save topology graphs (pickle for pipeline, JSON for inspection)."""

from __future__ import annotations

import json
import pickle
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import networkx as nx

ReadableFn = Callable[[nx.Graph], dict[str, Any]]


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return str(value)


def edge_kind_counts(graph: nx.Graph) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for _, _, data in graph.edges(data=True):
        kind = data.get("edge_kind")
        if kind:
            counts[str(kind)] += 1
            continue
        kinds = data.get("edge_kinds") or []
        if not kinds:
            counts["unlabeled"] += 1
            continue
        for item in kinds:
            counts[str(item)] += 1
    return dict(sorted(counts.items()))


def default_readable_dict(graph: nx.Graph) -> dict[str, Any]:
    return {
        "graph": jsonable(dict(graph.graph)),
        "summary": {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "edge_kind_counts": edge_kind_counts(graph),
        },
    }


def save_graph(
    graph: nx.Graph,
    pkl_path: Path,
    json_path: Path,
    *,
    to_readable: ReadableFn | None = None,
) -> None:
    pkl_path.parent.mkdir(parents=True, exist_ok=True)
    with open(pkl_path, "wb") as f:
        pickle.dump(graph, f)
    readable = (to_readable or default_readable_dict)(graph)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(readable, f, ensure_ascii=False, indent=2)


def load_graph(pkl_path: Path) -> nx.Graph:
    with open(pkl_path, "rb") as f:
        graph = pickle.load(f)
    if not isinstance(graph, nx.Graph):
        raise TypeError(f"input must be a NetworkX undirected graph: {pkl_path}")
    return graph


def save_json_doc(data: Any, json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(jsonable(data), f, ensure_ascii=False, indent=2)


def load_json_doc(json_path: Path) -> Any:
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)
