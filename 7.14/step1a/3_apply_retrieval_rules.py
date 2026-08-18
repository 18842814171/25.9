"""Script 3: retrieved_elements_graph + retrieval_rules → candidate_cluster."""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

STEP1A_DIR = Path(__file__).resolve().parent
if str(STEP1A_DIR) not in sys.path:
    sys.path.insert(0, str(STEP1A_DIR))

from config import (
    Step1aConfig,
    candidate_cluster_json,
    candidate_cluster_pkl,
    candidate_cluster_png,
    cluster_centers_png,
    corridor_json,
    retrieved_elements_graph_pkl,
    retrieval_rules_json,
)
from candidate_scoring import (
    cluster_total_score,
    distance_decay_score,
    layer_score,
    member_total_score,
    orientation_score,
)
from geometry_fingerprint import dist, median_char_height
from graph_io import load_graph, load_json_doc, save_graph
from graph_nodes import (
    adjacent_text_records,
    annotation_records,
    attach_clusters,
    bind_group_member_ids,
    build_text_value_bind_chains,
    list_bind_groups,
)
from text_roles import (
    annotation_family,
    classify_text_role,
    clean_text,
    is_control_point_layer,
    is_elevation_text,
    is_point_id_candidate,
    role_allowed_for_cluster,
    seed_role_from_layer_name,
)
from visualize_clusters import (
    clusters_for_visualize,
    load_corridor_entities,
    visualize,
    visualize_cluster_centers,
)

CFG = Step1aConfig()

_ID_ROLES = {"point_id", "borehole_id"}
_VALUE_ROLES = {"elevation", "collar", "seam_value"}


def match_anchor(ent: dict, kind: str, kind_rule: dict, char_h: float) -> bool:
    """点状符号即可作锚点；图块名不参与判定（图例块名常与图面不一致）。"""
    del kind_rule, char_h  # 保留签名兼容调用方；块名/半径档不再硬过滤
    if str(ent.get("shape_type") or "") != "point-like":
        return False
    layer = str(ent.get("layer") or "")
    if kind == "borehole" and is_control_point_layer(layer):
        return False
    if kind == "control_point" and annotation_family(layer) == "borehole":
        return False
    return True


def find_anchors(entities: list[dict], kind: str, kind_rule: dict, char_h: float) -> list[dict]:
    matched = [e for e in entities if match_anchor(e, kind, kind_rule, char_h)]
    if kind == "borehole":
        by_id = {str(e["id"]): e for e in matched}
        for e in entities:
            if str(e.get("shape_type") or "") != "point-like":
                continue
            layer = str(e.get("layer") or "")
            if is_control_point_layer(layer):
                continue
            if "钻孔" in layer and "名称" not in layer:
                by_id.setdefault(str(e["id"]), e)
        matched = list(by_id.values())
        if matched:
            return matched
        return [
            e
            for e in entities
            if str(e.get("shape_type") or "") == "text"
            and classify_text_role(e.get("text", ""), e.get("layer", "")) == "borehole_id"
        ]
    if kind == "control_point":
        # 半径多档命中 + 控制点族图层回收（永久/临时导线点）
        by_id = {str(e["id"]): e for e in matched}
        for e in entities:
            if str(e.get("shape_type") or "") != "point-like":
                continue
            if is_control_point_layer(str(e.get("layer") or "")):
                by_id.setdefault(str(e["id"]), e)
        matched = list(by_id.values())
        if matched:
            return matched
        texts = [e for e in entities if str(e.get("shape_type") or "") == "text"]
        symbols = [
            e
            for e in entities
            if str(e.get("shape_type") or "") == "point-like"
        ]
        out = []
        for c in symbols:
            for t in texts:
                if dist(c, t) > 12.0 * char_h:
                    continue
                if is_point_id_candidate(t.get("text", ""), t.get("layer", "")):
                    out.append(c)
                    break
        return out
    if matched:
        return matched
    return []


