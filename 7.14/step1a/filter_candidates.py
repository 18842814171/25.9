"""Resolve many-to-many candidate clusters into exclusive final memberships.

Every annotation that entered a candidate local graph keeps a final cluster
after filtering (no orphaned former candidates).
"""

from __future__ import annotations

import math
from typing import Any

import networkx as nx

from candidate_scoring import cluster_total_score
from config import Step1aConfig
from text_roles import clean_text

_ID_ROLES = {"point_id", "borehole_id"}


def _member_edge_score(graph: nx.Graph, cluster_id: str, mid: str) -> float:
    if not graph.has_edge(cluster_id, mid):
        return -1.0
    edata = graph.edges[cluster_id, mid]
    kinds = edata.get("edge_kinds") or []
    if "member" not in kinds:
        return -1.0
    score = edata.get("score_total")
    if score is not None:
        return float(score)
    node_score = graph.nodes[mid].get("score_total")
    if node_score is not None:
        return float(node_score)
    conf = graph.nodes[cluster_id].get("confidence")
    return float(conf) if conf is not None else 0.0


def _is_member_edge(graph: nx.Graph, u: str, v: str) -> bool:
    if not graph.has_edge(u, v):
        return False
    kinds = graph.edges[u, v].get("edge_kinds") or []
    return "member" in kinds


def _required_id_role(cluster_type: str) -> str | None:
    if cluster_type == "控制点":
        return "point_id"
    if cluster_type == "钻孔":
        return "borehole_id"
    return None


def _drop_member_edge(graph: nx.Graph, cluster_id: str, mid: str) -> None:
    if not graph.has_edge(cluster_id, mid):
        return
    edata = graph.edges[cluster_id, mid]
    kinds = [k for k in (edata.get("edge_kinds") or []) if k != "member"]
    if kinds:
        edata["edge_kinds"] = kinds
        edata.pop("score_total", None)
    else:
        graph.remove_edge(cluster_id, mid)


def _attach_member(
    graph: nx.Graph,
    cluster_id: str,
    mid: str,
    *,
    score: float | None = None,
) -> None:
    cdata = graph.nodes[cluster_id]
    data = graph.nodes[mid]
    data["cluster_id"] = cluster_id
    data["cluster_type"] = cdata.get("cluster_type")
    if score is not None:
        data["score_total"] = float(score)
    if graph.has_edge(cluster_id, mid):
        edata = graph.edges[cluster_id, mid]
        kinds = list(edata.get("edge_kinds") or [])
        if "member" not in kinds:
            kinds.append("member")
        edata["edge_kinds"] = kinds
        if score is not None:
            edata["score_total"] = float(score)
    else:
        edge_data: dict[str, Any] = {"edge_kinds": ["member"]}
        if score is not None:
            edge_data["score_total"] = float(score)
        graph.add_edge(cluster_id, mid, **edge_data)


def _snapshot_candidate_state(graph: nx.Graph) -> dict[str, Any]:
    """Capture many-to-many links before exclusive resolve."""
    member_scores: dict[str, list[tuple[float, str]]] = {}
    cluster_members: dict[str, list[str]] = {}
    for cid, cdata in graph.nodes(data=True):
        if cdata.get("node_kind") != "cluster":
            continue
        mids = [str(m) for m in (cdata.get("member_ids") or [])]
        cluster_members[str(cid)] = mids
    for mid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        links: list[tuple[float, str]] = []
        for cid in data.get("candidate_cluster_ids") or []:
            cid_s = str(cid)
            if cid_s not in graph.nodes:
                continue
            if not _is_member_edge(graph, cid_s, mid):
                continue
            links.append((_member_edge_score(graph, cid_s, str(mid)), cid_s))
        if links:
            links.sort(key=lambda item: (-item[0], item[1]))
            member_scores[str(mid)] = links
    return {"member_scores": member_scores, "cluster_members": cluster_members}


def _bind_value_ids(graph: nx.Graph, id_mid: str) -> list[str]:
    data = graph.nodes.get(id_mid) or {}
    vals = [str(v) for v in (data.get("bind_value_ids") or []) if str(v) in graph.nodes]
    if vals:
        return vals
    out: list[str] = []
    if id_mid not in graph:
        return out
    for nbr in graph.neighbors(id_mid):
        if graph.nodes[nbr].get("node_kind") != "annotation":
            continue
        kinds = graph.edges[id_mid, nbr].get("edge_kinds") or []
        if "bind" in kinds:
            out.append(str(nbr))
    return out


