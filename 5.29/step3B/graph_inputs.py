"""Load geometry from parallel_graph.pkl for residual_graph construction."""

from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np


def _seg_from_parallel_node(node_id: str, data: dict[str, Any]) -> dict[str, Any]:
  start = np.asarray(data["start"], dtype=float)[:2]
  end = np.asarray(data["end"], dtype=float)[:2]
  direction = np.asarray(data.get("direction") or [1.0, 0.0], dtype=float)[:2]
  return {
    "node_id": str(node_id),
    "node_type": str(data.get("node_type", "")),
    "start": start,
    "end": end,
    "mid": (start + end) / 2.0,
    "length": float(data.get("length", 0.0)),
    "direction": direction,
    "endpoints": [start, end],
  }


def wall_index_from_graph(graph: nx.Graph) -> dict[str, dict[str, Any]]:
  index: dict[str, dict[str, Any]] = {}
  for nid, data in graph.nodes(data=True):
    if data.get("node_type") != "wall":
      continue
    index[str(nid)] = _seg_from_parallel_node(str(nid), data)
  return index


def stub_segments_from_graph(graph: nx.Graph) -> dict[str, dict[str, Any]]:
  segs: dict[str, dict[str, Any]] = {}
  for nid, data in graph.nodes(data=True):
    if data.get("node_type") != "stub":
      continue
    segs[str(nid)] = _seg_from_parallel_node(str(nid), data)
  return segs


def geometry_docs_from_graph(
  graph: nx.Graph,
) -> tuple[dict[str, Any], dict[str, Any]]:
  """Build wall/residual geometry dicts for visualization."""
  walls: list[dict[str, Any]] = []
  elements: list[dict[str, Any]] = []
  for nid, data in graph.nodes(data=True):
    node_type = str(data.get("node_type", ""))
    row = {
      "attributes": {
        "start": list(data.get("start") or [0.0, 0.0, 0.0]),
        "end": list(data.get("end") or [0.0, 0.0, 0.0]),
      },
    }
    if node_type == "wall":
      row["wall_segment_id"] = str(nid)
      walls.append(row)
    elif node_type == "stub":
      row["handle"] = str(data.get("handle") or nid)
      row["type"] = "LINE"
      elements.append(row)
  return {"walls": walls}, {"elements": elements}


def load_from_parallel_graph(parallel_graph: nx.Graph) -> dict[str, Any]:
  """Geometry inputs for residual_graph construction (parallel_graph only)."""
  wall_doc, residual_doc = geometry_docs_from_graph(parallel_graph)
  return {
    "stub_segments": stub_segments_from_graph(parallel_graph),
    "wall_index": wall_index_from_graph(parallel_graph),
    "wall_doc": wall_doc,
    "residual_doc": residual_doc,
  }
