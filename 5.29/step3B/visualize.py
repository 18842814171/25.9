"""Step 3B residual_graph visualization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib.lines import Line2D
BG_WALL_COLOR = "#878787"
from utils.plot_bounds import apply_plot_bounds as _apply_bounds
from step3B.residual_graph import (
  EDGE_CORRIDOR_STUB_PARALLEL,
  EDGE_CORRIDOR_STUB_TOUCH,
  EDGE_STUB_STUB_PARALLEL,
  EDGE_STUB_STUB_TOUCH,
)

WALL_LW = 0.8
RESIDUAL_LW = 0.8
PARALLEL_LW = 2.8
TOUCH_MARKER_SIZE = 28
JUNCTION_LABEL_FONTSIZE = 5


def _palette(n: int) -> list[tuple[float, float, float, float]]:
  if n <= 0:
    return []
  cmap = plt.get_cmap("tab20")
  return [cmap(i % 20) for i in range(n)]


def _node_eps(
  graph: nx.Graph,
  nid: str,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
  data = graph.nodes.get(nid)
  if not data:
    return None
  start = data.get("start")
  end = data.get("end")
  if start is None or end is None:
    return None
  return (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))


def _closest_endpoint_pair(
  eps_a: tuple[tuple[float, float], tuple[float, float]],
  eps_b: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[tuple[float, float], tuple[float, float]]:
  best = float("inf")
  best_pair = (eps_a[0], eps_b[0])
  for pa in eps_a:
    for pb in eps_b:
      d = float(np.hypot(pa[0] - pb[0], pa[1] - pb[1]))
      if d < best:
        best = d
        best_pair = (pa, pb)
  return best_pair


def _stub_wall_junction(
  stub_eps: tuple[tuple[float, float], tuple[float, float]],
  wall_eps: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float]:
  """Return junction point (midpoint of closest approach between stub and wall)."""
  best = float("inf")
  best_pts = (stub_eps[0], wall_eps[0])

  def _proj(
    point: tuple[float, float],
    seg: tuple[tuple[float, float], tuple[float, float]],
  ) -> tuple[float, float]:
    p = np.asarray(point, dtype=float)
    a = np.asarray(seg[0], dtype=float)
    b = np.asarray(seg[1], dtype=float)
    ab = b - a
    ab_len = float(np.linalg.norm(ab))
    if ab_len < 1e-12:
      return seg[0]
    u = ab / ab_len
    t = float(np.dot(p - a, u))
    t = max(0.0, min(ab_len, t))
    q = a + u * t
    return (float(q[0]), float(q[1]))

  for sp in stub_eps:
    wp = _proj(sp, wall_eps)
    d = float(np.hypot(sp[0] - wp[0], sp[1] - wp[1]))
    if d < best:
      best = d
      best_pts = (sp, wp)
  for wp in wall_eps:
    sp = _proj(wp, stub_eps)
    d = float(np.hypot(sp[0] - wp[0], sp[1] - wp[1]))
    if d < best:
      best_pts = (sp, wp)
  pa, pb = best_pts
  return ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)


def _parallel_node_groups(graph: nx.Graph) -> list[list[str]]:
  """Connected components over stub-stub-parallel and corridor-stub-parallel edges."""
  para = nx.Graph()
  for u, v, data in graph.edges(data=True):
    kind = str(data.get("edge_kind", ""))
    if kind not in (EDGE_STUB_STUB_PARALLEL, EDGE_CORRIDOR_STUB_PARALLEL):
      continue
    para.add_edge(str(u), str(v))
  return [sorted(comp) for comp in nx.connected_components(para)]


def _node_parallel_color(
  groups: list[list[str]],
  colors: list[tuple[float, float, float, float]],
) -> dict[str, tuple[float, float, float, float]]:
  out: dict[str, tuple[float, float, float, float]] = {}
  for gi, group in enumerate(groups):
    color = colors[gi % len(colors)]
    for nid in group:
      out[str(nid)] = color
  return out


def _label_junction(
  ax: plt.Axes,
  point: tuple[float, float],
  label: str,
  *,
  color: str,
  zorder: int = 8,
) -> None:
  ax.scatter(
    [point[0]], [point[1]],
    s=TOUCH_MARKER_SIZE, c=color, edgecolors="white", linewidths=0.6, zorder=zorder,
  )
  ax.text(
    point[0],
    point[1],
    label,
    fontsize=JUNCTION_LABEL_FONTSIZE,
    ha="center",
    va="bottom",
    color=color,
    zorder=zorder + 1,
    bbox={
      "boxstyle": "round,pad=0.12",
      "facecolor": "white",
      "edgecolor": color,
      "alpha": 0.85,
      "linewidth": 0.4,
    },
  )


def visualize_residual_graph(
  graph: nx.Graph,
  save_path: str | Path,
  *,
  title: str | None = None,
  label: bool = False,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """Debug PNG: optional touch junction labels; parallel groups share segment color."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  parallel_groups = _parallel_node_groups(graph)
  palette = _palette(max(len(parallel_groups), 1))
  node_color = _node_parallel_color(parallel_groups, palette)

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  for nid, data in graph.nodes(data=True):
    eps = _node_eps(graph, str(nid))
    if eps is None:
      continue
    node_type = str(data.get("node_type", ""))
    para_color = node_color.get(str(nid))
    if para_color is not None:
      ax.plot(
        [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
        color=para_color, lw=PARALLEL_LW, alpha=1, zorder=5,
      )
    elif node_type == "wall":
      ax.plot(
        [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
        color=BG_WALL_COLOR, lw=WALL_LW, alpha=1, zorder=1,
      )
    elif node_type == "stub":
      ax.plot(
        [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
        color="#424242", lw=RESIDUAL_LW + 0.2, alpha=1, zorder=3,
      )
    elif node_type == "possible_corridor_wall":
      ax.plot(
        [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
        color="#e67e22", lw=PARALLEL_LW, alpha=0.98, zorder=5,
      )
    bounds.extend([eps[0], eps[1]])

  ss_touch_idx = 0
  cs_touch_idx = 0
  seen_touch: set[tuple[str, str]] = set()

  for u, v, data in graph.edges(data=True):
    kind = str(data.get("edge_kind", ""))
    key = tuple(sorted((str(u), str(v))))
    if key in seen_touch:
      continue

    eps_u = _node_eps(graph, str(u))
    eps_v = _node_eps(graph, str(v))
    if eps_u is None or eps_v is None:
      continue

    if kind == EDGE_STUB_STUB_TOUCH:
      seen_touch.add(key)
      if not label:
        continue
      ss_touch_idx += 1
      pa, pb = _closest_endpoint_pair(eps_u, eps_v)
      junction = ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)
      _label_junction(ax, junction, f"ss{ss_touch_idx}", color="#616161")
      bounds.append(junction)

    elif kind == EDGE_CORRIDOR_STUB_TOUCH:
      seen_touch.add(key)
      if not label:
        continue
      cs_touch_idx += 1
      u_type = graph.nodes.get(u, {}).get("node_type")
      stub_eps = eps_u if u_type == "stub" else eps_v
      wall_eps = eps_v if u_type == "stub" else eps_u
      junction = _stub_wall_junction(stub_eps, wall_eps)
      _label_junction(ax, junction, f"cs{cs_touch_idx}", color="#2ca02c")
      bounds.append(junction)

  _apply_bounds(ax, bounds)
  edge_counts = graph.graph.get("edge_counts") or {}
  ax.set_title(
    title or (
      f"residual_graph stubs={sum(1 for _, d in graph.nodes(data=True) if d.get('node_type') == 'stub')} "
      f"ss_touch={edge_counts.get(EDGE_STUB_STUB_TOUCH, 0)} "
      f"cs_touch={edge_counts.get(EDGE_CORRIDOR_STUB_TOUCH, 0)} "
      f"ss_para={edge_counts.get(EDGE_STUB_STUB_PARALLEL, 0)} "
      f"cs_para={edge_counts.get(EDGE_CORRIDOR_STUB_PARALLEL, 0)} "
      f"para_groups={len(parallel_groups)}"
    ),
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")

  legend = [
    Line2D([0], [0], color="#424242", lw=RESIDUAL_LW, label="stub"),
    Line2D([0], [0], color=BG_WALL_COLOR, lw=WALL_LW, label="wall"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#616161",
           markersize=6, label=f"{EDGE_STUB_STUB_TOUCH} junction"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#2ca02c",
           markersize=6, label=f"{EDGE_CORRIDOR_STUB_TOUCH} junction"),
    Line2D([0], [0], color=palette[0] if palette else "#ff7f0e",
           lw=PARALLEL_LW, label="parallel group (shared color)"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


_DETERMINED_WALL_COLOR = "#4a6fa5"
_POSSIBLE_WALL_COLOR = "#e67e22"
_REMAINING_STUB_COLOR = BG_WALL_COLOR
_WALL_DRAW_LW = 2.2
_CANDIDATE_DRAW_LW = 2.8
_FIXED_CL_COLOR = "#2ca02c"
_ORIGINAL_CL_COLOR = "#c7c7c7"
_PROMOTED_WALL_COLOR = "#1f77b4"


def visualize_secondary_wall_candidates(
  graph: nx.Graph,
  save_path: str | Path,
  *,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """Step 3B: determined walls vs secondary wall candidates (from stubs)."""
  from step3B.corridor_wall_candidates import (
    NODE_POSSIBLE_CORRIDOR_WALL,
    NODE_STUB,
    NODE_WALL,
  )

  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []
  n_wall = 0
  n_candidate = 0
  n_stub = 0

  for nid, data in graph.nodes(data=True):
    eps = _node_eps(graph, str(nid))
    if eps is None:
      continue
    node_type = str(data.get("node_type", ""))
    if node_type == NODE_WALL:
      color = _DETERMINED_WALL_COLOR
      lw = _WALL_DRAW_LW
      alpha = 0.85
      zorder = 2
      n_wall += 1
    elif node_type == NODE_POSSIBLE_CORRIDOR_WALL:
      color = _POSSIBLE_WALL_COLOR
      lw = _CANDIDATE_DRAW_LW
      alpha = 0.98
      zorder = 5
      n_candidate += 1
    elif node_type == NODE_STUB:
      color = _REMAINING_STUB_COLOR
      lw = RESIDUAL_LW
      alpha = 1
      zorder = 1
      n_stub += 1
    else:
      continue
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=color, lw=lw, alpha=alpha, zorder=zorder,
    )
    bounds.extend([eps[0], eps[1]])

  _apply_bounds(ax, bounds)
  ax.set_title(
    title or (
      f"secondary wall candidates: determined={n_wall} "
      f"secondary={n_candidate} remaining_stub={n_stub}"
    ),
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=_DETERMINED_WALL_COLOR, lw=_WALL_DRAW_LW, label="primary / determined wall"),
    Line2D([0], [0], color=_POSSIBLE_WALL_COLOR, lw=_CANDIDATE_DRAW_LW, label="secondary wall candidate"),
    Line2D([0], [0], color=_REMAINING_STUB_COLOR, lw=RESIDUAL_LW, alpha=0.5, label="stub (not picked)"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


_SYNTHESIZED_CL_COLOR = "#9467bd"
_CONNECTOR_WALL_COLOR = "#7b6ba8"


def visualize_centerline_fix(
  residual_graph: nx.Graph,
  fixed_centerline_graph: nx.Graph,
  promotions: list[dict[str, Any]],
  save_path: str | Path,
  *,
  syntheses: list[dict[str, Any]] | None = None,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """Walls + deferred possible walls, with fixed centerlines highlighted."""
  from step3B.centerline_synthesis import SYNTHESIS_STATUS
  from step3B.corridor_wall_candidates import NODE_POSSIBLE_CORRIDOR_WALL, NODE_WALL

  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  promoted_handles = {str(row["residual_handle"]) for row in promotions}
  extended_cids: set[str] = set()
  for row in promotions:
    for cid in row.get("target_corridor_ids") or []:
      extended_cids.add(str(cid))
  synthesized_cids = {
    str(row["corridor_id"])
    for row in syntheses or []
    if row.get("status") == SYNTHESIS_STATUS and row.get("corridor_id")
  }
  connector_wall_handles: set[str] = set()
  for row in syntheses or []:
    if row.get("status") != SYNTHESIS_STATUS:
      continue
    for wid in row.get("left_wall_ids") or []:
      connector_wall_handles.add(str(wid))
    for wid in row.get("right_wall_ids") or []:
      connector_wall_handles.add(str(wid))

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  for nid, data in residual_graph.nodes(data=True):
    eps = _node_eps(residual_graph, str(nid))
    if eps is None:
      continue
    node_type = str(data.get("node_type", ""))
    if str(nid) in connector_wall_handles:
      color = _CONNECTOR_WALL_COLOR
      lw = _CANDIDATE_DRAW_LW
      alpha = 1.0
      zorder = 5
    elif node_type == NODE_WALL:
      color = _PROMOTED_WALL_COLOR if str(nid) in promoted_handles else _DETERMINED_WALL_COLOR
      lw = _CANDIDATE_DRAW_LW if str(nid) in promoted_handles else _WALL_DRAW_LW
      alpha = 0.95 if str(nid) in promoted_handles else 0.55
      zorder = 4 if str(nid) in promoted_handles else 2
    elif node_type == NODE_POSSIBLE_CORRIDOR_WALL:
      color = _POSSIBLE_WALL_COLOR
      lw = _CANDIDATE_DRAW_LW
      alpha = 0.9
      zorder = 3
    else:
      continue
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=color, lw=lw, alpha=alpha, zorder=zorder,
    )
    bounds.extend([eps[0], eps[1]])

  for nid, data in fixed_centerline_graph.nodes(data=True):
    if data.get("node_type") != "corridor":
      continue
    eps = _node_eps(fixed_centerline_graph, str(nid))
    if eps is None:
      continue
    cid = str(nid)
    if cid in synthesized_cids:
      color = _SYNTHESIZED_CL_COLOR
      lw = 3.6
      alpha = 1.0
      zorder = 7
    elif cid in extended_cids:
      color = _FIXED_CL_COLOR
      lw = 3.2
      alpha = 1.0
      zorder = 6
    else:
      color = _ORIGINAL_CL_COLOR
      lw = 1.4
      alpha = 0.7
      zorder = 1
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=color, lw=lw, alpha=alpha, zorder=zorder, linestyle="--",
    )
    bounds.extend([eps[0], eps[1]])

  _apply_bounds(ax, bounds)
  ax.set_title(
    title or (
      f"centerline fix: promoted={len(promoted_handles)} "
      f"extended_corridors={len(extended_cids)}"
    ),
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=_DETERMINED_WALL_COLOR, lw=_WALL_DRAW_LW, label="determined wall"),
    Line2D([0], [0], color=_PROMOTED_WALL_COLOR, lw=_CANDIDATE_DRAW_LW, label="promoted wall"),
    Line2D([0], [0], color=_POSSIBLE_WALL_COLOR, lw=_CANDIDATE_DRAW_LW, label="deferred possible"),
    Line2D([0], [0], color=_CONNECTOR_WALL_COLOR, lw=_CANDIDATE_DRAW_LW, label="connector wall"),
    Line2D([0], [0], color=_FIXED_CL_COLOR, lw=3, linestyle="--", label="fixed centerline"),
    Line2D(
      [0], [0], color=_SYNTHESIZED_CL_COLOR, lw=3.6, linestyle="--",
      label="synthesized connector",
    ),
    Line2D([0], [0], color=_ORIGINAL_CL_COLOR, lw=1.4, linestyle="--", label="original centerline"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path
