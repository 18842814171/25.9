"""
Stage 2 line-only visualizations (main geometry path).

No circles, squares, or markers — polylines only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib.lines import Line2D

WALL_LINE_COLOR = "#2c3e50"
ISOLATED_STUB_COLOR = "#e67e22"
ENDPOINT_LINK_COLOR = "#95a5a6"
UNGROUPED_SEGMENT_COLOR = "#bdc3c7"


def _xy2(p) -> tuple[float, float]:
  return float(p[0]), float(p[1])


def _apply_data_bounds(
  ax,
  points: list[tuple[float, float]],
  *,
  pad_ratio: float = 0.03,
) -> None:
  if not points:
    return
  xs = np.array([p[0] for p in points], dtype=float)
  ys = np.array([p[1] for p in points], dtype=float)
  lo_x, hi_x = np.percentile(xs, [1, 99])
  lo_y, hi_y = np.percentile(ys, [1, 99])
  dx = max(hi_x - lo_x, 1.0)
  dy = max(hi_y - lo_y, 1.0)
  ax.set_xlim(lo_x - dx * pad_ratio, hi_x + dx * pad_ratio)
  ax.set_ylim(lo_y - dy * pad_ratio, hi_y + dy * pad_ratio)


def _draw_geometry_records(
  ax,
  records: list[dict[str, Any]],
  bounds: list[tuple[float, float]],
  *,
  color: str,
  linewidth: float = 1.0,
  alpha: float = 0.9,
  zorder: int = 2,
) -> None:
  for rec in records:
    etype = str(rec.get("type", "LINE")).upper()
    attrs = rec.get("attributes", {})
    start, end = attrs.get("start"), attrs.get("end")
    if not start or not end:
      continue
    x0, y0 = _xy2(start)
    x1, y1 = _xy2(end)
    ls = "--" if etype == "ARC" else "-"
    ax.plot(
      [x0, x1], [y0, y1],
      color=color,
      linewidth=linewidth,
      linestyle=ls,
      alpha=alpha,
      zorder=zorder,
    )
    bounds.extend([(x0, y0), (x1, y1)])


def _draw_cluster_polylines(
  ax,
  clusters: list[dict[str, Any]],
  bounds: list[tuple[float, float]],
  *,
  color: str,
  linewidth: float = 1.4,
  zorder: int = 3,
) -> None:
  """Draw clusters as 2-point or 3-point polylines (no raw arc geometry)."""
  for cluster in clusters:
    ep1 = cluster.get("endpoint1")
    ep2 = cluster.get("endpoint2")
    bend_point = cluster.get("bend_point")
    bend_kind = cluster.get("bend_kind", "line")

    if bend_kind in ("方折", "圆角") and ep1 and ep2 and bend_point:
      xs = [float(ep1[0]), float(bend_point[0]), float(ep2[0])]
      ys = [float(ep1[1]), float(bend_point[1]), float(ep2[1])]
    elif ep1 and ep2:
      xs = [float(ep1[0]), float(ep2[0])]
      ys = [float(ep1[1]), float(ep2[1])]
    else:
      continue

    ax.plot(xs, ys, color=color, linewidth=linewidth, alpha=0.95, zorder=zorder)
    bounds.extend([(xs[i], ys[i]) for i in range(len(xs))])


def _draw_wall_and_stub_background(
  ax,
  wall_lines: list[dict[str, Any]],
  stubs: list[dict[str, Any]],
  bounds: list[tuple[float, float]],
  *,
  wall_color: str = WALL_LINE_COLOR,
  stub_color: str = ISOLATED_STUB_COLOR,
  wall_linewidth: float = 1.2,
  stub_linewidth: float = 0.9,
) -> None:
  _draw_geometry_records(
    ax, wall_lines, bounds,
    color=wall_color, linewidth=wall_linewidth, alpha=0.95, zorder=2,
  )
  _draw_geometry_records(
    ax, stubs, bounds,
    color=stub_color, linewidth=stub_linewidth, alpha=0.9, zorder=2,
  )


def visualize_wall_lines(
  wall_lines: list[dict[str, Any]],
  save_path: str | Path,
  *,
  stubs: list[dict[str, Any]] | None = None,
  title: str | None = None,
  figsize: tuple[float, float] = (16, 12),
  dpi: int = 200,
) -> Path:
  """Continuous wall lines and isolated stubs — distinct colors, no markers."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []
  stub_list = stubs or []
  _draw_wall_and_stub_background(ax, wall_lines, stub_list, bounds)

  _apply_data_bounds(ax, bounds)
  n_walls = len(wall_lines)
  n_stubs = len(stub_list)
  ax.set_title(
    title or f"Continuous walls: {n_walls}, isolated stubs: {n_stubs}",
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=WALL_LINE_COLOR, lw=1.2, label="Continuous wall line"),
  ]
  if stub_list:
    legend.append(
      Line2D([0], [0], color=ISOLATED_STUB_COLOR, lw=0.9, label="Isolated stub"),
    )
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


