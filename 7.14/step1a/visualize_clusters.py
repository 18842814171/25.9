"""Draw retrieved_clusters check figure (final memberships only)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.plot_font import setup_cjk_font

from config import Step1aConfig
from text_roles import clean_text

CFG = Step1aConfig()


def _axis_limits(
    xs: list[float],
    ys: list[float],
    cfg: Step1aConfig,
) -> tuple[float, float, float, float]:
    """
    按主体坐标分位数裁切视野，避免远距飞点（如错位块参照）把核对图挤到一角。
    阈值取自顶层配置 view_percentile_* / view_pad_ratio。
    """
    from geometry_fingerprint import percentile

    if not xs or not ys:
        return 0.0, 1.0, 0.0, 1.0
    lo = float(cfg.view_percentile_low)
    hi = float(cfg.view_percentile_high)
    x0 = percentile(xs, lo)
    x1 = percentile(xs, hi)
    y0 = percentile(ys, lo)
    y1 = percentile(ys, hi)
    if x1 <= x0:
        x0, x1 = min(xs), max(xs)
    if y1 <= y0:
        y0, y1 = min(ys), max(ys)
    span = max(x1 - x0, y1 - y0, 1.0)
    pad = span * float(cfg.view_pad_ratio)
    return x0 - pad, x1 + pad, y0 - pad, y1 + pad


def load_corridor_entities(path: Path) -> list[dict]:
    import json

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"corridor export must be a list: {path}")
    return data


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
    return xs, ys


def clusters_for_visualize(graph) -> list[dict]:
    """Build the cluster list expected by visualize() from a filtered graph."""
    rows: list[dict] = []
    for cid, cdata in sorted(
        (
            (str(nid), data)
            for nid, data in graph.nodes(data=True)
            if data.get("node_kind") == "cluster"
        ),
        key=lambda item: item[0],
    ):
        members = []
        for mid in cdata.get("member_ids") or []:
            if mid not in graph.nodes:
                continue
            m = graph.nodes[mid]
            members.append(
                {
                    "id": str(mid),
                    "shape_type": m.get("shape_type"),
                    "layer": m.get("layer"),
                    "text": clean_text(m.get("text") or ""),
                    "role": m.get("role"),
                    "x": m.get("x"),
                    "y": m.get("y"),
                    "radius": m.get("radius"),
                    "block_name": m.get("block_name"),
                    "score_total": m.get("score_total"),
                }
            )
        rows.append(
            {
                "cluster_id": cid,
                "cluster_type": cdata.get("cluster_type"),
                "confidence": cdata.get("confidence"),
                "members": members,
            }
        )
    return rows


def _family_palette(
    n: int,
    *,
    family: str,
) -> list[tuple[float, float, float]]:
    """n distinct RGB colors in a typed family (control=blue-green, borehole=red)."""
    import colorsys

    # Hand-picked distinct swatches (cycle if more groups than swatches).
    if family == "control":
        # Teal → cyan → azure → blue-green (skip corridor green).
        base_hex = [
            "#0d9488",  # teal
            "#0891b2",  # cyan
            "#0284c7",  # sky blue
            "#2563eb",  # blue
            "#0f766e",  # deep teal
            "#06b6d4",  # bright cyan
            "#1d4ed8",  # strong blue
            "#14b8a6",  # mint teal
            "#0369a1",  # steel cyan
            "#4338ca",  # indigo-blue edge
        ]
    else:
        base_hex = [
            "#dc2626",  # red
            "#ea580c",  # orange-red
            "#b91c1c",  # crimson
            "#f97316",  # orange
            "#991b1b",  # deep red
            "#ef4444",  # bright red
            "#c2410c",  # burnt orange
            "#e11d48",  # rose-red
            "#9f1239",  # wine
            "#fb7185",  # light rose
        ]

    def _hex_to_rgb(h: str) -> tuple[float, float, float]:
        h = h.lstrip("#")
        return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)

    base = [_hex_to_rgb(h) for h in base_hex]
    if n <= 0:
        return []
    if n <= len(base):
        return base[:n]
    # Extra groups: keep cycling with slight HSV shifts.
    out = list(base)
    i = 0
    while len(out) < n:
        r, g, b = base[i % len(base)]
        hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
        shift = 0.03 * ((len(out) // len(base)) + 1)
        hh = (hh + shift) % 1.0
        vv = max(0.45, min(0.92, vv - 0.05 * ((len(out) // len(base)) % 3)))
        out.append(colorsys.hsv_to_rgb(hh, ss, vv))
        i += 1
    return out


def _cluster_color_map(
    clusters: list[dict],
    *,
    cfg: Step1aConfig,
) -> dict[str, tuple[float, float, float]]:
    """
    One color per cluster. Control points → blue–green band;
    boreholes → red band.
    """
    cps = [
        c
        for c in clusters
        if c.get("cluster_type") == "控制点" or c.get("kind") == "control_point"
    ]
    bhs = [
        c
        for c in clusters
        if c.get("cluster_type") == "钻孔" or c.get("kind") == "borehole"
    ]
    cps = sorted(cps, key=lambda c: str(c.get("cluster_id") or ""))
    bhs = sorted(bhs, key=lambda c: str(c.get("cluster_id") or ""))
    cp_colors = _family_palette(len(cps), family="control")
    bh_colors = _family_palette(len(bhs), family="borehole")
    out: dict[str, tuple[float, float, float]] = {}
    for c, color in zip(cps, cp_colors):
        out[str(c.get("cluster_id") or id(c))] = color
    for c, color in zip(bhs, bh_colors):
        out[str(c.get("cluster_id") or id(c))] = color
    _ = cfg
    return out


def visualize(
    clusters: list[dict],
    entities: list[dict],
    out_png: Path,
    *,
    corridors: list[dict] | None = None,
    title: str = "retrieved_clusters",
    cfg: Step1aConfig | None = None,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Circle, FancyBboxPatch

    cfg = cfg or CFG
    setup_cjk_font(cfg.figure_font_candidates)

    # Ensure each cluster has a stable id for coloring.
    for i, c in enumerate(clusters):
        if not c.get("cluster_id"):
            c["cluster_id"] = f"cluster_{i:04d}"
    color_by_cid = _cluster_color_map(clusters, cfg=cfg)

    fig, ax = plt.subplots(figsize=(10, 8), dpi=cfg.figure_dpi)
    xs = [e["x"] for e in entities]
    ys = [e["y"] for e in entities]

    if corridors:
        cxs, cys = draw_corridors(
            ax, corridors, cfg.color_corridor, cfg.corridor_linewidth
        )
        xs.extend(cxs)
        ys.extend(cys)

    if not xs:
        fig.savefig(out_png)
        plt.close(fig)
        return
    x0, x1, y0, y1 = _axis_limits(xs, ys, cfg)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_title(title)

    id_to_cluster = {}
    id_to_score = {}
    for c in clusters:
        for m in c["members"]:
            mid = m["id"]
            score = float(m.get("score_total") or c.get("confidence") or 0.0)
            prev = id_to_score.get(mid)
            if prev is None or score >= prev:
                id_to_cluster[mid] = c
                id_to_score[mid] = score

    for e in entities:
        c = id_to_cluster.get(e["id"])
        if c:
            cid = str(c.get("cluster_id") or c.get("_viz_color_key") or "")
            color = color_by_cid.get(cid, cfg.color_unassigned)
        else:
            color = cfg.color_unassigned
        if str(e.get("shape_type") or "") == "point-like":
            if e.get("radius"):
                ax.add_patch(
                    Circle(
                        (e["x"], e["y"]),
                        float(e["radius"]),
                        fill=False,
                        edgecolor=color,
                        linewidth=1.2,
                        zorder=2,
                    )
                )
            else:
                ax.plot(e["x"], e["y"], "o", color=color, markersize=4, zorder=2)
        elif str(e.get("shape_type") or "") == "text":
            h = max(float(e.get("char_height") or 4.0), 2.0)
            w = max(len(clean_text(e.get("text", ""))) * h * 0.5, h)
            ax.add_patch(
                FancyBboxPatch(
                    (e["x"], e["y"]),
                    w,
                    h,
                    boxstyle="round,pad=0.2",
                    linewidth=0.4,
                    edgecolor=color,
                    facecolor=color,
                    alpha=0.25,
                    zorder=2,
                )
            )
            ax.text(
                e["x"],
                e["y"] + h * 0.1,
                clean_text(e.get("text", ""))[:12],
                fontsize=5,
                color=color,
                zorder=3,
            )

    # Legend: family exemplars (not every group — too many).
    cp_swatch = next(
        (
            color_by_cid[str(c["cluster_id"])]
            for c in clusters
            if (c.get("cluster_type") == "控制点" or c.get("kind") == "control_point")
            and str(c.get("cluster_id") or "") in color_by_cid
        ),
        cfg.color_control_point,
    )
    bh_swatch = next(
        (
            color_by_cid[str(c["cluster_id"])]
            for c in clusters
            if (c.get("cluster_type") == "钻孔" or c.get("kind") == "borehole")
            and str(c.get("cluster_id") or "") in color_by_cid
        ),
        cfg.color_borehole,
    )
    handles = [
        Line2D([0], [0], color=cp_swatch, lw=4, label="测点(蓝绿系·每组一色)"),
        Line2D([0], [0], color=bh_swatch, lw=4, label="钻孔(红色系·每组一色)"),
        Line2D([0], [0], color=cfg.color_unassigned, lw=4, label="未归入簇"),
    ]
    if corridors:
        handles.append(Line2D([0], [0], color=cfg.color_corridor, lw=2, label="巷道"))
    ax.legend(handles=handles, loc="upper right", fontsize=8)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)


def _bind_chain_palette(n: int) -> list[tuple[float, float, float]]:
    """Distinct RGB colors for n bind chains (tab20 cycle, then HSV)."""
    import matplotlib.pyplot as plt

    if n <= 0:
        return []
    if n <= 20:
        cmap = plt.get_cmap("tab20")
        return [cmap(i / max(n, 1))[:3] for i in range(n)]
    import colorsys

    return [
        colorsys.hsv_to_rgb((i / n) % 1.0, 0.75, 0.88) for i in range(n)
    ]


def visualize_bind_chains(
    graph,
    out_png: Path,
    *,
    corridors: list[dict] | None = None,
    title: str = "bind_chains (字–值 / 值–值，选圆前)",
    cfg: Step1aConfig | None = None,
) -> None:
    """
    Stage check after script-0 chain build: one color per bind group.
    Circles/blocks and unbound texts stay grey (context only).
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Circle, FancyBboxPatch

    from graph_nodes import list_bind_groups

    cfg = cfg or CFG
    setup_cjk_font(cfg.figure_font_candidates)

    groups = list_bind_groups(graph)
    groups = sorted(
        groups,
        key=lambda g: (
            min(float(graph.nodes[m]["x"]) for m in g),
            min(float(graph.nodes[m]["y"]) for m in g),
        ),
    )
    palette = _bind_chain_palette(len(groups))
    id_to_color: dict[str, tuple[float, float, float]] = {}
    id_to_label: dict[str, str] = {}
    for i, members in enumerate(groups):
        color = palette[i]
        label = f"链{i + 1}"
        texts = [
            clean_text(graph.nodes[m].get("text") or "")
            for m in members
            if clean_text(graph.nodes[m].get("text") or "")
        ]
        if texts:
            label = f"链{i + 1}:{texts[0]}"
        for mid in members:
            id_to_color[mid] = color
            id_to_label[mid] = label

    fig, ax = plt.subplots(figsize=(10, 8), dpi=cfg.figure_dpi)
    xs: list[float] = []
    ys: list[float] = []

    if corridors:
        cxs, cys = draw_corridors(
            ax, corridors, cfg.color_corridor, cfg.corridor_linewidth
        )
        xs.extend(cxs)
        ys.extend(cys)

    grey = cfg.color_unassigned
    # Context: all annotations; bind members get chain color later.
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        try:
            x = float(data["x"])
            y = float(data["y"])
        except (KeyError, TypeError, ValueError):
            continue
        xs.append(x)
        ys.append(y)
        st = str(data.get("shape_type") or "")
        color = id_to_color.get(str(nid), grey)
        if st == "point-like":
            if data.get("radius"):
                ax.add_patch(
                    Circle(
                        (x, y),
                        float(data["radius"]),
                        fill=False,
                        edgecolor=grey,
                        linewidth=1.0,
                        zorder=1,
                    )
                )
            else:
                ax.plot(x, y, "o", color=grey, markersize=3, zorder=1)
        elif st == "text":
            h = max(float(data.get("char_height") or 4.0), 2.0)
            txt = clean_text(data.get("text") or "")
            w = max(len(txt) * h * 0.5, h)
            ax.add_patch(
                FancyBboxPatch(
                    (x, y),
                    w,
                    h,
                    boxstyle="round,pad=0.2",
                    linewidth=0.5 if str(nid) in id_to_color else 0.3,
                    edgecolor=color,
                    facecolor=color,
                    alpha=0.35 if str(nid) in id_to_color else 0.12,
                    zorder=2,
                )
            )
            ax.text(
                x,
                y + h * 0.1,
                txt[:12],
                fontsize=5,
                color=color if str(nid) in id_to_color else "#888888",
                zorder=3,
            )

    # Bind edges: same-group links.
    for a, b, edata in graph.edges(data=True):
        kinds = edata.get("edge_kinds") or []
        if "bind" not in kinds:
            continue
        sa, sb = str(a), str(b)
        if sa not in id_to_color or sb not in id_to_color:
            continue
        if id_to_color[sa] != id_to_color[sb]:
            continue
        da, db = graph.nodes[sa], graph.nodes[sb]
        ax.plot(
            [float(da["x"]), float(db["x"])],
            [float(da["y"]), float(db["y"])],
            color=id_to_color[sa],
            linewidth=1.4,
            alpha=0.85,
            zorder=4,
        )

    if not xs:
        fig.savefig(out_png)
        plt.close(fig)
        return
    x0, x1, y0, y1 = _axis_limits(xs, ys, cfg)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_title(f"{title}  groups={len(groups)}")

    handles = [
        Line2D([0], [0], color=grey, lw=4, label="未入链 / 符号"),
    ]
    if corridors:
        handles.append(Line2D([0], [0], color=cfg.color_corridor, lw=2, label="巷道"))
    # Cap legend entries so dense sheets stay readable.
    seen_labels: list[str] = []
    for mid, label in id_to_label.items():
        if label in seen_labels:
            continue
        seen_labels.append(label)
        if len(seen_labels) > 12:
            handles.append(
                Line2D([0], [0], color="#666666", lw=4, label=f"…共{len(groups)}链")
            )
            break
        handles.append(
            Line2D([0], [0], color=id_to_color[mid], lw=4, label=label[:18])
        )
    ax.legend(handles=handles, loc="upper right", fontsize=7)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)


