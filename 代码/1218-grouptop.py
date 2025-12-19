import json
from collections import defaultdict

def extract_top_circles(entities):
    """
    Extract circles from a flat TOP-view entity list.
    """
    circles = []
    cid = 1

    for e in entities:
        if e.get("type") == "CIRCLE":
            x, y, _ = e["attributes"]["center"]
            circles.append({
                "circle_id": cid,
                "handle": e["handle"],
                "x": float(x),
                "y": float(y),
                "label": e["attributes"].get("associated_label") 
            })
            cid += 1

    return circles

# =========================
# CONFIG
# =========================
TOL = 3.0   # alignment tolerance (drawing units)
MAX_Y_GAP = 600
# =========================
# CLUSTERING FUNCTIONS
# =========================
def group_center(group, axis):
    """Calculate center coordinate for a group of circles along specified axis."""
    return sum(p[axis] for p in group) / len(group)

def cluster_1d(points, axis, tol, ortho_axis=None, max_ortho_gap=None):
    points = sorted(points, key=lambda p: p[axis])
    groups = []

    for p in points:
        placed = False
        for g in groups:
            center = group_center(g, axis)

            # primary alignment check (X or Y)
            if abs(p[axis] - center) > tol:
                continue

            #  NEW: orthogonal continuity check
            if ortho_axis and max_ortho_gap:
                ys = sorted(pt[ortho_axis] for pt in g)
                if min(abs(p[ortho_axis] - ys[0]),
                       abs(p[ortho_axis] - ys[-1])) > max_ortho_gap:
                    continue

            g.append(p)
            placed = True
            break

        if not placed:
            groups.append([p])

    return groups

# =========================
# GROUP TOP CIRCLES
# =========================


def group_top_circles(circles, tol=TOL):
    # 水平和垂直方向的分组
    h_groups = [g for g in cluster_1d(circles, "y", tol) if len(g) >= MIN_GROUP_SIZE]
    v_groups = [
    g for g in cluster_1d(
        circles,
        axis="x",
        tol=tol,
        ortho_axis="y",
        max_ortho_gap=MAX_Y_GAP
    )
    if len(g) >= MIN_GROUP_SIZE
]

    result = {
        "horizontal": [],
        "vertical": [],
        "circle_index": {}
    }

    # 处理水平分组（相同的 y 坐标）
    for i, g in enumerate(h_groups):
        y0 = group_center(g, "y")
        ids = [p["circle_id"] for p in g]
        result["horizontal"].append({
            "group_id": i,
            "y": y0,
            "circle_ids": ids
        })
        for cid in ids:
            result["circle_index"].setdefault(cid, {})["horizontal"] = i

    # 处理垂直分组（相同的 x 坐标）
    for i, g in enumerate(v_groups):
        x0 = group_center(g, "x")
        ids = [p["circle_id"] for p in g]
        result["vertical"].append({
            "group_id": i,
            "x": x0,
            "circle_ids": ids
        })
        for cid in ids:
            result["circle_index"].setdefault(cid, {})["vertical"] = i

    return result

# =========================
# RUN
# =========================
if __name__ == "__main__":
    with open("info/1204-tagged-circles/1204-top_tagged.json", "r", encoding="utf-8") as f:
        entities = json.load(f)

    circles = extract_top_circles(entities)
    print(f"Extracted {len(circles)} circles")
    
    MIN_GROUP_SIZE = 2  # 设置最小组大小
    grouped = group_top_circles(circles, tol=3.0)
    
    # 输出统计信息
    print(f"Horizontal groups: {len(grouped['horizontal'])}")
    print(f"Vertical groups: {len(grouped['vertical'])}")
    
    with open(r"info\1219-grouped\1218-grouptop.json", "w", encoding="utf-8") as f:
        json.dump(grouped, f, indent=2, ensure_ascii=False)

    print("All circles grouped!")