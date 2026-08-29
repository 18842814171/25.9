"""图元形状抽象：按几何特征评为 text / point-like / line-like。

不依赖 DXF 原始类型。line-like 可参与字–线–字绑定与图例分隔线记录；
锚点与文字组合仍以 point-like 与 text 的关联为主。

像点 vs 像线以**长宽比 / 闭合 / 圆度**为主，不以绝对外框尺寸否决：
正方形大符号（如图块包围盒偏大）仍可为 point-like；细长描边才为 line-like。
"""

from __future__ import annotations

import math
from typing import Any


# 相对字高的软参考（仅作弱权重，不单独决定 line-like）
DEFAULT_MAX_POINT_SIDE = 5.0
DEFAULT_MAX_POINT_AREA = 40.0
DEFAULT_POINT_SCORE_THRESHOLD = 0.55
# 长宽比超过该值，强烈倾向线状
DEFAULT_LINE_ASPECT = 3.0


def _as_xy_points(attrs: dict) -> list[tuple[float, float]]:
    if attrs.get("points"):
        return [(float(p[0]), float(p[1])) for p in attrs["points"]]
    if attrs.get("vertices"):
        return [(float(p[0]), float(p[1])) for p in attrs["vertices"]]
    if attrs.get("path_points"):
        return [(float(p[0]), float(p[1])) for p in attrs["path_points"]]
    if "start" in attrs and "end" in attrs:
        s, e = attrs["start"], attrs["end"]
        return [(float(s[0]), float(s[1])), (float(e[0]), float(e[1]))]
    return []


def _polyline_length(pts: list[tuple[float, float]], closed: bool) -> float:
    if len(pts) < 2:
        return 0.0
    length = sum(
        math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        for i in range(len(pts) - 1)
    )
    if closed and len(pts) >= 2:
        length += math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
    return length


def _polygon_area(pts: list[tuple[float, float]]) -> float:
    if len(pts) < 3:
        return 0.0
    area = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def geometry_features(entity: dict) -> dict[str, Any]:
    """从导出 JSON 实体计算外框、闭合、圆度、面积等。"""
    et = str(entity.get("type") or entity.get("entity_type") or "")
    attrs = entity.get("attributes") or {}
    feats: dict[str, Any] = {
        "entity_type": et,
        "bbox_w": 0.0,
        "bbox_h": 0.0,
        "max_side": 0.0,
        "min_side": 0.0,
        "aspect": 1.0,
        "closed": False,
        "circularity": 0.0,
        "area": 0.0,
        "perimeter": 0.0,
        "const_width": 0.0,
    }

    if et in {"TEXT", "MTEXT"}:
        h = float(attrs.get("char_height") or attrs.get("height") or 0.0)
        feats["bbox_w"] = h
        feats["bbox_h"] = h
        feats["max_side"] = h
        feats["min_side"] = h
        feats["area"] = h * h
        return feats

    if et == "CIRCLE":
        r = float(attrs.get("radius") or 0.0)
        d = 2.0 * r
        feats.update(
            {
                "bbox_w": d,
                "bbox_h": d,
                "max_side": d,
                "min_side": d,
                "closed": True,
                "circularity": 1.0,
                "area": math.pi * r * r,
                "perimeter": 2.0 * math.pi * r,
            }
        )
        return feats

    if et == "POINT":
        feats["closed"] = True
        feats["circularity"] = 1.0
        return feats

    if et == "INSERT":
        # 优先用导出/清洗脚本写入的真实包围盒；否则退回 scale 代理
        bw = attrs.get("bbox_w")
        bh = attrs.get("bbox_h")
        if bw is not None and bh is not None:
            sx = abs(float(bw))
            sy = abs(float(bh))
        else:
            scale = attrs.get("scale") or [1, 1, 1]
            sx = abs(float(scale[0])) if scale else 1.0
            sy = abs(float(scale[1])) if len(scale) > 1 else sx
        feats.update(
            {
                "bbox_w": sx,
                "bbox_h": sy,
                "max_side": max(sx, sy),
                "min_side": min(sx, sy),
                "aspect": max(sx, sy) / max(min(sx, sy), 1e-9),
                "closed": True,
                "circularity": 0.7,
                "area": sx * sy,
            }
        )
        return feats

    if et == "ARC":
        r = float(attrs.get("radius") or 0.0)
        a0 = float(attrs.get("start_angle") or 0.0)
        a1 = float(attrs.get("end_angle") or 0.0)
        span = abs(a1 - a0)
        if span > 360:
            span = span % 360
        closed = span >= 350
        d = 2.0 * r
        feats.update(
            {
                "bbox_w": d,
                "bbox_h": d,
                "max_side": d,
                "min_side": d,
                "closed": closed,
                "circularity": 1.0 if closed else 0.5,
                "area": math.pi * r * r if closed else 0.0,
                "perimeter": span * math.pi / 180.0 * r,
            }
        )
        return feats

    pts = _as_xy_points(attrs)
    closed = bool(attrs.get("closed") or False)
    const_w = float(attrs.get("const_width") or 0.0)
    feats["const_width"] = const_w
    feats["closed"] = closed

    if not pts:
        return feats

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    bw = max(xs) - min(xs)
    bh = max(ys) - min(ys)
    # 线宽计入有效外框（两点加宽多段线常见于测点符号）
    if const_w > 0:
        if bw < 1e-9:
            bw = const_w
        if bh < 1e-9:
            bh = const_w
        bw = max(bw, const_w * 0.5)
        bh = max(bh, const_w * 0.5)

    peri = _polyline_length(pts, closed)
    area = _polygon_area(pts) if closed and len(pts) >= 3 else 0.0
    if area <= 1e-12 and const_w > 0 and peri > 0:
        area = peri * const_w
    if area <= 1e-12 and bw > 0 and bh > 0:
        area = bw * bh

    circ = 0.0
    if peri > 1e-12 and area > 1e-12:
        circ = float(min(1.0, 4.0 * math.pi * area / (peri * peri)))

    max_side = max(bw, bh, const_w)
    raw_min = min(bw, bh) if min(bw, bh) > 0 else 0.0
    if raw_min <= 1e-12 and max_side > 1e-12:
        # 纯线段等退化外框：视为极细长，避免 min_side 回退成 max_side 导致 aspect=1
        min_side = max_side * 1e-6
        aspect = max_side / min_side
    else:
        min_side = raw_min if raw_min > 1e-12 else max_side
        aspect = max_side / max(min_side, 1e-9)
    feats.update(
        {
            "bbox_w": bw,
            "bbox_h": bh,
            "max_side": max_side,
            "min_side": min_side,
            "aspect": aspect,
            "circularity": circ,
            "area": area,
            "perimeter": peri,
        }
    )
    return feats


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def score_point_likeness(
    feats: dict[str, Any],
    *,
    max_point_side: float = DEFAULT_MAX_POINT_SIDE,
    max_point_area: float = DEFAULT_MAX_POINT_AREA,
    line_aspect: float = DEFAULT_LINE_ASPECT,
) -> float:
    """综合长宽比、闭合、圆度 → 像点的程度 [0,1]。

    绝对尺寸只作弱参考；近方/近圆的大符号仍可为高分，细长才压低。
    """
    del max_point_area  # 兼容旧调用签名；面积不再主导
    max_side = float(feats.get("max_side") or 0.0)
    closed = bool(feats.get("closed"))
    circ = float(feats.get("circularity") or 0.0)
    aspect = max(float(feats.get("aspect") or 1.0), 1.0)

    # 长宽比：1 → 1.0；越大越像线
    aspect_score = _clamp01(1.0 / aspect)
    if aspect >= line_aspect:
        aspect_score = min(aspect_score, 0.25)

    closed_score = 1.0 if closed else 0.3
    if circ > 1e-9:
        circ_score = circ
    elif closed and aspect <= 2.0:
        circ_score = 0.65
    else:
        circ_score = 0.15

    # 仅当「又大又扁」时略降，不因单纯外框大否决
    size_soft = 1.0
    if max_point_side > 0 and max_side > max_point_side * 4.0 and aspect >= 2.0:
        size_soft = 0.7

    score = (0.55 * aspect_score + 0.25 * closed_score + 0.20 * circ_score) * size_soft
    return _clamp01(score)


