"""Step 3B stub topology graph (Phase 1).

Primary artefact: ``residual_graph.pkl`` with four edge kinds:

  - ``stub-stub-touch``       — stub endpoints linked within endpoint gap
  - ``corridor-stub-touch``   — stub touches a corridor boundary wall
  - ``stub-stub-parallel``    — parallel stub pair at corridor-like spacing
  - ``corridor-stub-parallel`` — stub parallel to a corridor boundary wall

RC grouping (versioned view, not a permanent definition):

  RC_v1 = connected components over stub nodes + ``stub-stub-touch`` edges.

Later phases may introduce RC_v2 (e.g. union with parallel-linked stubs).
"""

from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np

from step2B.config import ParallelGraphConfig
from step2B.parallel_graph import _iter_parallel_candidate_pairs, _parallel_pair_ok
from step2B.width_estimate import apply_width_band
from step3B.graph_inputs import _seg_from_parallel_node
from utils.segment_geometry import point_segment_distance as _point_segment_distance


def _segment_endpoints(seg: dict[str, Any]) -> list[np.ndarray]:
  return [np.asarray(seg["start"], dtype=float)[:2], np.asarray(seg["end"], dtype=float)[:2]]


def _seg_aabb(seg: dict[str, Any]) -> tuple[float, float, float, float]:
  xs = (float(seg["start"][0]), float(seg["end"][0]))
  ys = (float(seg["start"][1]), float(seg["end"][1]))
  return min(xs), max(xs), min(ys), max(ys)


def _iter_bbox_near_cross_pairs(
  segs_a: list[dict[str, Any]],
  segs_b: list[dict[str, Any]],
  *,
  pad: float,
  progress_label: str | None = None,
  progress_every: int = 500,
) -> list[tuple[int, int]]:
  """
  Index pairs (ia, ib) whose AABBs come within ``pad``.

  Spatial hash only — objects stay whole; grid never partitions geometry.
  Each segment occupies every cell overlapping its AABB expanded by ``pad``.
  """
  if not segs_a or not segs_b or pad < 0:
    return []

  cell = max(float(pad), 1e-6)
  inv = 1.0 / cell
  buckets: dict[tuple[int, int], list[int]] = {}
  n_b = len(segs_b)
  n_a = len(segs_a)

  for ib, seg in enumerate(segs_b):
    x0, x1, y0, y1 = _seg_aabb(seg)
    cx0, cx1 = int(np.floor((x0 - pad) * inv)), int(np.floor((x1 + pad) * inv))
    cy0, cy1 = int(np.floor((y0 - pad) * inv)), int(np.floor((y1 + pad) * inv))
    for cx in range(cx0, cx1 + 1):
      for cy in range(cy0, cy1 + 1):
        buckets.setdefault((cx, cy), []).append(ib)
    if progress_label and progress_every > 0:
      done = ib + 1
      if done % progress_every == 0 or done == n_b:
        print(
          f"[step3B/residual_graph] {progress_label} index {done}/{n_b}",
          flush=True,
        )

  pairs: set[tuple[int, int]] = set()
  for ia, seg in enumerate(segs_a):
    x0, x1, y0, y1 = _seg_aabb(seg)
    cx0, cx1 = int(np.floor((x0 - pad) * inv)), int(np.floor((x1 + pad) * inv))
    cy0, cy1 = int(np.floor((y0 - pad) * inv)), int(np.floor((y1 + pad) * inv))
    seen: set[int] = set()
    for cx in range(cx0, cx1 + 1):
      for cy in range(cy0, cy1 + 1):
        for ib in buckets.get((cx, cy), ()):
          if ib in seen:
            continue
          seen.add(ib)
          pairs.add((ia, ib))
    if progress_label and progress_every > 0:
      done = ia + 1
      if done % progress_every == 0 or done == n_a:
        print(
          f"[step3B/residual_graph] {progress_label} query {done}/{n_a} "
          f"pairs={len(pairs)}",
          flush=True,
        )
  return sorted(pairs)


def _progress_pairs(label: str, done: int, total: int, *, every: int = 500) -> None:
  if every <= 0:
    return
  if done % every == 0 or done == total:
    print(f"[step3B/residual_graph] {label} {done}/{total}", flush=True)

EDGE_STUB_STUB_TOUCH = "stub-stub-touch"
EDGE_CORRIDOR_STUB_TOUCH = "corridor-stub-touch"
EDGE_STUB_STUB_PARALLEL = "stub-stub-parallel"
EDGE_CORRIDOR_STUB_PARALLEL = "corridor-stub-parallel"

