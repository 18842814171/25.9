"""Build annotation relationship graph: nodes + proximity adjacency edges."""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

import networkx as nx

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.entity_json import load_annotation_records

from config import Step1aConfig
from geometry_fingerprint import median_char_height

CFG = Step1aConfig()


def _node_record(nid: str, data: dict) -> dict:
    return {
        "id": str(nid),
        "layer": str(data.get("layer") or ""),
        "text": data.get("text") or "",
        "x": float(data["x"]),
        "y": float(data["y"]),
        "char_height": float(data.get("char_height") or 0.0),
        "rotation": float(data.get("rotation") or 0.0),
        "radius": data.get("radius"),
        "block_name": data.get("block_name"),
        "length": float(data.get("length") or 0.0),
        "shape_type": data.get("shape_type"),
        "point_score": data.get("point_score"),
        "closed": data.get("closed"),
    }


def _is_text_node(data: dict) -> bool:
    return str(data.get("shape_type") or "") == "text"


def _is_symbol_node(data: dict) -> bool:
    return str(data.get("shape_type") or "") == "point-like"


def _is_line_node(data: dict) -> bool:
    return str(data.get("shape_type") or "") == "line-like"


def _text_span_length(data: dict) -> float:
    """Text span length: prefer length, else char_height * char count."""
    length = float(data.get("length") or 0.0)
    if length > 1e-12:
        return length
    h = float(data.get("char_height") or 0.0)
    n = max(len(str(data.get("text") or "")), 1)
    return h * n