def resolve_role(ent: dict, kind: str, kind_rule: dict) -> str | None:
    """图层优先定角色；异类图层文字不入本类簇。不再做形态正则核对。"""
    layer_roles = kind_rule.get("layer_roles") or {}
    layer = str(ent.get("layer") or "")
    family = annotation_family(layer)
    if kind == "control_point" and family == "borehole":
        return None
    if kind == "borehole" and family == "control_point":
        return None

    role_from_text = classify_text_role(ent.get("text", ""), layer)
    seeded = seed_role_from_layer_name(layer)

    if layer in layer_roles:
        role = layer_roles[layer]
        if kind == "borehole" and role == "elevation" and role_from_text in {
            "seam_value",
            "collar",
        }:
            return role_from_text
        if role == "point_id":
            if is_point_id_candidate(ent.get("text", ""), layer) or role_from_text == "point_id":
                return "point_id"
            return None
        # 钻孔编号：图层已标明且非纯数字即可
        if role == "borehole_id":
            if is_elevation_text(ent.get("text", "")):
                return None
            return "borehole_id"
        # 值角色图层上仍按文字形态分流：数值→值，非数值→孔号/测点号
        if role in {"seam_value", "collar", "elevation"}:
            if role_from_text in {"elevation", "seam_value", "collar"}:
                if kind == "borehole" and role in {"seam_value", "collar"}:
                    return role
                return role_from_text
            if role_from_text in {"borehole_id", "point_id"} and role_allowed_for_cluster(
                kind, role_from_text
            ):
                return role_from_text
            return None
        if role_allowed_for_cluster(kind, role):
            return role

    if seeded and role_allowed_for_cluster(kind, seeded):
        if seeded == "borehole_id":
            if is_elevation_text(ent.get("text", "")):
                return None
            return "borehole_id"
        if seeded in {"seam_value", "collar"}:
            if is_elevation_text(ent.get("text", "")):
                return seeded
            if role_from_text == "borehole_id":
                return "borehole_id"
            return None
        if seeded == "point_id" and (
            is_point_id_candidate(ent.get("text", ""), layer) or role_from_text == "point_id"
        ):
            return "point_id"
        if seeded == "elevation" and role_from_text == "elevation":
            return "elevation"

    if kind == "control_point" and (
        role_from_text == "point_id" or is_point_id_candidate(ent.get("text", ""), layer)
    ):
        return "point_id"
    if kind == "control_point" and role_from_text == "elevation":
        mapped = layer_roles.get(layer)
        if is_control_point_layer(layer) or mapped == "elevation":
            return "elevation"
        return None
    if kind == "borehole" and role_from_text == "borehole_id":
        return role_from_text
    if kind == "borehole" and role_from_text in {"seam_value", "collar"}:
        return role_from_text
    if kind == "borehole" and role_from_text == "elevation" and family == "borehole":
        return role_from_text
    return None


def _member_payload(
    ent: dict,
    role: str,
    d: float,
    *,
    scores: dict | None = None,
) -> dict:
    row = {
        "id": ent["id"],
        "layer": ent.get("layer"),
        "text": clean_text(ent.get("text", "")),
        "role": role,
        "dist": d,
        "x": ent.get("x"),
        "y": ent.get("y"),
        "radius": ent.get("radius"),
        "block_name": ent.get("block_name"),
        "char_height": ent.get("char_height"),
        "rotation": ent.get("rotation"),
    }
    if scores:
        row.update(scores)
    return row


def _score_member(ent: dict, role: str, d: float, kind_rule: dict, search_radius: float) -> dict | None:
    d_score = distance_decay_score(d, search_radius)
    if d_score is None:
        return None
    l_score = layer_score(ent, role, kind_rule)
    # Per-member orientation placeholder; group orientation applied after packing.
    o_score = 1.0
    total = member_total_score(layer=l_score, distance=d_score, orientation=o_score)
    return {
        "score_layer": round(l_score, 4),
        "score_distance": round(d_score, 4),
        "score_orientation": round(o_score, 4),
        "score_total": round(total, 4),
    }


