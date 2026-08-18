"""Complete corridor centerlines from stage 4 semantics and build tunnel graph."""

from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np

from stage4.stub_classify import (
  SEM_AUXILIARY_CORRIDOR,
  SEM_NICHE,
  SEM_POSSIBLE_CORRIDOR_WALL,
  SEM_UNCLASSIFIED,
)
from step2B.config import CenterlineGraphConfig
from step3B.centerline_fix import apply_centerline_fixes
from step3B.graph_inputs import _seg_from_parallel_node
from step3B.residual_graph import EDGE_CORRIDOR_STUB_TOUCH
from step3B.wall_promotion import determined_partner_walls, target_corridor_ids
from utils.centerline_graph import cand_wall_to_id_from_graph
from utils.segment_geometry import acute_angle_deg, assign_left_right, endpoint_gap, overlap_centerline

NODE_CENTERLINE = "centerline"
NODE_STRUCTURE = "structure"

STRUCT_NICHE = "niche"
STRUCT_CROSSBAR = "crossbar"
STRUCT_UNKNOWN = "unknown"

# Flattened roles for the step-4B structure graph (巷道 / 支巷道 / 小室 / 未分类).
ROLE_CORRIDOR = "corridor"
ROLE_AUXILIARY = "auxiliary"
ROLE_NICHE = "niche"
ROLE_UNCLASSIFIED = "unclassified"

EDGE_ENDPOINT_TOUCH = "endpoint-touch"
EDGE_CROSSBAR_CONNECT = "crossbar-connect"
EDGE_NICHE_CONNECT = "niche-connect"

_STRUCTURE_BY_SEMANTIC = {
  SEM_NICHE: STRUCT_NICHE,
  SEM_AUXILIARY_CORRIDOR: STRUCT_CROSSBAR,
  SEM_UNCLASSIFIED: STRUCT_UNKNOWN,
}


def _corridor_seg_from_node(node_id: str, data: dict[str, Any]) -> dict[str, Any]:
  start = np.asarray(data["start"], dtype=float)[:2]
  end = np.asarray(data["end"], dtype=float)[:2]
  direction = np.asarray(data.get("direction") or [1.0, 0.0], dtype=float)[:2]
  return {
    "node_id": str(node_id),
    "start": start,
    "end": end,
    "mid": (start + end) / 2.0,
    "length": float(data.get("length", 0.0)),
    "direction": direction,
    "endpoints": [start, end],
  }


def _promotions_from_possible_walls(
  semantic_graph: nx.Graph,
  centerline_graph: nx.Graph,
  *,
  width_tol: float,
  angle_th_deg: float,
) -> list[dict[str, Any]]:
  """Build wall-promotion records for POSSIBLE_CORRIDOR_WALL stubs."""
  cand_wall_to_id = cand_wall_to_id_from_graph(centerline_graph)
  promotions: list[dict[str, Any]] = []

  for nid, data in sorted(semantic_graph.nodes(data=True)):
    if data.get("node_type") != "stub":
      continue
    if str(data.get("region_semantic", "")) != SEM_POSSIBLE_CORRIDOR_WALL:
      continue
    sid = str(nid)
    partners, reason = determined_partner_walls(
      semantic_graph,
      sid,
      width_tol=width_tol,
      angle_th_deg=angle_th_deg,
    )
    if not partners:
      continue
    corridor_ids = target_corridor_ids(
      semantic_graph,
      centerline_graph,
      cand_wall_to_id,
      sid,
      partners,
    )
    promotions.append({
      "residual_handle": sid,
      "partner_wall_ids": partners,
      "promotion_reason": reason,
      "target_corridor_ids": corridor_ids,
      "length": round(float(data.get("length", 0.0)), 4),
    })
  return promotions


def _next_auxiliary_id(graph: nx.Graph) -> str:
  max_idx = 0
  for nid in graph.nodes:
    text = str(nid)
    if text.startswith("AX") and text[2:].isdigit():
      max_idx = max(max_idx, int(text[2:]))
  return f"AX{max_idx + 1:03d}"


def _auxiliary_pairs(semantic_graph: nx.Graph) -> list[dict[str, Any]]:
  """Collect unique AUXILIARY_CORRIDOR parallel pairs."""
  seen: set[tuple[str, str]] = set()
  pairs: list[dict[str, Any]] = []

  for _nid, data in semantic_graph.nodes(data=True):
    if str(data.get("region_semantic", "")) != SEM_AUXILIARY_CORRIDOR:
      continue
    raw = data.get("parallel_pair")
    if not raw or len(raw) != 2:
      continue
    key = tuple(sorted(str(h) for h in raw))
    if key in seen:
      continue
    seen.add(key)
    pairs.append({
      "leg_a": key[0],
      "leg_b": key[1],
      "parallel_width": float(data.get("parallel_width") or 0.0),
    })
  return pairs