def _bind_id_ids(graph: nx.Graph, value_mid: str) -> list[str]:
    data = graph.nodes.get(value_mid) or {}
    ids = [str(i) for i in (data.get("bind_id_ids") or []) if str(i) in graph.nodes]
    if ids:
        return ids
    out: list[str] = []
    if value_mid not in graph:
        return out
    for nbr in graph.neighbors(value_mid):
        if graph.nodes[nbr].get("node_kind") != "annotation":
            continue
        kinds = graph.edges[value_mid, nbr].get("edge_kinds") or []
        if "bind" not in kinds:
            continue
        if graph.nodes[nbr].get("role") in _ID_ROLES:
            out.append(str(nbr))
    return out


def _assign_to_cluster(
    graph: nx.Graph,
    mid: str,
    winner: str,
    *,
    best_score: float,
    full_cands: list[str] | None = None,
) -> int:
    """Assign mid exclusively to winner; drop other member edges. Return drops."""
    data = graph.nodes[mid]
    dropped = 0
    cluster_ids = [
        str(nid)
        for nid, nd in graph.nodes(data=True)
        if nd.get("node_kind") == "cluster"
    ]
    for cid in cluster_ids:
        if cid == winner:
            continue
        if _is_member_edge(graph, cid, mid):
            _drop_member_edge(graph, cid, mid)
            dropped += 1
    if not _is_member_edge(graph, winner, mid):
        _attach_member(graph, winner, mid, score=best_score)
    data["cluster_id"] = winner
    data["cluster_type"] = graph.nodes[winner].get("cluster_type")
    if full_cands is not None:
        data["candidate_cluster_ids"] = full_cands
    data["score_total"] = best_score
    return dropped


def _linked_borehole_clusters(
    graph: nx.Graph, mid: str, cluster_ids: list[str]
) -> list[tuple[float, str]]:
    """Member edges from mid to borehole clusters, scored descending."""
    cands: list[tuple[float, str]] = []
    for cid in cluster_ids:
        if not _is_member_edge(graph, cid, mid):
            continue
        if str(graph.nodes[cid].get("cluster_type") or "") != "钻孔":
            continue
        cands.append((_member_edge_score(graph, cid, mid), cid))
    cands.sort(key=lambda item: (-item[0], item[1]))
    return cands


def _preserve_borehole_multi_membership(
    graph: nx.Graph, mid: str, cluster_ids: list[str]
) -> bool:
    """
    Keep all borehole candidate links for this annotation.
    Returns True when mid only participates in borehole clusters (skip exclusive).
    """
    linked = [
        cid
        for cid in cluster_ids
        if _is_member_edge(graph, cid, mid)
    ]
    if not linked:
        return False
    if any(str(graph.nodes[cid].get("cluster_type") or "") != "钻孔" for cid in linked):
        return False
    bh_cands = _linked_borehole_clusters(graph, mid, cluster_ids)
    if not bh_cands:
        return False
    best_score, primary = bh_cands[0]
    full_cands = list(graph.nodes[mid].get("candidate_cluster_ids") or [])
    for _score, cid in bh_cands:
        if cid not in full_cands:
            full_cands.append(cid)
    data = graph.nodes[mid]
    data["cluster_id"] = primary
    data["cluster_type"] = "钻孔"
    data["candidate_cluster_ids"] = full_cands
    data["score_total"] = best_score
    data["membership_mode"] = "borehole_multi"
    return True


