"""Build structure_graph_with_texts by attaching clusters and corridor labels.

Primary topology input: structure_graph
Annotation payload: final_cluster (cluster nodes + corridor-layer texts)
Output topology: structure_graph_with_texts
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import networkx as nx

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.attach_centerlines import centerline_catalog, infer_attach_threshold
from utils.attach_geometry import nearest_centerline

from config import Step1bConfig

EDGE_ON_CENTERLINE = "on-centerline"
EDGE_MEMBER = "member"
ATTACH_KIND_CORRIDOR_NAME = "巷道名称"


def _candidate_anchor_points(
    clusters: nx.Graph,
    cfg: Step1bConfig,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for _, data in clusters.nodes(data=True):
        if data.get("node_kind") != "cluster":
            continue
        if data.get("x") is None or data.get("y") is None:
            continue
        points.append((float(data["x"]), float(data["y"])))
    for _, data in collect_isolated_text_nodes(clusters, cfg):
        points.append((float(data["x"]), float(data["y"])))
    return points


def _cluster_label(clusters: nx.Graph, cluster_id: str, cdata: dict) -> str:
    members = cdata.get("member_ids") or []
    preferred_roles = ("point_id", "borehole_id", "collar")
    for role in preferred_roles:
        for mid in members:
            if mid not in clusters:
                continue
            m = clusters.nodes[mid]
            if m.get("role") == role and m.get("text"):
                return str(m["text"]).strip()
    for mid in members:
        if mid not in clusters:
            continue
        m = clusters.nodes[mid]
        text = str(m.get("text") or "").strip()
        if text:
            return text
    return str(cdata.get("cluster_type") or cluster_id)


def _copy_annotation_node(graph: nx.Graph, nid: str, data: dict, **extra: Any) -> None:
    payload = {
        "node_kind": "annotation",
        "shape_type": data.get("shape_type"),
        "layer": data.get("layer"),
        "text": data.get("text"),
        "x": data.get("x"),
        "y": data.get("y"),
        "char_height": data.get("char_height"),
        "rotation": data.get("rotation"),
        "radius": data.get("radius"),
        "block_name": data.get("block_name"),
        "role": data.get("role"),
        "cluster_id": data.get("cluster_id"),
        "cluster_type": data.get("cluster_type"),
        "point_score": data.get("point_score"),
    }
    payload.update(extra)
    graph.add_node(str(nid), **payload)


def _try_attach(
    graph: nx.Graph,
    source_id: str,
    px: float,
    py: float,
    centerlines: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any] | None:
    hit = nearest_centerline(px, py, centerlines)
    if hit is None:
        return None
    if float(hit["distance"]) > threshold:
        graph.nodes[source_id]["attach_status"] = "beyond_threshold"
        graph.nodes[source_id]["nearest_centerline_id"] = hit["centerline_id"]
        graph.nodes[source_id]["nearest_distance"] = hit["distance"]
        return None
    cid = hit["centerline_id"]
    graph.add_edge(
        source_id,
        cid,
        edge_kind=EDGE_ON_CENTERLINE,
        distance=float(hit["distance"]),
        t=float(hit["t"]),
        foot_x=float(hit["foot_x"]),
        foot_y=float(hit["foot_y"]),
    )
    graph.nodes[source_id]["attach_status"] = "attached"
    graph.nodes[source_id]["attached_centerline_id"] = cid
    return hit


def collect_isolated_text_nodes(
    clusters: nx.Graph,
    cfg: Step1bConfig,
) -> list[tuple[str, dict]]:
    """未入组的孤立文字（核对图中灰色文字）一律视为巷道名称。"""
    rows: list[tuple[str, dict]] = []
    for nid, data in clusters.nodes(data=True):
        if data.get("node_kind") != "annotation":
            continue
        if data.get("cluster_id"):
            continue
        if str(data.get("shape_type") or "") != "text":
            continue
        text = str(data.get("text") or "").strip()
        if not text:
            continue
        if data.get("x") is None or data.get("y") is None:
            continue
        rows.append((str(nid), data))
    rows.sort(key=lambda item: item[0])
    return rows


def build_structure_graph_with_texts(
    structure: nx.Graph,
    clusters: nx.Graph,
    cfg: Step1bConfig,
) -> nx.Graph:
    """Copy structure graph and hang clusters / corridor labels onto centerlines."""
    graph = copy.deepcopy(structure)
    centerlines = centerline_catalog(graph, cfg.attach_centerline_roles)
    threshold = infer_attach_threshold(
        graph,
        _candidate_anchor_points(clusters, cfg),
        centerlines,
        outlier_cap_width_factor=cfg.outlier_cap_width_factor,
        attach_distance_percentile=cfg.attach_distance_percentile,
        attach_distance_width_factor=cfg.attach_distance_width_factor,
        attach_distance_fallback=cfg.attach_distance_fallback,
    )

    attached = {"控制点": 0, "钻孔": 0, ATTACH_KIND_CORRIDOR_NAME: 0}
    skipped = {"beyond_threshold": 0, "missing_xy": 0}

    cluster_nodes = [
        (str(nid), data)
        for nid, data in clusters.nodes(data=True)
        if data.get("node_kind") == "cluster"
    ]
    cluster_nodes.sort(key=lambda item: item[0])

    for cid, cdata in cluster_nodes:
        if cid in graph:
            raise ValueError(f"cluster id collides with structure node: {cid}")
        px = cdata.get("x")
        py = cdata.get("y")
        label = _cluster_label(clusters, cid, cdata)
        cluster_type = str(cdata.get("cluster_type") or "")
        graph.add_node(
            cid,
            node_kind="cluster",
            cluster_type=cluster_type,
            kind=cdata.get("kind"),
            confidence=cdata.get("confidence"),
            member_ids=list(cdata.get("member_ids") or []),
            x=px,
            y=py,
            label_text=label,
            text=label,
            attach_kind=cluster_type or "cluster",
        )
        for mid in cdata.get("member_ids") or []:
            mid_s = str(mid)
            if mid_s not in clusters:
                continue
            if mid_s not in graph:
                _copy_annotation_node(graph, mid_s, clusters.nodes[mid_s])
            graph.add_edge(
                cid,
                mid_s,
                edge_kind=EDGE_MEMBER,
                edge_kinds=[EDGE_MEMBER],
            )

        if px is None or py is None:
            skipped["missing_xy"] += 1
            graph.nodes[cid]["attach_status"] = "missing_xy"
            continue
        hit = _try_attach(graph, cid, float(px), float(py), centerlines, threshold)
        if hit is None:
            if graph.nodes[cid].get("attach_status") == "beyond_threshold":
                skipped["beyond_threshold"] += 1
        else:
            if cluster_type in attached:
                attached[cluster_type] += 1

    for nid, data in collect_isolated_text_nodes(clusters, cfg):
        if nid in graph:
            raise ValueError(f"annotation id collides with structure node: {nid}")
        text = str(data.get("text") or "").strip()
        _copy_annotation_node(
            graph,
            nid,
            data,
            attach_kind=ATTACH_KIND_CORRIDOR_NAME,
            label_text=text,
        )
        px = float(data["x"])
        py = float(data["y"])
        hit = _try_attach(graph, nid, px, py, centerlines, threshold)
        if hit is None:
            if graph.nodes[nid].get("attach_status") == "beyond_threshold":
                skipped["beyond_threshold"] += 1
        else:
            attached[ATTACH_KIND_CORRIDOR_NAME] += 1

    graph.graph["graph_name"] = "structure_graph_with_texts"
    graph.graph["kind"] = "structure_graph_with_texts"
    graph.graph["schema_version"] = 1
    graph.graph["attach_threshold"] = threshold
    graph.graph["attach_summary"] = {
        "attached": attached,
        "skipped": skipped,
        "centerline_candidates": len(centerlines),
    }
    graph.graph["step1b_config"] = cfg.to_json()
    return graph
