"""Stage 4 attached-regions overlay visualization."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D

from stage4.corrected_centerlines import (
  NODE_CENTERLINE,
  NODE_STRUCTURE,
  ROLE_AUXILIARY,
  ROLE_CORRIDOR,
  ROLE_NICHE,
  ROLE_UNCLASSIFIED,
  STRUCT_CROSSBAR,
  STRUCT_NICHE,
  STRUCT_UNKNOWN,
)
from stage4.stub_classify import (
  SEM_AUXILIARY_CORRIDOR,
  SEM_NICHE,
  SEM_POSSIBLE_CORRIDOR_WALL,
  SEM_UNCLASSIFIED,
)
from utils.plot_bounds import apply_plot_bounds as _apply_bounds

SEM_COLORS = {
  SEM_NICHE: "#9467bd",
  SEM_POSSIBLE_CORRIDOR_WALL: "#2ca02c",
  SEM_AUXILIARY_CORRIDOR: "#ff7f0e",
  SEM_UNCLASSIFIED: "#aaaaaa",
}
WALL_COLOR = "#878787"
CENTERLINE_COLOR = "#1f77b4"
CENTERLINE_LW = 1.2
STUB_LW = 2.4
HANDLE_LABEL_FONTSIZE = 5


def _cjk_font_properties():
  """Return FontProperties for an installed CJK font, if any."""
  from matplotlib import font_manager

  patterns = ("msyh", "simhei", "microsoft yahei", "noto sans cjk", "pingfang")
  for font in font_manager.fontManager.ttflist:
    name = str(font.name).lower()
    path = str(font.fname).lower()
    if any(p in name or p in path for p in patterns):
      return font_manager.FontProperties(fname=font.fname)
  return None


def _configure_plot_font():
  """Prefer a CJK font when available (Windows-friendly)."""
  prop = _cjk_font_properties()
  if prop is not None:
    family = prop.get_name()
    plt.rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
  else:
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
  plt.rcParams["axes.unicode_minus"] = False
  return prop


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


def _seg_midpoint(
  eps: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float]:
  return (
    (eps[0][0] + eps[1][0]) / 2.0,
    (eps[0][1] + eps[1][1]) / 2.0,
  )


def _draw_stub_handle_labels(
  ax: plt.Axes,
  semantic_graph: nx.Graph,
) -> None:
  """Label every stub at its midpoint with its handle."""
  for nid, data in semantic_graph.nodes(data=True):
    if str(data.get("node_type", "")) != "stub":
      continue
    eps = _node_eps(semantic_graph, str(nid))
    if eps is None:
      continue
    mid = _seg_midpoint(eps)
    ax.text(
      mid[0],
      mid[1],
      str(nid),
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


def visualize_attached_regions(
  semantic_graph: nx.Graph,
  centerline_graph: nx.Graph,
  save_path: str | Path,
  *,
  label: bool = False,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  for nid, data in centerline_graph.nodes(data=True):
    if data.get("node_type") != "corridor":
      continue
    eps = _node_eps(centerline_graph, str(nid))
    if eps is None:
      continue
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=CENTERLINE_COLOR, lw=CENTERLINE_LW, alpha=0.55, zorder=1,
    )
    bounds.extend([eps[0], eps[1]])

  for nid, data in semantic_graph.nodes(data=True):
    node_type = str(data.get("node_type", ""))
    eps = _node_eps(semantic_graph, str(nid))
    if eps is None:
      continue
    if node_type == "wall":
      ax.plot(
        [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
        color=WALL_COLOR, lw=0.7, alpha=0.35, zorder=2,
      )
      bounds.extend([eps[0], eps[1]])
      continue
    if node_type != "stub":
      continue
    sem = str(data.get("region_semantic") or SEM_UNCLASSIFIED)
    color = SEM_COLORS.get(sem, SEM_COLORS[SEM_UNCLASSIFIED])
    alpha = 0.95 if sem != SEM_UNCLASSIFIED else 0.55
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=color, lw=STUB_LW, alpha=alpha, linestyle="-", zorder=4,
    )
    bounds.extend([eps[0], eps[1]])

  if label:
    _draw_stub_handle_labels(ax, semantic_graph)

  _apply_bounds(ax, bounds)
  ax.set_aspect("equal")
  ax.set_title(title or "Stage 4 attached regions")
  ax.axis("off")

  legend = [
    Line2D([0], [0], color=CENTERLINE_COLOR, lw=CENTERLINE_LW, label="centerline"),
    Line2D([0], [0], color=SEM_COLORS[SEM_NICHE], lw=STUB_LW, label="NICHE"),
    Line2D(
      [0], [0], color=SEM_COLORS[SEM_POSSIBLE_CORRIDOR_WALL], lw=STUB_LW,
      label="possible corridor wall",
    ),
    Line2D(
      [0], [0], color=SEM_COLORS[SEM_AUXILIARY_CORRIDOR], lw=STUB_LW,
      label="auxiliary corridor",
    ),
    Line2D([0], [0], color=SEM_COLORS[SEM_UNCLASSIFIED], lw=STUB_LW, label="unclassified"),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=8)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


STRUCT_COLORS = {
  STRUCT_NICHE: "#9467bd",
  STRUCT_CROSSBAR: "#ff7f0e",
  STRUCT_UNKNOWN: "#aaaaaa",
}
AUX_CENTERLINE_COLOR = "#17becf"

ROLE_COLORS = {
  ROLE_CORRIDOR: CENTERLINE_COLOR,
  ROLE_AUXILIARY: AUX_CENTERLINE_COLOR,
  ROLE_NICHE: STRUCT_COLORS[STRUCT_NICHE],
  ROLE_UNCLASSIFIED: STRUCT_COLORS[STRUCT_UNKNOWN],
}


def _node_role(data: dict) -> str:
  role = str(data.get("role") or "")
  if role in ROLE_COLORS:
    return role
  node_type = str(data.get("node_type", ""))
  if node_type == NODE_CENTERLINE:
    return (
      ROLE_AUXILIARY
      if str(data.get("corridor_role") or "main") == "auxiliary"
      else ROLE_CORRIDOR
    )
  kind = str(data.get("structure_kind") or STRUCT_UNKNOWN)
  if kind == STRUCT_NICHE:
    return ROLE_NICHE
  if kind == STRUCT_CROSSBAR:
    return ROLE_AUXILIARY
  return ROLE_UNCLASSIFIED


def _niche_label_handle(data: dict, nid: str) -> str | None:
  """Return handle to label for a niche; for U-chains only the middle segment."""
  handle = str(data.get("handle") or nid)
  chain = [str(h) for h in (data.get("niche_chain") or data.get("shape_handles") or [])]
  if len(chain) >= 3:
    # niche_chain = [leg_a, mid, leg_c]; annotate the back/mid segment only
    return chain[1] if handle == chain[1] else None
  return handle


def _draw_auxiliary_and_niche_labels(
  ax: plt.Axes,
  tunnel_graph: nx.Graph,
  *,
  font_prop=None,
) -> None:
  """Label auxiliary corridors and niche structures on corrected centerlines map."""
  for nid, data in tunnel_graph.nodes(data=True):
    eps = _node_eps(tunnel_graph, str(nid))
    if eps is None:
      continue
    mid = _seg_midpoint(eps)
    node_type = str(data.get("node_type", ""))

    if node_type == NODE_CENTERLINE:
      if str(data.get("corridor_role") or "main") != "auxiliary":
        continue
      cid = str(data.get("corridor_id") or nid)
      text = f"Aux {cid}"
      color = "#0d4f5c"
    elif node_type == NODE_STRUCTURE:
      if str(data.get("structure_kind") or "") != STRUCT_NICHE:
        continue
      label_handle = _niche_label_handle(data, str(nid))
      if label_handle is None:
        continue
      text = f"Ch {label_handle}"
      color = "#4a235a"
    else:
      continue

    ax.text(
      mid[0],
      mid[1],
      text,
      fontsize=HANDLE_LABEL_FONTSIZE,
      ha="center",
      va="center",
      color=color,
      zorder=10,
      fontproperties=font_prop,
      bbox={
        "boxstyle": "round,pad=0.15",
        "facecolor": "white",
        "edgecolor": "none",
        "alpha": 0.8,
      },
    )


def visualize_corrected_centerlines(
  tunnel_graph: nx.Graph,
  save_path: str | Path,
  *,
  label: bool = False,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """Draw corrected centerlines tunnel graph (geometry only, no logical edges)."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)
  _configure_plot_font()
  font_prop = _cjk_font_properties()

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  for nid, data in tunnel_graph.nodes(data=True):
    eps = _node_eps(tunnel_graph, str(nid))
    if eps is None:
      continue
    role = _node_role(data)
    color = ROLE_COLORS.get(role, ROLE_COLORS[ROLE_UNCLASSIFIED])
    if data.get("node_type") == NODE_CENTERLINE:
      lw = CENTERLINE_LW + (0.4 if role == ROLE_AUXILIARY else 0.0)
      zorder = 3
    else:
      lw = STUB_LW
      zorder = 4
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=color, lw=lw, alpha=0.9, zorder=zorder,
    )
    bounds.extend([eps[0], eps[1]])

  if label:
    _draw_auxiliary_and_niche_labels(ax, tunnel_graph, font_prop=font_prop)

  _apply_bounds(ax, bounds)
  ax.set_aspect("equal")
  roles = tunnel_graph.graph.get("role_counts") or {}
  ax.set_title(
    title
    or (
      f"corrected centerlines"
      f"{' (labeled)' if label else ''} — "
      f"Corr={roles.get(ROLE_CORRIDOR, 0)} "
      f"Aux={roles.get(ROLE_AUXILIARY, 0)} "
      f"Ch={roles.get(ROLE_NICHE, 0)} "
      f"Unc={roles.get(ROLE_UNCLASSIFIED, 0)}"
    ),
  )
  ax.axis("off")

  legend = [
    Line2D([0], [0], color=ROLE_COLORS[ROLE_CORRIDOR], lw=CENTERLINE_LW, label="corridor"),
    Line2D(
      [0], [0], color=ROLE_COLORS[ROLE_AUXILIARY], lw=CENTERLINE_LW + 0.4,
      label="auxiliary (Aux)",
    ),
    Line2D([0], [0], color=ROLE_COLORS[ROLE_NICHE], lw=STUB_LW, label="niche (Ch)"),
    Line2D(
      [0], [0], color=ROLE_COLORS[ROLE_UNCLASSIFIED], lw=STUB_LW,
      label="unclassified (Unc)",
    ),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=7, prop=font_prop)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path