def _apply_group_orientation(slot_members: list[dict]) -> float:
    o_score = orientation_score(slot_members)
    w_l = float(CFG.score_weight_layer)
    w_d = float(CFG.score_weight_distance)
    w_o = float(CFG.score_weight_orientation)
    total_w = w_l + w_d + w_o
    for m in slot_members:
        m["score_orientation"] = round(o_score, 4)
        if total_w > 0:
            m["score_total"] = round(
                (
                    w_l * float(m.get("score_layer") or 0)
                    + w_d * float(m.get("score_distance") or 0)
                    + w_o * o_score
                )
                / total_w,
                4,
            )
    return o_score


def _finish_candidate_cluster(
    anchor: dict,
    kind: str,
    kind_rule: dict,
    slot_members: list[dict],
) -> dict | None:
    members: list[dict] = []
    if str(anchor.get("shape_type") or "") == "point-like":
        members.append(
            {
                "id": anchor["id"],
                "layer": anchor.get("layer"),
                "text": "",
                "role": None,
                "x": anchor.get("x"),
                "y": anchor.get("y"),
                "radius": anchor.get("radius"),
                "block_name": anchor.get("block_name"),
                "shape_type": "point-like",
            }
        )
    members.extend(slot_members)

    if kind == "control_point" and not any(m.get("role") == "point_id" for m in members):
        return None
    if kind == "borehole" and not any(m.get("role") == "borehole_id" for m in members):
        return None

    o_score = _apply_group_orientation([m for m in members if m.get("role")])
    scored = [float(m["score_total"]) for m in members if m.get("score_total") is not None]
    has_id = any(m.get("role") in _ID_ROLES for m in members)
    confidence = cluster_total_score(scored, has_required_id=has_id)

    return {
        "cluster_type": "控制点" if kind == "control_point" else "钻孔",
        "kind": kind,
        "anchor_id": anchor["id"],
        "matching_stage": "candidate",
        "confidence": confidence,
        "score_orientation": round(o_score, 4),
        "members": [
            {
                "id": m["id"],
                "layer": m.get("layer"),
                "text": clean_text(m.get("text", "")),
                "role": m.get("role"),
                "x": m.get("x"),
                "y": m.get("y"),
                "radius": m.get("radius"),
                "block_name": m.get("block_name"),
                "rotation": m.get("rotation"),
                "dist": m.get("dist"),
                "score_layer": m.get("score_layer"),
                "score_distance": m.get("score_distance"),
                "score_orientation": m.get("score_orientation"),
                "score_total": m.get("score_total"),
            }
            for m in members
        ],
    }


