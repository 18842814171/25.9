"""Visualization for structure_graph_with_texts."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import networkx as nx

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.plot_font import setup_cjk_font

from config import Step1bConfig


def load_corridor_entities(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"corridor export must be a list: {path}")
    # 与 stage2 核对图一致：剔除飞出主体图幅的异常巷道图元
    from stage2.visualize import filter_corridor_spatial_outliers

    return filter_corridor_spatial_outliers(data)


def draw_corridors(
    ax,
    corridors: list[dict],
    color: str,
    linewidth: float,
) -> tuple[list[float], list[float]]:
    from matplotlib.patches import Arc

    xs: list[float] = []
    ys: list[float] = []
    for ent in corridors:
        et = ent.get("type")
        attrs = ent.get("attributes") or {}
        if et == "LINE":
            start = attrs.get("start") or []
            end = attrs.get("end") or []
            if len(start) < 2 or len(end) < 2:
                continue
            x0, y0 = float(start[0]), float(start[1])
            x1, y1 = float(end[0]), float(end[1])
            ax.plot([x0, x1], [y0, y1], color=color, linewidth=linewidth, zorder=0)
            xs.extend([x0, x1])
            ys.extend([y0, y1])
        elif et == "ARC":
            center = attrs.get("center") or []
            if len(center) < 2:
                continue
            cx, cy = float(center[0]), float(center[1])
            radius = float(attrs.get("radius") or 0.0)
            if radius <= 0:
                continue
            a0 = float(attrs.get("start_angle") or 0.0)
            a1 = float(attrs.get("end_angle") or 0.0)
            ax.add_patch(
                Arc(
                    (cx, cy),
                    2 * radius,
                    2 * radius,
                    angle=0.0,
                    theta1=a0,
                    theta2=a1,
                    color=color,
                    linewidth=linewidth,
                    zorder=0,
                )
            )
            for ang in (a0, a1, (a0 + a1) / 2.0):
                rad = math.radians(ang)
                xs.append(cx + radius * math.cos(rad))
                ys.append(cy + radius * math.sin(rad))
        elif et == "LWPOLYLINE":
            pts = attrs.get("points") or []
            if len(pts) < 2:
                continue
            xs_p = [float(p[0]) for p in pts if len(p) >= 2]
            ys_p = [float(p[1]) for p in pts if len(p) >= 2]
            if len(xs_p) < 2:
                continue
            ax.plot(xs_p, ys_p, color=color, linewidth=linewidth, zorder=0)
            xs.extend(xs_p)
            ys.extend(ys_p)
    return xs, ys


def draw_structure_graph_with_texts(
    graph: nx.Graph,
    out_png: Path,
    cfg: Step1bConfig | None = None,
    *,
    corridors: list[dict] | None = None,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Circle

    cfg = cfg or Step1bConfig()
    setup_cjk_font(cfg.figure_font_candidates)

    fig, ax = plt.subplots(figsize=(11, 9), dpi=cfg.figure_dpi)
    xs: list[float] = []
    ys: list[float] = []

    # 原始巷道图元（黑色）
    if corridors:
        cxs, cys = draw_corridors(
            ax,
            corridors,
            cfg.color_corridor_entities,
            cfg.corridor_entity_linewidth,
        )
        xs.extend(cxs)
        ys.extend(cys)

    # centerlines
    for _, data in graph.nodes(data=True):
        if data.get("node_type") != "centerline":
            continue
        start = data.get("start")
        end = data.get("end")
        if not start or not end:
            continue
        role = str(data.get("role") or "")
        if role == "auxiliary":
            color = cfg.color_centerline_auxiliary
        else:
            color = cfg.color_centerline_corridor
        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=cfg.centerline_linewidth,
            zorder=1,
        )
        xs.extend([start[0], end[0]])
        ys.extend([start[1], end[1]])

    # residual structure：洞室单独着色，其余灰色
    has_niche = False
    for _, data in graph.nodes(data=True):
        if data.get("node_type") != "structure":
            continue
        start = data.get("start")
        end = data.get("end")
        if not start or not end:
            continue
        role = str(data.get("role") or "")
        if role == "niche":
            has_niche = True
            color = cfg.color_structure_niche
            linewidth = cfg.structure_niche_linewidth
        else:
            color = cfg.color_structure_other
            linewidth = cfg.structure_linewidth
        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=linewidth,
            zorder=0,
        )
        xs.extend([start[0], end[0]])
        ys.extend([start[1], end[1]])

    # attachment edges
    for u, v, edata in graph.edges(data=True):
        if edata.get("edge_kind") != "on-centerline":
            continue
        src = u
        if graph.nodes[u].get("node_type") == "centerline":
            src = v
        sdata = graph.nodes[src]
        sx, sy = sdata.get("x"), sdata.get("y")
        fx, fy = edata.get("foot_x"), edata.get("foot_y")
        if sx is None or sy is None or fx is None or fy is None:
            continue
        ax.plot(
            [sx, fx],
            [sy, fy],
            color=cfg.color_attach_edge,
            linewidth=cfg.attach_edge_linewidth,
            linestyle="--",
            zorder=2,
        )

    # clusters and corridor labels
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") == "cluster":
            x, y = data.get("x"), data.get("y")
            if x is None or y is None:
                continue
            ctype = str(data.get("cluster_type") or "")
            color = (
                cfg.color_borehole
                if ctype == "钻孔"
                else cfg.color_control_point
            )
            ax.plot(x, y, "o", color=color, markersize=6, zorder=4)
            label = str(data.get("label_text") or data.get("text") or "")[:16]
            if label:
                ax.text(x, y, label, fontsize=5, color=color, zorder=5)
            xs.append(float(x))
            ys.append(float(y))
            continue

        if data.get("attach_kind") == "巷道名称":
            x, y = data.get("x"), data.get("y")
            if x is None or y is None:
                continue
            color = cfg.color_corridor_label
            text = str(data.get("text") or "")[:16]
            ax.plot(x, y, "s", color=color, markersize=3, zorder=4)
            if text:
                ax.text(x, y, text, fontsize=5, color=color, zorder=5)
            xs.append(float(x))
            ys.append(float(y))

        if str(data.get("shape_type") or "") == "point-like" and data.get("radius"):
            x, y = data.get("x"), data.get("y")
            if x is None or y is None:
                continue
            ax.add_patch(
                Circle(
                    (x, y),
                    float(data["radius"]),
                    fill=False,
                    edgecolor=cfg.color_control_point,
                    linewidth=0.8,
                    alpha=0.5,
                    zorder=3,
                )
            )
        elif str(data.get("shape_type") or "") == "point-like":
            x, y = data.get("x"), data.get("y")
            if x is None or y is None:
                continue
            ax.plot(x, y, "o", color=cfg.color_control_point, markersize=3, zorder=3)

    if xs and ys:
        pad = max(max(xs) - min(xs), max(ys) - min(ys), 1.0) * 0.05
        ax.set_xlim(min(xs) - pad, max(xs) + pad)
        ax.set_ylim(min(ys) - pad, max(ys) + pad)

    ax.set_aspect("equal")
    title = graph.graph.get("graph_name") or "structure_graph_with_texts"
    stem = graph.graph.get("stem") or ""
    ax.set_title(f"{title}  {stem}".strip())

    handles = []
    if corridors:
        handles.append(
            Line2D(
                [0],
                [0],
                color=cfg.color_corridor_entities,
                lw=2,
                label="原始巷道图元",
            )
        )
    handles.extend(
        [
            Line2D(
                [0], [0], color=cfg.color_centerline_corridor, lw=2, label="主巷中心线"
            ),
            Line2D(
                [0],
                [0],
                color=cfg.color_centerline_auxiliary,
                lw=2,
                label="辅巷中心线",
            ),
        ]
    )
    if has_niche or (graph.graph.get("role_counts") or {}).get("niche"):
        handles.append(
            Line2D(
                [0], [0], color=cfg.color_structure_niche, lw=2, label="洞室结构"
            )
        )
    handles.extend(
        [
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor=cfg.color_control_point,
                markersize=8,
                label="控制点簇",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor=cfg.color_borehole,
                markersize=8,
                label="钻孔簇",
            ),
            Line2D(
                [0],
                [0],
                marker="s",
                color="w",
                markerfacecolor=cfg.color_corridor_label,
                markersize=6,
                label="巷道名称",
            ),
            Line2D(
                [0],
                [0],
                color=cfg.color_attach_edge,
                lw=1,
                linestyle="--",
                label="挂接",
            ),
        ]
    )
    ax.legend(handles=handles, loc="upper right", fontsize=8)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)
