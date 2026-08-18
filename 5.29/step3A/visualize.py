"""Step 3A corridor candidate and centerline graph visualization PNGs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D

from utils.plot_bounds import apply_plot_bounds as _apply_bounds

BG_WALL_COLOR = "#d0d0d0"
UNPAIRED_WALL_COLOR = "#bdbdbd"
CENTERLINE_LW = 2.0
WALL_LW = 2.2
CL_GRAPH_LW = 2.5
CL_NO_GROUP_COLOR = "#cfcfcf"
CC_LABEL_FONTSIZE = 6


# Saturated palette — avoid light yellow on white background
_CANDIDATE_COLORS = [
  "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
  "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
  "#393b79", "#637939", "#8c6d31", "#843c39", "#7b4173",
  "#5254a3", "#6b6ecf", "#9c9ede", "#637939", "#b5cf6b",
]


def _candidate_colors(n: int) -> list[tuple[float, float, float, float]]:
  if n <= 0:
    return []
  from matplotlib.colors import to_rgba
  return [to_rgba(_CANDIDATE_COLORS[i % len(_CANDIDATE_COLORS)]) for i in range(n)]


def _component_colors(n: int) -> list[tuple[float, float, float, float]]:
  return _candidate_colors(n)


def _seg_endpoints(row: dict[str, Any]) -> tuple[tuple[float, float], tuple[float, float]] | None:
  attrs = row.get("attributes") or {}
  start = attrs.get("start")
  end = attrs.get("end")
  if start is None or end is None:
    return None
  return (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))


def _centerline_endpoints(cand: dict[str, Any]) -> tuple[tuple[float, float], tuple[float, float]] | None:
  cl = cand.get("centerline") or {}
  start = cl.get("start")
  end = cl.get("end")
  if start is None or end is None:
    return None
  return (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))


def visualize_primary_wall_pairs(
  wall_doc: dict[str, Any],
  candidates_doc: dict[str, Any],
  save_path: str | Path,
  *,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """Step 3A: each primary wall pair (corridor candidate) shares one color."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  candidates = list(candidates_doc.get("candidates") or [])
  colors = _candidate_colors(len(candidates))
  wall_to: dict[str, tuple[float, float, float, float]] = {}
  for idx, cand in enumerate(candidates):
    color = colors[idx]
    wall_to[str(cand["left_wall_id"])] = color
    wall_to[str(cand["right_wall_id"])] = color

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  for row in wall_doc.get("walls") or []:
    eps = _seg_endpoints(row)
    if eps is None:
      continue
    ws_id = str(row.get("wall_segment_id", ""))
    color = wall_to.get(ws_id, UNPAIRED_WALL_COLOR)
    lw = WALL_LW if ws_id in wall_to else 0.8
    alpha = 0.95 if ws_id in wall_to else 0.45
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=color, lw=lw, alpha=alpha, zorder=3 if ws_id in wall_to else 1,
    )
    bounds.extend([eps[0], eps[1]])

  _apply_bounds(ax, bounds)
  ax.set_title(
    title or f"Primary wall pairs: n={len(candidates)}",
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=colors[0] if colors else "#333333", lw=WALL_LW, label="primary wall pair"),
    Line2D([0], [0], color=UNPAIRED_WALL_COLOR, lw=0.8, label="other wall"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


def visualize_corridor_centerlines(
  candidates_doc: dict[str, Any],
  save_path: str | Path,
  *,
  wall_doc: dict[str, Any] | None = None,
  show_ids: bool = False,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """Draw each corridor candidate centerline in a distinct color."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  candidates = list(candidates_doc.get("candidates") or [])
  colors = _candidate_colors(len(candidates))

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  if wall_doc is not None:
    for row in wall_doc.get("walls") or []:
      eps = _seg_endpoints(row)
      if eps is None:
        continue
      ax.plot(
        [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
        color=BG_WALL_COLOR, lw=0.6, alpha=0.35, zorder=1,
      )
      bounds.extend([eps[0], eps[1]])

  for idx, cand in enumerate(candidates):
    eps = _centerline_endpoints(cand)
    if eps is None:
      continue
    color = colors[idx]
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=color, lw=CENTERLINE_LW, alpha=0.95, zorder=4,
    )
    bounds.extend([eps[0], eps[1]])
    if show_ids:
      mid = ((eps[0][0] + eps[1][0]) / 2.0, (eps[0][1] + eps[1][1]) / 2.0)
      ax.text(
        mid[0], mid[1], str(cand.get("corridor_id", "")),
        fontsize=CC_LABEL_FONTSIZE, ha="center", va="center", color="#111111",
        zorder=10,
        bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.8},
      )

  _apply_bounds(ax, bounds)
  ax.set_title(
    title or f"Corridor centerlines: n={len(candidates)}",
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=colors[0] if colors else "#2980b9", lw=CENTERLINE_LW, label="centerline"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


def visualize_centerline_graph(
  graph: nx.Graph,
  parallel_groups: list[list[str]],
  save_path: str | Path,
  *,
  title: str | None = None,
  show_ids: bool = False,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """
  Step 2B-style parallel group coloring on corridor centerline logical graph.

  Each parallel centerline group shares a color; ungrouped corridors in light grey.
  """
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  node_to_group: dict[str, int] = {}
  for gi, group in enumerate(parallel_groups):
    for node_id in group:
      node_to_group[str(node_id)] = gi
  colors = _candidate_colors(max(len(parallel_groups), 1))

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  for node_id, data in graph.nodes(data=True):
    start = data.get("start")
    end = data.get("end")
    if start is None or end is None:
      continue
    p0 = (float(start[0]), float(start[1]))
    p1 = (float(end[0]), float(end[1]))
    if node_id in node_to_group:
      color = colors[node_to_group[node_id] % len(colors)]
      lw = CL_GRAPH_LW
      alpha = 0.95
      zorder = 3
    else:
      color = CL_NO_GROUP_COLOR
      lw = 1.2
      alpha = 0.8
      zorder = 2
    ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=color, lw=lw, alpha=alpha, zorder=zorder)
    bounds.extend([p0, p1])
    if show_ids:
      mid = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
      ax.text(
        mid[0],
        mid[1],
        str(node_id),
        fontsize=CC_LABEL_FONTSIZE,
        ha="center",
        va="center",
        color="#111111",
        zorder=11,
        bbox={
          "boxstyle": "round,pad=0.12",
          "facecolor": "white",
          "edgecolor": "none",
          "alpha": 0.8,
        },
      )

  _apply_bounds(ax, bounds)
  ax.set_title(
    title or f"Centerline graph: parallel_groups={len(parallel_groups)}",
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=colors[0] if colors else "#1f77b4", lw=CL_GRAPH_LW, label="parallel centerline group"),
    Line2D([0], [0], color=CL_NO_GROUP_COLOR, lw=1.2, label="corridor (no parallel group)"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path
