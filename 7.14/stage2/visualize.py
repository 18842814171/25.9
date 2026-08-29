"""Visualization for facility_graph and structure_graph_with_facilities."""

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

from config import Stage2Config


def _facility_color(_ftype: str, cfg: Stage2Config) -> str:
    return cfg.color_facility_default


def _percentile_sorted(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (pct / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return float(ordered[lo] * (1.0 - frac) + ordered[hi] * frac)


def _entity_xy_points(ent: dict) -> list[tuple[float, float]]:
    attrs = ent.get("attributes") or {}
    pts: list[tuple[float, float]] = []
    for key in ("start", "end", "center"):
        val = attrs.get(key)
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            pts.append((float(val[0]), float(val[1])))
    for pt in attrs.get("points") or []:
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            pts.append((float(pt[0]), float(pt[1])))
    return pts


def filter_corridor_spatial_outliers(
    entities: list[dict],
    *,
    percentile_low: float = 5.0,
    percentile_high: float = 95.0,
    pad_ratio: float = 1.0,
) -> list[dict]:
    """Drop corridor entities whose centroid is far outside the core drawing bbox."""
    sample_x: list[float] = []
    sample_y: list[float] = []
    centers: list[tuple[float, float] | None] = []
    for ent in entities:
        pts = _entity_xy_points(ent)
        if not pts:
            centers.append(None)
            continue
        for x, y in pts:
            sample_x.append(x)
            sample_y.append(y)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        centers.append((cx, cy))

    if len(sample_x) < 8:
        return list(entities)

    x0 = _percentile_sorted(sample_x, percentile_low)
    x1 = _percentile_sorted(sample_x, percentile_high)
    y0 = _percentile_sorted(sample_y, percentile_low)
    y1 = _percentile_sorted(sample_y, percentile_high)
    pad_x = max((x1 - x0) * pad_ratio, 1.0)
    pad_y = max((y1 - y0) * pad_ratio, 1.0)
    x0 -= pad_x
    x1 += pad_x
    y0 -= pad_y
    y1 += pad_y

    kept: list[dict] = []
    for ent, center in zip(entities, centers):
        if center is None:
            kept.append(ent)
            continue
        cx, cy = center
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            kept.append(ent)
    return kept


def load_corridor_entities(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"corridor export must be a list: {path}")
    return filter_corridor_spatial_outliers(data)


def draw_corridors(
    ax,
    corridors: list[dict],
    color: str,
    linewidth: float,
    *,
    linestyle: str | tuple = "solid",
    alpha: float = 1.0,
    zorder: int = 0,
) -> tuple[list[float], list[float]]:
    from matplotlib.patches import Arc

    xs: list[float] = []
    ys: list[float] = []
    dashed = linestyle not in ("solid", "-", None)
    plot_kw = {
        "color": color,
        "linewidth": linewidth,
        "linestyle": linestyle,
        "alpha": alpha,
        "zorder": zorder,
        "solid_capstyle": "butt",
    }
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
            ax.plot([x0, x1], [y0, y1], **plot_kw)
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
            if dashed:
                # Arc patch ignores dash; sample polyline so linestyle applies.
                span = (a1 - a0) % 360.0
                if span < 1e-9:
                    span = 360.0
                n = max(12, int(span / 6.0) + 1)
                angs = [a0 + span * i / n for i in range(n + 1)]
                xs_a = [cx + radius * math.cos(math.radians(a)) for a in angs]
                ys_a = [cy + radius * math.sin(math.radians(a)) for a in angs]
                ax.plot(xs_a, ys_a, **plot_kw)
                xs.extend(xs_a)
                ys.extend(ys_a)
            else:
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
                        alpha=alpha,
                        zorder=zorder,
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
            ax.plot(xs_p, ys_p, **plot_kw)
            xs.extend(xs_p)
            ys.extend(ys_p)
    return xs, ys


def _path_xy(data: dict) -> tuple[list[float], list[float]]:
    raw = data.get("path_points") or data.get("endpoints") or []
    xs: list[float] = []
    ys: list[float] = []
    for p in raw:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            xs.append(float(p[0]))
            ys.append(float(p[1]))
    return xs, ys


def draw_primitive_geometry(
    ax,
    data: dict,
    *,
    color: str,
    linewidth: float,
    hatch_alpha: float,
    zorder: int = 2,
) -> bool:
    """Draw stroke/hatch geometry for one primitive. Returns True if something was drawn."""
    from matplotlib.patches import Arc, Polygon

    et = str(data.get("entity_type") or "")
    if et == "ARC":
        r = float(data.get("radius") or 0.0)
        cx, cy = data.get("x"), data.get("y")
        a0 = data.get("arc_start_angle")
        a1 = data.get("arc_end_angle")
        if cx is None or cy is None or r <= 0 or a0 is None or a1 is None:
            xs, ys = _path_xy(data)
            if len(xs) >= 2:
                ax.plot(xs, ys, color=color, linewidth=linewidth, zorder=zorder)
                return True
            return False
        ax.add_patch(
            Arc(
                (float(cx), float(cy)),
                2 * r,
                2 * r,
                angle=0.0,
                theta1=float(a0),
                theta2=float(a1),
                color=color,
                linewidth=linewidth,
                zorder=zorder,
            )
        )
        return True

    if et == "HATCH":
        xs, ys = _path_xy(data)
        if len(xs) >= 3:
            verts = list(zip(xs, ys))
            ax.add_patch(
                Polygon(
                    verts,
                    closed=True,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=linewidth * 0.6,
                    alpha=float(hatch_alpha),
                    zorder=zorder,
                )
            )
            return True
        # fallback: size box around centroid
        size = float(data.get("size") or 0.0)
        cx, cy = data.get("x"), data.get("y")
        if cx is None or cy is None or size <= 0:
            return False
        half = size * 0.5
        box = [
            (float(cx) - half, float(cy) - half),
            (float(cx) + half, float(cy) - half),
            (float(cx) + half, float(cy) + half),
            (float(cx) - half, float(cy) + half),
        ]
        ax.add_patch(
            Polygon(
                box,
                closed=True,
                facecolor=color,
                edgecolor=color,
                linewidth=linewidth * 0.6,
                alpha=float(hatch_alpha),
                zorder=zorder,
            )
        )
        return True

    if et in {"LINE", "LWPOLYLINE", "POLYLINE"}:
        xs, ys = _path_xy(data)
        if len(xs) < 2:
            return False
        if bool(data.get("closed")) and len(xs) >= 3:
            ax.plot(
                xs + [xs[0]],
                ys + [ys[0]],
                color=color,
                linewidth=linewidth,
                zorder=zorder,
            )
        else:
            ax.plot(xs, ys, color=color, linewidth=linewidth, zorder=zorder)
        return True

    if et == "CIRCLE":
        r = float(data.get("radius") or 0.0)
        cx, cy = data.get("x"), data.get("y")
        if cx is None or cy is None or r <= 0:
            return False
        ax.add_patch(
            Arc(
                (float(cx), float(cy)),
                2 * r,
                2 * r,
                angle=0.0,
                theta1=0.0,
                theta2=360.0,
                color=color,
                linewidth=linewidth,
                zorder=zorder,
            )
        )
        return True

    return False


def _facility_legend_handles(legend_types: set[str], cfg: Stage2Config):
    from matplotlib.lines import Line2D

    handles = []
    for t in sorted(legend_types):
        handles.append(
            Line2D(
                [0],
                [0],
                color=_facility_color(t, cfg),
                lw=2.5,
                label=t,
            )
        )
    return handles


def _draw_facilities_as_geometry(
    ax,
    graph: nx.Graph,
    cfg: Stage2Config,
) -> set[str]:
    """Draw facility member strokes/hatches; small centroid only when no geometry."""
    legend_types: set[str] = set()
    for fid, fdata in graph.nodes(data=True):
        if fdata.get("node_kind") != "facility":
            continue
        ftype = str(fdata.get("facility_type") or "通风设施")
        legend_types.add(ftype)
        color = _facility_color(ftype, cfg)
        drew = False
        for mid in fdata.get("member_ids") or []:
            mid_s = str(mid)
            if mid_s not in graph:
                continue
            pdata = graph.nodes[mid_s]
            if draw_primitive_geometry(
                ax,
                pdata,
                color=color,
                linewidth=cfg.facility_stroke_linewidth,
                hatch_alpha=cfg.facility_hatch_alpha,
                zorder=3,
            ):
                drew = True
        if not drew and fdata.get("x") is not None and fdata.get("y") is not None:
            ax.scatter(
                [fdata["x"]],
                [fdata["y"]],
                s=cfg.facility_marker_size,
                c=color,
                zorder=3,
                edgecolors="k",
                linewidths=0.3,
            )
    return legend_types


def draw_facility_graph(
    graph: nx.Graph,
    out_png: Path,
    cfg: Stage2Config | None = None,
    *,
    corridors: list[dict] | None = None,
) -> None:
    """设施图元拓扑核对图：巷道灰虚线，图元黑点，图元关联边黑实线。"""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    cfg = cfg or Stage2Config()
    setup_cjk_font(cfg.figure_font_candidates)
    fig, ax = plt.subplots(figsize=(11, 9), dpi=cfg.figure_dpi)

    corridor_color = "#808080"
    node_edge_color = "#000000"
    marker_size = max(8.0, float(cfg.facility_marker_size))

    if corridors:
        draw_corridors(
            ax,
            corridors,
            corridor_color,
            cfg.corridor_linewidth,
            linestyle="--",
            alpha=0.9,
            zorder=0,
        )

    # 图元之间的关联边（端点连接 / 无端点邻近）
    has_assoc = False
    for u, v, edata in graph.edges(data=True):
        kind = edata.get("edge_kind")
        if kind not in {"endpoint-join", "orphan-near"}:
            continue
        udata, vdata = graph.nodes[u], graph.nodes[v]
        if udata.get("node_kind") != "primitive" or vdata.get("node_kind") != "primitive":
            continue
        ux, uy = udata.get("x"), udata.get("y")
        vx, vy = vdata.get("x"), vdata.get("y")
        if ux is None or uy is None or vx is None or vy is None:
            continue
        has_assoc = True
        ax.plot(
            [ux, vx],
            [uy, vy],
            color=node_edge_color,
            linewidth=0.7,
            zorder=2,
        )

    # 设施原始图元：一律用点
    has_primitive = False
    px: list[float] = []
    py: list[float] = []
    for _, data in graph.nodes(data=True):
        if data.get("node_kind") != "primitive":
            continue
        x, y = data.get("x"), data.get("y")
        if x is None or y is None:
            continue
        has_primitive = True
        px.append(float(x))
        py.append(float(y))
    if px:
        ax.scatter(
            px,
            py,
            s=marker_size,
            c=node_edge_color,
            zorder=3,
            linewidths=0,
        )

    handles = []
    if corridors:
        handles.append(
            Line2D(
                [0],
                [0],
                color=corridor_color,
                lw=2,
                linestyle="--",
                label="巷道",
            )
        )
    if has_primitive:
        handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor=node_edge_color,
                markersize=6,
                linestyle="None",
                label="设施图元",
            )
        )
    if has_assoc:
        handles.append(
            Line2D([0], [0], color=node_edge_color, lw=1.5, label="关联边")
        )
    if handles:
        ax.legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.9)

    n = (graph.graph.get("facility_summary") or {}).get("facility_count")
    ax.set_aspect("equal")
    ax.set_title(f"facility_graph  n={n}")
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)