def _synthesize_auxiliary_centerlines(
  centerline_graph: nx.Graph,
  semantic_graph: nx.Graph,
) -> tuple[nx.Graph, list[dict[str, Any]]]:
  """Add auxiliary-corridor centerline nodes from crossbar parallel pairs."""
  graph = centerline_graph.copy()
  records: list[dict[str, Any]] = []

  for pair in _auxiliary_pairs(semantic_graph):
    leg_a = str(pair["leg_a"])
    leg_b = str(pair["leg_b"])
    if not semantic_graph.has_node(leg_a) or not semantic_graph.has_node(leg_b):
      records.append({**pair, "status": "skipped", "reason": "missing_stub"})
      continue

    seg_a = _seg_from_parallel_node(leg_a, semantic_graph.nodes[leg_a])
    seg_b = _seg_from_parallel_node(leg_b, semantic_graph.nodes[leg_b])
    cl = overlap_centerline(seg_a, seg_b)
    if cl is None:
      records.append({**pair, "status": "skipped", "reason": "no_overlap_centerline"})
      continue

    left_id, right_id = assign_left_right(leg_a, leg_b, seg_a, seg_b, cl)
    width = float(pair.get("parallel_width") or 0.0)
    if width <= 0.0:
      width = float(
        np.linalg.norm(np.asarray(seg_b["mid"]) - np.asarray(seg_a["mid"]))
      )

    cid = _next_auxiliary_id(graph)
    graph.add_node(
      cid,
      node_type="corridor",
      corridor_id=cid,
      corridor_role="auxiliary",
      start=list(cl["start"]),
      end=list(cl["end"]),
      length=float(cl["length"]),
      corridor_length=float(cl["length"]),
      width=round(width, 4),
      direction=list(cl["direction"]),
      left_wall_id=str(left_id),
      right_wall_id=str(right_id),
      centerline=cl,
      source_stubs=[leg_a, leg_b],
    )
    records.append({
      **pair,
      "status": "synthesized",
      "corridor_id": cid,
      "left_wall_id": str(left_id),
      "right_wall_id": str(right_id),
      "length": round(float(cl["length"]), 4),
    })

  return graph, records


def complete_centerlines(
  fixed_centerline_graph: nx.Graph,
  semantic_graph: nx.Graph,
  *,
  width_tol: float,
  angle_th_deg: float,
  para_cfg: CenterlineGraphConfig | None = None,
) -> tuple[nx.Graph, dict[str, Any]]:
  """
  Extend fixed centerlines using stage-4 POSSIBLE_CORRIDOR_WALL stubs,
  then synthesize auxiliary-corridor centerlines from crossbar pairs.
  """
  para_cfg = para_cfg or CenterlineGraphConfig()
  promotions = _promotions_from_possible_walls(
    semantic_graph,
    fixed_centerline_graph,
    width_tol=width_tol,
    angle_th_deg=angle_th_deg,
  )
  extended, fixes = apply_centerline_fixes(
    fixed_centerline_graph,
    semantic_graph,
    promotions,
    para_cfg=para_cfg,
  )
  with_aux, syntheses = _synthesize_auxiliary_centerlines(extended, semantic_graph)
  with_aux.graph["kind"] = "centerline_graph_corrected"
  with_aux.graph["schema_version"] = 1
  return with_aux, {
    "promotions": promotions,
    "fixes": fixes,
    "auxiliary_syntheses": syntheses,
  }


def _structure_kind(semantic: str) -> str | None:
  return _STRUCTURE_BY_SEMANTIC.get(str(semantic))


def _role_for_centerline(corridor_role: str) -> str:
  return ROLE_AUXILIARY if corridor_role == "auxiliary" else ROLE_CORRIDOR


def _role_for_structure(kind: str) -> str:
  if kind == STRUCT_NICHE:
    return ROLE_NICHE
  if kind == STRUCT_CROSSBAR:
    return ROLE_AUXILIARY
  return ROLE_UNCLASSIFIED


