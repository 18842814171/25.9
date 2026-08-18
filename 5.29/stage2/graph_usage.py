"""
Segment usage labels derived from merged wall_lines + endpoint graph nodes.
"""

from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np


def collect_used_handles(wall_lines: list[dict[str, Any]]) -> set[str]:
  """DXF handles absorbed into continuous wall lines (sources + bridge arcs)."""
  used: set[str] = set()
  for wall in wall_lines:
    used.update(str(h) for h in wall.get("source_handles", []))
    used.update(str(h) for h in wall.get("arc_handles", []))
  return used


def normalize_graph_segment(data: dict[str, Any]) -> dict[str, Any]:
  """Ensure ndarray fields on a graph node segment record."""
  row = dict(data)
  for key in ("start", "end", "direction", "mid"):
    if key in row and row[key] is not None:
      row[key] = np.asarray(row[key], dtype=float)[:2]
  if "endpoints" in row:
    row["endpoints"] = [
      np.asarray(p, dtype=float)[:2] for p in row["endpoints"]
    ]
  elif "start" in row and "end" in row:
    row["endpoints"] = [row["start"], row["end"]]
  if "mid" not in row and "start" in row and "end" in row:
    row["mid"] = (row["start"] + row["end"]) / 2.0
  return row


def info_list_from_endpoint_graph(graph: nx.Graph) -> list[dict[str, Any]]:
  """Rebuild indexed segment list aligned with graph node ids."""
  if not graph.nodes:
    return []
  max_id = max(int(nid) for nid in graph.nodes)
  info: list[dict[str, Any] | None] = [None] * (max_id + 1)
  for nid, data in graph.nodes(data=True):
    info[int(nid)] = normalize_graph_segment(data)
  missing = [i for i, row in enumerate(info) if row is None]
  if missing:
    raise ValueError(f"endpoint graph node ids not contiguous: missing {missing[:5]}")
  return info  # type: ignore[return-value]


def unused_handles(graph: nx.Graph, used_handles: set[str]) -> set[str]:
  return {
    str(data["handle"])
    for _, data in graph.nodes(data=True)
    if str(data["handle"]) not in used_handles
  }


def segment_info_by_handle(
  graph: nx.Graph,
  used_handles: set[str],
) -> dict[str, dict[str, Any]]:
  """Unused segment records keyed by DXF handle."""
  by_handle: dict[str, dict[str, Any]] = {}
  for _, data in graph.nodes(data=True):
    handle = str(data["handle"])
    if handle in used_handles:
      continue
    by_handle[handle] = normalize_graph_segment(data)
  return by_handle


def isolated_stubs_from_graph(
  graph: nx.Graph,
  wall_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  """Unused endpoint-graph nodes as stub records (same layout as isolated_stubs.json)."""
  used = collect_used_handles(wall_lines)
  stubs: list[dict[str, Any]] = []
  for _, data in graph.nodes(data=True):
    handle = str(data["handle"])
    if handle in used:
      continue
    geo = str(data.get("geo_type", "line")).lower()
    row: dict[str, Any] = {
      "handle": handle,
      "type": "ARC" if geo == "arc" else "LINE",
      "attributes": {
        "start": [float(data["start"][0]), float(data["start"][1]), 0.0],
        "end": [float(data["end"][0]), float(data["end"][1]), 0.0],
      },
    }
    if data.get("layer") is not None:
      row["layer"] = data["layer"]
    stubs.append(row)
  return stubs