def _draw_text_annotations(ax, graph: nx.Graph, cfg: Stage2Config) -> dict[str, bool]:
    """Draw cluster labels and corridor names already on the fused structure graph."""
    from matplotlib.patches import Circle

    flags = {
        "control_point": False,
        "borehole": False,
        "corridor_label": False,
        "niche": False,
    }
    drawn_cluster_member_texts: set[str] = set()
    for _, data in graph.nodes(data=True):
        if data.get("node_kind") == "cluster":
            x, y = data.get("x"), data.get("y")
            if x is None or y is None:
                continue
            ctype = str(data.get("cluster_type") or "")
            if ctype == "钻孔":
                color = cfg.color_borehole
                flags["borehole"] = True
            else:
                color = cfg.color_control_point
                flags["control_point"] = True
            # 只画圆点锚点；编号/标高保留在成员原文位置，避免贴着圆点再写一遍。
            ax.plot(x, y, "o", color=color, markersize=5, zorder=4)
            for mid in data.get("member_ids") or []:
                mid_s = str(mid)
                if mid_s in drawn_cluster_member_texts or mid_s not in graph:
                    continue
                mdata = graph.nodes[mid_s]
                mx, my = mdata.get("x"), mdata.get("y")
                text = str(mdata.get("text") or "").strip()[:16]
                if mx is None or my is None or not text:
                    continue
                if str(mdata.get("shape_type") or "") != "text":
                    continue
                ax.text(mx, my, text, fontsize=5, color=color, zorder=5)
                # 成员文字 → 圆点：表明已识别入组
                ax.plot(
                    [mx, x],
                    [my, y],
                    color=color,
                    linewidth=0.4,
                    linestyle=":",
                    alpha=0.55,
                    zorder=2,
                )
                drawn_cluster_member_texts.add(mid_s)
            continue

        if data.get("attach_kind") == "巷道名称":
            x, y = data.get("x"), data.get("y")
            if x is None or y is None:
                continue
            flags["corridor_label"] = True
            color = cfg.color_corridor_label
            text = str(data.get("text") or "")[:16]
            ax.plot(x, y, "s", color=color, markersize=3, zorder=4)
            if text:
                ax.text(x, y, text, fontsize=5, color=color, zorder=5)

        if str(data.get("shape_type") or "") == "point-like" and data.get("radius"):
            x, y = data.get("x"), data.get("y")
            if x is None or y is None:
                continue
            ctype = str(data.get("cluster_type") or "")
            edgecolor = (
                cfg.color_borehole
                if ctype == "钻孔"
                else cfg.color_control_point
            )
            ax.add_patch(
                Circle(
                    (x, y),
                    float(data["radius"]),
                    fill=False,
                    edgecolor=edgecolor,
                    linewidth=0.8,
                    alpha=0.45,
                    zorder=3,
                )
            )
        elif str(data.get("shape_type") or "") == "point-like":
            x, y = data.get("x"), data.get("y")
            if x is None or y is None:
                continue
            ctype = str(data.get("cluster_type") or "")
            color = (
                cfg.color_borehole
                if ctype == "钻孔"
                else cfg.color_control_point
            )
            ax.plot(x, y, "o", color=color, markersize=3, zorder=3)
    return flags