def add_adjacency_edges(graph: nx.Graph, *, radius: float) -> int:
    """
    Link each text to nearby point-like symbols within radius.
    Edge kind: adjacent; attribute distance stores Euclidean length.
    """
    symbols: list[tuple[str, dict]] = []
    texts: list[tuple[str, dict]] = []
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if _is_symbol_node(data):
            symbols.append((str(nid), data))
        elif _is_text_node(data):
            texts.append((str(nid), data))

    if not symbols or not texts or radius <= 0:
        return 0

    cell = max(float(radius), 1.0)
    grid: dict[tuple[int, int], list[tuple[str, dict]]] = defaultdict(list)
    for sid, sdata in symbols:
        key = (int(float(sdata["x"]) // cell), int(float(sdata["y"]) // cell))
        grid[key].append((sid, sdata))

    added = 0
    for tid, tdata in texts:
        tx = float(tdata["x"])
        ty = float(tdata["y"])
        cx = int(tx // cell)
        cy = int(ty // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for sid, sdata in grid.get((cx + dx, cy + dy), []):
                    d = math.hypot(tx - float(sdata["x"]), ty - float(sdata["y"]))
                    if d > radius or d < 1e-12:
                        continue
                    if graph.has_edge(tid, sid):
                        prev = float(graph.edges[tid, sid].get("distance") or d)
                        if d < prev:
                            graph.edges[tid, sid]["distance"] = round(d, 4)
                        continue
                    graph.add_edge(
                        tid,
                        sid,
                        edge_kinds=["adjacent"],
                        distance=round(d, 4),
                    )
                    added += 1
    return added


def _angle_diff_deg(a: float, b: float) -> float:
    diff = abs(float(a) - float(b)) % 180.0
    if diff > 90.0:
        diff = 180.0 - diff
    return diff


def _add_text_text_edge_kind(
    graph: nx.Graph,
    na: str,
    nb: str,
    *,
    kind: str,
    distance: float,
) -> bool:
    """Add or merge an edge kind between two text nodes. True if kind newly added."""
    if graph.has_edge(na, nb):
        edge = graph.edges[na, nb]
        kinds = list(edge.get("edge_kinds") or [])
        if kind in kinds:
            return False
        kinds.append(kind)
        edge["edge_kinds"] = kinds
        prev = edge.get("distance")
        if prev is None or float(distance) < float(prev):
            edge["distance"] = round(float(distance), 4)
        return True
    graph.add_edge(
        na,
        nb,
        edge_kinds=[kind],
        distance=round(float(distance), 4),
    )
    return True


def add_text_proximity_edges(graph: nx.Graph, *, radius: float) -> int:
    """Link nearby text pairs (edge kind: proximity)."""
    texts: list[tuple[str, dict]] = []
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if not _is_text_node(data):
            continue
        texts.append((str(nid), data))
    if len(texts) < 2 or radius <= 0:
        return 0

    cell = max(float(radius), 1.0)
    grid: dict[tuple[int, int], list[tuple[str, dict]]] = defaultdict(list)
    for tid, tdata in texts:
        key = (int(float(tdata["x"]) // cell), int(float(tdata["y"]) // cell))
        grid[key].append((tid, tdata))

    added = 0
    seen: set[tuple[str, str]] = set()
    for tid, tdata in texts:
        tx = float(tdata["x"])
        ty = float(tdata["y"])
        cx = int(tx // cell)
        cy = int(ty // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for oid, odata in grid.get((cx + dx, cy + dy), []):
                    if oid == tid:
                        continue
                    pair = (tid, oid) if tid < oid else (oid, tid)
                    if pair in seen:
                        continue
                    d = math.hypot(tx - float(odata["x"]), ty - float(odata["y"]))
                    if d > radius or d < 1e-12:
                        continue
                    seen.add(pair)
                    if _add_text_text_edge_kind(
                        graph, tid, oid, kind="proximity", distance=d
                    ):
                        added += 1
    return added


def add_text_parallel_edges(
    graph: nx.Graph,
    *,
    radius: float,
    angle_tolerance_deg: float,
) -> int:
    """
    Link nearby text pairs with consistent rotation (edge kind: parallel).
    Often overlaps proximity; both kinds may coexist on one edge.
    """
    texts: list[tuple[str, dict]] = []
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if not _is_text_node(data):
            continue
        texts.append((str(nid), data))
    if len(texts) < 2 or radius <= 0:
        return 0

    cell = max(float(radius), 1.0)
    grid: dict[tuple[int, int], list[tuple[str, dict]]] = defaultdict(list)
    for tid, tdata in texts:
        key = (int(float(tdata["x"]) // cell), int(float(tdata["y"]) // cell))
        grid[key].append((tid, tdata))

    tol = max(float(angle_tolerance_deg), 0.0)
    added = 0
    seen: set[tuple[str, str]] = set()
    for tid, tdata in texts:
        tx = float(tdata["x"])
        ty = float(tdata["y"])
        trot = float(tdata.get("rotation") or 0.0)
        cx = int(tx // cell)
        cy = int(ty // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for oid, odata in grid.get((cx + dx, cy + dy), []):
                    if oid == tid:
                        continue
                    pair = (tid, oid) if tid < oid else (oid, tid)
                    if pair in seen:
                        continue
                    d = math.hypot(tx - float(odata["x"]), ty - float(odata["y"]))
                    if d > radius or d < 1e-12:
                        continue
                    if _angle_diff_deg(trot, float(odata.get("rotation") or 0.0)) > tol:
                        continue
                    seen.add(pair)
                    if _add_text_text_edge_kind(
                        graph, tid, oid, kind="parallel", distance=d
                    ):
                        added += 1
    return added


def build_retrieved_elements_graph(
    *,
    stem: str,
    template_layer: str,
    adjacency_radius_norm: float | None = None,
    fallback_char_height: float | None = None,
    text_json_path: Path | str | None = None,
) -> nx.Graph:
    """Load annotation records from `{stem}-??.json`; build edges."""
    records, source_json_path = load_annotation_records(
        stem,
        path=text_json_path,
    )
    from text_roles import annotation_family, classify_text_role, is_excluded_layer

    graph = nx.Graph()
    graph.graph["graph_name"] = "retrieved_elements_graph"
    graph.graph["stem"] = stem
    graph.graph["source_text_json"] = str(source_json_path.as_posix())
    graph.graph["template_layer"] = template_layer
    skipped_excluded = 0
    for rec in records:
        nid = str(rec["id"])
        layer = str(rec.get("layer") or "")
        # skip excluded layers
        if is_excluded_layer(layer):
            skipped_excluded += 1
            continue
        text = rec.get("text") or ""
        family = annotation_family(layer)
        shape_type = str(rec.get("shape_type") or "")
        role = (
            classify_text_role(text, layer)
            if shape_type == "text"
            else None
        )
        graph.add_node(
            nid,
            node_kind="annotation",
            layer=layer,
            text=text,
            x=float(rec["x"]),
            y=float(rec["y"]),
            char_height=float(rec.get("char_height") or 0.0),
            rotation=float(rec.get("rotation") or 0.0),
            radius=rec.get("radius"),
            block_name=rec.get("block_name"),
            length=float(rec.get("length") or 0.0),
            annotation_family=family,
            text_role=role,
            shape_type=shape_type or None,
            point_score=rec.get("point_score"),
            closed=rec.get("closed"),
            shape_features=rec.get("shape_features"),
        )
    graph.graph["excluded_layer_skipped"] = skipped_excluded


    texts = [
        _node_record(nid, data)
        for nid, data in graph.nodes(data=True)
        if _is_text_node(data)
    ]
    char_h = median_char_height(
        texts,
        fallback=float(fallback_char_height or CFG.fallback_char_height),
    )
    adj_norm = float(
        adjacency_radius_norm
        if adjacency_radius_norm is not None
        else CFG.adjacency_radius_norm
    )
    radius = adj_norm * char_h
    n_adj = add_adjacency_edges(graph, radius=radius)
    prox_r = float(CFG.text_proximity_norm) * char_h
    par_r = float(CFG.text_parallel_norm) * char_h
    n_prox = add_text_proximity_edges(graph, radius=prox_r)
    n_par = add_text_parallel_edges(
        graph,
        radius=par_r,
        angle_tolerance_deg=float(CFG.text_parallel_angle_tol_deg),
    )
    graph.graph["median_char_height"] = char_h
    n_bind = build_text_value_bind_chains(graph, cfg=CFG, char_h=char_h)
    graph.graph["adjacency_radius"] = round(radius, 4)
    graph.graph["adjacency_radius_norm"] = adj_norm
    graph.graph["adjacency_edge_count"] = n_adj
    graph.graph["text_proximity_radius"] = round(prox_r, 4)
    graph.graph["text_parallel_radius"] = round(par_r, 4)
    graph.graph["text_proximity_edge_count"] = n_prox
    graph.graph["text_parallel_edge_count"] = n_par
    graph.graph["bind_edge_count"] = n_bind
    return graph


def annotation_records(
    graph: nx.Graph,
    *,
    layers: set[str] | None = None,
    exclude_layers: set[str] | None = None,
) -> list[dict]:
    """Export annotation nodes as dict records compatible with clustering helpers."""
    exclude = exclude_layers or set()
    out: list[dict] = []
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        layer = str(data.get("layer") or "")
        if layers is not None and layer not in layers:
            continue
        if layer in exclude:
            continue
        out.append(_node_record(str(nid), data))
    return out


def adjacent_text_records(graph: nx.Graph, symbol_id: str) -> list[tuple[float, dict]]:
    """Return (distance, text_record) for texts linked by adjacent edges."""
    sid = str(symbol_id)
    if sid not in graph:
        return []
    out: list[tuple[float, dict]] = []
    for nid in graph.neighbors(sid):
        data = graph.nodes[nid]
        if not _is_text_node(data):
            continue
        if data.get("node_kind") != "annotation":
            continue
        kinds = graph.edges[sid, nid].get("edge_kinds") or []
        if "adjacent" not in kinds:
            continue
        d = float(graph.edges[sid, nid].get("distance") or 0.0)
        out.append((d, _node_record(str(nid), data)))
    out.sort(key=lambda item: item[0])
    return out


def attach_clusters(graph: nx.Graph, clusters: list[dict]) -> None:
    """Add cluster nodes and member edges; allow many-to-many candidate membership."""
    for index, cluster in enumerate(clusters):
        cluster_id = f"cluster_{index:04d}"
        member_ids = [str(m["id"]) for m in cluster["members"]]
        anchor_id = str(cluster["anchor_id"])
        if anchor_id in graph.nodes:
            ax = float(graph.nodes[anchor_id]["x"])
            ay = float(graph.nodes[anchor_id]["y"])
        else:
            ax = float(cluster["members"][0]["x"])
            ay = float(cluster["members"][0]["y"])
        graph.add_node(
            cluster_id,
            node_kind="cluster",
            cluster_type=cluster["cluster_type"],
            kind=cluster.get("kind"),
            confidence=cluster.get("confidence"),
            matching_stage=cluster.get("matching_stage") or "candidate",
            score_orientation=cluster.get("score_orientation"),
            anchor_id=anchor_id,
            member_ids=member_ids,
            x=ax,
            y=ay,
            text=cluster["cluster_type"],
            layer="",
            char_height=0.0,
            rotation=0.0,
            radius=None,
            block_name=None,
            shape_type=None,
        )
        for mid in member_ids:
            if mid not in graph.nodes:
                continue
            member = None
            for m in cluster["members"]:
                if str(m["id"]) == mid:
                    member = m
                    break
            role = member.get("role") if member else None
            score_total = member.get("score_total") if member else None

            cids = list(graph.nodes[mid].get("candidate_cluster_ids") or [])
            if cluster_id not in cids:
                cids.append(cluster_id)
            graph.nodes[mid]["candidate_cluster_ids"] = cids

            # Keep the highest-scoring candidate membership for display fields.
            prev = graph.nodes[mid].get("score_total")
            if prev is None or (score_total is not None and float(score_total) >= float(prev)):
                graph.nodes[mid]["cluster_id"] = cluster_id
                graph.nodes[mid]["cluster_type"] = cluster["cluster_type"]
                if role is not None:
                    graph.nodes[mid]["role"] = role
                if score_total is not None:
                    graph.nodes[mid]["score_total"] = score_total
                if member:
                    for key in ("score_layer", "score_distance", "score_orientation"):
                        if member.get(key) is not None:
                            graph.nodes[mid][key] = member.get(key)

            if graph.has_edge(cluster_id, mid):
                kinds = list(graph.edges[cluster_id, mid].get("edge_kinds") or [])
                if "member" not in kinds:
                    kinds.append("member")
                graph.edges[cluster_id, mid]["edge_kinds"] = kinds
            else:
                edge_data = {"edge_kinds": ["member"]}
                if score_total is not None:
                    edge_data["score_total"] = score_total
                graph.add_edge(cluster_id, mid, **edge_data)


def _rotation_close(a: float, b: float, *, tol_deg: float) -> bool:
    diff = abs(float(a) - float(b)) % 180.0
    if diff > 90.0:
        diff = 180.0 - diff
    return diff <= float(tol_deg)


def _chain_kind(text: str, layer: str) -> tuple[str, str] | None:
    """Script 0: same-family texts may enter one bind chain; return (family, id|value)."""
    from text_roles import annotation_family, classify_text_role

    layer = layer or ""
    family = annotation_family(layer)
    if family not in {"control_point", "borehole"}:
        return None
    role = classify_text_role(text, layer)
    if family == "control_point":
        if role == "point_id":
            return ("control_point", "id")
        if role == "elevation":
            return ("control_point", "value")
        return None
    if family == "borehole":
        if role == "borehole_id":
            return ("borehole", "id")
        if role in {"collar", "seam_value", "elevation"}:
            return ("borehole", "value")
        return None
    return None


def _infer_bind_radius(
    distances: list[float],
    *,
    floor: float,
    cap: float,
    percentile: float,
) -> float:
    """Infer bind radius from neighbor distances, clamped to floor/cap."""
    from geometry_fingerprint import percentile as pct

    if not distances:
        return floor
    learned = float(pct(distances, percentile))
    return min(max(learned, floor), cap)


def _add_or_merge_bind_edge(
    graph: nx.Graph,
    a: str,
    b: str,
    *,
    group_id: str,
    distance: float,
) -> bool:
    if graph.has_edge(a, b):
        edata = graph.edges[a, b]
        kinds = list(edata.get("edge_kinds") or [])
        newly = "bind" not in kinds
        if newly:
            kinds.append("bind")
            edata["edge_kinds"] = kinds
        edata["bind_group_id"] = group_id
        prev = edata.get("distance")
        if prev is None or float(distance) < float(prev):
            edata["distance"] = round(float(distance), 4)
        return newly
    graph.add_edge(
        a,
        b,
        edge_kinds=["bind"],
        distance=round(float(distance), 4),
        bind_group_id=group_id,
    )
    return True


def build_text_value_bind_chains(
    graph: nx.Graph,
    *,
    cfg: Step1aConfig | None = None,
    char_h: float | None = None,
) -> int:
    """
    Pre-circle binding among same-family texts.
    Control point: id-value / value-value; line-like may bridge text-line-text.
    Borehole: peer link within radius; keep all members; no id/value seat rules.
    """
    cfg = cfg or CFG
    if char_h is None:
        char_h = graph.graph.get("median_char_height")
    char_h = float(char_h if char_h is not None else cfg.fallback_char_height)
    graph.graph["median_char_height"] = char_h
    angle_tol = float(cfg.text_parallel_angle_tol_deg)
    probe = float(cfg.bind_learn_probe_norm) * max(char_h, 1e-6)
    id_floor = float(cfg.bind_id_value_norm) * max(char_h, 1e-6)
    vv_floor = float(cfg.bind_value_value_norm) * max(char_h, 1e-6)
    id_cap = float(cfg.bind_id_value_cap_norm) * max(char_h, 1e-6)
    vv_cap = float(cfg.bind_value_value_cap_norm) * max(char_h, 1e-6)
    bh_floor = float(cfg.borehole_bind_floor_norm) * max(char_h, 1e-6)
    bh_cap = float(cfg.borehole_bind_cap_norm) * max(char_h, 1e-6)
    pct = float(cfg.bind_distance_percentile)
    line_lo = float(cfg.bind_line_length_ratio_lo)
    line_hi = float(cfg.bind_line_length_ratio_hi)

    texts: list[str] = []
    families: dict[str, str] = {}
    kinds: dict[str, str] = {}
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if not _is_text_node(data):
            continue
        layer = str(data.get("layer") or "")
        chain = _chain_kind(str(data.get("text") or ""), layer)
        if chain is None:
            continue
        family, kind = chain
        node_family = data.get("annotation_family") or family
        if node_family != family:
            continue
        sid = str(nid)
        texts.append(sid)
        families[sid] = family
        kinds[sid] = kind
        data.pop("bind_group_id", None)
        data.pop("bind_family", None)
        data.pop("bind_kind", None)
        data.pop("bind_value_ids", None)
        data.pop("bind_id_ids", None)
        data.pop("bind_via_line", None)

    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if not _is_line_node(data):
            continue
        data.pop("bind_group_id", None)
        data.pop("bind_family", None)
        data.pop("bind_kind", None)
        data.pop("bind_via_line", None)

    def _pair_dist(a: str, b: str) -> float:
        da, db = graph.nodes[a], graph.nodes[b]
        return math.hypot(float(da["x"]) - float(db["x"]), float(da["y"]) - float(db["y"]))

    def _orient_ok(a: str, b: str) -> bool:
        return _rotation_close(
            float(graph.nodes[a].get("rotation") or 0.0),
            float(graph.nodes[b].get("rotation") or 0.0),
            tol_deg=angle_tol,
        )

    def _union_find(nodes: list[str]):
        parent = {t: t for t in nodes}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        return find, union

    cp_texts = [t for t in texts if families[t] == "control_point"]
    bh_texts = [t for t in texts if families[t] == "borehole"]

    cp_find, cp_union = _union_find(cp_texts)
    cp_ids = [t for t in cp_texts if kinds[t] == "id"]
    cp_vals = [t for t in cp_texts if kinds[t] == "value"]
    id_val_samples: list[float] = []
    vv_samples: list[float] = []
    for iid in cp_ids:
        for vid in cp_vals:
            d = _pair_dist(iid, vid)
            if 1e-12 < d <= probe and _orient_ok(iid, vid):
                id_val_samples.append(d)
    for i, va in enumerate(cp_vals):
        for vb in cp_vals[i + 1 :]:
            d = _pair_dist(va, vb)
            if 1e-12 < d <= probe and _orient_ok(va, vb):
                vv_samples.append(d)
    id_val_max = _infer_bind_radius(
        id_val_samples, floor=id_floor, cap=id_cap, percentile=pct
    )
    vv_max = _infer_bind_radius(
        vv_samples, floor=vv_floor, cap=vv_cap, percentile=pct
    )
    link_pairs: list[tuple[str, str, float]] = []
    line_bridge_edges: list[tuple[str, str, float]] = []
    line_bridge_count = 0

    for iid in cp_ids:
        for vid in cp_vals:
            d = _pair_dist(iid, vid)
            if d > id_val_max or d < 1e-12 or not _orient_ok(iid, vid):
                continue
            link_pairs.append((iid, vid, d))
            cp_union(iid, vid)
    for i, va in enumerate(cp_vals):
        for vb in cp_vals[i + 1 :]:
            d = _pair_dist(va, vb)
            if d > vv_max or d < 1e-12 or not _orient_ok(va, vb):
                continue
            ra, rb = cp_find(va), cp_find(vb)
            ids_a = [x for x in cp_texts if kinds[x] == "id" and cp_find(x) == ra]
            ids_b = [x for x in cp_texts if kinds[x] == "id" and cp_find(x) == rb]
            if ids_a and ids_b and set(ids_a) != set(ids_b):
                continue
            link_pairs.append((va, vb, d))
            cp_union(va, vb)

    # ??????????????????????????????????
    # ????????????????????????
    line_r = max(id_val_max, vv_max)
    line_text_r = max(line_r, id_cap) * float(cfg.bind_line_dist_slack)
    from text_roles import annotation_family

    line_ids = [
        str(nid)
        for nid, data in graph.nodes(data=True)
        if data.get("node_kind") == "annotation"
        and _is_line_node(data)
        and annotation_family(str(data.get("layer") or "")) == "control_point"
        and float(data.get("length") or 0.0) > 1e-12
        and not bool(data.get("closed"))
    ]
    for lid in line_ids:
        ldata = graph.nodes[lid]
        line_len = float(ldata.get("length") or 0.0)
        near: list[tuple[str, float]] = []
        for tid in cp_texts:
            d = _pair_dist(lid, tid)
            if d > line_text_r or d < 1e-12:
                continue
            near.append((tid, d))
        if len(near) < 2:
            continue
        # Bridge id-value or value-value via this line
        for i, (a, da) in enumerate(near):
            for b, db in near[i + 1 :]:
                ka, kb = kinds[a], kinds[b]
                if {ka, kb} == {"id", "value"}:
                    pass
                elif ka == "value" and kb == "value":
                    ra, rb = cp_find(a), cp_find(b)
                    ids_a = [x for x in cp_texts if kinds[x] == "id" and cp_find(x) == ra]
                    ids_b = [x for x in cp_texts if kinds[x] == "id" and cp_find(x) == rb]
                    if ids_a and ids_b and set(ids_a) != set(ids_b):
                        continue
                else:
                    continue
                span_a = _text_span_length(graph.nodes[a])
                span_b = _text_span_length(graph.nodes[b])
                if span_a <= 1e-12 or span_b <= 1e-12:
                    continue
                # ????????????????????????????
                ratios = (
                    line_len / max(span_a, span_b),
                    line_len / span_a,
                    line_len / span_b,
                )
                if not any(line_lo <= r <= line_hi for r in ratios):
                    continue
                cp_union(a, b)
                link_pairs.append((a, b, da + db))
                line_bridge_edges.append((a, lid, da))
                line_bridge_edges.append((b, lid, db))
                line_bridge_count += 1
                graph.nodes[a]["bind_via_line"] = lid
                graph.nodes[b]["bind_via_line"] = lid
                graph.nodes[lid]["bind_via_line"] = True

    bh_find, bh_union = _union_find(bh_texts)
    bh_samples: list[float] = []
    for i, a in enumerate(bh_texts):
        for b in bh_texts[i + 1 :]:
            d = _pair_dist(a, b)
            if 1e-12 < d <= probe and _orient_ok(a, b):
                bh_samples.append(d)
    bh_max = _infer_bind_radius(
        bh_samples, floor=bh_floor, cap=bh_cap, percentile=pct
    )
    for i, a in enumerate(bh_texts):
        for b in bh_texts[i + 1 :]:
            d = _pair_dist(a, b)
            if d > bh_max or d < 1e-12 or not _orient_ok(a, b):
                continue
            link_pairs.append((a, b, d))
            bh_union(a, b)

    # 孤立孔号并入最近的钻孔数值绑定组（同孔号列常见孔号与煤厚分列）
    id_attach = float(cfg.borehole_id_attach_norm) * max(char_h, 1e-6)
    multi_roots: dict[str, list[str]] = {}
    for tid in bh_texts:
        root = bh_find(tid)
        multi_roots.setdefault(root, []).append(tid)
    multi_roots = {r: ms for r, ms in multi_roots.items() if len(ms) >= 2}
    grouped_ids = {tid for ms in multi_roots.values() for tid in ms}
    for oid in bh_texts:
        if kinds[oid] != "id" or oid in grouped_ids:
            continue
        ox = float(graph.nodes[oid]["x"])
        oy = float(graph.nodes[oid]["y"])
        best_root = ""
        best_d = float("inf")
        for root, members in multi_roots.items():
            xs = [float(graph.nodes[mid]["x"]) for mid in members]
            ys = [float(graph.nodes[mid]["y"]) for mid in members]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            d = math.hypot(ox - cx, oy - cy)
            if d <= id_attach and d < best_d:
                best_d = d
                best_root = root
        if not best_root:
            continue
        for mid in multi_roots[best_root]:
            d = _pair_dist(oid, mid)
            if d <= id_attach:
                link_pairs.append((oid, mid, d))
                bh_union(oid, mid)
        multi_roots[best_root].append(oid)
        grouped_ids.add(oid)

    components: dict[str, list[str]] = defaultdict(list)
    for tid in cp_texts:
        components[("control_point", cp_find(tid))].append(tid)
    for tid in bh_texts:
        components[("borehole", bh_find(tid))].append(tid)

    # Attach bridge lines into bind groups by text membership
    text_to_lines: dict[str, set[str]] = defaultdict(set)
    for a, lid, _d in line_bridge_edges:
        text_to_lines[a].add(lid)

    added = 0
    group_count = 0
    for (fam, _root), members in components.items():
        if len(members) < 2:
            continue
        members = sorted(members)
        g_ids = [m for m in members if kinds[m] == "id"]
        g_vals = [m for m in members if kinds[m] == "value"]

        if fam == "control_point":
            if not g_vals:
                continue
            if len(g_ids) > 1:
                vx = sum(float(graph.nodes[v]["x"]) for v in g_vals) / len(g_vals)
                vy = sum(float(graph.nodes[v]["y"]) for v in g_vals) / len(g_vals)

                def _id_dist(i: str) -> float:
                    d = graph.nodes[i]
                    return math.hypot(float(d["x"]) - vx, float(d["y"]) - vy)

                g_ids = [min(g_ids, key=_id_dist)]
                members = sorted(set(g_ids + g_vals))

        center = g_ids[0] if g_ids else (g_vals[0] if g_vals else members[0])
        group_id = f"bind_{center}"
        group_count += 1
        bridge_lines = sorted({lid for mid in members for lid in text_to_lines.get(mid, ())})
        for mid in members:
            graph.nodes[mid]["bind_group_id"] = group_id
            graph.nodes[mid]["bind_family"] = fam
            graph.nodes[mid]["bind_kind"] = kinds[mid]
        for lid in bridge_lines:
            graph.nodes[lid]["bind_group_id"] = group_id
            graph.nodes[lid]["bind_family"] = fam
            graph.nodes[lid]["bind_kind"] = "separator"
        for iid in g_ids:
            graph.nodes[iid]["bind_value_ids"] = list(g_vals)
        for vid in g_vals:
            graph.nodes[vid]["bind_id_ids"] = list(g_ids)
            graph.nodes[vid]["bind_value_ids"] = [v for v in g_vals if v != vid]

        member_set = set(members) | set(bridge_lines)
        for a, b, d in link_pairs:
            if a in member_set and b in member_set:
                if _add_or_merge_bind_edge(graph, a, b, group_id=group_id, distance=d):
                    added += 1
        for a, lid, d in line_bridge_edges:
            if a in member_set and lid in member_set:
                if _add_or_merge_bind_edge(graph, a, lid, group_id=group_id, distance=d):
                    added += 1

    graph.graph["bind_edge_count"] = added
    graph.graph["bind_group_count"] = group_count
    graph.graph["bind_id_value_radius"] = round(id_val_max, 4)
    graph.graph["bind_value_value_radius"] = round(vv_max, 4)
    graph.graph["bind_borehole_radius"] = round(bh_max, 4)
    graph.graph["bind_id_value_samples"] = len(id_val_samples)
    graph.graph["bind_value_value_samples"] = len(vv_samples)
    graph.graph["bind_borehole_samples"] = len(bh_samples)
    graph.graph["bind_line_bridge_count"] = line_bridge_count
    graph.graph["bind_line_radius"] = round(line_text_r, 4)
    return added


def bind_group_member_ids(graph: nx.Graph, nid: str) -> list[str]:
    """All annotation ids sharing bind_group_id with nid (at least [nid])."""
    sid = str(nid)
    if sid not in graph.nodes:
        return []
    gid = graph.nodes[sid].get("bind_group_id")
    if not gid:
        return [sid]
    out = [
        str(n)
        for n, d in graph.nodes(data=True)
        if d.get("node_kind") == "annotation" and d.get("bind_group_id") == gid
    ]
    return sorted(out) if out else [sid]


def list_bind_groups(
    graph: nx.Graph,
    family: str | None = None,
) -> list[list[str]]:
    """Unique bind groups (size >= 1 for id/value texts that chained)."""
    groups: dict[str, list[str]] = {}
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if not _is_text_node(data):
            continue
        if family is not None and data.get("bind_family") != family:
            continue
        gid = data.get("bind_group_id")
        if gid:
            groups.setdefault(str(gid), []).append(str(nid))
    return [sorted(v) for v in groups.values()]
