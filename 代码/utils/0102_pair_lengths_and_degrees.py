import json
import numpy as np
import os
from utils.dim_utils_1128 import (
    load_entities,
    parse_dim_value,
    is_slope_dimension,
    vector_distance_to_line
)

# ============================================================
# Geometry helpers
# ============================================================

def intersect_lines(p1, p2, p3, p4, eps=1e-6):
    """
    Intersection of infinite lines (p1–p2) and (p3–p4).
    Returns None if parallel or ill-conditioned.
    """
    p1 = np.array(p1); p2 = np.array(p2)
    p3 = np.array(p3); p4 = np.array(p4)

    d1 = p2 - p1
    d2 = p4 - p3

    cross = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(cross) < eps:
        return None

    t = ((p3[0] - p1[0]) * d2[1] - (p3[1] - p1[1]) * d2[0]) / cross
    return p1 + t * d1


# ============================================================
# Angular dimension resolution
# ============================================================

def resolve_angular_dimension(dim, lines, view):
    attrs = dim["attributes"]
    value = parse_dim_value(dim)
    if value is None:
        return None

    # ---- Required DXF points (already fixed in your extractor)
    required = ("line1_p1", "line1_p2", "line2_p1", "vertex_projection")
    if not all(k in attrs for k in required):
        return None

    p1a = np.array(attrs["line1_p1"][:2])
    p1b = np.array(attrs["line1_p2"][:2])
    p2a = np.array(attrs["line2_p1"][:2])
    p2b = np.array(attrs["vertex_projection"][:2])

    # ---- Compute true vertex
    vertex = intersect_lines(p1a, p1b, p2a, p2b)
    if vertex is None:
        return None
    def outward_ray(vertex, a, b):
        return (a - vertex) if np.linalg.norm(a - vertex) > np.linalg.norm(b - vertex) else (b - vertex)

    ray1 = outward_ray(vertex, p1a, p1b)
    ray2 = outward_ray(vertex, p2a, p2b)


    # --------------------------------------------------------

    def match_ray(ray_dir, vertex, lines, exclude_handle=None):
        """
        Match a ray direction to the best LINE entity.
        """
        if np.linalg.norm(ray_dir) < 1e-6:
            return None, 0.0, False

        norm_ray = ray_dir / np.linalg.norm(ray_dir)
        used_baseline = False

        # ---- Horizontal shortcut (strictly gated)
        if abs(norm_ray[1]) < 0.01 and abs(norm_ray[0]) > 0.99:
            for line in lines:
                s = np.array(line["attributes"]["start"][:2])
                e = np.array(line["attributes"]["end"][:2])
                if abs(s[1] - e[1]) < 1e-3:
                    dist = vector_distance_to_line(vertex, s, e)
                    if dist < 20:   # CRITICAL spatial gate
                        return line["handle"], 0.95, True

        best_handle = None
        best_score = 0.0

        for line in lines:
            handle = line["handle"]
            if handle == exclude_handle:
                continue

            s = np.array(line["attributes"]["start"][:2])
            e = np.array(line["attributes"]["end"][:2])
            v = e - s
            if np.linalg.norm(v) < 1e-6:
                continue

            v_unit = v / np.linalg.norm(v)

            # Direction agreement
            dir_score = abs(np.dot(norm_ray, v_unit))
            if dir_score < 0.85:
                continue

            # Distance from true vertex
            dist = vector_distance_to_line(vertex, s, e)
            score = dir_score * np.exp(-dist / 200.0)

            if score > best_score:
                best_score = score
                best_handle = handle

        return best_handle, best_score, used_baseline

    # ---- Match both rays
    h1, s1, b1 = match_ray(ray1, vertex, lines)
    h2, s2, b2 = match_ray(ray2, vertex, lines, exclude_handle=h1)

    if not h1 or not h2 or h1 == h2:
        return {
            "id": dim["handle"],
            "type": "angular_constraint",
            "value": round(value),
            "view": view,
            "between": [h1, h2],
            "confidence": 0.0,
            "status": "ambiguous"
        }

    confidence = min(s1, s2)
    if b1 or b2:
        confidence *= 0.85

    status = "resolved" if confidence > 0.8 else "partial"

    return {
        "id": dim["handle"],
        "type": "angular_constraint",
        "value": round(value),
        "view": view,
        "between": [h1, h2],
        "confidence": round(confidence, 2),
        "status": status,
        "raw": {
            "text": attrs.get("text"),
            "measurement": attrs.get("measurement"),
            "defpoints": {
                "vertex": vertex.tolist(),
                "ray1_end": p1b.tolist(),
                "ray2_end": p2a.tolist()
            }
        }
    }


# ============================================================
# Linear dimension resolution
# ============================================================

def resolve_linear_dimension(dim, lines, view):
    attrs = dim["attributes"]
    value = parse_dim_value(dim)
    if value is None:
        return None

    pts = []
    for k in ("vertex_projection", "line1_p1", "line1_p2"):
        if k in attrs:
            pts.append(np.array(attrs[k][:2]))

    if len(pts) < 2:
        return None

    dim_mid = np.mean(pts, axis=0)

    dx, dy = abs(pts[0][0] - pts[1][0]), abs(pts[0][1] - pts[1][1])
    orientation = "horizontal" if dy < dx else "vertical"

    best_line = None
    best_score = 0.0
    best_len = None

    for line in lines:
        s = np.array(line["attributes"]["start"][:2])
        e = np.array(line["attributes"]["end"][:2])
        v = e - s
        line_len = np.linalg.norm(v)
        if line_len < 1e-6:
            continue

        if orientation == "horizontal" and abs(v[1]) > abs(v[0]):
            continue
        if orientation == "vertical" and abs(v[0]) > abs(v[1]):
            continue

        dist = vector_distance_to_line(dim_mid, s, e)

        line_dir = v / line_len
        proj = np.dot(dim_mid - s, line_dir)
        within = 0 <= proj <= line_len

        score = (1 / (1 + dist)) * (1.5 if within else 0.5)

        if score > best_score:
            best_score = score
            best_line = line
            best_len = line_len

    if not best_line:
        return {
            "id": dim["handle"],
            "type": "linear_constraint",
            "value": round(value),
            "status": "ambiguous",
            "applies_to": {"view": view, "entities": []},
            "confidence": 0.0
        }

    coverage = value / best_len
    status = "resolved" if coverage > 0.95 else "partial"

    return {
        "id": dim["handle"],
        "type": "linear_constraint",
        "value": round(value),
        "status": status,
        "applies_to": {"view": view, "entities": [best_line["handle"]]},
        "confidence": round(min(best_score, 1.0), 2)
    }


# ============================================================
# Dispatcher
# ============================================================

def resolve_dimensions(all_entities, view="front"):
    lines = [e for e in all_entities if e["type"] == "LINE"]
    dims = [e for e in all_entities if e["type"] == "DIMENSION"]

    constraints = []
    for dim in dims:
        if is_slope_dimension(dim):
            c = resolve_angular_dimension(dim, lines, view)
        else:
            c = resolve_linear_dimension(dim, lines, view)
        if c:
            constraints.append(c)

    return constraints


# ============================================================
# Entry
# ============================================================

def main():
    input_file = r"info\0102_export-front.json"
    print(f"Loading from {input_file}...")

    all_entities = load_entities(input_file)
    constraints = resolve_dimensions(all_entities, view="front")

    output_path = "info/0102resolve/0102_front_constraints.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(constraints, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(constraints)} constraints.")


if __name__ == "__main__":
    main()