def match_kind_candidates_on_graph(
    graph,
    anchors: list[dict],
    kind: str,
    kind_rule: dict,
) -> list[dict]:
    """
    Candidate stage: many-to-many for boreholes.
    Control points: bind groups ↔ circles via mutual top-K within tier1
    (fallback mutual top-K in tier2 for leftovers).
    """
    max_members = kind_rule.get("max_members") or dict(CFG.max_members)
    search_radius = float(kind_rule.get("search_radius") or 0.0)
    if search_radius <= 0:
        floor_norm = (
            CFG.control_search_floor_norm
            if kind == "control_point"
            else CFG.borehole_search_floor_norm
        )
        search_radius = floor_norm * CFG.fallback_char_height
    outer = CFG.distance_tier2_ratio * search_radius

    if kind == "control_point":
        return _match_control_points_by_bind_groups(
            graph,
            anchors,
            kind_rule=kind_rule,
            max_members=max_members,
            search_radius=search_radius,
            outer=outer,
        )

    clusters: list[dict] = []
    for anchor in anchors:
        aid = str(anchor["id"])
        by_role: dict[str, list[tuple[float, dict, dict]]] = defaultdict(list)
        seen_member_ids: set[str] = set()

        # 钻孔：按几何半径搜集种子文字（不依赖邻接边），再展开整个绑定组
        # 避免左侧标高列因无邻接边、仅右侧有邻接而被整组漏掉
        for _d, ent in _borehole_texts_near_anchor(graph, anchor, outer=outer):
            member_ids = [str(ent["id"])]
            if (
                str(ent["id"]) in graph.nodes
                and graph.nodes[str(ent["id"])].get("bind_family") == "borehole"
            ):
                member_ids = bind_group_member_ids(graph, str(ent["id"]))
            for mid in member_ids:
                if mid in seen_member_ids or mid not in graph.nodes:
                    continue
                seen_member_ids.add(mid)
                mdata = graph.nodes[mid]
                ent2 = {
                    "id": mid,
                    "layer": mdata.get("layer"),
                    "text": mdata.get("text"),
                    "x": mdata.get("x"),
                    "y": mdata.get("y"),
                    "rotation": mdata.get("rotation"),
                    "char_height": mdata.get("char_height"),
                    "radius": mdata.get("radius"),
                    "block_name": mdata.get("block_name"),
                }
                role = resolve_role(ent2, kind, kind_rule)
                if role is None:
                    continue
                if role == "elevation":
                    layer_roles = kind_rule.get("layer_roles") or {}
                    if layer_roles.get(str(ent2.get("layer") or "")) == "collar":
                        role = "collar"
                d2 = _min_dist_group_to_anchor(graph, [mid], anchor)
                if d2 is None:
                    continue
                scores = _score_member(ent2, role, d2, kind_rule, search_radius)
                if scores is None and mdata.get("bind_family") == "borehole":
                    scores = {
                        "score_layer": layer_score(ent2, role, kind_rule),
                        "score_distance": 0.5,
                        "score_orientation": 1.0,
                        "score_total": 0.5,
                    }
                if scores is None:
                    continue
                by_role[role].append(
                    (float(scores["score_total"]), ent2, {**scores, "dist": d2})
                )

        slot_members: list[dict] = []
        order = ["borehole_id", "collar", "elevation", "seam_value"]
        for role in order:
            bucket = sorted(by_role.get(role) or [], key=lambda x: x[0], reverse=True)
            # 钻孔：绑定组内成员全部入簇，不再按角色名额截断
            lim = len(bucket) if kind == "borehole" else int(max_members.get(role, 1))
            for _total, ent, scores in bucket[:lim]:
                slot_members.append(
                    _member_payload(ent, role, float(scores["dist"]), scores=scores)
                )

        if not any(m.get("role") == "collar" for m in slot_members):
            elev_bucket = sorted(
                by_role.get("elevation") or [], key=lambda x: x[0], reverse=True
            )
            taken = {m["id"] for m in slot_members}
            for _total, ent, scores in elev_bucket:
                if ent["id"] in taken:
                    continue
                try:
                    val = abs(float(clean_text(ent.get("text", ""))))
                except ValueError:
                    val = -1.0
                if val < 0:
                    continue
                slot_members.append(
                    _member_payload(ent, "collar", float(scores["dist"]), scores=scores)
                )
                break

        cluster = _finish_candidate_cluster(anchor, kind, kind_rule, slot_members)
        if cluster is not None:
            clusters.append(cluster)
    return clusters


