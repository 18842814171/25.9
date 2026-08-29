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
from geometry_fingerprint import median_char_height
from graph_io import load_graph, load_json_doc, save_graph
from graph_nodes import (
    annotation_records,
    attach_clusters,
    build_text_value_bind_chains,
    list_bind_groups,
)
from text_roles import (
    annotation_family,
    classify_text_role,
    clean_text,
    is_borehole_symbol_layer,
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
    """锚点仅限钻孔 / 测点（控制点）符号图层上的 point-like，其他图块不参与。"""
    del kind_rule, char_h
    if str(ent.get("shape_type") or "") != "point-like":
        return False
    layer = str(ent.get("layer") or "")
    if kind == "borehole":
        return is_borehole_symbol_layer(layer)
    if kind == "control_point":
        return is_control_point_layer(layer)
    return False


def find_anchors(entities: list[dict], kind: str, kind_rule: dict, char_h: float) -> list[dict]:
    """同类锚点：图层已归入钻孔族或测点族符号层的圆/块。"""
    out: list[dict] = []
    seen: set[str] = set()
    for ent in entities:
        if not match_anchor(ent, kind, kind_rule, char_h):
            continue
        eid = str(ent["id"])
        if eid in seen:
            continue
        seen.add(eid)
        out.append(ent)
    return out


def resolve_role(ent: dict, kind: str, kind_rule: dict) -> str | None:
    """图层优先定角色；异类图层文字不入本类组。不再做形态正则核对。"""
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
    同类文字（绑定组或孤立字）↔ 同类锚点，双向 Top-K 互选；
    未匹配文字保持孤立，other 族文字不参与。
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
    return _match_kind_by_bind_groups(
        graph,
        anchors,
        kind=kind,
        kind_rule=kind_rule,
        max_members=max_members,
        search_radius=search_radius,
        outer=outer,
    )


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


_KIND_SINGLETON_ROLES: dict[str, set[str]] = {
    "control_point": {"point_id", "elevation"},
    "borehole": {"borehole_id", "collar", "elevation", "seam_value"},
}


def _collect_kind_text_groups(graph, kind: str, kind_rule: dict) -> list[list[str]]:
    """同类绑定组 + 尚未入组的同类孤立文字（单字一组）。"""
    allowed = _KIND_SINGLETON_ROLES.get(kind, set())
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
        if annotation_family(str(data.get("layer") or "")) != kind:
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
        if role_guess in allowed:
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


def _slot_members_from_group(
    graph,
    members: list[str],
    anchor: dict,
    *,
    kind: str,
    kind_rule: dict,
    max_members: dict,
    search_radius: float,
    max_member_dist: float,
) -> list[dict]:
    """从文字组中选取距锚点不超过 max_member_dist 的成员入组。"""
    by_role: dict[str, list[dict]] = defaultdict(list)

    for mid in members:
        if mid not in graph.nodes:
            continue
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
            if kind == "control_point":
                if is_elevation_text(str(ent.get("text") or "")):
                    role = "elevation"
                elif is_point_id_candidate(
                    str(ent.get("text") or ""), str(ent.get("layer") or "")
                ):
                    role = "point_id"
            if role is None:
                continue
        if role == "elevation" and kind == "borehole":
            layer_roles = kind_rule.get("layer_roles") or {}
            if layer_roles.get(str(ent.get("layer") or "")) == "collar":
                role = "collar"
        d = _min_dist_group_to_anchor(graph, [mid], anchor)
        if d is None or d > max_member_dist:
            continue
        scores = _score_member(ent, role, d, kind_rule, search_radius)
        if scores is None:
            continue
        by_role[role].append(_member_payload(ent, role, d, scores=scores))

    if kind == "control_point":
        elev_lim = int(max_members.get("elevation", 2))
        id_lim = int(max_members.get("point_id", 1))
        elevs = sorted(by_role.get("elevation") or [], key=lambda m: m["dist"])
        ids = sorted(by_role.get("point_id") or [], key=lambda m: m["dist"])
        return elevs[:elev_lim] + ids[:id_lim]

    slot_members: list[dict] = []
    order = ["borehole_id", "collar", "elevation", "seam_value"]
    for role in order:
        bucket = sorted(by_role.get(role) or [], key=lambda m: m["dist"])
        slot_members.extend(bucket)
    if not any(m.get("role") == "collar" for m in slot_members):
        for m in sorted(by_role.get("elevation") or [], key=lambda x: x["dist"]):
            try:
                val = abs(float(clean_text(m.get("text", ""))))
            except ValueError:
                continue
            if val < 0:
                continue
            slot_members.append({**m, "role": "collar"})
            break
    return slot_members


def _match_kind_by_bind_groups(
    graph,
    anchors: list[dict],
    *,
    kind: str,
    kind_rule: dict,
    max_members: dict,
    search_radius: float,
    outer: float,
) -> list[dict]:
    """
    同类绑定组 / 孤立文字 ↔ 同类锚点：tier1 双向 Top-K，剩余 tier2 再互选。
    未匹配文字保持孤立。
    """
    groups = _collect_kind_text_groups(graph, kind, kind_rule)
    tier1 = CFG.distance_tier1_ratio * search_radius
    assignment: dict[str, list[str]] = {}
    member_dist: dict[str, float] = {}

    def _merge_assign(new: dict[str, list[str]], *, max_dist: float) -> None:
        for aid, mems in new.items():
            assignment[aid] = mems
            member_dist[aid] = max_dist

    _merge_assign(
        _assign_groups_to_anchors_exclusive(graph, groups, anchors, max_dist=tier1),
        max_dist=tier1,
    )
    assigned_members = {mid for g in assignment.values() for mid in g}
    leftover_groups = [
        g for g in groups if not any(mid in assigned_members for mid in g)
    ]
    leftover_anchors = [a for a in anchors if str(a["id"]) not in assignment]
    if leftover_groups and leftover_anchors and outer > tier1:
        _merge_assign(
            _assign_groups_to_anchors_exclusive(
                graph, leftover_groups, leftover_anchors, max_dist=outer
            ),
            max_dist=outer,
        )

    anchor_by_id = {str(a["id"]): a for a in anchors}
    clusters: list[dict] = []
    for aid, members in assignment.items():
        anchor = anchor_by_id.get(aid)
        if anchor is None:
            continue
        slot_members = _slot_members_from_group(
            graph,
            members,
            anchor,
            kind=kind,
            kind_rule=kind_rule,
            max_members=max_members,
            search_radius=search_radius,
            max_member_dist=member_dist.get(aid, tier1),
        )
        cluster = _finish_candidate_cluster(anchor, kind, kind_rule, slot_members)
        if cluster is not None:
            clusters.append(cluster)
    return clusters


def _borehole_anchor_xy(cluster: dict) -> tuple[str, float, float, str] | None:
    aid = str(cluster.get("anchor_id") or "")
    for m in cluster.get("members") or []:
        if str(m.get("id") or "") == aid and m.get("x") is not None:
            return (
                aid,
                float(m["x"]),
                float(m["y"]),
                str(m.get("layer") or ""),
            )
    for m in cluster.get("members") or []:
        if str(m.get("shape_type") or "") == "point-like" and m.get("x") is not None:
            return (
                str(m.get("id") or aid),
                float(m["x"]),
                float(m["y"]),
                str(m.get("layer") or ""),
            )
    return None


def _borehole_cluster_rank(cluster: dict, char_h: float) -> tuple[float, float]:
    """Higher is better: (score, negative anchor-id distance)."""
    bid_xy: tuple[float, float] | None = None
    for m in cluster.get("members") or []:
        if m.get("role") == "borehole_id" and m.get("x") is not None:
            bid_xy = (float(m["x"]), float(m["y"]))
            break
    anchor = _borehole_anchor_xy(cluster)
    score = 0.0
    dist = float("inf")
    if anchor is not None:
        _aid, ax, ay, layer = anchor
        if is_borehole_symbol_layer(layer):
            score += 1000.0
        if bid_xy is not None:
            dist = math.hypot(ax - bid_xy[0], ay - bid_xy[1])
            score -= dist
        member_pts = [
            (float(m["x"]), float(m["y"]))
            for m in cluster.get("members") or []
            if m.get("role") not in {None, ""}
            and str(m.get("shape_type") or "") == "text"
            and m.get("x") is not None
        ]
        if member_pts and math.isfinite(dist):
            cx = sum(p[0] for p in member_pts) / len(member_pts)
            cy = sum(p[1] for p in member_pts) / len(member_pts)
            score -= 0.1 * math.hypot(ax - cx, ay - cy)
    conf = float(cluster.get("confidence") or 0.0)
    return (score + conf, -dist if math.isfinite(dist) else 0.0)


def dedupe_borehole_clusters(clusters: list[dict], char_h: float) -> list[dict]:
    kept: list[dict] = []
    borehole: list[dict] = []
    for c in clusters:
        if c["kind"] != "borehole":
            kept.append(c)
        else:
            borehole.append(c)

    buckets: dict[tuple[str, int, int], list[dict]] = defaultdict(list)
    for c in borehole:
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
        key = (
            bid,
            int(round(ax / max(char_h, 1e-6))),
            int(round(ay / max(char_h, 1e-6))),
        )
        buckets[key].append(c)

    for group in buckets.values():
        best = max(group, key=lambda c: _borehole_cluster_rank(c, char_h))
        kept.append(best)
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
