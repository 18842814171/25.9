"""读取 entity_export 写出的根目录 JSON（handle/type/layer/attributes 列表）。"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

from .text_clean import clean_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Fixed product naming when callers do not pass an export config.
_MODE_SUFFIX = {
    "line": "巷道",
    "text": "文字",
    "facility": "设施",
    "legend": "图例",
}


def load_export_config(config_path: Path | str) -> dict:
    if config_path is None or str(config_path).strip() == "":
        raise ValueError("必须指定导出配置文件路径，不允许默认或留空")
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"导出配置不存在: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def exported_json_path(
    stem: str,
    mode: str,
    *,
    config_path: Path | str | None = None,
    base_dir: Path | str | None = None,
    filename: str | None = None,
) -> Path:
    """解析导出 JSON 路径。

    若传入 ``config_path``，按配置中该 mode 的 ``output_filename`` 模板；
    否则仅用固定命名 ``{stem}-{巷道|文字|设施|图例}.json``（不读取任何默认配置文件）。
    """
    if filename:
        name = filename
    elif config_path is not None and str(config_path).strip() != "":
        config = load_export_config(config_path)
        section = config[mode]
        # 图号含点号（如 2026.1-1），不可用 Path(stem).stem，否则会被截断
        name = (
            section["output_filename"]
            .replace("{dxf_name}", stem)
            .replace("{dxf_stem}", stem)
        )
    else:
        suffix = _MODE_SUFFIX.get(mode)
        if not suffix:
            raise ValueError(f"unknown export mode for fixed naming: {mode}")
        name = f"{stem}-{suffix}.json"
    root = Path(base_dir) if base_dir is not None else PROJECT_ROOT
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    return root / name


def resolve_output_filename(template: str, dxf_path: Path) -> str:
    dxf_name = dxf_path.stem
    return (
        template.replace("{dxf_name}", dxf_name)
        .replace("{dxf_stem}", dxf_name)
        .replace("{dxf_file_path}", dxf_path.as_posix())
    )


def load_entity_export(path: Path | str) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"entity export JSON not found: {p} "
            f"(run: python utils/entity_export.py --mode …)"
        )
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"entity export must be a list: {p}")
    return data


def filter_export_entities(
    entities: list[dict],
    *,
    types: Iterable[str] | None = None,
    layers: Iterable[str] | None = None,
) -> list[dict]:
    type_set = set(types) if types is not None else None
    layer_set = set(layers) if layers is not None else None
    out: list[dict] = []
    for ent in entities:
        if type_set is not None and ent.get("type") not in type_set:
            continue
        if layer_set is not None and ent.get("layer") not in layer_set:
            continue
        out.append(ent)
    return out


def _xy_from_attributes(attributes: dict) -> tuple[float, float] | None:
    if "insert_point" in attributes:
        p = attributes["insert_point"]
        return float(p[0]), float(p[1])
    if "center" in attributes:
        p = attributes["center"]
        return float(p[0]), float(p[1])
    if "location" in attributes:
        p = attributes["location"]
        return float(p[0]), float(p[1])
    if "start" in attributes and "end" in attributes:
        s, e = attributes["start"], attributes["end"]
        return (float(s[0]) + float(e[0])) * 0.5, (float(s[1]) + float(e[1])) * 0.5
    if "points" in attributes and attributes["points"]:
        pts = attributes["points"]
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        return (min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5
    if "vertices" in attributes and attributes["vertices"]:
        pts = attributes["vertices"]
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        return (min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5
    if "path_points" in attributes and attributes["path_points"]:
        pts = attributes["path_points"]
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        return (min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5
    return None


def to_annotation_record(entity: dict, *, ref_size: float | None = None) -> dict | None:
    """导出实体 → step1a 标注节点；只保留抽象 shape_type，不存原始 DXF 类型。

    保留 text / point-like / line-like；line-like 可参与字–线–字绑定与图例分隔线记录。
    """
    from .shape_abstract import classify_shape

    attrs = entity.get("attributes") or {}
    pos = _xy_from_attributes(attrs)
    if pos is None:
        return None

    shape = classify_shape(entity, ref_size=ref_size)
    shape_type = shape["shape_type"]
    if shape_type == "other":
        return None

    feats = dict(shape.get("features") or {})
    feats.pop("entity_type", None)

    rec = {
        "id": str(entity.get("handle") or ""),
        "layer": str(entity.get("layer") or ""),
        "text": clean_text(str(attrs.get("text") or attrs.get("actual_text") or "")),
        "x": pos[0],
        "y": pos[1],
        "char_height": 0.0,
        "rotation": float(attrs.get("rotation") or 0.0),
        "radius": None,
        "block_name": None,
        "length": float(feats.get("perimeter") or 0.0),
        "shape_type": shape_type,
        "point_score": shape.get("point_score"),
        "shape_features": feats,
        "closed": bool(feats.get("closed")),
    }
    if shape_type == "text":
        h = attrs.get("char_height", attrs.get("height", 0.0))
        rec["char_height"] = float(h or 0.0)
        # 字串横向跨度近似：字高 × 字符数（汉字按等宽）
        t = rec["text"]
        rec["length"] = float(h or 0.0) * max(len(t), 1)
    elif shape_type == "point-like":
        if attrs.get("radius") is not None:
            rec["radius"] = float(attrs["radius"])
        else:
            max_side = float(feats.get("max_side") or 0.0)
            if max_side > 0:
                rec["radius"] = max_side * 0.5
        if attrs.get("block_name"):
            rec["block_name"] = str(attrs.get("block_name") or "")
    elif shape_type == "line-like":
        if "start" in attrs and "end" in attrs:
            s, e = attrs["start"], attrs["end"]
            dx = float(e[0]) - float(s[0])
            dy = float(e[1]) - float(s[1])
            length = math.hypot(dx, dy)
            rec["length"] = length
            if length > 1e-12:
                rec["rotation"] = math.degrees(math.atan2(dy, dx))
        elif not rec["length"]:
            rec["length"] = float(feats.get("max_side") or 0.0)
    if not rec["id"]:
        return None
    return rec


def to_facility_record(entity: dict) -> dict | None:
    """设施导出实体 → stage2 图元节点字段。"""
    et = str(entity.get("type") or "")
    attrs = entity.get("attributes") or {}
    pos = _xy_from_attributes(attrs)
    if pos is None:
        return None
    rec: dict = {
        "id": str(entity.get("handle") or ""),
        "entity_type": et,
        "layer": str(entity.get("layer") or ""),
        "text": clean_text(str(attrs.get("text") or attrs.get("actual_text") or "")),
        "x": pos[0],
        "y": pos[1],
        "char_height": 0.0,
        "rotation": float(attrs.get("rotation") or 0.0),
        "radius": None,
        "block_name": None,
        "length": 0.0,
        "size": 0.0,
        "vertex_count": 0,
        "closed": bool(attrs.get("closed") or False),
        "pattern_name": attrs.get("pattern_name"),
        "scale_x": 1.0,
        "scale_y": 1.0,
        "endpoints": [],
        "path_points": [],
        "arc_start_angle": None,
        "arc_end_angle": None,
    }
    if not rec["id"]:
        return None

    if et == "TEXT":
        rec["char_height"] = float(attrs.get("height") or 0.0)
        rec["size"] = rec["char_height"]
        rec["endpoints"] = [[rec["x"], rec["y"]]]
    elif et == "MTEXT":
        rec["char_height"] = float(attrs.get("char_height") or 0.0)
        rec["size"] = rec["char_height"]
        rec["endpoints"] = [[rec["x"], rec["y"]]]
    elif et == "CIRCLE":
        r = float(attrs.get("radius") or 0.0)
        rec["radius"] = r
        rec["length"] = 2.0 * math.pi * r
        rec["size"] = 2.0 * r
        rec["closed"] = True
    elif et == "ARC":
        r = float(attrs.get("radius") or 0.0)
        a0 = float(attrs.get("start_angle") or 0.0)
        a1 = float(attrs.get("end_angle") or 0.0)
        cx, cy = float(attrs["center"][0]), float(attrs["center"][1])
        rec["radius"] = r
        rec["length"] = abs(a1 - a0) * math.pi / 180.0 * r
        rec["size"] = r
        rec["rotation"] = a0
        rec["arc_start_angle"] = a0
        rec["arc_end_angle"] = a1
        r0, r1 = math.radians(a0), math.radians(a1)
        rec["endpoints"] = [
            [cx + r * math.cos(r0), cy + r * math.sin(r0)],
            [cx + r * math.cos(r1), cy + r * math.sin(r1)],
        ]
        rec["path_points"] = list(rec["endpoints"])
    elif et == "LINE":
        x1, y1 = float(attrs["start"][0]), float(attrs["start"][1])
        x2, y2 = float(attrs["end"][0]), float(attrs["end"][1])
        length = math.hypot(x2 - x1, y2 - y1)
        rec["length"] = length
        rec["size"] = length
        rec["vertex_count"] = 2
        if length > 1e-12:
            rec["rotation"] = math.degrees(math.atan2(y2 - y1, x2 - x1))
        rec["endpoints"] = [[x1, y1], [x2, y2]]
        rec["path_points"] = list(rec["endpoints"])
    elif et == "LWPOLYLINE":
        pts = [[float(p[0]), float(p[1])] for p in (attrs.get("points") or [])]
        if len(pts) < 2:
            return None
        length = sum(
            math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            for i in range(len(pts) - 1)
        )
        if attrs.get("closed") and len(pts) >= 2:
            length += math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        rec["length"] = length
        rec["size"] = max(max(xs) - min(xs), max(ys) - min(ys), length)
        rec["vertex_count"] = len(pts)
        rec["path_points"] = pts
        rec["endpoints"] = list(pts) if attrs.get("closed") else [pts[0], pts[-1]]
    elif et == "POLYLINE":
        pts = [[float(p[0]), float(p[1])] for p in (attrs.get("vertices") or [])]
        if len(pts) < 2:
            return None
        length = sum(
            math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            for i in range(len(pts) - 1)
        )
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        rec["length"] = length
        rec["size"] = max(max(xs) - min(xs), max(ys) - min(ys), length)
        rec["vertex_count"] = len(pts)
        rec["path_points"] = pts
        rec["endpoints"] = list(pts) if attrs.get("closed") else [pts[0], pts[-1]]
    elif et == "INSERT":
        rec["block_name"] = str(attrs.get("block_name") or "")
        scale = attrs.get("scale") or [1, 1, 1]
        rec["scale_x"] = float(scale[0]) if len(scale) > 0 else 1.0
        rec["scale_y"] = float(scale[1]) if len(scale) > 1 else 1.0
        rec["size"] = float(max(abs(rec["scale_x"]), abs(rec["scale_y"])))
        rec["endpoints"] = [[rec["x"], rec["y"]]]
        rec["path_points"] = [[rec["x"], rec["y"]]]
    elif et == "HATCH":
        pts = [[float(p[0]), float(p[1])] for p in (attrs.get("path_points") or [])]
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            size = max(max(xs) - min(xs), max(ys) - min(ys))
            rec["x"] = (min(xs) + max(xs)) * 0.5
            rec["y"] = (min(ys) + max(ys)) * 0.5
            rec["size"] = float(size)
            rec["length"] = float(size)
            rec["path_points"] = pts
        else:
            rec["size"] = 0.0
        rec["closed"] = True
        rec["pattern_name"] = str(attrs.get("pattern_name") or "")
    else:
        return None
    return rec


def load_annotation_records(
    stem: str,
    *,
    path: Path | str | None = None,
    types: Iterable[str] | None = None,
    include_line_like: bool = True,
) -> tuple[list[dict], Path]:
    """加载文字导出 JSON → 标注记录（含 shape_type）。

    默认不限 DXF 类型；默认保留 line-like（字–线–字绑定 / 图例分隔线）。
    """
    json_path = Path(path) if path else exported_json_path(stem, "text")
    entities = filter_export_entities(load_entity_export(json_path), types=types)
    # 先收文字估字高，再统一分类
    provisional_heights = []
    for ent in entities:
        et = str(ent.get("type") or "")
        if et not in {"TEXT", "MTEXT"}:
            continue
        attrs = ent.get("attributes") or {}
        h = attrs.get("char_height", attrs.get("height", 0.0))
        if h:
            provisional_heights.append(float(h))
    ref_size = None
    if provisional_heights:
        provisional_heights.sort()
        ref_size = provisional_heights[len(provisional_heights) // 2]

    records = []
    for ent in entities:
        rec = to_annotation_record(ent, ref_size=ref_size)
        if rec is None:
            continue
        if not include_line_like and rec.get("shape_type") == "line-like":
            continue
        records.append(rec)
    return records, json_path


def load_facility_records(
    stem: str,
    *,
    path: Path | str | None = None,
    types: Iterable[str] | None = None,
    layers: Iterable[str] | None = None,
) -> tuple[list[dict], Path]:
    json_path = Path(path) if path else exported_json_path(stem, "facility")
    entities = filter_export_entities(
        load_entity_export(json_path), types=types, layers=layers
    )
    records = []
    for ent in entities:
        rec = to_facility_record(ent)
        if rec is not None:
            records.append(rec)
    return records, json_path


def load_legend_annotation_records(
    stem: str,
    *,
    path: Path | str | None = None,
    types: Iterable[str] | None = None,
    include_line_like: bool = True,
) -> tuple[list[dict], Path]:
    """图例 JSON → step1a 标注记录（测点/钻孔图例模板；默认含 line-like）。"""
    json_path = Path(path) if path else exported_json_path(stem, "legend")
    entities = filter_export_entities(load_entity_export(json_path), types=types)
    provisional_heights = []
    for ent in entities:
        et = str(ent.get("type") or "")
        if et not in {"TEXT", "MTEXT"}:
            continue
        attrs = ent.get("attributes") or {}
        h = attrs.get("char_height", attrs.get("height", 0.0))
        if h:
            provisional_heights.append(float(h))
    ref_size = None
    if provisional_heights:
        provisional_heights.sort()
        ref_size = provisional_heights[len(provisional_heights) // 2]
    records = []
    for ent in entities:
        rec = to_annotation_record(ent, ref_size=ref_size)
        if rec is None:
            continue
        if not include_line_like and rec.get("shape_type") == "line-like":
            continue
        records.append(rec)
    return records, json_path


def load_legend_facility_records(
    stem: str,
    *,
    path: Path | str | None = None,
    types: Iterable[str] | None = None,
) -> tuple[list[dict], Path]:
    """图例 JSON → stage2 设施图元记录（通风设施图例模板）。"""
    json_path = Path(path) if path else exported_json_path(stem, "legend")
    entities = filter_export_entities(load_entity_export(json_path), types=types)
    records = []
    for ent in entities:
        rec = to_facility_record(ent)
        if rec is not None:
            records.append(rec)
    return records, json_path