def resolve_exclusive_memberships(graph: nx.Graph) -> dict[str, Any]:
    """
    Control-point annotations: exclusive membership by score (ID–value bind stars).
    Borehole annotations: keep all candidate cluster links (many-to-many).
    """
    cluster_ids = [
        str(nid)
        for nid, data in graph.nodes(data=True)
        if data.get("node_kind") == "cluster"
    ]
    reassigned = 0
    assigned: set[str] = set()

    def _candidates_for(mid: str) -> list[tuple[float, str]]:
        cands: list[tuple[float, str]] = []
        for cid in cluster_ids:
            if not _is_member_edge(graph, cid, mid):
                continue
            cands.append((_member_edge_score(graph, cid, mid), cid))
        cands.sort(key=lambda item: (-item[0], item[1]))
        return cands

    # 0) Borehole: retain every candidate link; only record a primary cluster_id.
    for mid, data in list(graph.nodes(data=True)):
        if data.get("node_kind") != "annotation":
            continue
        if _preserve_borehole_multi_membership(graph, mid, cluster_ids):
            assigned.add(mid)

    # 1) Resolve ID-role annotations (bind star centers).
    for mid, data in list(graph.nodes(data=True)):
        if data.get("node_kind") != "annotation":
            continue
        if mid in assigned:
            continue
        if data.get("role") not in _ID_ROLES:
            continue
        candidates = _candidates_for(mid)
        if not candidates:
            continue
        best_score, winner = candidates[0]
        full_cands = list(data.get("candidate_cluster_ids") or [])
        for cid in (c for _, c in candidates):
            if cid not in full_cands:
                full_cands.append(cid)
        reassigned += _assign_to_cluster(
            graph, mid, winner, best_score=best_score, full_cands=full_cands
        )
        assigned.add(mid)

        # Pull bind-linked values into the same winning cluster.
        for vid in _bind_value_ids(graph, mid):
            if vid in assigned:
                continue
            vdata = graph.nodes[vid]
            v_score = _member_edge_score(graph, winner, vid)
            if v_score < 0:
                v_score = float(vdata.get("score_total") or best_score)
            v_cands = list(vdata.get("candidate_cluster_ids") or [])
            if winner not in v_cands:
                v_cands.append(winner)
            reassigned += _assign_to_cluster(
                graph, vid, winner, best_score=v_score, full_cands=v_cands
            )
            assigned.add(vid)

    # 2) Remaining annotations: normal exclusive resolve; values still try bound IDs.
    for mid, data in list(graph.nodes(data=True)):
        if data.get("node_kind") != "annotation":
            continue
        if mid in assigned:
            continue
        bound_ids = _bind_id_ids(graph, mid)
        follow: tuple[float, str] | None = None
        for iid in bound_ids:
            icid = graph.nodes[iid].get("cluster_id")
            if not icid or str(icid) not in graph.nodes:
                continue
            if graph.nodes[str(icid)].get("node_kind") != "cluster":
                continue
            score = _member_edge_score(graph, str(icid), mid)
            if score < 0:
                score = float(data.get("score_total") or graph.nodes[iid].get("score_total") or 0.0)
            if follow is None or score > follow[0]:
                follow = (score, str(icid))
        if follow is not None:
            best_score, winner = follow
            full_cands = list(data.get("candidate_cluster_ids") or [])
            if winner not in full_cands:
                full_cands.append(winner)
            reassigned += _assign_to_cluster(
                graph, mid, winner, best_score=best_score, full_cands=full_cands
            )
            assigned.add(mid)
            continue

        candidates = _candidates_for(mid)
        if not candidates:
            continue
        best_score, winner = candidates[0]
        full_cands = list(data.get("candidate_cluster_ids") or [])
        for cid in (c for _, c in candidates):
            if cid not in full_cands:
                full_cands.append(cid)
        reassigned += _assign_to_cluster(
            graph, mid, winner, best_score=best_score, full_cands=full_cands
        )
        assigned.add(mid)

    return {"memberships_dropped": reassigned}


def _rebuild_member_ids(graph: nx.Graph) -> None:
    for cid, cdata in graph.nodes(data=True):
        if cdata.get("node_kind") != "cluster":
            continue
        members: list[str] = []
        for nbr in graph.neighbors(cid):
            if graph.nodes[nbr].get("node_kind") != "annotation":
                continue
            if _is_member_edge(graph, cid, nbr):
                members.append(str(nbr))
        members.sort()
        cdata["member_ids"] = members


def _recompute_confidence(graph: nx.Graph) -> None:
    for cid, cdata in graph.nodes(data=True):
        if cdata.get("node_kind") != "cluster":
            continue
        scores: list[float] = []
        has_id = False
        for mid in cdata.get("member_ids") or []:
            if mid not in graph.nodes:
                continue
            mdata = graph.nodes[mid]
            role = mdata.get("role")
            if role in _ID_ROLES:
                has_id = True
            if mdata.get("score_total") is not None:
                scores.append(float(mdata["score_total"]))
            elif graph.has_edge(cid, mid):
                edge_score = graph.edges[cid, mid].get("score_total")
                if edge_score is not None:
                    scores.append(float(edge_score))
        cdata["confidence"] = cluster_total_score(scores, has_required_id=has_id)