RC_V1_EDGE_KIND = EDGE_STUB_STUB_TOUCH

_PARALLEL_ENDPOINT_KINDS = frozenset({"endpoint", "endpoint_parallel"})


def corridors_touching_stub(graph: nx.Graph, stub_id: str) -> set[str]:
  """Corridor ids reachable from *stub_id* via ``corridor-stub-touch`` edges."""
  out: set[str] = set()
  sid = str(stub_id)
  if not graph.has_node(sid):
    return out
  for _nb, data in graph[sid].items():
    if data.get("edge_kind") != EDGE_CORRIDOR_STUB_TOUCH:
      continue
    cid = data.get("corridor_id")
    if cid:
      out.add(str(cid))
  return out


def walls_touching_stub(graph: nx.Graph, stub_id: str) -> list[dict[str, Any]]:
  """Wall contacts for *stub_id* from ``corridor-stub-touch`` edges."""
  sid = str(stub_id)
  if not graph.has_node(sid):
    return []
  rows: list[dict[str, Any]] = []
  for wall_id, data in graph[sid].items():
    if data.get("edge_kind") != EDGE_CORRIDOR_STUB_TOUCH:
      continue
    rows.append({
      "wall_segment_id": str(wall_id),
      "corridor_id": data.get("corridor_id"),
      "distance": data.get("distance"),
      "attach_kind": data.get("attach_kind"),
    })
  rows.sort(key=lambda r: str(r["wall_segment_id"]))
  return rows


def stub_neighbors_by_kind(
  graph: nx.Graph,
  stub_id: str,
  edge_kind: str,
) -> list[str]:
  """Adjacent stub ids linked by *edge_kind*."""
  sid = str(stub_id)
  if not graph.has_node(sid):
    return []
  out: list[str] = []
  for nb, data in graph[sid].items():
    if data.get("edge_kind") != edge_kind:
      continue
    if graph.nodes.get(nb, {}).get("node_type") == "stub":
      out.append(str(nb))
  return sorted(out)


def _parallel_graph_config(
  parallel_graph: nx.Graph,
  median_corridor_width: float | None,
) -> ParallelGraphConfig:
  cfg = ParallelGraphConfig.from_pipeline()
  if median_corridor_width is not None and median_corridor_width > 0:
    apply_width_band(cfg, median_corridor_width)
  stored = parallel_graph.graph.get("config")
  if isinstance(stored, dict):
    for key in ("angle_th_deg", "min_overlap_ratio", "endpoint_link_gap"):
      if key in stored:
        setattr(cfg, key, float(stored[key]))
  return cfg


def _add_stub_stub_touch_edges(
  graph: nx.Graph,
  parallel_graph: nx.Graph,
) -> int:
  count = 0
  for u, v, data in parallel_graph.edges(data=True):
    if str(data.get("edge_kind", "")) not in _PARALLEL_ENDPOINT_KINDS:
      continue
    ut = parallel_graph.nodes.get(u, {}).get("node_type")
    vt = parallel_graph.nodes.get(v, {}).get("node_type")
    if ut != "stub" or vt != "stub":
      continue
    if graph.has_edge(u, v):
      continue
    graph.add_edge(
      u,
      v,
      edge_kind=EDGE_STUB_STUB_TOUCH,
      endpoint_gap=data.get("endpoint_gap"),
      angle_deg=data.get("angle_deg"),
    )
    count += 1
  return count


def _stub_wall_touch_attrs(
  stub_id: str,
  seg: dict[str, Any],
  wall_seg: dict[str, Any],
  attach_tol: float,
) -> dict[str, Any] | None:
  """Return touch edge attrs if stub–wall distance ≤ *attach_tol*."""
  best = float("inf")
  attach_kind = "endpoint"
  for pt in _segment_endpoints(seg):
    dist = _point_segment_distance(pt, wall_seg["start"], wall_seg["end"])
    if dist < best:
      best = dist
      attach_kind = "endpoint"
  for pt in _segment_endpoints(wall_seg):
    dist = _point_segment_distance(
      pt,
      np.asarray(seg["start"], dtype=float),
      np.asarray(seg["end"], dtype=float),
    )
    if dist < best:
      best = dist
      attach_kind = "endpoint"
  seg_dist = _segment_pair_min_distance(seg, wall_seg)
  if seg_dist < best:
    best = seg_dist
    attach_kind = "segment_gap"
  if best > attach_tol:
    return None
  return {
    "edge_kind": EDGE_CORRIDOR_STUB_TOUCH,
    "distance": round(best, 4),
    "attach_kind": attach_kind,
    "residual_handle": str(stub_id),
  }


