"""Logical endpoint + parallel graph over corridor candidate centerlines."""

from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np

from step2B.config import ParallelGraphConfig
from utils.centerline_graph import cand_wall_to_id_from_graph
from utils.segment_geometry import (
  acute_angle_deg,
  endpoint_gap,
  parallel_pair_ok,
  unit,
)


def _centerline_to_seg(cand: dict[str, Any]) -> dict[str, Any] | None:
  cl = cand.get("centerline") or {}
  start_raw = cl.get("start")
  end_raw = cl.get("end")
  if start_raw is None or end_raw is None:
    return None
  start = np.asarray(start_raw, dtype=float)[:2]
  end = np.asarray(end_raw, dtype=float)[:2]
  vec = end - start
  length = float(np.linalg.norm(vec))
  direction = unit(vec) if length >= 1e-12 else np.array([1.0, 0.0])
  cid = str(cand.get("corridor_id", ""))
  if not cid:
    return None
  cl = {
    "start": [round(float(start[0]), 4), round(float(start[1]), 4)],
    "end": [round(float(end[0]), 4), round(float(end[1]), 4)],
    "direction": [round(float(direction[0]), 6), round(float(direction[1]), 6)],
    "length": round(length, 4),
  }
  return {
    "node_id": cid,
    "node_type": "corridor",
    "start": start,
    "end": end,
    "mid": (start + end) / 2.0,
    "length": length,
    "direction": direction,
    "endpoints": [start, end],
    "width": float(cand.get("width", 0.0)),
    "corridor_length": float(cand.get("corridor_length", length)),
    "pair_id": str(cand.get("pair_id", "")),
    "left_wall_id": str(cand.get("left_wall_id", "")),
    "right_wall_id": str(cand.get("right_wall_id", "")),
    "centerline": cl,
    "overlap_ratio": float(cand.get("overlap_ratio", 0.0)),
    "confidence": float(cand.get("confidence", 0.0)),
  }


def segments_from_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
  segments: list[dict[str, Any]] = []
  for cand in candidates:
    seg = _centerline_to_seg(cand)
    if seg is not None:
      segments.append(seg)
  return segments


def _parallel_pair_ok(
  seg_a: dict[str, Any],
  seg_b: dict[str, Any],
  cfg: ParallelGraphConfig,
) -> tuple[bool, float, float]:
  return parallel_pair_ok(
    seg_a,
    seg_b,
    angle_th_deg=cfg.angle_th_deg,
    min_width=cfg.min_width,
    max_width=cfg.max_width,
    min_overlap_ratio=cfg.min_overlap_ratio,
  )


def build_centerline_graph(
  candidates: list[dict[str, Any]],
  cfg: ParallelGraphConfig | None = None,
) -> nx.Graph:
  """
  Build logical graph on corridor centerlines (same edge model as Step 2B).

  Nodes: corridor candidates (centerline segments).
  Edges:
    - endpoint: endpoint_gap, angle_deg, is_parallel, is_ortho
    - is_parallel / endpoint_parallel: width, overlap_ratio

  Note: all-pairs over candidates. Fine for part drawings (~tens–hundreds of
  corridors). Full-map scale (thousands) needs a spatial index — not yet.
  """
  cfg = cfg or ParallelGraphConfig()
  segments = segments_from_candidates(candidates)
  graph = nx.Graph()
  graph.graph["kind"] = "centerline_graph"
  graph.graph["schema_version"] = 2

  for seg in segments:
    graph.add_node(
      seg["node_id"],
      node_type=seg["node_type"],
      corridor_id=seg["node_id"],
      start=[float(seg["start"][0]), float(seg["start"][1])],
      end=[float(seg["end"][0]), float(seg["end"][1])],
      length=float(seg["length"]),
      corridor_length=float(seg["corridor_length"]),
      width=float(seg["width"]),
      direction=[float(seg["direction"][0]), float(seg["direction"][1])],
      pair_id=seg.get("pair_id", ""),
      left_wall_id=seg.get("left_wall_id", ""),
      right_wall_id=seg.get("right_wall_id", ""),
      centerline=seg.get("centerline"),
      overlap_ratio=float(seg.get("overlap_ratio", 0.0)),
      confidence=float(seg.get("confidence", 0.0)),
    )

  n = len(segments)
  for i in range(n):
    for j in range(i + 1, n):
      seg_a, seg_b = segments[i], segments[j]
      gap = endpoint_gap(seg_a, seg_b)
      if gap <= cfg.endpoint_link_gap:
        angle = acute_angle_deg(seg_a["direction"], seg_b["direction"])
        graph.add_edge(
          seg_a["node_id"],
          seg_b["node_id"],
          edge_kind="endpoint",
          endpoint_gap=round(gap, 4),
          angle_deg=round(angle, 4),
          is_parallel=angle < cfg.angle_th_deg,
          is_ortho=abs(angle - 90.0) < cfg.angle_th_deg,
        )

      ok, width, overlap = _parallel_pair_ok(seg_a, seg_b, cfg)
      if not ok:
        continue
      u, v = seg_a["node_id"], seg_b["node_id"]
      if graph.has_edge(u, v):
        graph[u][v]["edge_kind"] = "endpoint_parallel"
        graph[u][v]["is_parallel"] = True
        graph[u][v]["width"] = round(width, 4)
        graph[u][v]["overlap_ratio"] = round(overlap, 4)
      else:
        graph.add_edge(
          u,
          v,
          edge_kind="is_parallel",
          width=round(width, 4),
          overlap_ratio=round(overlap, 4),
          is_parallel=True,
        )

  return graph