def _valid_cluster_ids(graph: nx.Graph, *, min_confidence: float) -> set[str]:
    valid: set[str] = set()
    for cid, cdata in graph.nodes(data=True):
        if cdata.get("node_kind") != "cluster":
            continue
        cluster_type = str(cdata.get("cluster_type") or "")
        need = _required_id_role(cluster_type)
        members = list(cdata.get("member_ids") or [])
        has_id = False
        if need:
            for mid in members:
                if mid in graph.nodes and graph.nodes[mid].get("role") == need:
                    has_id = True
                    break
        conf = float(cdata.get("confidence") or 0.0)
        if (need and not has_id) or conf < float(min_confidence):
            continue
        valid.add(str(cid))
    return valid


def _invalid_cluster_ids(graph: nx.Graph, *, min_confidence: float) -> list[str]:
    valid = _valid_cluster_ids(graph, min_confidence=min_confidence)
    return sorted(
        str(cid)
        for cid, cdata in graph.nodes(data=True)
        if cdata.get("node_kind") == "cluster" and str(cid) not in valid
    )


def _xy(graph: nx.Graph, nid: str) -> tuple[float, float] | None:
    data = graph.nodes.get(nid) or {}
    if data.get("x") is None or data.get("y") is None:
        return None
    return float(data["x"]), float(data["y"])


def _pick_rehome_target(
    graph: nx.Graph,
    mid: str,
    *,
    snapped_links: list[tuple[float, str]],
    dropped_cids: set[str],
    cluster_members_snap: dict[str, list[str]],
    valid_ids: set[str],
) -> tuple[str, float | None] | None:
    """Choose a surviving cluster for an orphaned former candidate member."""
    # 1) Best original candidate that still survives.
    for score, cid in snapped_links:
        if cid in valid_ids:
            return cid, score

    # 2) Homes of co-members that shared a dropped local graph with this node.
    relevant_dropped = {
        cid
        for cid in dropped_cids
        if mid in (cluster_members_snap.get(cid) or [])
    }
    votes: dict[str, float] = {}
    for dropped in relevant_dropped:
        for peer in cluster_members_snap.get(dropped) or []:
            if peer == mid or peer not in graph.nodes:
                continue
            peer_cid = graph.nodes[peer].get("cluster_id")
            if not peer_cid or str(peer_cid) not in valid_ids:
                continue
            peer_cid = str(peer_cid)
            peer_score = graph.nodes[peer].get("score_total")
            votes[peer_cid] = max(
                votes.get(peer_cid, -1.0),
                float(peer_score) if peer_score is not None else 0.0,
            )
    if votes:
        best_cid = max(votes.items(), key=lambda item: (item[1], item[0]))[0]
        return best_cid, votes[best_cid]

    # 3) Nearest surviving cluster of the same type (else any type).
    src = _xy(graph, mid)
    if src is None:
        return None
    preferred_type = graph.nodes[mid].get("cluster_type")
    best: tuple[float, str] | None = None
    fallback: tuple[float, str] | None = None
    for cid in valid_ids:
        cxy = _xy(graph, cid)
        if cxy is None:
            continue
        dist = math.hypot(src[0] - cxy[0], src[1] - cxy[1])
        ctype = graph.nodes[cid].get("cluster_type")
        if preferred_type and ctype == preferred_type:
            if best is None or dist < best[0]:
                best = (dist, cid)
        elif fallback is None or dist < fallback[0]:
            fallback = (dist, cid)
    pick = best or fallback
    if pick is None:
        return None
    return pick[1], None