def _centerline_node_attrs(node_id: str, data: dict[str, Any]) -> dict[str, Any]:
  cl = data.get("centerline") or {}
  corridor_role = str(data.get("corridor_role") or "main")
  return {
    "node_type": NODE_CENTERLINE,
    "corridor_id": str(data.get("corridor_id") or node_id),
    "corridor_role": corridor_role,
    "role": _role_for_centerline(corridor_role),
    "start": list(data.get("start") or cl.get("start") or [0.0, 0.0]),
    "end": list(data.get("end") or cl.get("end") or [0.0, 0.0]),
    "direction": list(data.get("direction") or cl.get("direction") or [1.0, 0.0]),
    "length": float(data.get("length") or cl.get("length") or 0.0),
    "width": float(data.get("width") or 0.0),
    "left_wall_id": str(data.get("left_wall_id") or ""),
    "right_wall_id": str(data.get("right_wall_id") or ""),
    "centerline": cl if cl else {
      "start": list(data.get("start") or [0.0, 0.0]),
      "end": list(data.get("end") or [0.0, 0.0]),
      "direction": list(data.get("direction") or [1.0, 0.0]),
      "length": float(data.get("length") or 0.0),
    },
  }


def _structure_node_attrs(handle: str, data: dict[str, Any]) -> dict[str, Any] | None:
  kind = _structure_kind(str(data.get("region_semantic", "")))
  if kind is None:
    return None
  chain = data.get("niche_chain") or data.get("shape_handles") or []
  return {
    "node_type": NODE_STRUCTURE,
    "handle": str(handle),
    "structure_kind": kind,
    "role": _role_for_structure(kind),
    "region_semantic": str(data.get("region_semantic", "")),
    "detail_type": str(data.get("detail_type") or kind),
    "start": list(data.get("start") or [0.0, 0.0]),
    "end": list(data.get("end") or [0.0, 0.0]),
    "direction": list(data.get("direction") or [1.0, 0.0]),
    "length": float(data.get("length") or 0.0),
    "rc_id": str(data.get("rc_id") or ""),
    "niche_chain": [str(h) for h in chain] if chain else [],
    "shape_handles": [str(h) for h in (data.get("shape_handles") or [])],
  }


def _add_endpoint_touch_edges(
  graph: nx.Graph,
  centerline_ids: list[str],
  centerline_graph: nx.Graph,
  *,
  endpoint_link_gap: float,
  angle_th_deg: float,
) -> int:
  """Connect centerline nodes whose endpoints are within gap tolerance."""
  segs = {
    cid: _corridor_seg_from_node(cid, centerline_graph.nodes[cid])
    for cid in centerline_ids
    if centerline_graph.has_node(cid)
  }
  count = 0
  ids = sorted(segs)
  for i in range(len(ids)):
    for j in range(i + 1, len(ids)):
      u, v = ids[i], ids[j]
      gap = endpoint_gap(segs[u], segs[v])
      if gap > endpoint_link_gap:
        continue
      angle = acute_angle_deg(segs[u]["direction"], segs[v]["direction"])
      graph.add_edge(
        u,
        v,
        edge_kind=EDGE_ENDPOINT_TOUCH,
        endpoint_gap=round(gap, 4),
        angle_deg=round(angle, 4),
      )
      count += 1
  return count


def _add_wall_contact_edges(
  tunnel_graph: nx.Graph,
  semantic_graph: nx.Graph,
  centerline_ids: set[str],
) -> tuple[int, int]:
  """Add niche-connect and crossbar-connect from corridor-stub-touch wall data."""
  niche_count = 0
  crossbar_count = 0

  for stub_id, wall_id, edge_data in _corridor_stub_touches(semantic_graph):
    stub_data = semantic_graph.nodes.get(stub_id, {})
    kind = _structure_kind(str(stub_data.get("region_semantic", "")))
    if kind is None:
      continue

    corridor_id = str(edge_data.get("corridor_id") or "")
    if not corridor_id or corridor_id not in centerline_ids:
      continue
    if not tunnel_graph.has_node(stub_id) or not tunnel_graph.has_node(corridor_id):
      continue

    edge_kind = (
      EDGE_NICHE_CONNECT if kind == STRUCT_NICHE else EDGE_CROSSBAR_CONNECT
    )
    attrs = {
      "edge_kind": edge_kind,
      "wall_segment_id": str(wall_id),
      "corridor_id": corridor_id,
      "distance": edge_data.get("distance"),
      "attach_kind": edge_data.get("attach_kind"),
    }
    if tunnel_graph.has_edge(stub_id, corridor_id):
      existing = tunnel_graph[stub_id][corridor_id].get("edge_kind")
      if existing == edge_kind:
        continue
    tunnel_graph.add_edge(stub_id, corridor_id, **attrs)
    if edge_kind == EDGE_NICHE_CONNECT:
      niche_count += 1
    else:
      crossbar_count += 1

  return niche_count, crossbar_count