def parallel_centerline_groups(graph: nx.Graph) -> list[list[str]]:
  """Connected components among corridor nodes linked by is_parallel."""
  para = nx.Graph()
  for node, data in graph.nodes(data=True):
    if data.get("node_type") == "corridor":
      para.add_node(node)
  for u, v, data in graph.edges(data=True):
    if not data.get("is_parallel"):
      continue
    if para.has_node(u) and para.has_node(v):
      para.add_edge(u, v)
  return [sorted(comp) for comp in nx.connected_components(para)]


def centerline_graph_summary(
  graph: nx.Graph,
  *,
  source_stem: str,
  cfg: ParallelGraphConfig,
  median_corridor_width: float | None = None,
) -> dict[str, Any]:
  groups = parallel_centerline_groups(graph)
  n_endpoint = sum(
    1 for _, _, d in graph.edges(data=True) if d.get("edge_kind") == "endpoint"
  )
  n_parallel = sum(
    1 for _, _, d in graph.edges(data=True) if d.get("is_parallel")
  )
  doc: dict[str, Any] = {
    "kind": "centerline_graph_summary",
    "schema_version": 1,
    "source_stem": source_stem,
    "config": cfg.to_json(),
    "node_count": graph.number_of_nodes(),
    "edge_count": graph.number_of_edges(),
    "endpoint_edge_count": n_endpoint,
    "parallel_edge_count": n_parallel,
    "corridor_count": graph.number_of_nodes(),
    "parallel_group_count": len(groups),
    "parallel_groups": [
      {"group_id": f"CG{idx:03d}", "corridor_ids": group}
      for idx, group in enumerate(groups, start=1)
    ],
  }
  if median_corridor_width is not None:
    doc["median_corridor_width"] = round(median_corridor_width, 4)
  return doc


def candidates_from_centerline_graph(graph: nx.Graph) -> list[dict[str, Any]]:
  """Rebuild candidate records from centerline_graph nodes (Step 3B input)."""
  out: list[dict[str, Any]] = []
  for nid, data in graph.nodes(data=True):
    if data.get("node_type") != "corridor":
      continue
    cid = str(data.get("corridor_id") or nid)
    cl = data.get("centerline")
    if cl is None:
      cl = {
        "start": list(data.get("start") or [0.0, 0.0]),
        "end": list(data.get("end") or [0.0, 0.0]),
        "direction": list(data.get("direction") or [1.0, 0.0]),
        "length": float(data.get("length", 0.0)),
      }
    out.append({
      "corridor_id": cid,
      "pair_id": str(data.get("pair_id", "")),
      "left_wall_id": str(data.get("left_wall_id", "")),
      "right_wall_id": str(data.get("right_wall_id", "")),
      "centerline": cl,
      "corridor_length": float(data.get("corridor_length", cl.get("length", 0.0))),
      "width": float(data.get("width", 0.0)),
      "overlap_ratio": float(data.get("overlap_ratio", 0.0)),
      "confidence": float(data.get("confidence", 0.0)),
    })
  out.sort(key=lambda c: str(c["corridor_id"]))
  return out


__all__ = [
  "build_centerline_graph",
  "cand_wall_to_id_from_graph",
  "candidates_from_centerline_graph",
  "centerline_graph_summary",
  "parallel_centerline_groups",
  "segments_from_candidates",
]