def _segment_pair_min_distance(
  seg_a: dict[str, Any],
  seg_b: dict[str, Any],
) -> float:
  best = float("inf")
  for pa in _segment_endpoints(seg_a):
    wall_start = np.asarray(seg_b["start"], dtype=float)[:2]
    wall_end = np.asarray(seg_b["end"], dtype=float)[:2]
    best = min(best, _point_segment_distance(pa, wall_start, wall_end))
  for pb in _segment_endpoints(seg_b):
    res_start = np.asarray(seg_a["start"], dtype=float)[:2]
    res_end = np.asarray(seg_a["end"], dtype=float)[:2]
    best = min(best, _point_segment_distance(pb, res_start, res_end))
  return best


def _add_corridor_stub_touch_edges(
  graph: nx.Graph,
  stub_segments: dict[str, dict[str, Any]],
  wall_index: dict[str, dict[str, Any]],
  attach_tol: float,
  cand_wall_to_id: dict[str, str],
) -> int:
  if not stub_segments:
    print(
      "[step3B/residual_graph] corridor-stub-touch skipped (stubs=0)",
      flush=True,
    )
    return 0
  if not wall_index:
    print(
      "[step3B/residual_graph] corridor-stub-touch skipped (walls=0)",
      flush=True,
    )
    return 0

  stub_ids = sorted(stub_segments)
  wall_ids = sorted(wall_index)
  stub_list = [stub_segments[s] for s in stub_ids]
  wall_list = [wall_index[w] for w in wall_ids]
  candidates = _iter_bbox_near_cross_pairs(
    stub_list,
    wall_list,
    pad=attach_tol,
    progress_label="corridor-stub-touch",
  )
  total = len(candidates)
  count = 0
  for n, (ia, ib) in enumerate(candidates, start=1):
    stub_id = stub_ids[ia]
    wall_id = wall_ids[ib]
    attrs = _stub_wall_touch_attrs(
      stub_id, stub_list[ia], wall_list[ib], attach_tol,
    )
    if attrs is not None:
      cid = cand_wall_to_id.get(wall_id)
      if cid is not None:
        attrs["corridor_id"] = str(cid)
      graph.add_edge(stub_id, wall_id, **attrs)
      count += 1
    _progress_pairs("corridor-stub-touch check", n, total)
  return count