def _corridor_stub_touches(
  semantic_graph: nx.Graph,
) -> list[tuple[str, str, dict[str, Any]]]:
  rows: list[tuple[str, str, dict[str, Any]]] = []
  for u, v, data in semantic_graph.edges(data=True):
    if str(data.get("edge_kind", "")) != EDGE_CORRIDOR_STUB_TOUCH:
      continue
    u_type = str(semantic_graph.nodes.get(u, {}).get("node_type", ""))
    v_type = str(semantic_graph.nodes.get(v, {}).get("node_type", ""))
    if u_type == "stub" and v_type == "wall":
      rows.append((str(u), str(v), dict(data)))
    elif v_type == "stub" and u_type == "wall":
      rows.append((str(v), str(u), dict(data)))
  return rows


def build_tunnel_graph(
  corrected_centerline_graph: nx.Graph,
  semantic_graph: nx.Graph,
  *,
  endpoint_link_gap: float,
  angle_th_deg: float = 5.0,
) -> nx.Graph:
  """
  Build tunnel logical graph: centerline nodes, structure nodes, three edge kinds.

  Wall-contact edges are derived from original corridor-stub-touch data;
  node geometry uses centerlines and stub segments respectively.
  """
  tunnel = nx.Graph()
  centerline_ids: list[str] = []

  for nid, data in corrected_centerline_graph.nodes(data=True):
    if data.get("node_type") != "corridor":
      continue
    cid = str(data.get("corridor_id") or nid)
    tunnel.add_node(cid, **_centerline_node_attrs(cid, data))
    centerline_ids.append(cid)

  for nid, data in semantic_graph.nodes(data=True):
    if data.get("node_type") != "stub":
      continue
    attrs = _structure_node_attrs(str(nid), data)
    if attrs is None:
      continue
    tunnel.add_node(str(nid), **attrs)

  endpoint_count = _add_endpoint_touch_edges(
    tunnel,
    centerline_ids,
    corrected_centerline_graph,
    endpoint_link_gap=endpoint_link_gap,
    angle_th_deg=angle_th_deg,
  )
  niche_count, crossbar_count = _add_wall_contact_edges(
    tunnel,
    semantic_graph,
    set(centerline_ids),
  )

  role_counts: dict[str, int] = {
    ROLE_CORRIDOR: 0,
    ROLE_AUXILIARY: 0,
    ROLE_NICHE: 0,
    ROLE_UNCLASSIFIED: 0,
  }
  for _, data in tunnel.nodes(data=True):
    role = str(data.get("role") or "")
    if role in role_counts:
      role_counts[role] += 1

  tunnel.graph["kind"] = "corrected_centerlines"
  tunnel.graph["schema_version"] = 1
  tunnel.graph["centerline_count"] = len(centerline_ids)
  tunnel.graph["structure_count"] = sum(
    1 for _, d in tunnel.nodes(data=True) if d.get("node_type") == NODE_STRUCTURE
  )
  tunnel.graph["role_counts"] = role_counts
  tunnel.graph["edge_counts"] = {
    EDGE_ENDPOINT_TOUCH: endpoint_count,
    EDGE_NICHE_CONNECT: niche_count,
    EDGE_CROSSBAR_CONNECT: crossbar_count,
  }
  return tunnel


def build_corrected_centerlines(
  fixed_centerline_graph: nx.Graph,
  semantic_graph: nx.Graph,
  *,
  width_tol: float,
  angle_th_deg: float,
  para_cfg: CenterlineGraphConfig | None = None,
) -> tuple[nx.Graph, dict[str, Any]]:
  """Complete centerlines and emit the tunnel logical graph."""
  para_cfg = para_cfg or CenterlineGraphConfig()
  corrected, audit = complete_centerlines(
    fixed_centerline_graph,
    semantic_graph,
    width_tol=width_tol,
    angle_th_deg=angle_th_deg,
    para_cfg=para_cfg,
  )
  tunnel = build_tunnel_graph(
    corrected,
    semantic_graph,
    endpoint_link_gap=float(para_cfg.endpoint_link_gap),
    angle_th_deg=float(para_cfg.angle_th_deg),
  )
  audit["corrected_centerline_graph"] = corrected
  return tunnel, audit