def visualize_structure_graph(
  tunnel_graph: nx.Graph,
  save_path: str | Path,
  *,
  label: bool = False,
  title: str | None = None,
  figsize: tuple[float, float] = (20, 14),
  dpi: int = 200,
) -> Path:
  """Draw structure graph: corridor / auxiliary / niche / unclassified (geometry only)."""
  save_path = Path(save_path)
  save_path.parent.mkdir(parents=True, exist_ok=True)
  _configure_plot_font()
  font_prop = _cjk_font_properties()

  fig, ax = plt.subplots(figsize=figsize)
  bounds: list[tuple[float, float]] = []

  for nid, data in tunnel_graph.nodes(data=True):
    eps = _node_eps(tunnel_graph, str(nid))
    if eps is None:
      continue
    role = _node_role(data)
    color = ROLE_COLORS.get(role, ROLE_COLORS[ROLE_UNCLASSIFIED])
    lw = CENTERLINE_LW + (
      0.4 if role == ROLE_AUXILIARY and data.get("node_type") == NODE_CENTERLINE else 0.0
    )
    if data.get("node_type") == NODE_STRUCTURE:
      lw = STUB_LW
    ax.plot(
      [eps[0][0], eps[1][0]], [eps[0][1], eps[1][1]],
      color=color, lw=lw, alpha=0.9, zorder=3,
    )
    bounds.extend([eps[0], eps[1]])

  if label:
    _draw_auxiliary_and_niche_labels(ax, tunnel_graph, font_prop=font_prop)

  _apply_bounds(ax, bounds)
  ax.set_aspect("equal")
  roles = tunnel_graph.graph.get("role_counts") or {}
  ax.set_title(
    title
    or (
      "structure graph"
      f"{' (labeled)' if label else ''} — "
      f"Corr={roles.get(ROLE_CORRIDOR, 0)} "
      f"Aux={roles.get(ROLE_AUXILIARY, 0)} "
      f"Ch={roles.get(ROLE_NICHE, 0)} "
      f"Unc={roles.get(ROLE_UNCLASSIFIED, 0)}"
    ),
  )
  ax.axis("off")

  legend = [
    Line2D([0], [0], color=ROLE_COLORS[ROLE_CORRIDOR], lw=CENTERLINE_LW, label="corridor"),
    Line2D(
      [0], [0], color=ROLE_COLORS[ROLE_AUXILIARY], lw=CENTERLINE_LW + 0.4,
      label="auxiliary (Aux)",
    ),
    Line2D([0], [0], color=ROLE_COLORS[ROLE_NICHE], lw=STUB_LW, label="niche (Ch)"),
    Line2D(
      [0], [0], color=ROLE_COLORS[ROLE_UNCLASSIFIED], lw=STUB_LW,
      label="unclassified (Unc)",
    ),
  ]
  ax.legend(handles=legend, loc="upper right", fontsize=7, prop=font_prop)
  fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
  plt.close(fig)
  return save_path