def draw_structure_graph_with_facilities(
    graph: nx.Graph,
    out_png: Path,
    cfg: Stage2Config | None = None,
    *,
    corridors: list[dict] | None = None,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    cfg = cfg or Stage2Config()
    setup_cjk_font(cfg.figure_font_candidates)
    fig, ax = plt.subplots(figsize=(11, 9), dpi=cfg.figure_dpi)

    if corridors:
        draw_corridors(ax, corridors, cfg.color_corridor, cfg.corridor_linewidth)

    for _, data in graph.nodes(data=True):
        if data.get("node_type") != "centerline":
            continue
        start, end = data.get("start"), data.get("end")
        if not start or not end:
            continue
        role = str(data.get("role") or "")
        color = (
            cfg.color_centerline_auxiliary
            if role == "auxiliary"
            else cfg.color_centerline
        )
        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=cfg.centerline_linewidth,
            zorder=1,
        )

    for _, data in graph.nodes(data=True):
        if data.get("node_type") != "structure":
            continue
        start, end = data.get("start"), data.get("end")
        if not start or not end:
            continue
        role = str(data.get("role") or "")
        if role == "niche":
            color = cfg.color_structure_niche
            linewidth = 0.9
        else:
            color = cfg.color_structure_other
            linewidth = 0.5
        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=linewidth,
            zorder=0,
        )

    has_attach = False
    for u, v, edata in graph.edges(data=True):
        if edata.get("edge_kind") != "on-centerline":
            continue
        src = u
        if graph.nodes[u].get("node_type") == "centerline":
            src = v
        # 设施 / 控制点组 / 钻孔组 / 巷道名称 → 中心线 的关联边都画出来
        sdata = graph.nodes[src]
        kind = str(sdata.get("node_kind") or "")
        if kind not in {"facility", "cluster"} and sdata.get("attach_kind") != "巷道名称":
            continue
        sx, sy = sdata.get("x"), sdata.get("y")
        fx, fy = edata.get("foot_x"), edata.get("foot_y")
        if sx is None or sy is None or fx is None or fy is None:
            continue
        has_attach = True
        ax.plot(
            [sx, fx],
            [sy, fy],
            color=cfg.color_attach_edge,
            linewidth=cfg.attach_edge_linewidth,
            linestyle="--",
            zorder=2,
        )

    text_flags = _draw_text_annotations(ax, graph, cfg)
    legend_types = _draw_facilities_as_geometry(ax, graph, cfg)

    handles = []
    if corridors:
        handles.append(
            Line2D([0], [0], color=cfg.color_corridor, lw=2, label="巷道")
        )
    handles.append(
        Line2D([0], [0], color=cfg.color_centerline, lw=2, label="主巷中心线")
    )
    handles.append(
        Line2D(
            [0], [0], color=cfg.color_centerline_auxiliary, lw=2, label="辅巷中心线"
        )
    )
    if graph.graph.get("role_counts", {}).get("niche"):
        handles.append(
            Line2D([0], [0], color=cfg.color_structure_niche, lw=2, label="洞室结构")
        )
    if text_flags["control_point"]:
        handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor=cfg.color_control_point,
                markersize=7,
                label="控制点",
            )
        )
    if text_flags["borehole"]:
        handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor=cfg.color_borehole,
                markersize=7,
                label="钻孔",
            )
        )
    if text_flags["corridor_label"]:
        handles.append(
            Line2D(
                [0],
                [0],
                marker="s",
                color="w",
                markerfacecolor=cfg.color_corridor_label,
                markersize=6,
                label="巷道名称",
            )
        )
    if has_attach:
        handles.append(
            Line2D(
                [0],
                [0],
                color=cfg.color_attach_edge,
                lw=1,
                linestyle="--",
                label="关联边",
            )
        )
    handles.extend(_facility_legend_handles(legend_types, cfg))
    if handles:
        ax.legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.9)

    ax.set_aspect("equal")
    stem = str(graph.graph.get("stem") or "")
    ax.set_title(f"structure_graph_with_facilities  {stem}".strip())
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)
