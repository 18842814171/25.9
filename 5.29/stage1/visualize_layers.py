"""Draw DXF geometry: classifier label 1 = red, 0 = grey."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf
import matplotlib.pyplot as plt
import numpy as np
from ezdxf import select

from .dxf_inventory import _window_from_corners

DRAW_TYPES = frozenset({"LINE", "LWPOLYLINE", "ARC", "POLYLINE"})
COLOR_POS = "#e53935"  # red
COLOR_NEG = "#9e9e9e"  # grey
LW_POS = 0.6
LW_NEG = 0.25
ALPHA_POS = 0.85
ALPHA_NEG = 0.35


def _plot_entity(ax, entity, color: str, lw: float, alpha: float) -> None:
  et = entity.dxftype()
  try:
    if et == "LINE":
      x = [entity.dxf.start.x, entity.dxf.end.x]
      y = [entity.dxf.start.y, entity.dxf.end.y]
      ax.plot(x, y, color=color, linewidth=lw, alpha=alpha, solid_capstyle="round")
    elif et == "LWPOLYLINE":
      pts = list(entity.get_points(format="xy"))
      if len(pts) < 2:
        return
      xs = [p[0] for p in pts]
      ys = [p[1] for p in pts]
      ax.plot(xs, ys, color=color, linewidth=lw, alpha=alpha, solid_capstyle="round")
    elif et == "ARC":
      s = entity.start_point
      e = entity.end_point
      ax.plot([s.x, e.x], [s.y, e.y], color=color, linewidth=lw, alpha=alpha, linestyle="--")
    elif et == "POLYLINE":
      verts = [v.dxf.location for v in entity.vertices]
      if len(verts) < 2:
        return
      xs = [v.x for v in verts]
      ys = [v.y for v in verts]
      ax.plot(xs, ys, color=color, linewidth=lw, alpha=alpha)
  except Exception:
    return


def visualize_layer_classification(
  dxf_path: str | Path,
  predictions: dict[str, dict[str, Any]],
  save_path: str | Path,
  window_corners: tuple | None = None,
  figsize: tuple[float, float] = (14, 10),
  dpi: int = 150,
) -> Path:
  """
  predictions: {layer_name: {"label": 0|1, "probability": float}, ...}
  """
  dxf_path = Path(dxf_path)
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  doc = ezdxf.readfile(str(dxf_path))
  msp = doc.modelspace()

  if window_corners is not None:
    win = _window_from_corners(window_corners)
    entities = list(select.bbox_inside(win, msp))
  else:
    entities = list(msp)

  # Draw grey (0) first, red (1) on top
  fig, ax = plt.subplots(figsize=figsize)

  n0 = n1 = 0
  for entity in entities:
    if entity.dxftype() not in DRAW_TYPES:
      continue
    layer = entity.dxf.layer.strip() if hasattr(entity.dxf, "layer") else "0"
    pred = predictions.get(layer, {}).get("label", 0)
    if pred == 1:
      n1 += 1
    else:
      n0 += 1

  for entity in entities:
    if entity.dxftype() not in DRAW_TYPES:
      continue
    layer = entity.dxf.layer.strip() if hasattr(entity.dxf, "layer") else "0"
    if predictions.get(layer, {}).get("label", 0) != 0:
      continue
    _plot_entity(ax, entity, COLOR_NEG, LW_NEG, ALPHA_NEG)

  for entity in entities:
    if entity.dxftype() not in DRAW_TYPES:
      continue
    layer = entity.dxf.layer.strip() if hasattr(entity.dxf, "layer") else "0"
    if predictions.get(layer, {}).get("label", 0) != 1:
      continue
    _plot_entity(ax, entity, COLOR_POS, LW_POS, ALPHA_POS)

  pos_layers = [n for n, p in predictions.items() if p.get("label") == 1]
  ax.set_aspect("equal", adjustable="datalim")
  ax.axis("off")
  ax.set_title(f"Layer classification: red=corridor (1), grey=other (0); {len(pos_layers)} corridor layers")

  from matplotlib.lines import Line2D

  ax.legend(
    handles=[
      Line2D([0], [0], color=COLOR_POS, lw=2, label=f"corridor (1), {n1} entities"),
      Line2D([0], [0], color=COLOR_NEG, lw=2, label=f"non-corridor (0), {n0} entities"),
    ],
    loc="upper right",
    fontsize=8,
  )

  plt.tight_layout()
  plt.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path