def _cluster_anchor_id(cdata: dict, member_ids: list[str], graph) -> str | None:
    """Resolve cluster anchor node id (stored anchor_id, else first point-like member)."""
    aid = cdata.get("anchor_id")
    if aid is not None and str(aid) in graph.nodes:
        return str(aid)
    for mid in member_ids:
        if mid not in graph.nodes:
            continue
        if str(graph.nodes[mid].get("shape_type") or "") == "point-like":
            return str(mid)
    return None


def visualize_cluster_centers(
    graph,
    out_png: Path,
    *,
    corridors: list[dict] | None = None,
    title: str = "cluster_centers（识别出的锚点）",
    cfg: Step1aConfig | None = None,
) -> None:
    """
    Stage check after clustering: same paint rules as bind_chains, plus
    highlighted markers for point-like nodes that became cluster anchors.
    Unclaimed point-like symbols stay grey (not identified as anchors).
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Circle, FancyBboxPatch

    from graph_nodes import list_bind_groups

    cfg = cfg or CFG
    setup_cjk_font(cfg.figure_font_candidates)

    groups = list_bind_groups(graph)
    groups = sorted(
        groups,
        key=lambda g: (
            min(float(graph.nodes[m]["x"]) for m in g),
            min(float(graph.nodes[m]["y"]) for m in g),
        ),
    )
    palette = _bind_chain_palette(len(groups))
    id_to_color: dict[str, tuple[float, float, float]] = {}
    id_to_label: dict[str, str] = {}
    member_to_group: dict[str, int] = {}
    for i, members in enumerate(groups):
        color = palette[i]
        label = f"链{i + 1}"
        texts = [
            clean_text(graph.nodes[m].get("text") or "")
            for m in members
            if clean_text(graph.nodes[m].get("text") or "")
        ]
        if texts:
            label = f"链{i + 1}:{texts[0]}"
        for mid in members:
            sid = str(mid)
            id_to_color[sid] = color
            id_to_label[sid] = label
            member_to_group[sid] = i

    # Cluster anchors → color of any bind-chain member in the same cluster.
    anchor_color: dict[str, tuple[float, float, float]] = {}
    anchor_label: dict[str, str] = {}
    for cid, cdata in graph.nodes(data=True):
        if cdata.get("node_kind") != "cluster":
            continue
        member_ids = [str(m) for m in (cdata.get("member_ids") or [])]
        aid = _cluster_anchor_id(cdata, member_ids, graph)
        if not aid:
            continue
        color = None
        label = None
        for mid in member_ids:
            if mid in id_to_color:
                color = id_to_color[mid]
                label = id_to_label.get(mid)
                break
        if color is None:
            # No bind chain on this cluster: still mark as identified, use grey-blue.
            color = (0.35, 0.55, 0.75)
            label = str(cdata.get("cluster_type") or "锚点")
        anchor_color[aid] = color
        if label:
            anchor_label[aid] = label

    fig, ax = plt.subplots(figsize=(10, 8), dpi=cfg.figure_dpi)
    xs: list[float] = []
    ys: list[float] = []

    if corridors:
        cxs, cys = draw_corridors(
            ax, corridors, cfg.color_corridor, cfg.corridor_linewidth
        )
        xs.extend(cxs)
        ys.extend(cys)

    grey = cfg.color_unassigned
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        try:
            x = float(data["x"])
            y = float(data["y"])
        except (KeyError, TypeError, ValueError):
            continue
        xs.append(x)
        ys.append(y)
        st = str(data.get("shape_type") or "")
        sid = str(nid)
        if st == "point-like":
            if sid in anchor_color:
                continue  # drawn after texts, on top
            if data.get("radius"):
                ax.add_patch(
                    Circle(
                        (x, y),
                        float(data["radius"]),
                        fill=False,
                        edgecolor=grey,
                        linewidth=1.0,
                        zorder=1,
                    )
                )
            else:
                ax.plot(x, y, "o", color=grey, markersize=3, zorder=1)
        elif st == "text":
            color = id_to_color.get(sid, grey)
            h = max(float(data.get("char_height") or 4.0), 2.0)
            txt = clean_text(data.get("text") or "")
            w = max(len(txt) * h * 0.5, h)
            ax.add_patch(
                FancyBboxPatch(
                    (x, y),
                    w,
                    h,
                    boxstyle="round,pad=0.2",
                    linewidth=0.5 if sid in id_to_color else 0.3,
                    edgecolor=color,
                    facecolor=color,
                    alpha=0.35 if sid in id_to_color else 0.12,
                    zorder=2,
                )
            )
            ax.text(
                x,
                y + h * 0.1,
                txt[:12],
                fontsize=5,
                color=color if sid in id_to_color else "#888888",
                zorder=3,
            )

    for a, b, edata in graph.edges(data=True):
        kinds = edata.get("edge_kinds") or []
        if "bind" not in kinds:
            continue
        sa, sb = str(a), str(b)
        if sa not in id_to_color or sb not in id_to_color:
            continue
        if id_to_color[sa] != id_to_color[sb]:
            continue
        da, db = graph.nodes[sa], graph.nodes[sb]
        ax.plot(
            [float(da["x"]), float(db["x"])],
            [float(da["y"]), float(db["y"])],
            color=id_to_color[sa],
            linewidth=1.4,
            alpha=0.85,
            zorder=4,
        )

    # Identified anchors: filled + ring, chain color.
    for aid, color in anchor_color.items():
        data = graph.nodes[aid]
        try:
            x = float(data["x"])
            y = float(data["y"])
        except (KeyError, TypeError, ValueError):
            continue
        r = float(data["radius"]) if data.get("radius") else 2.0
        r = max(r, 1.2)
        ax.add_patch(
            Circle(
                (x, y),
                r * 1.8,
                fill=False,
                edgecolor=color,
                linewidth=2.0,
                zorder=6,
            )
        )
        ax.add_patch(
            Circle(
                (x, y),
                r,
                fill=True,
                facecolor=color,
                edgecolor=color,
                alpha=0.85,
                zorder=7,
            )
        )

    if not xs:
        fig.savefig(out_png)
        plt.close(fig)
        return
    x0, x1, y0, y1 = _axis_limits(xs, ys, cfg)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_title(f"{title}  anchors={len(anchor_color)}  groups={len(groups)}")

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="#5c8cbc",
            markeredgecolor="#5c8cbc",
            markersize=8,
            label="识别出的锚点",
        ),
        Line2D([0], [0], color=grey, lw=4, label="未入链 / 未作锚点"),
    ]
    if corridors:
        handles.append(Line2D([0], [0], color=cfg.color_corridor, lw=2, label="巷道"))
    seen_labels: list[str] = []
    for mid, label in id_to_label.items():
        if label in seen_labels:
            continue
        seen_labels.append(label)
        if len(seen_labels) > 12:
            handles.append(
                Line2D([0], [0], color="#666666", lw=4, label=f"…共{len(groups)}链")
            )
            break
        handles.append(
            Line2D([0], [0], color=id_to_color[mid], lw=4, label=label[:18])
        )
    ax.legend(handles=handles, loc="upper right", fontsize=7)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)
