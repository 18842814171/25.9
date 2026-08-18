"""Endpoint-join edges and connected-component clustering for facility primitives."""

from __future__ import annotations

import math
from typing import Any, Iterable

import networkx as nx


EDGE_ENDPOINT = "endpoint-join"
EDGE_ORPHAN_NEAR = "orphan-near"


def _endpoints_of(data: dict) -> list[tuple[float, float]]:
    raw = data.get("endpoints") or []
    out: list[tuple[float, float]] = []
    for p in raw:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            out.append((float(p[0]), float(p[1])))
    return out


def has_stroke_endpoints(data: dict) -> bool:
    et = str(data.get("entity_type") or "")
    if et not in {"LINE", "LWPOLYLINE", "POLYLINE", "ARC"}:
        return False
    return bool(_endpoints_of(data))


def add_endpoint_join_edges(
    graph: nx.Graph,
    *,
    join_tol: float,
    orphan_tol: float,
) -> dict[str, int]:
    """Add same-layer endpoint-join edges; attach orphan symbols by centroid proximity.

    Stroke primitives (line/polyline/arc) join when any endpoints are within join_tol.
    HATCH / INSERT / CIRCLE / TEXT / MTEXT without usable stroke ends attach to the
    nearest same-layer stroke node within orphan_tol (so they enter the same component).
    """
    join_tol = max(float(join_tol), 1e-9)
    orphan_tol = max(float(orphan_tol), 1e-9)
    join_n = 0
    orphan_n = 0

    # index endpoints by layer + grid
    cell = join_tol
    buckets: dict[tuple[str, int, int], list[tuple[str, float, float]]] = {}
    stroke_ids: list[str] = []
    orphan_ids: list[str] = []

    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "primitive":
            continue
        layer = str(data.get("layer") or "")
        if has_stroke_endpoints(data):
            stroke_ids.append(str(nid))
            for x, y in _endpoints_of(data):
                gx = int(math.floor(x / cell))
                gy = int(math.floor(y / cell))
                buckets.setdefault((layer, gx, gy), []).append((str(nid), x, y))
        else:
            et = str(data.get("entity_type") or "")
            if et in {"HATCH", "INSERT", "CIRCLE", "TEXT", "MTEXT", "POINT"}:
                orphan_ids.append(str(nid))

    # endpoint–endpoint joins (same layer only)
    seen_pairs: set[tuple[str, str]] = set()
    for nid in stroke_ids:
        data = graph.nodes[nid]
        layer = str(data.get("layer") or "")
        for x, y in _endpoints_of(data):
            gx = int(math.floor(x / cell))
            gy = int(math.floor(y / cell))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for oid, ox, oy in buckets.get((layer, gx + dx, gy + dy), []):
                        if oid == nid:
                            continue
                        key = (nid, oid) if nid < oid else (oid, nid)
                        if key in seen_pairs:
                            continue
                        if (x - ox) ** 2 + (y - oy) ** 2 <= join_tol * join_tol:
                            seen_pairs.add(key)
                            if not graph.has_edge(nid, oid):
                                graph.add_edge(
                                    nid,
                                    oid,
                                    edge_kind=EDGE_ENDPOINT,
                                    edge_kinds=[EDGE_ENDPOINT],
                                    join_distance=math.hypot(x - ox, y - oy),
                                )
                                join_n += 1

    # orphan → nearest stroke by centroid or endpoint within orphan_tol (same layer)
    ocell = orphan_tol
    stroke_cent_buckets: dict[tuple[str, int, int], list[str]] = {}
    stroke_end_buckets: dict[tuple[str, int, int], list[tuple[str, float, float]]] = {}
    for sid in stroke_ids:
        sdata = graph.nodes[sid]
        layer = str(sdata.get("layer") or "")
        sx, sy = float(sdata["x"]), float(sdata["y"])
        gx = int(math.floor(sx / ocell))
        gy = int(math.floor(sy / ocell))
        stroke_cent_buckets.setdefault((layer, gx, gy), []).append(sid)
        for ex, ey in _endpoints_of(sdata):
            egx = int(math.floor(ex / ocell))
            egy = int(math.floor(ey / ocell))
            stroke_end_buckets.setdefault((layer, egx, egy), []).append((sid, ex, ey))

    for oid in orphan_ids:
        odata = graph.nodes[oid]
        layer = str(odata.get("layer") or "")
        ox, oy = float(odata["x"]), float(odata["y"])
        gx = int(math.floor(ox / ocell))
        gy = int(math.floor(oy / ocell))
        best_sid = None
        best_d2 = orphan_tol * orphan_tol
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for sid in stroke_cent_buckets.get((layer, gx + dx, gy + dy), []):
                    sdata = graph.nodes[sid]
                    ddx = ox - float(sdata["x"])
                    ddy = oy - float(sdata["y"])
                    d2 = ddx * ddx + ddy * ddy
                    if d2 <= best_d2:
                        best_d2 = d2
                        best_sid = sid
                for sid, ex, ey in stroke_end_buckets.get((layer, gx + dx, gy + dy), []):
                    d2 = (ox - ex) ** 2 + (oy - ey) ** 2
                    if d2 <= best_d2:
                        best_d2 = d2
                        best_sid = sid
        if best_sid is not None and not graph.has_edge(oid, best_sid):
            graph.add_edge(
                oid,
                best_sid,
                edge_kind=EDGE_ORPHAN_NEAR,
                edge_kinds=[EDGE_ORPHAN_NEAR],
                join_distance=math.sqrt(best_d2),
            )
            orphan_n += 1

    return {"endpoint_join_edges": join_n, "orphan_near_edges": orphan_n}