FILLET_MARKER_COLOR = "#c0392b"
SQUARE_MARKER_COLOR = "#2980b9"


def visualize_step2a_overview(
  wall_lines: list[dict[str, Any]],
  bend_markers: list[dict[str, Any]],
  save_path: str | Path,
  *,
  stubs: list[dict[str, Any]] | None = None,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
  label_fontsize: float = 5.0,
) -> Path:
  """
  Full-map Step 2A view: wall lines, optional stubs, bend markers with ids.

  Fillet markers: red; square markers: blue.  Id format ``Y0001`` (shared sequence).
  """
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []
  stub_list = stubs or []
  _draw_wall_and_stub_background(ax, wall_lines, stub_list, bounds)

  n_fillet = 0
  n_square = 0
  for marker in bend_markers:
    bp = marker.get("bend_point")
    if not bp:
      continue
    bx, by = float(bp[0]), float(bp[1])
    bounds.append((bx, by))
    kind = str(marker.get("kind", ""))
    label = str(marker.get("id", ""))
    if kind == "fillet":
      color = FILLET_MARKER_COLOR
      n_fillet += 1
    else:
      color = SQUARE_MARKER_COLOR
      n_square += 1
    ax.plot(bx, by, "o", color=color, markersize=4, zorder=4)
    ax.annotate(
      label,
      (bx, by),
      textcoords="offset points",
      xytext=(2, 2),
      fontsize=label_fontsize,
      color=color,
      alpha=0.85,
      zorder=5,
    )

  _apply_data_bounds(ax, bounds)
  n_walls = len(wall_lines)
  ax.set_title(
    title or (
      f"Step 2A: wall_lines={n_walls}, bend Y fillet={n_fillet}, square={n_square}"
    ),
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=WALL_LINE_COLOR, lw=1.2, label="wall_line"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor=FILLET_MARKER_COLOR,
           markersize=6, label="Y fillet"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor=SQUARE_MARKER_COLOR,
           markersize=6, label="Y square"),
  ]
  if stub_list:
    legend.append(
      Line2D([0], [0], color=ISOLATED_STUB_COLOR, lw=0.9, label="isolated stub"),
    )
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