def _add_parallel_edges(
  graph: nx.Graph,
  stub_segments: dict[str, dict[str, Any]],
  wall_index: dict[str, dict[str, Any]],
  cfg: ParallelGraphConfig,
) -> tuple[int, int]:
  stub_stub = 0
  corridor_stub = 0
  stub_ids = sorted(stub_segments)
  wall_ids = sorted(wall_index)
  stub_list = [stub_segments[s] for s in stub_ids]
  wall_list = [wall_index[w] for w in wall_ids]
  n_stub = len(stub_list)

  if n_stub == 0:
    print(
      "[step3B/residual_graph] stub-stub-parallel skipped (stubs=0)",
      flush=True,
    )
    print(
      "[step3B/residual_graph] corridor-stub-parallel skipped (stubs=0)",
      flush=True,
    )
    return 0, 0

  print("[step3B/residual_graph] stub-stub-parallel candidates…", flush=True)
  ss_cands = _iter_parallel_candidate_pairs(
    stub_list,
    min_width=cfg.min_width,
    max_width=cfg.max_width,
    angle_th_deg=cfg.angle_th_deg,
  )
  ss_total = len(ss_cands)
  for n, (i, j) in enumerate(ss_cands, start=1):
    ok, width, overlap = _parallel_pair_ok(
      stub_list[i],
      stub_list[j],
      angle_th_deg=cfg.angle_th_deg,
      min_width=cfg.min_width,
      max_width=cfg.max_width,
      min_overlap_ratio=cfg.min_overlap_ratio,
    )
    if ok:
      u, v = stub_ids[i], stub_ids[j]
      if not graph.has_edge(u, v):
        graph.add_edge(
          u,
          v,
          edge_kind=EDGE_STUB_STUB_PARALLEL,
          width=round(width, 4),
          overlap_ratio=round(overlap, 4),
        )
        stub_stub += 1
    _progress_pairs("stub-stub-parallel check", n, ss_total)

  if not wall_list:
    print(
      "[step3B/residual_graph] corridor-stub-parallel skipped (walls=0)",
      flush=True,
    )
    return stub_stub, 0

  # Combined list: stubs then walls; keep only stub–wall candidate pairs.
  combined = stub_list + wall_list
  print(
    f"[step3B/residual_graph] corridor-stub-parallel candidates "
    f"(n={len(combined)})…",
    flush=True,
  )
  cs_cands = _iter_parallel_candidate_pairs(
    combined,
    min_width=cfg.min_width,
    max_width=cfg.max_width,
    angle_th_deg=cfg.angle_th_deg,
  )
  cs_total = len(cs_cands)
  for n, (i, j) in enumerate(cs_cands, start=1):
    if (i < n_stub) != (j < n_stub):
      si, wi = (i, j) if i < n_stub else (j, i)
      wall_idx = wi - n_stub
      stub_id = stub_ids[si]
      wall_id = wall_ids[wall_idx]
      ok, width, overlap = _parallel_pair_ok(
        stub_list[si],
        wall_list[wall_idx],
        angle_th_deg=cfg.angle_th_deg,
        min_width=cfg.min_width,
        max_width=cfg.max_width,
        min_overlap_ratio=cfg.min_overlap_ratio,
      )
      if ok and not graph.has_edge(stub_id, wall_id):
        graph.add_edge(
          stub_id,
          wall_id,
          edge_kind=EDGE_CORRIDOR_STUB_PARALLEL,
          width=round(width, 4),
          overlap_ratio=round(overlap, 4),
        )
        corridor_stub += 1
    _progress_pairs("corridor-stub-parallel check", n, cs_total)
  return stub_stub, corridor_stub


def build_residual_graph(
  parallel_graph: nx.Graph,
  *,
  stub_segments: dict[str, dict[str, Any]] | None = None,
  wall_index: dict[str, dict[str, Any]] | None = None,
  cand_wall_to_id: dict[str, str] | None = None,
  attach_tol: float,
  median_corridor_width: float | None = None,
  source_stem: str = "",
) -> nx.Graph:
  """
  Build stub topology graph from ``parallel_graph.pkl`` inputs.

  Copies stub and wall nodes, then adds the four canonical edge kinds.
  Corridor nodes are not required; corridor ids live on touch edges.
  """
  if stub_segments is None:
    stub_segments = {
      str(nid): _seg_from_parallel_node(str(nid), data)
      for nid, data in parallel_graph.nodes(data=True)
      if data.get("node_type") == "stub"
    }
  if wall_index is None:
    wall_index = {
      str(nid): _seg_from_parallel_node(str(nid), data)
      for nid, data in parallel_graph.nodes(data=True)
      if data.get("node_type") == "wall"
    }
  cand_wall_to_id = cand_wall_to_id or {}

  graph = nx.Graph()
  graph.graph["kind"] = "residual_graph"
  graph.graph["schema_version"] = 1
  graph.graph["source_stem"] = source_stem
  graph.graph["rc_view"] = {
    "version": "RC_v1",
    "edge_kind": RC_V1_EDGE_KIND,
    "description": "Connected components over stub-stub-touch (reproduces legacy RC)",
  }

  for nid, data in parallel_graph.nodes(data=True):
    node_type = str(data.get("node_type", ""))
    if node_type not in ("stub", "wall"):
      continue
    graph.add_node(
      str(nid),
      node_type=node_type,
      start=list(data.get("start") or [0.0, 0.0]),
      end=list(data.get("end") or [0.0, 0.0]),
      length=float(data.get("length", 0.0)),
      direction=list(data.get("direction") or [1.0, 0.0]),
      handle=str(data.get("handle") or nid),
    )

  touch_ss = _add_stub_stub_touch_edges(graph, parallel_graph)
  print(
    f"[step3B/residual_graph] stubs={len(stub_segments)} "
    f"walls={len(wall_index)} attach_tol={attach_tol:.4f}",
    flush=True,
  )
  touch_cs = _add_corridor_stub_touch_edges(
    graph,
    stub_segments,
    wall_index,
    attach_tol,
    cand_wall_to_id,
  )
  para_cfg = _parallel_graph_config(parallel_graph, median_corridor_width)
  para_ss, para_cs = _add_parallel_edges(
    graph, stub_segments, wall_index, para_cfg,
  )

  graph.graph["edge_counts"] = {
    EDGE_STUB_STUB_TOUCH: touch_ss,
    EDGE_CORRIDOR_STUB_TOUCH: touch_cs,
    EDGE_STUB_STUB_PARALLEL: para_ss,
    EDGE_CORRIDOR_STUB_PARALLEL: para_cs,
  }
  graph.graph["attach_tol"] = attach_tol
  graph.graph["parallel_config"] = para_cfg.to_json()
  return graph


