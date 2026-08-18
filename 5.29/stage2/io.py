from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import networkx as nx


def load_json(path: Path) -> Any:
  with path.open("r", encoding="utf-8") as f:
    return json.load(f)


def save_json(data: Any, path: Path) -> Path:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
  return path


def load_graph(path: Path) -> nx.Graph | nx.MultiDiGraph:
  with path.open("rb") as f:
    obj = pickle.load(f)
  if isinstance(obj, (nx.Graph, nx.MultiDiGraph)):
    return obj
  if isinstance(obj, dict) and "graph" in obj:
    g = obj["graph"]
    if isinstance(g, (nx.Graph, nx.MultiDiGraph)):
      return g
  raise ValueError(f"Expected NetworkX graph in {path}, got {type(obj)!r}")


def save_graph(graph: nx.Graph | nx.MultiDiGraph, path: Path) -> Path:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("wb") as f:
    pickle.dump(graph, f)
  return path


def _json_safe(value: Any) -> Any:
  if isinstance(value, (str, int, float, bool)) or value is None:
    return value
  if isinstance(value, (list, tuple)):
    return [_json_safe(v) for v in value]
  if isinstance(value, dict):
    return {str(k): _json_safe(v) for k, v in value.items()}
  return str(value)


ENDPOINT_GRAPH_SCHEMA_VERSION = 3
ENDPOINT_NODE_DROP_KEYS = frozenset({"mid"})
ENDPOINT_NODE_KEEP_KEYS = frozenset({"bend_ids"})
ENDPOINT_EDGE_KEYS = frozenset({
  "edge_kind",
  "endpoint_gap",
  "angle_deg",
  "is_shared",
  "is_para",
  "is_ortho",
  "is_bend",
  "bend_id",
  "deflection_deg",
  "endpoint_cluster_id",
})


def endpoint_graph_to_storage(graph: nx.Graph) -> nx.Graph:
  """Copy endpoint graph with canonical node/edge fields for persistence."""
  stored = graph.copy()
  stored.graph = dict(graph.graph)
  for nid in stored.nodes:
    for key in ENDPOINT_NODE_DROP_KEYS:
      stored.nodes[nid].pop(key, None)
  for u, v, data in stored.edges(data=True):
    if data.get("edge_kind") != "endpoint":
      continue
    for key in list(data.keys()):
      if key not in ENDPOINT_EDGE_KEYS:
        del data[key]
  return stored


def graph_to_read_json(graph: nx.Graph | nx.MultiDiGraph) -> dict[str, Any]:
  """Serializable graph snapshot for human inspection (not used as pipeline input)."""
  nodes = []
  for nid, data in graph.nodes(data=True):
    nodes.append({"id": str(nid), **_json_safe(dict(data))})
  edges = []
  if isinstance(graph, nx.MultiDiGraph):
    for u, v, key, data in graph.edges(keys=True, data=True):
      edges.append({
        "source": str(u),
        "target": str(v),
        "key": str(key),
        **_json_safe(dict(data)),
      })
  else:
    for u, v, data in graph.edges(data=True):
      edges.append({"source": str(u), "target": str(v), **_json_safe(dict(data))})
  doc: dict[str, Any] = {
    "kind": graph.graph.get("kind"),
    "nodes": nodes,
    "edges": edges,
  }
  if graph.graph.get("bend_markers"):
    doc["bend_markers"] = _json_safe(graph.graph["bend_markers"])
  if graph.graph.get("corners"):
    doc["corners"] = _json_safe(graph.graph["corners"])
  if graph.graph.get("endpoint_clusters"):
    doc["endpoint_clusters"] = _json_safe(graph.graph["endpoint_clusters"])
  return doc


def endpoint_graph_to_json(graph: nx.Graph) -> dict[str, Any]:
  """Canonical endpoint-graph JSON (schema_version 2)."""
  doc = graph_to_read_json(endpoint_graph_to_storage(graph))
  doc["schema_version"] = ENDPOINT_GRAPH_SCHEMA_VERSION
  return doc


def corridor_json_path_for_pkl(pkl_path: Path) -> Path:
  stem = pkl_path.stem
  if stem.endswith("_corridor_graph"):
    stem = stem[: -len("_corridor_graph")]
  return pkl_path.with_name(f"{stem}_corridors.json")


def context_json_path_for_pkl(pkl_path: Path) -> Path:
  stem = pkl_path.stem
  if stem.endswith("_context_graph"):
    stem = stem[: -len("_context_graph")]
  return pkl_path.with_name(f"{stem}_context.json")


def hetero_json_path_for_pkl(pkl_path: Path) -> Path:
  stem = pkl_path.stem
  if stem.endswith("_hetero_graph"):
    stem = stem[: -len("_hetero_graph")]
  return pkl_path.with_name(f"{stem}_hetero.json")


def semantic_json_path_for_pkl(pkl_path: Path) -> Path:
  stem = pkl_path.stem
  if stem.endswith("_semantic_graph"):
    stem = stem[: -len("_semantic_graph")]
  return pkl_path.with_name(f"{stem}_semantic.json")
