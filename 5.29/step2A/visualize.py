"""Step 2A overview PNG: normalized LINE segments + bend markers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

LINE_COLOR = "#1f77b4"
FILLET_MARKER_COLOR = "#d62728"
SQUARE_MARKER_COLOR = "#1f77b4"


def _seg_endpoints(row: dict[str, Any]) -> tuple[tuple[float, float], tuple[float, float]] | None:
  attrs = row.get("attributes") or {}
  start = attrs.get("start") or row.get("start")
  end = attrs.get("end") or row.get("end")
  if start is None or end is None:
    return None
  return (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))


def _draw_segment(
  ax,
  start: tuple[float, float],
  end: tuple[float, float],
  *,
  color: str,
  lw: float,
  bounds: list[tuple[float, float]],
) -> None:
  ax.plot([start[0], end[0]], [start[1], end[1]], color=color, lw=lw, solid_capstyle="round")
  bounds.extend([start, end])


def _load_bends(doc: dict[str, Any] | None) -> list[dict[str, Any]]:
  if not doc:
    return []
  if doc.get("bends"):
    return list(doc["bends"])
  markers: list[dict[str, Any]] = []
  for row in doc.get("arcs") or []:
    if row.get("status") != "fillet":
      continue
    bp = row.get("bend_point")
    if not bp:
      continue
    markers.append({
      "kind": "fillet",
      "id": row.get("id"),
      "bend_point": bp,
      "line1": row.get("line1"),
      "line2": row.get("line2"),
      "source_arc": row.get("arc_handle"),
      "confidence": row.get("confidence"),
    })
  return markers


def visualize_step2a_overall(
  normalized_geometry_doc: dict[str, Any],
  square_bend_doc: dict[str, Any] | None,
  arc_bend_doc: dict[str, Any] | None,
  save_path: str | Path,
  *,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
  show_labels: bool = False,
  label_fontsize: float = 5.0,
) -> Path:
  """Overview: merged normalized LINE segments and bend markers."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  fig, ax = plt.subplots(figsize=figsize)
  segment_bounds: list[tuple[float, float]] = []
  line_count = 0

  for row in normalized_geometry_doc.get("elements") or []:
    if str(row.get("type", "")).upper() != "LINE":
      continue
    eps = _seg_endpoints(row)
    if eps is None:
      continue
    _draw_segment(ax, eps[0], eps[1], color=LINE_COLOR, lw=0.8, bounds=segment_bounds)
    line_count += 1

  n_fillet = 0
  n_square = 0
  for marker in _load_bends(square_bend_doc) + _load_bends(arc_bend_doc):
    bp = marker.get("bend_point")
    if not bp:
      continue
    bx, by = float(bp[0]), float(bp[1])
    kind = str(marker.get("kind", ""))
    label = str(marker.get("id", ""))
    if kind == "fillet":
      color = FILLET_MARKER_COLOR
      n_fillet += 1
    else:
      color = SQUARE_MARKER_COLOR
      n_square += 1
    ax.plot(bx, by, "o", color=color, markersize=4, zorder=4)
    if show_labels:
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

  if segment_bounds:
    xs = [p[0] for p in segment_bounds]
    ys = [p[1] for p in segment_bounds]
    pad_x = max((max(xs) - min(xs)) * 0.02, 1.0)
    pad_y = max((max(ys) - min(ys)) * 0.02, 1.0)
    ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
    ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)

  ax.set_title(
    title or (
      f"Step 2A overall: lines={line_count}, "
      f"bends fillet={n_fillet}, square={n_square}"
    ),
    fontsize=12,
  )
  ax.set_aspect("equal")
  ax.grid(True, alpha=0.2, linestyle=":")
  legend = [
    Line2D([0], [0], color=LINE_COLOR, lw=0.9, label="normalized LINE"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor=FILLET_MARKER_COLOR,
           markersize=6, label="Y fillet"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor=SQUARE_MARKER_COLOR,
           markersize=6, label="Y square"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path