def connected_primitive_components(
    graph: nx.Graph,
    *,
    layer: str | None = None,
    node_ids: Iterable[str] | None = None,
) -> list[list[dict[str, Any]]]:
    """Return connected components of primitive nodes (endpoint/orphan edges)."""
    if node_ids is not None:
        allowed = {str(n) for n in node_ids}
    else:
        allowed = {
            str(nid)
            for nid, data in graph.nodes(data=True)
            if data.get("node_kind") == "primitive"
            and (layer is None or data.get("layer") == layer)
        }

    sub = graph.subgraph(allowed).copy()
    # keep only join-related edges
    drop = []
    for u, v, data in sub.edges(data=True):
        kind = data.get("edge_kind")
        if kind not in {EDGE_ENDPOINT, EDGE_ORPHAN_NEAR}:
            drop.append((u, v))
    sub.remove_edges_from(drop)

    components: list[list[dict[str, Any]]] = []
    for comp in nx.connected_components(sub):
        members = [dict(graph.nodes[nid], id=str(nid)) for nid in sorted(comp)]
        components.append(members)
    # isolated nodes with no edges still appear as singleton components
    return components


def pick_nearest_component(
    components: list[list[dict[str, Any]]],
    x: float,
    y: float,
) -> list[dict[str, Any]] | None:
    if not components:
        return None
    best = None
    best_d = float("inf")
    for members in components:
        xs = [float(m["x"]) for m in members if m.get("x") is not None]
        ys = [float(m["y"]) for m in members if m.get("y") is not None]
        if not xs:
            continue
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        d = math.hypot(cx - x, cy - y)
        if d < best_d:
            best_d = d
            best = members
    return best


_STROKE_ENTITY_TYPES = {
    "LINE",
    "LWPOLYLINE",
    "POLYLINE",
    "ARC",
    "HATCH",
    "INSERT",
    "CIRCLE",
}


def stroke_member_count(members: list[dict[str, Any]]) -> int:
    return sum(1 for m in members if m.get("entity_type") in _STROKE_ENTITY_TYPES)


def pick_legend_symbol_component(
    components: list[list[dict[str, Any]]],
    x: float,
    y: float,
    *,
    min_strokes: int = 2,
) -> list[dict[str, Any]] | None:
    """Prefer richer, length-balanced stroke blocks near the caption.

    Legend captions often sit closer to a frame tick than to the real symbol (e.g. 风桥
    trapezoid). Ranking by stroke count, then length balance (min/max), then distance,
    recovers the symbol block instead of a long box edge plus a stub.
    """
    if not components:
        return None
    ranked: list[tuple[int, float, float, list[dict[str, Any]]]] = []
    for members in components:
        strokes = [m for m in members if m.get("entity_type") in _STROKE_ENTITY_TYPES]
        n_stroke = len(strokes)
        if n_stroke <= 0:
            continue
        xs = [float(m["x"]) for m in members if m.get("x") is not None]
        ys = [float(m["y"]) for m in members if m.get("y") is not None]
        if not xs:
            continue
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        d = math.hypot(cx - x, cy - y)
        lengths = [
            float(m.get("length") or m.get("size") or 0.0)
            for m in strokes
            if float(m.get("length") or m.get("size") or 0.0) > 1e-9
        ]
        if lengths:
            balance = min(lengths) / max(lengths)
        else:
            balance = 0.0
        ranked.append((n_stroke, balance, d, members))
    if not ranked:
        return pick_nearest_component(components, x, y)
    rich = [item for item in ranked if item[0] >= int(min_strokes)]
    pool = rich if rich else ranked
    pool.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return pool[0][3]


def components_with_extra_join(
    graph: nx.Graph,
    node_ids: Iterable[str],
    *,
    join_tol: float,
    orphan_tol: float,
) -> list[list[dict[str, Any]]]:
    """Connected components after adding endpoint joins at join_tol on a local copy."""
    allowed = [str(n) for n in node_ids]
    if not allowed:
        return []
    sub = graph.subgraph(allowed).copy()
    add_endpoint_join_edges(sub, join_tol=join_tol, orphan_tol=orphan_tol)
    return connected_primitive_components(sub, node_ids=allowed)
