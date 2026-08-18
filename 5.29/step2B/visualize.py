"""Step 2B straight wall vs residual geometry overview PNG."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

UNMERGED_COLOR = "#9e9e9e"

# Line widths (points) — adjust here for straight_wall.png
LW_MERGED_WALL = 2.0   # straight_wall_geometry.json
LW_OTHER = 0.7         # residual_geometry.json
LW_PARALLEL_WALL = 2.5  # parallel_graph.png
LW_STUB = 0.7           # parallel_graph.png stubs
WS_ID_LABEL_FONTSIZE = 6

# Handle label style — adjust fontsize here if labels overlap
HANDLE_LABEL_FONTSIZE = 5


def _seg_endpoints(row: dict[str, Any]) -> tuple[tuple[float, float], tuple[float, float]] | None:
  attrs = row.get("attributes") or {}
  start = attrs.get("start")
  end = attrs.get("end")
  if start is None or end is None:
    return None
  return (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))


def _seg_midpoint(row: dict[str, Any]) -> tuple[float, float] | None:
  eps = _seg_endpoints(row)
  if eps is None:
    return None
  return (eps[0][0] + eps[1][0]) / 2.0, (eps[0][1] + eps[1][1]) / 2.0


def _wall_colors(n: int) -> list[tuple[float, float, float, float]]:
  if n <= 0:
    return []
  cmap = plt.get_cmap("tab20")
  return [cmap(i % 20) for i in range(n)]


def _draw_handle_labels(
  ax: plt.Axes,
  prim_by_handle: dict[str, dict[str, Any]],
) -> None:
  """Label every LINE primitive at its midpoint with its handle."""
  for handle, row in sorted(prim_by_handle.items()):
    mid = _seg_midpoint(row)
    if mid is None:
      continue
    ax.text(
      mid[0],
      mid[1],
      str(handle),
      fontsize=HANDLE_LABEL_FONTSIZE,
      ha="center",
      va="center",
      color="#222222",
      zorder=10,
      bbox={
        "boxstyle": "round,pad=0.15",
        "facecolor": "white",
        "edgecolor": "none",
        "alpha": 0.75,
      },
    )


def visualize_straight_wall(
  wall_doc: dict[str, Any],
  residual_doc: dict[str, Any],
  save_path: str | Path,
  *,
  prim_by_handle: dict[str, dict[str, Any]] | None = None,
  show_handles: bool = False,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """Draw straight_wall_geometry (colored) and residual_geometry (gray)."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  walls = list(wall_doc.get("walls") or [])
  color_map = {
    str(w["wall_segment_id"]): _wall_colors(len(walls))[idx]
    for idx, w in enumerate(walls)
  }

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  for row in residual_doc.get("elements") or []:
    eps = _seg_endpoints(row)
    if eps is None:
      continue
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=UNMERGED_COLOR, lw=LW_OTHER, alpha=0.75, zorder=2,
    )
    bounds.extend([eps[0], eps[1]])

  for row in walls:
    eps = _seg_endpoints(row)
    if eps is None:
      continue
    ws_id = str(row.get("wall_segment_id", ""))
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=color_map.get(ws_id, UNMERGED_COLOR),
      lw=LW_MERGED_WALL, alpha=0.95, zorder=3,
    )
    bounds.extend([eps[0], eps[1]])

  if bounds:
    xs = [p[0] for p in bounds]
    ys = [p[1] for p in bounds]
    pad_x = max((max(xs) - min(xs)) * 0.02, 1.0)
    pad_y = max((max(ys) - min(ys)) * 0.02, 1.0)
    ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
    ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)

  if show_handles and prim_by_handle:
    _draw_handle_labels(ax, prim_by_handle)

  n_wall = len(walls)
  n_res = len(residual_doc.get("elements") or [])
  ax.set_title(
    title or f"Straight wall: walls={n_wall}, residual={n_res}",
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=_wall_colors(1)[0], lw=LW_MERGED_WALL, label="straight wall"),
    Line2D([0], [0], color=UNMERGED_COLOR, lw=LW_OTHER, label="other"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


def visualize_parallel_graph(
  graph: Any,
  parallel_groups: list[list[str]],
  save_path: str | Path,
  *,
  title: str | None = None,
  show_wall_ids: bool = False,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """Color each parallel wall group; stubs in gray; label wall nodes with WS***."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  node_to_group: dict[str, int] = {}
  for gi, group in enumerate(parallel_groups):
    for node_id in group:
      node_to_group[str(node_id)] = gi
  colors = _wall_colors(max(len(parallel_groups), 1))

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  for node_id, data in graph.nodes(data=True):
    start = data.get("start")
    end = data.get("end")
    if start is None or end is None:
      continue
    p0 = (float(start[0]), float(start[1]))
    p1 = (float(end[0]), float(end[1]))
    node_type = str(data.get("node_type", ""))
    if node_type == "stub":
      color = UNMERGED_COLOR
      lw = LW_STUB
      alpha = 0.65
      zorder = 1
    elif node_id in node_to_group:
      color = colors[node_to_group[node_id] % len(colors)]
      lw = LW_PARALLEL_WALL
      alpha = 0.95
      zorder = 3
    else:
      color = "#cfcfcf"
      lw = 1.2
      alpha = 0.8
      zorder = 2
    ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=color, lw=lw, alpha=alpha, zorder=zorder)
    bounds.extend([p0, p1])
    if show_wall_ids and node_type == "wall":
      mid = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
      ax.text(
        mid[0],
        mid[1],
        str(node_id),
        fontsize=WS_ID_LABEL_FONTSIZE,
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

  if bounds:
    xs = [p[0] for p in bounds]
    ys = [p[1] for p in bounds]
    pad_x = max((max(xs) - min(xs)) * 0.02, 1.0)
    pad_y = max((max(ys) - min(ys)) * 0.02, 1.0)
    ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
    ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)

  ax.set_title(title or f"parallel groups={len(parallel_groups)}", fontsize=12)
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=colors[0], lw=LW_PARALLEL_WALL, label="parallel wall group"),
    Line2D([0], [0], color="#cfcfcf", lw=1.2, label="wall (no parallel group)"),
    Line2D([0], [0], color=UNMERGED_COLOR, lw=LW_STUB, label="stub"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


def visualize_corridors(
  wall_doc: dict[str, Any],
  corridors_doc: dict[str, Any],
  main_doc: dict[str, Any],
  save_path: str | Path,
  *,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """Draw walls (gray), corridor centrelines (blue), main corridor (red thick)."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  main_id = corridors_doc.get("main_corridor_id")
  main = (main_doc.get("main_corridor") or {}) if main_id else {}
  main_walls = set(main.get("left_wall_segment_ids") or []) | set(main.get("right_wall_segment_ids") or [])

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  for row in wall_doc.get("walls") or []:
    eps = _seg_endpoints(row)
    if eps is None:
      continue
    ws_id = str(row.get("wall_segment_id", ""))
    color = "#e74c3c" if ws_id in main_walls else "#bdbdbd"
    lw = 2.5 if ws_id in main_walls else 1.0
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=color, lw=lw, alpha=0.9, zorder=2,
    )
    bounds.extend([eps[0], eps[1]])

  for corridor in corridors_doc.get("corridors") or []:
    cid = str(corridor.get("corridor_id", ""))
    start = corridor.get("centreline_start")
    end = corridor.get("centreline_end")
    if start is None or end is None:
      continue
    is_main = cid == main_id
    ax.plot(
      [start[0], end[0]], [start[1], end[1]],
      color="#c0392b" if is_main else "#2980b9",
      lw=4.0 if is_main else 1.5,
      alpha=0.95 if is_main else 0.7,
      zorder=4 if is_main else 3,
    )
    bounds.extend([(float(start[0]), float(start[1])), (float(end[0]), float(end[1]))])

  if bounds:
    xs = [p[0] for p in bounds]
    ys = [p[1] for p in bounds]
    pad_x = max((max(xs) - min(xs)) * 0.02, 1.0)
    pad_y = max((max(ys) - min(ys)) * 0.02, 1.0)
    ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
    ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)

  n_corr = len(corridors_doc.get("corridors") or [])
  ax.set_title(
    title or f"Corridors={n_corr}, main={main_id or 'none'}",
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color="#bdbdbd", lw=1.0, label="wall"),
    Line2D([0], [0], color="#e74c3c", lw=2.5, label="main corridor walls"),
    Line2D([0], [0], color="#2980b9", lw=1.5, label="corridor centreline"),
    Line2D([0], [0], color="#c0392b", lw=4.0, label="main corridor"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path