def _borehole_texts_near_anchor(
    graph,
    anchor: dict,
    *,
    outer: float,
) -> list[tuple[float, dict]]:
    """
    Borehole seed texts within geometric radius of the symbol.
    Uses bind_family / annotation_family, not adjacency edges.
    """
    from text_roles import annotation_family

    xy = _anchor_xy(anchor)
    if xy is None:
        return []
    ax, ay = xy
    out: list[tuple[float, dict]] = []
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if str(data.get("shape_type") or "") != "text":
            continue
        if data.get("x") is None or data.get("y") is None:
            continue
        text = str(data.get("text") or "").strip()
        if not text:
            continue
        fam = data.get("bind_family") or data.get("annotation_family")
        if fam != "borehole":
            if annotation_family(str(data.get("layer") or "")) != "borehole":
                continue
        d = math.hypot(float(data["x"]) - ax, float(data["y"]) - ay)
        if d > float(outer):
            continue
        out.append(
            (
                d,
                {
                    "id": str(nid),
                    "layer": data.get("layer"),
                    "text": data.get("text"),
                    "x": data.get("x"),
                    "y": data.get("y"),
                    "rotation": data.get("rotation"),
                    "char_height": data.get("char_height"),
                    "radius": data.get("radius"),
                    "block_name": data.get("block_name"),
                },
            )
        )
    out.sort(key=lambda item: item[0])
    return out


def _anchor_xy(anchor: dict) -> tuple[float, float] | None:
    if anchor.get("x") is None or anchor.get("y") is None:
        return None
    return float(anchor["x"]), float(anchor["y"])


def _min_dist_group_to_anchor(graph, member_ids: list[str], anchor: dict) -> float | None:
    axy = _anchor_xy(anchor)
    if axy is None:
        return None
    best = None
    for mid in member_ids:
        if mid not in graph.nodes:
            continue
        data = graph.nodes[mid]
        if data.get("x") is None or data.get("y") is None:
            continue
        d = math.hypot(float(data["x"]) - axy[0], float(data["y"]) - axy[1])
        if best is None or d < best:
            best = d
    return best


def _collect_control_point_text_groups(graph, kind_rule: dict) -> list[list[str]]:
    """Bind groups plus singleton id/elevation texts not already in a chain."""
    kind = "control_point"
    groups = list_bind_groups(graph, family=kind)
    covered = {mid for g in groups for mid in g}
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if str(data.get("shape_type") or "") != "text":
            continue
        sid = str(nid)
        if sid in covered:
            continue
        role_guess = resolve_role(
            {
                "id": sid,
                "text": data.get("text"),
                "layer": data.get("layer"),
                "x": data.get("x"),
                "y": data.get("y"),
                "rotation": data.get("rotation"),
                "char_height": data.get("char_height"),
            },
            kind,
            kind_rule,
        )
        if role_guess in {"point_id", "elevation"}:
            groups.append([sid])
    return groups


