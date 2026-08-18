"""Cluster facility primitives (endpoint components) and match legend templates."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import networkx as nx

from config import Stage2Config
from dxf_primitives import normalize_caption
from endpoint_connect import (
    components_with_extra_join,
    connected_primitive_components,
    pick_legend_symbol_component,
)


def fingerprint_from_members(members: list[dict]) -> dict[str, Any]:
    type_hist = Counter(str(m.get("entity_type") or "") for m in members)
    blocks = sorted(
        {
            str(m["block_name"])
            for m in members
            if m.get("entity_type") == "INSERT" and m.get("block_name")
        }
    )
    sizes = [float(m.get("size") or 0.0) for m in members if float(m.get("size") or 0.0) > 0]
    lengths = [
        float(m.get("length") or 0.0) for m in members if float(m.get("length") or 0.0) > 0
    ]
    texts = sorted(
        {
            str(m.get("text") or "").strip()
            for m in members
            if m.get("entity_type") in {"TEXT", "MTEXT"} and str(m.get("text") or "").strip()
        }
    )
    sizes_sorted = sorted(sizes)
    lengths_sorted = sorted(lengths)
    med_size = sizes_sorted[len(sizes_sorted) // 2] if sizes_sorted else 0.0
    med_len = lengths_sorted[len(lengths_sorted) // 2] if lengths_sorted else 0.0
    xs = [float(m["x"]) for m in members if m.get("x") is not None]
    ys = [float(m["y"]) for m in members if m.get("y") is not None]
    cx = sum(xs) / len(xs) if xs else None
    cy = sum(ys) / len(ys) if ys else None
    # 包围盒长短边比（≤1），旋转不敏感：图例横画、实例竖画可比
    if xs and ys:
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        long_side = max(bw, bh)
        short_side = min(bw, bh)
        if long_side <= 1e-9:
            aspect = 1.0
            bbox_long = med_size
        else:
            # 纯横/竖单线 short≈0，用下限避免外形比归零导致匹配失效
            aspect = float(max(short_side, long_side * 0.05) / long_side)
            bbox_long = float(long_side)
    else:
        aspect = 1.0
        bbox_long = med_size
    # 长度谱（归一化后排序），旋转不敏感
    if lengths_sorted and med_len > 1e-9:
        length_spectrum = [round(L / med_len, 3) for L in lengths_sorted]
    else:
        length_spectrum = []
    return {
        "type_hist": dict(sorted(type_hist.items())),
        "block_names": blocks,
        "median_size": med_size,
        "median_length": med_len,
        "aspect_ratio": aspect,
        "bbox_long": bbox_long,
        "length_spectrum": length_spectrum,
        "texts": texts,
        "member_count": len(members),
        "x": cx,
        "y": cy,
    }


def _hist_overlap(a: dict[str, int], b: dict[str, int]) -> float:
    if not a and not b:
        return 1.0
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    inter = sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)
    union = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return float(inter) / float(union) if union else 0.0


def score_against_template(
    cluster_fp: dict[str, Any],
    template: dict[str, Any],
    cfg: Stage2Config,
) -> float:
    c_hist = {k: int(v) for k, v in (cluster_fp.get("type_hist") or {}).items()}
    t_hist = {k: int(v) for k, v in (template.get("type_hist") or {}).items()}
    t_only_hatch = set(t_hist.keys()) <= {"HATCH"} and "HATCH" in t_hist
    c_has_stroke = any(k in c_hist for k in ("LINE", "LWPOLYLINE", "ARC", "INSERT"))
    if t_only_hatch and c_has_stroke:
        return 0.0
    t_has_stroke = any(k in t_hist for k in ("LINE", "LWPOLYLINE", "ARC", "INSERT"))
    c_only_hatch = set(c_hist.keys()) <= {"HATCH"} and "HATCH" in c_hist
    if t_has_stroke and c_only_hatch:
        return 0.0

    c_blocks = set(cluster_fp.get("block_names") or [])
    t_blocks = set(template.get("block_names") or [])
    if c_blocks and t_blocks:
        block_score = len(c_blocks & t_blocks) / len(c_blocks | t_blocks)
    elif not c_blocks and not t_blocks:
        block_score = 0.5
    else:
        block_score = 0.0

    hist_score = _hist_overlap(c_hist, t_hist)

    c_size = float(cluster_fp.get("median_size") or 0.0)
    t_size = float(template.get("median_size") or 0.0)
    if c_size > 1e-9 and t_size > 1e-9:
        size_score = float(min(c_size, t_size) / max(c_size, t_size))
    else:
        size_score = 0.5

    c_asp = float(cluster_fp.get("aspect_ratio") or 1.0)
    t_asp = float(template.get("aspect_ratio") or 1.0)
    if c_asp > 1e-9 and t_asp > 1e-9:
        aspect_score = float(min(c_asp, t_asp) / max(c_asp, t_asp))
    else:
        aspect_score = 0.5

    if c_blocks and t_blocks and c_blocks <= t_blocks:
        block_score = max(block_score, 0.95)

    return (
        cfg.score_weight_block * block_score
        + cfg.score_weight_type_hist * hist_score
        + cfg.score_weight_size * size_score
        + cfg.score_weight_aspect * aspect_score
    )


def match_facility_type(
    cluster_fp: dict[str, Any],
    templates: list[dict[str, Any]],
    cfg: Stage2Config,
) -> tuple[str, float]:
    best_type = "未分型"
    best_score = 0.0
    for tmpl in templates:
        score = score_against_template(cluster_fp, tmpl, cfg)
        if score > best_score:
            best_score = score
            best_type = str(tmpl.get("facility_type") or "未分型")
    if best_score < cfg.min_type_score:
        return "未分型", best_score
    return best_type, best_score


def build_facility_graph(
    primitives_graph: nx.Graph,
    templates_doc: dict[str, Any],
    cfg: Stage2Config,
) -> nx.Graph:
    median_h = float(
        primitives_graph.graph.get("median_char_height") or cfg.fallback_char_height
    )
    med_fac = primitives_graph.graph.get("median_facility_size")
    templates = list(templates_doc.get("templates") or [])

    graph = nx.Graph()
    graph.graph.update(
        {
            "graph_name": "facility_graph",
            "stem": primitives_graph.graph.get("stem"),
            "source_dxf": primitives_graph.graph.get("source_dxf"),
            "facility_layer": cfg.facility_layer,
            "median_char_height": median_h,
            "median_facility_size": med_fac,
            "endpoint_join_tol": primitives_graph.graph.get("endpoint_join_tol"),
            "cluster_mode": "endpoint_components",
            "stage2_config": cfg.to_json(),
            "template_stem": templates_doc.get("stem"),
        }
    )

    for nid, data in primitives_graph.nodes(data=True):
        if data.get("node_kind") != "primitive":
            continue
        if data.get("layer") != cfg.facility_layer:
            continue
        graph.add_node(str(nid), **dict(data))

    # 复制端点连接边（仅设施层）
    for u, v, edata in primitives_graph.edges(data=True):
        if u not in graph or v not in graph:
            continue
        kind = edata.get("edge_kind")
        if kind in {"endpoint-join", "orphan-near"}:
            graph.add_edge(u, v, **dict(edata))

    clusters = connected_primitive_components(graph, layer=cfg.facility_layer)
    # 过大连通分量拆成单点（图框等）
    expanded: list[list[dict]] = []
    for members in clusters:
        if len(members) > cfg.max_cluster_members:
            for m in members:
                expanded.append([m])
        else:
            expanded.append(members)
    clusters = expanded

    type_counts: Counter[str] = Counter()
    for idx, members in enumerate(clusters):
        fp = fingerprint_from_members(members)
        facility_type, score = match_facility_type(fp, templates, cfg)
        fid = f"facility_{idx:04d}"
        member_ids = [str(m["id"]) for m in members]
        graph.add_node(
            fid,
            node_kind="facility",
            facility_type=facility_type,
            confidence=float(score),
            member_ids=member_ids,
            block_names=list(fp.get("block_names") or []),
            type_hist=dict(fp.get("type_hist") or {}),
            aspect_ratio=float(fp.get("aspect_ratio") or 1.0),
            median_size=float(fp.get("median_size") or 0.0),
            x=fp.get("x"),
            y=fp.get("y"),
            label_text=facility_type,
            text=facility_type,
            attach_kind=facility_type,
        )
        for mid in member_ids:
            if mid in graph:
                graph.nodes[mid]["facility_id"] = fid
                graph.nodes[mid]["facility_type"] = facility_type
                graph.add_edge(fid, mid, edge_kind="member", edge_kinds=["member"])
        type_counts[facility_type] += 1

    graph.graph["facility_summary"] = {
        "facility_count": sum(type_counts.values()),
        "by_type": dict(sorted(type_counts.items())),
    }
    return graph


def collect_legend_seeds(primitives: list[dict], cfg: Stage2Config) -> list[dict]:
    alias = cfg.facility_caption_aliases
    seeds = []
    for p in primitives:
        if p.get("layer") != cfg.template_layer:
            continue
        if p.get("entity_type") not in {"TEXT", "MTEXT"}:
            continue
        key = normalize_caption(str(p.get("text") or ""))
        if key not in alias:
            continue
        seeds.append({**p, "facility_type": alias[key]})
    return seeds


def legend_symbol_members(
    graph: nx.Graph,
    seed: dict,
    *,
    probe: float,
    size_cap: float,
    cfg: Stage2Config,
    exclude_ids: set[str] | None = None,
) -> list[dict]:
    """Near seed, take endpoint-connected component(s), not loose centroid bags.

    Uses a legend-scale join tolerance (relative to char height) on a local copy so
    figure-scale gaps in the legend do not leave trapezoid strokes as isolated ticks.
    Among candidates, prefer the richest length-balanced stroke block rather than a
    nearby frame edge. Only considers primitives above the caption (legend layout).
    ``exclude_ids`` skips members already claimed by another legend caption.
    """
    sx, sy = float(seed["x"]), float(seed["y"])
    seed_id = str(seed.get("id"))
    blocked = exclude_ids or set()
    median_h = float(graph.graph.get("median_char_height") or cfg.fallback_char_height)
    below_tol = median_h * float(cfg.legend_symbol_below_tol_norm)
    near_ids: list[str] = []
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "primitive":
            continue
        nid_s = str(nid)
        if nid_s == seed_id or nid_s in blocked:
            continue
        if data.get("layer") not in {cfg.template_layer, cfg.facility_layer}:
            continue
        if data.get("x") is None or data.get("y") is None:
            continue
        py = float(data["y"])
        if py < sy - below_tol:
            continue
        d = math.hypot(float(data["x"]) - sx, py - sy)
        if d > probe or d < 1e-9:
            continue
        size = float(data.get("size") or 0.0)
        if data.get("entity_type") != "INSERT" and size > size_cap:
            continue
        near_ids.append(nid_s)
    if not near_ids:
        return []

    base_join = float(graph.graph.get("endpoint_join_tol") or cfg.endpoint_join_tol_floor)
    legend_join = max(
        base_join,
        median_h * float(cfg.legend_endpoint_join_tol_norm),
    )
    base_orphan = float(graph.graph.get("orphan_near_tol") or cfg.orphan_near_tol_floor)
    legend_orphan = max(base_orphan, legend_join)

    components = components_with_extra_join(
        graph,
        near_ids,
        join_tol=legend_join,
        orphan_tol=legend_orphan,
    )
    picked = pick_legend_symbol_component(
        components,
        sx,
        sy,
        min_strokes=int(cfg.legend_symbol_min_strokes),
    )
    return picked or []
