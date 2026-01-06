"""
Goal,               Variable Name,      Recommended Value for your CAD
Vertical alignment, TOL,                3.0 (keeps X-coords tight)
Vertical gap limit, MAX_Y_GAP,          600 (allows ~500 unit spacing)
Horizontal row height,  max_row_height,   200 (standard for row alignment)
Row skip limit,     max_rows,           10 (allows long vertical columns)
"""
import json
from collections import defaultdict

def extract_top_circles(entities):
    """
    Extract circles and use their CAD labels as the circle_id.
    """
    circles = []

    for e in entities:
        if e.get("type") == "CIRCLE":
            # Use the actual tag (e.g., "20", "46") as the ID
            tag = e["attributes"].get("associated_label")
            
            # Fallback: if a circle wasn't tagged, use its CAD handle so it's still unique
            circle_id = tag if tag else f"h{e['handle']}"
            
            x, y, _ = e["attributes"]["center"]
            circles.append({
                "circle_id": circle_id, 
                "handle": e["handle"],
                "x": float(x),
                "y": float(y),
                "label": tag 
            })

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

def split_rows_by_y(circles, max_row_height):
    circles = sorted(circles, key=lambda p: p["y"])
    rows = []
    current = [circles[0]]

    for p in circles[1:]:
        ys = [pt["y"] for pt in current]
        if max(ys + [p["y"]]) - min(ys + [p["y"]]) <= max_row_height:

            current.append(p)
        else:
            rows.append(current)
            current = [p]

    rows.append(current)
    return rows

# =========================
# GROUP TOP CIRCLES
# =========================

def cluster_1d(points, axis, tol, ortho_axis=None, max_ortho_gap=None): 
    points = sorted(points, key=lambda p: p[axis]) 
    groups = [] 
    for p in points: 
        placed = False 
        for g in groups: 
            center = group_center(g, axis) 
            # primary alignment check (X or Y) 
            if abs(p[axis] - center) > tol: continue
             # NEW: orthogonal continuity check 
            if ortho_axis and max_ortho_gap: 
                ys = sorted(pt[ortho_axis] for pt in g) 
                if min(abs(p[ortho_axis] - ys[0]), abs(p[ortho_axis] - ys[-1])) > max_ortho_gap: 
                    continue 
            g.append(p) 
            placed = True 
            break 
        if not placed: 
            groups.append([p]) 
            
    return groups

def split_vertical_groups_by_rows(v_groups, circle_index, max_rows=2):
    new_groups = []

    for g in v_groups:
        buckets = {}
        for p in g:
            row = circle_index[p["circle_id"]]["horizontal"]
            buckets.setdefault(row, []).append(p)

        rows = sorted(buckets.items())
        current = []
        last_row = None

        for row, pts in rows:
            if last_row is None or row == last_row + 1:
                current.extend(pts)
            else:
                new_groups.append(current)
                current = pts[:]
            last_row = row

            if len(set(
                circle_index[p["circle_id"]]["horizontal"]
                for p in current
            )) > max_rows:
                new_groups.append(current[:-len(pts)])
                current = pts[:]

        if current:
            new_groups.append(current)

    return new_groups
def group_top_circles(circles, tol=TOL):
    # 1. Initialize result structure first so it's accessible
    result = {
        "horizontal": [],
        "vertical": [],
        "circle_index": {}
    }

    # 2. Perform horizontal grouping
    # split_rows_by_y must come first to establish the 'rows' for circle_index
    h_groups = [
        g for g in split_rows_by_y(circles, max_row_height=200)
        if len(g) >= MIN_GROUP_SIZE
    ]
    for g in h_groups:
        ys = [p["y"] for p in g]
        if max(ys) - min(ys) > 200:
            raise ValueError(f"Row height violation: {ys}")

    
    # 3. Populate circle_index with horizontal info
    # This is the step your script was missing/misordering
    for i, g in enumerate(h_groups):
        y0 = sorted(p["y"] for p in g)[len(g)//2] 
        # 在 group_top_circles 函数内：
        ids = [p["circle_id"] for p in g] # 增加 sorted()
        result["horizontal"].append({
            "group_id": i,
            "y": y0,
            "circle_ids": ids
        })
        for cid in ids:
            result["circle_index"].setdefault(cid, {})["horizontal"] = i

    # 4. Perform raw vertical clustering by X-coordinate
    v_groups_raw = [
        g for g in cluster_1d(
            circles,
            axis="x",
            tol=tol,
            ortho_axis="y",
            max_ortho_gap=MAX_Y_GAP
        )
        if len(g) >= MIN_GROUP_SIZE
    ]
    
    # 5. Split vertical groups using the NOW-populated circle_index
    # This will now find vertical groups because it can see which row each circle belongs to
    v_groups = [
        g for g in split_vertical_groups_by_rows(
            v_groups_raw,
            result["circle_index"], 
            max_rows=10
        )
        if len(g) >= MIN_GROUP_SIZE
    ]

    # 6. Finalize vertical group data
    for i, g in enumerate(v_groups):
        x0 = sorted(p["x"] for p in g)[len(g)//2]
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
    with open(r"info\1221rewrite\1221-top_tagged_2.json", "r", encoding="utf-8") as f:
        entities = json.load(f)

    circles = extract_top_circles(entities)
    print(f"Extracted {len(circles)} circles")
    
    MIN_GROUP_SIZE = 2  # 设置最小组大小
    grouped = group_top_circles(circles, tol=3.0)
    
    # 输出统计信息
    print(f"Horizontal groups: {len(grouped['horizontal'])}")
    print(f"Vertical groups: {len(grouped['vertical'])}")
    
    with open(r"info\1221rewrite\1222-grouptop.json", "w", encoding="utf-8") as f:
        json.dump(grouped, f, indent=2, ensure_ascii=False)

    print("All circles grouped!")