def _assign_groups_to_anchors_exclusive(
    graph,
    groups: list[list[str]],
    anchors: list[dict],
    *,
    max_dist: float,
    top_k: int | None = None,
) -> dict[str, list[str]]:
    """
    文字组 ↔ 圆 1:1 互选：
    1) 每个文字组在 max_dist 内对圆按距离排序，保留最近 top_k 个；
    2) 每个圆在 max_dist 内对文字组同样保留最近 top_k 个；
    3) 仅当双方互在对方候选列表中才可连线；
    4) 按最近互选距离优先；最优被占用则依次尝试第 2、3 … 选项。
    """
    k = int(CFG.match_top_k if top_k is None else top_k)
    k = max(k, 1)
    if not groups or not anchors:
        return {}

    # gi -> [(dist, aid), ...] 最近 k 个圆
    group_cands: dict[int, list[tuple[float, str]]] = {}
    for gi, members in enumerate(groups):
        cands: list[tuple[float, str]] = []
        for anchor in anchors:
            d = _min_dist_group_to_anchor(graph, members, anchor)
            if d is None or d > max_dist:
                continue
            cands.append((d, str(anchor["id"])))
        cands.sort(key=lambda t: (t[0], t[1]))
        group_cands[gi] = cands[:k]

    # aid -> [(dist, gi), ...] 最近 k 个文字组
    circle_cands: dict[str, list[tuple[float, int]]] = {}
    for anchor in anchors:
        aid = str(anchor["id"])
        cands: list[tuple[float, int]] = []
        for gi, members in enumerate(groups):
            d = _min_dist_group_to_anchor(graph, members, anchor)
            if d is None or d > max_dist:
                continue
            cands.append((d, gi))
        cands.sort(key=lambda t: (t[0], t[1]))
        circle_cands[aid] = cands[:k]

    def _is_mutual(gi: int, aid: str) -> bool:
        if not any(a == aid for _, a in group_cands.get(gi, [])):
            return False
        return any(g == gi for _, g in circle_cands.get(aid, []))

    def _best_mutual_dist(gi: int) -> float:
        for d, aid in group_cands.get(gi, []):
            if _is_mutual(gi, aid):
                return d
        return float("inf")

    # 有更近互选对的文字组先匹配，避免远距组抢走近距圆
    order = sorted(range(len(groups)), key=lambda gi: (_best_mutual_dist(gi), gi))

    used_groups: set[int] = set()
    used_anchors: set[str] = set()
    assignment: dict[str, list[str]] = {}
    for gi in order:
        if gi in used_groups:
            continue
        # 按文字组自己的 1、2、3 偏好依次尝试
        for _d, aid in group_cands.get(gi, []):
            if aid in used_anchors:
                continue
            if not _is_mutual(gi, aid):
                continue
            used_groups.add(gi)
            used_anchors.add(aid)
            assignment[aid] = groups[gi]
            break
    return assignment


def _slot_members_from_bind_group(
    graph,
    members: list[str],
    anchor: dict,
    *,
    kind_rule: dict,
    max_members: dict,
    search_radius: float,
) -> list[dict]:
    """Build role payloads for a whole bind group; do not drop for distance."""
    kind = "control_point"
    elev_lim = int(max_members.get("elevation", 2))
    id_lim = int(max_members.get("point_id", 1))
    elevs: list[dict] = []
    ids: list[dict] = []

    for mid in members:
        data = graph.nodes[mid]
        if str(data.get("shape_type") or "") != "text":
            continue
        ent = {
            "id": mid,
            "layer": data.get("layer"),
            "text": data.get("text"),
            "x": data.get("x"),
            "y": data.get("y"),
            "rotation": data.get("rotation"),
            "char_height": data.get("char_height"),
            "radius": data.get("radius"),
            "block_name": data.get("block_name"),
        }
        role = resolve_role(ent, kind, kind_rule)
        if role is None:
            from text_roles import is_elevation_text

            if is_elevation_text(str(ent.get("text") or "")):
                role = "elevation"
            elif is_point_id_candidate(
                str(ent.get("text") or ""), str(ent.get("layer") or "")
            ):
                role = "point_id"
            else:
                continue
        d = _min_dist_group_to_anchor(graph, [mid], anchor) or 0.0
        scores = _score_member(ent, role, d, kind_rule, search_radius)
        if scores is None:
            # Candidate stage: keep bind-group members even if far from circle.
            scores = {
                "score_layer": layer_score(ent, role, kind_rule),
                "score_distance": 0.5,
                "score_orientation": 1.0,
                "score_total": 0.5,
            }
        payload = _member_payload(ent, role, d, scores=scores)
        if role == "elevation":
            elevs.append(payload)
        elif role == "point_id":
            ids.append(payload)

    elevs.sort(key=lambda m: float(m.get("dist") or 0.0))
    ids.sort(key=lambda m: float(m.get("dist") or 0.0))
    return elevs[:elev_lim] + ids[:id_lim]


