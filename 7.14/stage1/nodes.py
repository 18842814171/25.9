"""Helper: build annotation nodes from text export entities."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx


def load_entities(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("text export must be a list of entities")
    return data


def node_id_of(entity: dict) -> str:
    handle = str(entity.get("handle", "")).strip()
    if handle:
        return handle
    layer = entity.get("layer", "")
    etype = entity.get("type", "")
    return f"{etype}:{layer}:{id(entity)}"


def position_of(attributes: dict) -> tuple[float, float] | None:
    if "insert_point" in attributes:
        p = attributes["insert_point"]
        return float(p[0]), float(p[1])
    if "center" in attributes:
        p = attributes["center"]
        return float(p[0]), float(p[1])
    if "location" in attributes:
        p = attributes["location"]
        return float(p[0]), float(p[1])
    return None


def text_content_of(attributes: dict) -> str:
    text = attributes.get("text")
    if text is None:
        return ""
    return str(text)


def char_height_of(attributes: dict) -> float:
    for key in ("char_height", "height"):
        if key in attributes and attributes[key] is not None:
            return float(attributes[key])
    return 4.0


def rotation_of(attributes: dict) -> float:
    if "rotation" in attributes and attributes["rotation"] is not None:
        return float(attributes["rotation"])
    return 0.0


def entity_to_node_attrs(entity: dict) -> dict | None:
    etype = str(entity.get("type", ""))
    layer = str(entity.get("layer", ""))
    attributes = entity.get("attributes") or {}
    pos = position_of(attributes)
    if pos is None:
        return None

    attrs = {
        "node_kind": "annotation",
        "entity_type": etype,
        "layer": layer,
        "layer_class": "",
        "x": pos[0],
        "y": pos[1],
        "text": text_content_of(attributes),
        "char_height": char_height_of(attributes),
        "rotation": rotation_of(attributes),
        "radius": None,
        "block_name": None,
    }
    if etype == "CIRCLE":
        attrs["radius"] = float(attributes.get("radius", 0.0) or 0.0)
        attrs["char_height"] = 0.0
    if etype == "INSERT":
        attrs["block_name"] = attributes.get("name") or attributes.get("block_name")
        if "radius" in attributes and attributes["radius"] is not None:
            attrs["radius"] = float(attributes["radius"])
    return attrs


def build_node_graph(entities: list[dict]) -> nx.Graph:
    graph = nx.Graph()
    graph.graph["graph_name"] = "text_node_graph"
    for entity in entities:
        etype = str(entity.get("type", ""))
        if etype not in {"TEXT", "MTEXT", "CIRCLE", "INSERT", "POINT"}:
            continue
        attrs = entity_to_node_attrs(entity)
        if attrs is None:
            continue
        nid = node_id_of(entity)
        if graph.has_node(nid):
            continue
        graph.add_node(nid, **attrs)
    return graph
