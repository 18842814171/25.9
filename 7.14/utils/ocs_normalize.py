"""将非标准 extrusion 的 OCS 图元坐标规范为 WCS（XY 平面、extrusion=(0,0,1)）。

DXF 中 CIRCLE/ARC/LWPOLYLINE/TEXT/MTEXT/HATCH/INSERT 等的平面坐标在 OCS 下；
若 extrusion 不是 (0,0,1)，直接把 OCS 的 x/y 当平面坐标会导致位置飞出主体范围。
LINE/POINT/3D POLYLINE 等本身已是 WCS，本模块不改其坐标。
"""

from __future__ import annotations

from typing import Any

from ezdxf.math import Matrix44, OCS, OCSTransform, Vec3

# 与 (0,0,1) 的分量容差
_EPS = 1e-9

# 需要按 OCS→WCS 改写坐标的图元类型（坐标存于 OCS）
_OCS_ENTITY_TYPES = frozenset(
    {
        "LWPOLYLINE",
        "ARC",
        "CIRCLE",
        "TEXT",
        "MTEXT",
        "HATCH",
        "INSERT",
    }
)


def is_standard_extrusion(extrusion: Any) -> bool:
    """标准 extrusion：约等于 (0, 0, 1)，此时 OCS XY 与 WCS XY 重合。"""
    try:
        v = Vec3(extrusion)
    except Exception:
        return True
    return abs(v.x) <= _EPS and abs(v.y) <= _EPS and abs(v.z - 1.0) <= 1e-6


def _as_xyz_list(pt: Any, n: int = 3) -> list[float]:
    vals = [float(pt[i]) for i in range(min(n, len(pt)))]
    while len(vals) < n:
        vals.append(0.0)
    return vals


def _mark_normalized(attributes: dict, extrusion: Vec3) -> None:
    attributes["extrusion_original"] = [float(extrusion.x), float(extrusion.y), float(extrusion.z)]
    attributes["extrusion"] = [0.0, 0.0, 1.0]
    attributes["ocs_normalized"] = True


def _transform_xy_point(ocs: OCS, x: float, y: float, z: float = 0.0) -> list[float]:
    w = ocs.to_wcs((x, y, z))
    return [float(w.x), float(w.y), float(w.z)]


def normalize_attributes_to_wcs(entity, attributes: dict | None) -> dict | None:
    """若 entity 为非标准 extrusion 的 OCS 图元，就地改写 attributes 中的坐标。

    返回同一 attributes 引用；attributes 为 None 时原样返回。
    """
    if attributes is None:
        return None

    et = entity.dxftype()
    if et not in _OCS_ENTITY_TYPES:
        return attributes
    if not hasattr(entity.dxf, "extrusion"):
        return attributes

    extrusion = Vec3(entity.dxf.extrusion)
    if is_standard_extrusion(extrusion):
        return attributes

    ocs = OCS(extrusion)
    # old OCS → WCS(0,0,1)，用于角度
    angle_xf = OCSTransform.from_ocs(ocs, OCS((0.0, 0.0, 1.0)), Matrix44())

    if et == "LWPOLYLINE":
        old_pts = attributes.get("points") or []
        wcs_verts = list(entity.vertices_in_wcs())
        new_pts: list[list[float]] = []
        for i, w in enumerate(wcs_verts):
            sw = ew = bulge = 0.0
            if i < len(old_pts) and len(old_pts[i]) >= 5:
                sw, ew, bulge = float(old_pts[i][2]), float(old_pts[i][3]), float(old_pts[i][4])
            # 下游按平面图使用 xy；bulge 仍按原 OCS 弦弧比保留（倾斜面投影非圆时仅近似）
            new_pts.append([float(w.x), float(w.y), sw, ew, bulge])
        attributes["points"] = new_pts
        attributes["elevation"] = 0.0
        _mark_normalized(attributes, extrusion)
        return attributes

    if et == "CIRCLE":
        center = attributes.get("center") or list(entity.dxf.center)
        x, y, z = _as_xyz_list(center, 3)
        attributes["center"] = _transform_xy_point(ocs, x, y, z)
        _mark_normalized(attributes, extrusion)
        return attributes

    if et == "ARC":
        center = attributes.get("center") or list(entity.dxf.center)
        x, y, z = _as_xyz_list(center, 3)
        attributes["center"] = _transform_xy_point(ocs, x, y, z)
        a0 = float(attributes.get("start_angle", entity.dxf.start_angle))
        a1 = float(attributes.get("end_angle", entity.dxf.end_angle))
        na0, na1 = angle_xf.transform_ccw_arc_angles_deg(a0, a1)
        attributes["start_angle"] = float(na0)
        attributes["end_angle"] = float(na1)
        _mark_normalized(attributes, extrusion)
        return attributes

    if et in {"TEXT", "MTEXT", "INSERT"}:
        key = "insert_point"
        pt = attributes.get(key)
        if pt is None:
            return attributes
        x, y, z = _as_xyz_list(pt, 3)
        attributes[key] = _transform_xy_point(ocs, x, y, z)
        if "rotation" in attributes:
            attributes["rotation"] = float(
                angle_xf.transform_deg_angle(float(attributes["rotation"]))
            )
        _mark_normalized(attributes, extrusion)
        return attributes

    if et == "HATCH":
        path_points = attributes.get("path_points") or []
        if path_points:
            new_pp: list[list[float]] = []
            for p in path_points:
                if not isinstance(p, (list, tuple)) or len(p) < 2:
                    continue
                x, y = float(p[0]), float(p[1])
                z = float(p[2]) if len(p) >= 3 else 0.0
                w = _transform_xy_point(ocs, x, y, z)
                new_pp.append([w[0], w[1]])
            attributes["path_points"] = new_pp
        _mark_normalized(attributes, extrusion)
        return attributes

    return attributes