def _match_control_points_by_bind_groups(
    graph,
    anchors: list[dict],
    *,
    kind_rule: dict,
    max_members: dict,
    search_radius: float,
    outer: float,
) -> list[dict]:
    """
    Bind groups ↔ circles via mutual top-K within tier1; leftovers retry in tier2.
    Matched groups/circles leave the isolated pools; unmatched stay isolated.
    """
    kind = "control_point"
    groups = _collect_control_point_text_groups(graph, kind_rule)
    tier1 = CFG.distance_tier1_ratio * search_radius
    # 一阶：双向 Top-K 互选连线
    assignment = _assign_groups_to_anchors_exclusive(
        graph, groups, anchors, max_dist=tier1
    )
    assigned_members = {mid for g in assignment.values() for mid in g}
    leftover_groups = [
        g for g in groups if not any(mid in assigned_members for mid in g)
    ]
    leftover_anchors = [a for a in anchors if str(a["id"]) not in assignment]
    # 二阶：剩余孤立文字组 / 孤立圆再互选一次（半径 outer = tier2）
    if leftover_groups and leftover_anchors and outer > tier1:
        extra = _assign_groups_to_anchors_exclusive(
            graph, leftover_groups, leftover_anchors, max_dist=outer
        )
        assignment.update(extra)

    anchor_by_id = {str(a["id"]): a for a in anchors}
    clusters: list[dict] = []
    for aid, members in assignment.items():
        anchor = anchor_by_id.get(aid)
        if anchor is None:
            continue
        slot_members = _slot_members_from_bind_group(
            graph,
            members,
            anchor,
            kind_rule=kind_rule,
            max_members=max_members,
            search_radius=search_radius,
        )
        cluster = _finish_candidate_cluster(anchor, kind, kind_rule, slot_members)
        if cluster is not None:
            clusters.append(cluster)
    return clusters


def dedupe_borehole_clusters(clusters: list[dict], char_h: float) -> list[dict]:
    kept: list[dict] = []
    seen: list[tuple[str, float, float]] = []
    for c in clusters:
        if c["kind"] != "borehole":
            kept.append(c)
            continue
        bid = ""
        ax = ay = 0.0
        for m in c["members"]:
            if m.get("role") == "borehole_id":
                bid = clean_text(m.get("text") or "")
                ax, ay = float(m["x"]), float(m["y"])
                break
        if not bid:
            kept.append(c)
            continue
        dup = False
        for t, sx, sy in seen:
            if t == bid and math.hypot(ax - sx, ay - sy) < 3.0 * char_h:
                dup = True
                break
        if dup:
            continue
        seen.append((bid, ax, ay))
        kept.append(c)
    return kept