def rehome_invalid_cluster_members(
    graph: nx.Graph,
    snapshot: dict[str, Any],
    *,
    min_confidence: float,
) -> dict[str, Any]:
    """
    Drop id-less / weak clusters, but reattach every former member to a
    surviving local graph so no candidate annotation is left unassigned.
    """
    invalid = _invalid_cluster_ids(graph, min_confidence=min_confidence)
    if not invalid:
        return {"clusters_dropped": [], "members_rehomed": 0, "members_unassigned": 0}

    dropped_set = set(invalid)
    member_scores: dict[str, list[tuple[float, str]]] = snapshot["member_scores"]
    cluster_members_snap: dict[str, list[str]] = snapshot["cluster_members"]

    orphans: list[str] = []
    for cid in invalid:
        for mid in list(graph.nodes[cid].get("member_ids") or []):
            if mid not in graph.nodes:
                continue
            orphans.append(str(mid))
            _drop_member_edge(graph, cid, mid)
            if graph.nodes[mid].get("cluster_id") == cid:
                graph.nodes[mid].pop("cluster_id", None)
        graph.remove_node(cid)

    _rebuild_member_ids(graph)
    valid_ids = {
        str(cid)
        for cid, cdata in graph.nodes(data=True)
        if cdata.get("node_kind") == "cluster"
    }

    rehomed = 0
    unassigned = 0
    done: set[str] = set()

    def _rehome_one(mid: str, cid: str, score: float | None) -> None:
        nonlocal rehomed
        _attach_member(graph, cid, mid, score=score)
        rehomed += 1
        done.add(mid)

    # Prefer ID orphans first so bind values can follow them.
    orphan_ids = [
        m for m in orphans
        if m in graph.nodes and graph.nodes[m].get("role") in _ID_ROLES
    ]
    orphan_rest = [m for m in orphans if m not in orphan_ids]

    for mid in orphan_ids + orphan_rest:
        if mid not in graph.nodes or mid in done:
            continue
        cur = graph.nodes[mid].get("cluster_id")
        if cur and str(cur) in valid_ids and _is_member_edge(graph, str(cur), mid):
            done.add(mid)
            continue

        # Values: follow a bound ID that already has a surviving home.
        follow_cid = None
        follow_score = None
        for iid in _bind_id_ids(graph, mid):
            icid = graph.nodes[iid].get("cluster_id")
            if icid and str(icid) in valid_ids:
                follow_cid = str(icid)
                follow_score = graph.nodes[mid].get("score_total")
                break
        if follow_cid is not None:
            _rehome_one(mid, follow_cid, float(follow_score) if follow_score is not None else None)
            continue

        target = _pick_rehome_target(
            graph,
            mid,
            snapped_links=member_scores.get(mid) or [],
            dropped_cids=dropped_set,
            cluster_members_snap=cluster_members_snap,
            valid_ids=valid_ids,
        )
        if target is None:
            unassigned += 1
            continue
        cid, score = target
        _rehome_one(mid, cid, score)
        # ID: bring bind-linked values along.
        if graph.nodes[mid].get("role") in _ID_ROLES:
            for vid in _bind_value_ids(graph, mid):
                if vid in done or vid not in graph.nodes:
                    continue
                vcur = graph.nodes[vid].get("cluster_id")
                if vcur and str(vcur) in valid_ids and _is_member_edge(graph, str(vcur), vid):
                    done.add(vid)
                    continue
                vscore = graph.nodes[vid].get("score_total")
                _rehome_one(
                    vid, cid, float(vscore) if vscore is not None else score
                )

    _rebuild_member_ids(graph)
    return {
        "clusters_dropped": invalid,
        "members_rehomed": rehomed,
        "members_unassigned": unassigned,
    }


def absorb_duplicate_id_texts(
    graph: nx.Graph,
    *,
    distance_norm: float,
    median_char_height: float,
) -> dict[str, Any]:
    """
    Attach isolated texts that duplicate a final id label at nearly the same xy
    so they are not later treated as corridor names.
    """
    radius = max(float(distance_norm) * max(float(median_char_height), 1e-6), 1e-6)
    id_texts: list[tuple[str, str, float, float, str, str]] = []
    for mid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if data.get("role") not in _ID_ROLES:
            continue
        cid = data.get("cluster_id")
        if not cid or cid not in graph.nodes:
            continue
        text = clean_text(str(data.get("text") or ""))
        if not text or data.get("x") is None or data.get("y") is None:
            continue
        id_texts.append(
            (
                str(mid),
                text,
                float(data["x"]),
                float(data["y"]),
                str(cid),
                str(data.get("cluster_type") or ""),
            )
        )

    absorbed = 0
    for nid, data in graph.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if str(data.get("shape_type") or "") != "text":
            continue
        if data.get("cluster_id"):
            continue
        text = clean_text(str(data.get("text") or ""))
        if not text or data.get("x") is None or data.get("y") is None:
            continue
        x, y = float(data["x"]), float(data["y"])
        best: tuple[float, str, str, str] | None = None
        for mid, id_text, ix, iy, cid, ctype in id_texts:
            if mid == nid or id_text != text:
                continue
            d = math.hypot(x - ix, y - iy)
            if d > radius:
                continue
            if best is None or d < best[0]:
                best = (d, cid, ctype, mid)
        if best is None:
            continue
        _, cid, ctype, src = best
        data["cluster_id"] = cid
        data["cluster_type"] = ctype
        data["role"] = graph.nodes[src].get("role")
        data["candidate_cluster_ids"] = list(data.get("candidate_cluster_ids") or [cid])
        if cid not in data["candidate_cluster_ids"]:
            data["candidate_cluster_ids"].append(cid)
        data["duplicate_of"] = src
        members = list(graph.nodes[cid].get("member_ids") or [])
        if nid not in members:
            members.append(str(nid))
            members.sort()
            graph.nodes[cid]["member_ids"] = members
        if not graph.has_edge(cid, nid):
            graph.add_edge(cid, nid, edge_kinds=["member"])
        absorbed += 1
    return {"duplicate_texts_absorbed": absorbed}