def _seg_by_handle(info: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
  return {str(seg["handle"]): seg for seg in info}


def _draw_info_segment(
  ax,
  seg: dict[str, Any],
  bounds: list[tuple[float, float]],
  *,
  color: str,
  linewidth: float = 1.2,
  linestyle: str = "-",
  zorder: int = 2,
) -> None:
  start = np.asarray(seg["start"][:2], dtype=float)
  end = np.asarray(seg["end"][:2], dtype=float)
  x0, y0 = float(start[0]), float(start[1])
  x1, y1 = float(end[0]), float(end[1])
  ax.plot([x0, x1], [y0, y1], color=color, linewidth=linewidth, linestyle=linestyle, zorder=zorder)
  bounds.extend([(x0, y0), (x1, y1)])


def visualize_bend_marker_local(
  marker: dict[str, Any],
  info: list[dict[str, Any]],
  save_path: str | Path,
  *,
  margin: float = 15.0,
  dpi: int = 160,
) -> Path:
  """Local debug view: wall segments, optional arc chord, bend point marker."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)
  by_handle = _seg_by_handle(info)

  fig, ax = plt.subplots(figsize=(6, 6))
  bounds: list[tuple[float, float]] = []
  kind = str(marker.get("kind", ""))
  label = str(marker.get("id", ""))

  bp = np.asarray(marker["bend_point"][:2], dtype=float)
  for handle_key in ("line1", "line2"):
    handle = str(marker.get(handle_key, ""))
    seg = by_handle.get(handle)
    if seg is None:
      continue
    eps = [np.asarray(p, dtype=float)[:2] for p in seg["endpoints"]]
    d0, d1 = float(np.linalg.norm(eps[0] - bp)), float(np.linalg.norm(eps[1] - bp))
    far = eps[0] if d0 >= d1 else eps[1]
    row = {"start": far, "end": bp, "endpoints": [far, bp]}
    if float(np.linalg.norm(far - bp)) < 1e-8:
      continue
    _draw_info_segment(ax, row, bounds, color=WALL_LINE_COLOR, linewidth=1.4)

  if kind == "fillet":
    arc_handle = str(marker.get("source_arc", ""))
    arc_seg = by_handle.get(arc_handle)
    if arc_seg is not None:
      _draw_info_segment(
        ax, arc_seg, bounds,
        color="#7f8c8d", linewidth=1.0, linestyle="--",
      )

  bx, by = float(bp[0]), float(bp[1])
  bounds.append((bx, by))
  ax.plot(bx, by, "o", color="#c0392b", markersize=8, zorder=5)
  kind_label = "fillet" if kind == "fillet" else "square"
  ax.annotate(
    label,
    (bx, by),
    textcoords="offset points",
    xytext=(6, 6),
    fontsize=10,
    color="#c0392b",
    fontweight="bold",
  )

  if bounds:
    xs = [p[0] for p in bounds]
    ys = [p[1] for p in bounds]
    lo_x, hi_x = min(xs) - margin, max(xs) + margin
    lo_y, hi_y = min(ys) - margin, max(ys) + margin
    ax.set_xlim(lo_x, hi_x)
    ax.set_ylim(lo_y, hi_y)

  ax.set_title(f"{label} ({kind_label})", fontsize=11)
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.25, linestyle=":")
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


visualize_corner_local = visualize_bend_marker_local


def visualize_corners_debug(
  markers: list[dict[str, Any]],
  info: list[dict[str, Any]],
  debug_dir: str | Path,
  stem: str,
) -> list[Path]:
  """Write one local PNG per bend marker under ``debug_dir``."""
  debug_dir = Path(debug_dir)
  debug_dir.mkdir(parents=True, exist_ok=True)
  paths: list[Path] = []
  for marker in markers:
    mid = str(marker.get("id", "unknown"))
    out = debug_dir / f"{stem}_{mid}.png"
    paths.append(visualize_bend_marker_local(marker, info, out))
  return paths


def visualize_stub_clusters(
  clusters: list[dict[str, Any]],
  wall_lines: list[dict[str, Any]],
  stubs: list[dict[str, Any]],
  save_path: str | Path,
  *,
  title: str | None = None,
  cluster_color: str = "#8e44ad",
  figsize: tuple[float, float] = (16, 12),
  dpi: int = 200,
) -> Path:
  """
  Background = wall lines + all isolated stubs (distinct colors); colored = cluster polylines.
  Bend clusters use 3-point polylines; no circles or markers.
  """
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  _draw_wall_and_stub_background(
    ax, wall_lines, stubs, bounds,
    wall_linewidth=1.0, stub_linewidth=0.8,
  )
  _draw_cluster_polylines(
    ax, clusters, bounds, color=cluster_color, linewidth=1.4, zorder=3,
  )

  _apply_data_bounds(ax, bounds)
  ax.set_title(title or f"Stub clusters: {len(clusters)}", fontsize=12)
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=cluster_color, lw=1.4, label="Cluster polyline"),
    Line2D([0], [0], color=WALL_LINE_COLOR, lw=1.0, label="Continuous wall line"),
    Line2D([0], [0], color=ISOLATED_STUB_COLOR, lw=0.8, label="Isolated stub"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


def _node_endpoints(node: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
  start = np.array(node["start"][:2], dtype=float)
  end = np.array(node["end"][:2], dtype=float)
  return start, end


def _closest_endpoint_pair(
  nu: dict[str, Any],
  nv: dict[str, Any],
) -> tuple[tuple[float, float], tuple[float, float]]:
  pts1 = [_node_endpoints(nu)[0], _node_endpoints(nu)[1]]
  pts2 = [_node_endpoints(nv)[0], _node_endpoints(nv)[1]]
  best: tuple[tuple[float, float], tuple[float, float]] | None = None
  best_dist = float("inf")
  for p1 in pts1:
    for p2 in pts2:
      dist = float(np.linalg.norm(p1 - p2))
      if dist < best_dist:
        best_dist = dist
        best = (_xy2(p1), _xy2(p2))
  if best is None:
    return (0.0, 0.0), (0.0, 0.0)
  return best


def _wall_group_colors(
  wall_groups: list[set[int]] | None,
) -> dict[int, Any]:
  colors: dict[int, Any] = {}
  if not wall_groups:
    return colors
  cmap = plt.cm.tab20
  for gi, members in enumerate(wall_groups):
    color = cmap(gi % 20)
    for nid in members:
      colors[int(nid)] = color
  return colors


def visualize_endpoint_graph(
  graph: nx.Graph,
  save_path: str | Path,
  *,
  wall_groups: list[set[int]] | None = None,
  title: str | None = None,
  figsize: tuple[float, float] = (16, 12),
  dpi: int = 200,
) -> Path:
  """
  Draw the endpoint-adjacency graph from a saved ``.pkl``.

  Segments are colored by continuous wall group; dashed chords = arcs;
  thin gray links = endpoint adjacency edges.
  """
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []
  group_colors = _wall_group_colors(wall_groups)
  n_endpoint_edges = 0

  for u, v in graph.edges:
    p0, p1 = _closest_endpoint_pair(graph.nodes[u], graph.nodes[v])
    ax.plot(
      [p0[0], p1[0]], [p0[1], p1[1]],
      color=ENDPOINT_LINK_COLOR,
      linewidth=0.5,
      alpha=0.55,
      zorder=1,
    )
    bounds.extend([p0, p1])
    n_endpoint_edges += 1

  for nid, data in graph.nodes(data=True):
    start, end = _node_endpoints(data)
    x0, y0 = _xy2(start)
    x1, y1 = _xy2(end)
    geo_type = str(data.get("geo_type", "line")).lower()
    ls = "--" if geo_type == "arc" else "-"
    color = group_colors.get(int(nid), UNGROUPED_SEGMENT_COLOR)
    ax.plot(
      [x0, x1], [y0, y1],
      color=color,
      linewidth=1.1,
      linestyle=ls,
      alpha=0.95,
      zorder=2,
    )
    bounds.extend([(x0, y0), (x1, y1)])

  _apply_data_bounds(ax, bounds)
  n_groups = len(wall_groups) if wall_groups else 0
  ax.set_title(
    title or (
      f"Endpoint graph: {graph.number_of_nodes()} segs, "
      f"{n_endpoint_edges} links, {n_groups} wall groups"
    ),
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=ENDPOINT_LINK_COLOR, lw=0.8, label="Endpoint link"),
    Line2D([0], [0], color="C0", lw=1.1, label="Wall group segment"),
    Line2D([0], [0], color=UNGROUPED_SEGMENT_COLOR, lw=1.1, label="Ungrouped segment"),
    Line2D([0], [0], color="C0", lw=1.1, linestyle="--", label="Arc (chord)"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path