def detect_clusters_on_graph(graph, entities: list[dict], rulepack: dict) -> list[dict]:
    char_h = float(
        graph.graph.get("median_char_height")
        or median_char_height(
            entities,
            fallback=float(rulepack.get("median_char_height") or CFG.fallback_char_height),
        )
    )
    graph.graph["median_char_height"] = char_h
    if not graph.graph.get("bind_group_count") and not graph.graph.get("bind_edge_count"):
        build_text_value_bind_chains(graph, cfg=CFG, char_h=char_h)
    clusters: list[dict] = []
    for kind in ("control_point", "borehole"):
        kind_rule = dict(rulepack["kinds"][kind])
        anchors = find_anchors(entities, kind, kind_rule, char_h)
        clusters.extend(match_kind_candidates_on_graph(graph, anchors, kind, kind_rule))
    return dedupe_borehole_clusters(clusters, char_h)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply retrieval_rules on retrieved_elements_graph (candidate stage)"
    )
    parser.add_argument("--stem", type=str, default=CFG.default_part_stem)
    parser.add_argument(
        "--rules-from-stem",
        type=str,
        default="",
        help="load retrieval_rules from that stem (default: same as --stem)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="override product directory (default: step1a/output)",
    )
    parser.add_argument(
        "--graph-pkl",
        type=str,
        default="",
        help="override retrieved_elements_graph.pkl",
    )
    parser.add_argument(
        "--rules-json",
        type=str,
        default="",
        help="override retrieval_rules.json",
    )
    parser.add_argument(
        "--corridor-json",
        type=str,
        default="",
        help="override corridor geometry JSON for visualize",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="",
        help="directory for corridor JSON when --corridor-json omitted",
    )
    parser.add_argument(
        "--no-png",
        action="store_true",
        help="skip candidate_cluster verification PNG",
    )
    args = parser.parse_args()
    out = args.output_dir or None
    in_dir = args.input_dir or None

    in_path = (
        Path(args.graph_pkl)
        if args.graph_pkl
        else retrieved_elements_graph_pkl(args.stem, out)
    )
    rules_stem = args.rules_from_stem or args.stem
    rules_path = (
        Path(args.rules_json)
        if args.rules_json
        else retrieval_rules_json(rules_stem, out)
    )
    graph = load_graph(in_path).copy()
    rulepack = load_json_doc(rules_path)
    if not isinstance(rulepack, dict) or "kinds" not in rulepack:
        raise RuntimeError(f"invalid retrieval_rules: {rules_path}")

    template_layer = str(graph.graph.get("template_layer") or CFG.template_layer)
    entities = annotation_records(graph, exclude_layers={template_layer})
    clusters = detect_clusters_on_graph(graph, entities, rulepack)
    attach_clusters(graph, clusters)
    print(
        f"bind_groups: {graph.graph.get('bind_group_count')} "
        f"bind_edges: {graph.graph.get('bind_edge_count')}"
    )

    graph.graph["graph_name"] = "candidate_cluster"
    graph.graph["stem"] = args.stem
    graph.graph["step1a_config"] = CFG.to_json()
    graph.graph["matching_stage"] = "candidate"
    graph.graph["cluster_summary"] = {
        "cluster_count": len(clusters),
        "by_type": {
            "控制点": sum(1 for c in clusters if c["cluster_type"] == "控制点"),
            "钻孔": sum(1 for c in clusters if c["cluster_type"] == "钻孔"),
        },
    }

    out_pkl = candidate_cluster_pkl(args.stem, out)
    out_json = candidate_cluster_json(args.stem, out)
    save_graph(graph, out_pkl, out_json)

    if not args.no_png:
        corr_path = corridor_json(
            args.stem,
            CFG,
            base_dir=in_dir,
            path=args.corridor_json or None,
        )
        if not corr_path.is_file():
            raise FileNotFoundError(f"corridor file not found: {corr_path}")
        corridors = load_corridor_entities(corr_path)
        print(f"corridor: {corr_path} ({len(corridors)} entities)")

        out_png = candidate_cluster_png(args.stem, out)
        try:
            visualize(
                clusters_for_visualize(graph),
                entities,
                out_png,
                corridors=corridors,
                title="candidate_cluster",
                cfg=CFG,
            )
            print(f"png: {out_png}")
        except Exception as exc:
            print(f"visualize skipped: {exc}")

        centers_png = cluster_centers_png(args.stem, out)
        try:
            visualize_cluster_centers(
                graph,
                centers_png,
                corridors=corridors,
                title="cluster_centers（识别出的锚点）",
                cfg=CFG,
            )
            print(f"cluster_centers_png: {centers_png}")
        except Exception as exc:
            print(f"cluster_centers visualize skipped: {exc}")

    print(f"input_graph: {in_path}")
    print(f"input_rules: {rules_path}")
    print(f"output_pkl: {out_pkl}")
    print("matching_stage: candidate (many-to-many)")
    print(f"clusters: {graph.graph['cluster_summary']['by_type']}")
    for c in clusters:
        labels = [m["text"] for m in c["members"] if m.get("text")]
        #print(
        #    f"  {c['cluster_type']} conf={c['confidence']} "
         #   f"orient={c.get('score_orientation')} {labels[:8]}"
        #)


if __name__ == "__main__":
    main()