def classify_shape(
    entity: dict,
    *,
    ref_size: float | None = None,
    point_score_threshold: float = DEFAULT_POINT_SCORE_THRESHOLD,
) -> dict[str, Any]:
    """返回 shape_type / point_score / features。

    - text：TEXT/MTEXT
    - point-like：外形紧凑（长宽比接近 1、闭合/圆度好）；不因绝对尺寸大而否决
    - line-like：细长描边（高长宽比）
    """
    et = str(entity.get("type") or entity.get("entity_type") or "")
    max_side_lim = DEFAULT_MAX_POINT_SIDE
    max_area_lim = DEFAULT_MAX_POINT_AREA
    if ref_size and ref_size > 0:
        max_side_lim = max(max_side_lim, 0.8 * float(ref_size))
        max_area_lim = max(max_area_lim, (0.8 * float(ref_size)) ** 2)

    feats = geometry_features(entity)
    if et in {"TEXT", "MTEXT"}:
        return {
            "shape_type": "text",
            "point_score": 0.0,
            "features": feats,
        }

    aspect = float(feats.get("aspect") or 1.0)
    score = score_point_likeness(
        feats, max_point_side=max_side_lim, max_point_area=max_area_lim
    )
    if et == "POINT":
        score = max(score, 0.95)
    elif et == "CIRCLE" and aspect <= DEFAULT_LINE_ASPECT:
        score = max(score, 0.85)
    elif et == "INSERT" and aspect <= DEFAULT_LINE_ASPECT:
        score = max(score, 0.9)

    if aspect >= DEFAULT_LINE_ASPECT * 1.5:
        shape_type = "line-like"
    elif score >= point_score_threshold:
        shape_type = "point-like"
    elif aspect >= DEFAULT_LINE_ASPECT:
        shape_type = "line-like"
    else:
        shape_type = "other"

    return {
        "shape_type": shape_type,
        "point_score": round(score, 4),
        "features": feats,
    }


def is_point_like(rec: dict) -> bool:
    return str(rec.get("shape_type") or "") == "point-like"


def is_text_shape(rec: dict) -> bool:
    st = str(rec.get("shape_type") or "")
    if st == "text":
        return True
    return str(rec.get("entity_type") or "") in {"TEXT", "MTEXT"}


def is_cluster_symbol(rec: dict) -> bool:
    """可参与测点/钻孔组合的符号锚点。"""
    return is_point_like(rec)