def residual_components_v1(graph: nx.Graph) -> list[dict[str, Any]]:
  """
  RC_v1: connected components over stub nodes linked by ``stub-stub-touch``.

  This reproduces legacy ``build_residual_components_from_stubs`` grouping when
  stub-stub-touch edges match parallel_graph endpoint links among stubs.
  """
  touch = nx.Graph()
  for nid, data in graph.nodes(data=True):
    if data.get("node_type") != "stub":
      continue
    touch.add_node(
      str(nid),
      length=float(data.get("length", 0.0)),
    )

  for u, v, data in graph.edges(data=True):
    if data.get("edge_kind") != RC_V1_EDGE_KIND:
      continue
    if touch.has_node(u) and touch.has_node(v):
      touch.add_edge(u, v, **{k: v_ for k, v_ in data.items() if k != "edge_kind"})

  components: list[dict[str, Any]] = []
  for idx, comp in enumerate(nx.connected_components(touch), start=1):
    handles = sorted(str(h) for h in comp)
    total_length = round(
      sum(float(touch.nodes[h].get("length", 0.0)) for h in handles),
      4,
    )
    components.append({
      "rc_id": f"RC{idx:03d}",
      "rc_view": "RC_v1",
      "handles": handles,
      "singleton": len(handles) == 1,
      "handle_count": len(handles),
      "total_length": total_length,
      "edge_count": touch.subgraph(handles).number_of_edges(),
    })
  return components


def compare_rc_v1_to_legacy(
  rc_v1: list[dict[str, Any]],
  legacy_rc: list[dict[str, Any]],
) -> dict[str, Any]:
  """Compare RC_v1 handle sets with legacy residual components."""

  def _sets(rc_list: list[dict[str, Any]]) -> list[frozenset[str]]:
    return sorted(
      (frozenset(str(h) for h in rc.get("handles") or []) for rc in rc_list),
      key=lambda s: sorted(s),
    )

  v1_sets = _sets(rc_v1)
  leg_sets = _sets(legacy_rc)
  matched = sum(1 for s in v1_sets if s in leg_sets)
  return {
    "rc_v1_count": len(rc_v1),
    "legacy_count": len(legacy_rc),
    "matched_partitions": matched,
    "identical_partitioning": v1_sets == leg_sets,
  }


def residual_graph_summary(
  graph: nx.Graph,
  *,
  source_stem: str,
  rc_v1: list[dict[str, Any]] | None = None,
  legacy_rc_compare: dict[str, Any] | None = None,
) -> dict[str, Any]:
  edge_counts = dict(graph.graph.get("edge_counts") or {})
  if not edge_counts:
    for _u, _v, data in graph.edges(data=True):
      kind = str(data.get("edge_kind", ""))
      edge_counts[kind] = edge_counts.get(kind, 0) + 1

  stub_count = sum(
    1 for _, d in graph.nodes(data=True) if d.get("node_type") == "stub"
  )
  wall_count = sum(
    1 for _, d in graph.nodes(data=True) if d.get("node_type") == "wall"
  )

  doc: dict[str, Any] = {
    "kind": "residual_graph_summary",
    "schema_version": 1,
    "source_stem": source_stem,
    "node_count": graph.number_of_nodes(),
    "edge_count": graph.number_of_edges(),
    "stub_count": stub_count,
    "wall_count": wall_count,
    "edge_counts": edge_counts,
    "rc_view": graph.graph.get("rc_view"),
    "attach_tol": graph.graph.get("attach_tol"),
    "parallel_config": graph.graph.get("parallel_config"),
  }
  if rc_v1 is not None:
    doc["rc_v1_count"] = len(rc_v1)
    doc["rc_v1_singleton_count"] = sum(1 for rc in rc_v1 if rc.get("singleton"))
  if legacy_rc_compare is not None:
    doc["legacy_rc_compare"] = legacy_rc_compare
  return doc
