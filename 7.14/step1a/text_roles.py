"""文字按图层归类：1) 过滤无关图层 2) 关键词→三类 3) 族内按是否数值定角色。

词典形态：{control_point: [词…], borehole: [词…]}（见 stage1/layer_synonyms.json）。
族内：非数值 → 标号；数值 → 标高 / 孔口 / 煤层相关值。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.layer_synonyms import (
    is_collar_layer,
    match_family,
)
from utils.text_clean import clean_text

from config import Step1aConfig

__all__ = [
    "clean_text",
    "annotation_family",
    "classify_caption_kind",
    "classify_text_role",
    "has_chinese",
    "is_borehole_layer",
    "is_control_point_layer",
    "is_excluded_layer",
    "is_elevation_text",
    "is_point_id_candidate",
    "is_pure_numeric",
    "borehole_layer_numeric_role",
    "borehole_layer_id_layer",
    "seed_role_from_layer_name",
    "role_allowed_for_cluster",
]

CFG = Step1aConfig()


def has_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))


def is_pure_numeric(text: str) -> bool:
    """纯数值（标高 / 煤厚一类）。用解析判断，不用正则。"""
    t = clean_text(text)
    if not t:
        return False
    try:
        float(t)
    except ValueError:
        return False
    return True


def is_elevation_text(text: str) -> bool:
    """数值型标高文字；容忍导出时尾随逗号。"""
    t = clean_text(text).rstrip(",").strip()
    return is_pure_numeric(t)


def is_excluded_layer(layer: str, cfg: Step1aConfig | None = None) -> bool:
    """步骤1：是否命中无关图层排除名单。"""
    cfg = cfg or CFG
    layer = layer or ""
    if not layer:
        return False
    if layer == cfg.template_layer:
        return True
    if layer in set(cfg.layer_exclude_names):
        return True
    return any(tok in layer for tok in cfg.layer_exclude_tokens)


def annotation_family(layer: str) -> str:
    """
    步骤2：图层关键词 → control_point / borehole / other。
    排除名单与未命中词典一律 other。
    """
    if is_excluded_layer(layer):
        return "other"
    return match_family(layer or "")


def is_control_point_layer(layer: str) -> bool:
    return annotation_family(layer) == "control_point"


def is_borehole_layer(layer: str) -> bool:
    return annotation_family(layer) == "borehole"


def borehole_layer_id_layer(layer: str) -> bool:
    """图层名是否像孔号层（含孔号/钻孔名称等）；族内非数值本就可当地号。"""
    if annotation_family(layer) != "borehole":
        return False
    layer = layer or ""
    return any(tok in layer for tok in ("孔号", "钻孔名称", "钻孔号"))


def borehole_layer_numeric_role(layer: str) -> str:
    """钻孔族纯数字：孔口类图层 → collar，其余 → seam_value。"""
    if is_collar_layer(layer):
        return "collar"
    return "seam_value"


def seed_role_from_layer_name(layer: str) -> str | None:
    """
    识别规则种子：只看族 + 少量图层提示。
    混合层（如「钻孔」兼有孔号与数值）返回 None，由文字是否数值决定。
    """
    family = annotation_family(layer)
    if family == "control_point":
        layer = layer or ""
        if "高程" in layer or "标高" in layer:
            return "elevation"
        return "point_id"
    if family == "borehole":
        if borehole_layer_id_layer(layer):
            return "borehole_id"
        if is_collar_layer(layer):
            return "collar"
        return None
    return None


def is_point_id_candidate(text: str, layer: str = "") -> bool:
    """测点族图层上，非空且非纯数值 → 标号。"""
    t = clean_text(text)
    if not t or is_pure_numeric(t):
        return False
    return annotation_family(layer) == "control_point"


def classify_caption_kind(text: str) -> str | None:
    """图例标题：与图层同一套同义词词典子串匹配 → control_point / borehole / None。"""
    t = clean_text(text)
    if not t or len(t) > 40:
        return None
    family = match_family(t)
    return None if family == "other" else family


def classify_text_role(text: str, layer: str | None = None) -> str:
    """
    文字角色：三类族 + 是否纯数值。
    族内：非数值 → 标号；数值 → 标高/孔口/煤层值。
    """
    t = clean_text(text)
    layer = layer or ""
    if not t:
        return "other"

    family = annotation_family(layer)
    if family == "other":
        return "other"

    kind = classify_caption_kind(t)
    if kind == "control_point" and has_chinese(t):
        return "caption_control"
    if kind == "borehole" and has_chinese(t):
        return "caption_borehole"

    if family == "control_point":
        if is_elevation_text(t):
            return "elevation"
        return "point_id"

    if family == "borehole":
        if is_elevation_text(t):
            return borehole_layer_numeric_role(layer)
        return "borehole_id"

    return "other"


def role_allowed_for_cluster(cluster_type: str, role: str) -> bool:
    if cluster_type == "control_point":
        return role in {"point_id", "elevation"}
    if cluster_type == "borehole":
        return role in {"borehole_id", "elevation", "collar", "seam_value"}
    return False