def renumber_clusters(graph: nx.Graph) -> dict[str, str]:
    """Rename surviving clusters to contiguous cluster_XXXX ids."""
    old_ids = sorted(
        str(nid)
        for nid, data in graph.nodes(data=True)
        if data.get("node_kind") == "cluster"
    )
    mapping = {old: f"cluster_{i:04d}" for i, old in enumerate(old_ids)}
    if all(old == new for old, new in mapping.items()):
        return mapping

    for _, data in graph.nodes(data=True):
        cid = data.get("cluster_id")
        if cid in mapping:
            data["cluster_id"] = mapping[cid]
        cands = data.get("candidate_cluster_ids")
        if isinstance(cands, list):
            data["candidate_cluster_ids"] = [mapping.get(c, c) for c in cands]

    temp = {old: f"__tmp_cluster_{i:04d}" for i, old in enumerate(old_ids)}
    nx.relabel_nodes(graph, temp, copy=False)
    nx.relabel_nodes(
        graph,
        {temp[old]: mapping[old] for old in old_ids},
        copy=False,
    )
    return mapping


def _count_candidate_annotations_without_home(graph: nx.Graph, snapshot: dict[str, Any]) -> int:
    former = set(snapshot.get("member_scores") or {})
    missing = 0
    for mid in former:
        if mid not in graph.nodes:
            missing += 1
            continue
        cid = graph.nodes[mid].get("cluster_id")
        if not cid or cid not in graph.nodes:
            missing += 1
    return missing


def filter_candidates_to_final(
    graph: nx.Graph,
    cfg: Step1aConfig | None = None,
) -> tuple[nx.Graph, dict[str, Any]]:
    """
    Candidate graph → final clusters.
    Control points: exclusive by score_total.
    Boreholes: keep many-to-many candidate memberships.
    Invalid clusters may be dropped; control-point orphans are rehomed.
    """
    cfg = cfg or Step1aConfig()
    out = graph.copy()
    stats: dict[str, Any] = {
        "input_clusters": sum(
            1 for _, d in out.nodes(data=True) if d.get("node_kind") == "cluster"
        )
    }

    snapshot = _snapshot_candidate_state(out)
    stats.update(resolve_exclusive_memberships(out))
    _rebuild_member_ids(out)
    _recompute_confidence(out)
    stats.update(
        rehome_invalid_cluster_members(
            out,
            snapshot,
            min_confidence=float(cfg.min_final_confidence),
        )
    )
    _recompute_confidence(out)

    char_h = float(
        out.graph.get("median_char_height") or cfg.fallback_char_height
    )
    stats.update(
        absorb_duplicate_id_texts(
            out,
            distance_norm=float(cfg.duplicate_id_text_norm),
            median_char_height=char_h,
        )
    )
    _recompute_confidence(out)
    mapping = renumber_clusters(out)
    stats["cluster_id_mapping"] = mapping
    stats["candidate_members_unassigned"] = _count_candidate_annotations_without_home(
        out, snapshot
    )

    for _, cdata in out.nodes(data=True):
        if cdata.get("node_kind") == "cluster":
            cdata["matching_stage"] = "final"

    by_type = {"控制点": 0, "钻孔": 0}
    for _, cdata in out.nodes(data=True):
        if cdata.get("node_kind") != "cluster":
            continue
        ct = str(cdata.get("cluster_type") or "")
        if ct in by_type:
            by_type[ct] += 1
    cluster_count = sum(by_type.values())
    out.graph["matching_stage"] = "final"
    out.graph["cluster_summary"] = {
        "cluster_count": cluster_count,
        "by_type": by_type,
    }
    out.graph["filter_stats"] = {
        "memberships_dropped": stats.get("memberships_dropped"),
        "clusters_dropped": stats.get("clusters_dropped"),
        "members_rehomed": stats.get("members_rehomed"),
        "members_unassigned": stats.get("members_unassigned"),
        "duplicate_texts_absorbed": stats.get("duplicate_texts_absorbed"),
        "candidate_members_unassigned": stats.get("candidate_members_unassigned"),
    }
    stats["output_clusters"] = cluster_count
    stats["by_type"] = by_type
    return out, stats
