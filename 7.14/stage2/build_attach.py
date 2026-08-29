"""Attach facility nodes onto structure_graph_with_texts."""

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

from config import Stage2Config

EDGE_ON_CENTERLINE = "on-centerline"
EDGE_MEMBER = "member"


def build_structure_graph_with_facilities(
    structure: nx.Graph,
    facility_graph: nx.Graph,
    cfg: Stage2Config,
) -> nx.Graph:
    graph = copy.deepcopy(structure)
    centerlines = centerline_catalog(graph, cfg.attach_centerline_roles)

    facility_nodes = [
        (str(nid), dict(data))
        for nid, data in facility_graph.nodes(data=True)
        if data.get("node_kind") == "facility"
    ]
    facility_nodes.sort(key=lambda item: item[0])
    anchors = [
        (float(d["x"]), float(d["y"]))
        for _, d in facility_nodes
        if d.get("x") is not None and d.get("y") is not None
    ]
    threshold = infer_attach_threshold(
        graph,
        anchors,
        centerlines,
        outlier_cap_width_factor=cfg.outlier_cap_width_factor,
        attach_distance_percentile=cfg.attach_distance_percentile,
        attach_distance_width_factor=cfg.attach_distance_width_factor,
        attach_distance_fallback=cfg.attach_distance_fallback,
    )

    attached: dict[str, int] = {}
    skipped = {"beyond_threshold": 0, "missing_xy": 0, "id_collision": 0}

    for fid, fdata in facility_nodes:
        if fid in graph:
            skipped["id_collision"] += 1
            continue
        facility_type = str(fdata.get("facility_type") or "通风设施")
        graph.add_node(
            fid,
            node_kind="facility",
            facility_type=facility_type,
            confidence=fdata.get("confidence"),
            member_ids=list(fdata.get("member_ids") or []),
            block_names=list(fdata.get("block_names") or []),
            x=fdata.get("x"),
            y=fdata.get("y"),
            label_text=facility_type,
            text=facility_type,
            attach_kind=facility_type,
        )

        for mid in fdata.get("member_ids") or []:
            mid_s = str(mid)
            if mid_s not in facility_graph:
                continue
            if mid_s in graph:
                continue
            pdata = facility_graph.nodes[mid_s]
            graph.add_node(
                mid_s,
                node_kind="primitive",
                entity_type=pdata.get("entity_type"),
                layer=pdata.get("layer"),
                text=pdata.get("text"),
                x=pdata.get("x"),
                y=pdata.get("y"),
                block_name=pdata.get("block_name"),
                length=pdata.get("length"),
                size=pdata.get("size"),
                closed=pdata.get("closed"),
                radius=pdata.get("radius"),
                endpoints=list(pdata.get("endpoints") or []),
                path_points=list(pdata.get("path_points") or []),
                arc_start_angle=pdata.get("arc_start_angle"),
                arc_end_angle=pdata.get("arc_end_angle"),
                facility_id=fid,
                facility_type=facility_type,
            )
            graph.add_edge(fid, mid_s, edge_kind=EDGE_MEMBER, edge_kinds=[EDGE_MEMBER])

        px, py = fdata.get("x"), fdata.get("y")
        if px is None or py is None:
            skipped["missing_xy"] += 1
            graph.nodes[fid]["attach_status"] = "missing_xy"
            continue

        hit = nearest_centerline(float(px), float(py), centerlines)
        if hit is None or float(hit["distance"]) > threshold:
            skipped["beyond_threshold"] += 1
            graph.nodes[fid]["attach_status"] = "beyond_threshold"
            if hit is not None:
                graph.nodes[fid]["nearest_centerline_id"] = hit["centerline_id"]
                graph.nodes[fid]["nearest_distance"] = hit["distance"]
            continue

        cid = hit["centerline_id"]
        graph.add_edge(
            fid,
            cid,
            edge_kind=EDGE_ON_CENTERLINE,
            distance=float(hit["distance"]),
            t=float(hit["t"]),
            foot_x=float(hit["foot_x"]),
            foot_y=float(hit["foot_y"]),
        )
        graph.nodes[fid]["attach_status"] = "attached"
        graph.nodes[fid]["attached_centerline_id"] = cid
        attached[facility_type] = attached.get(facility_type, 0) + 1

    graph.graph["graph_name"] = "structure_graph_with_facilities"
    graph.graph["kind"] = "structure_graph_with_facilities"
    graph.graph["facility_attach_threshold"] = threshold
    graph.graph["facility_attach_summary"] = {
        "attached": attached,
        "skipped": skipped,
        "centerline_candidates": len(centerlines),
    }
    graph.graph["stage2_config"] = cfg.to_json()
    return graph
