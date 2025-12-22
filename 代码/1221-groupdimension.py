# Step 1 — Normalize dimension value
def get_dim_value(dim):
    texts = dim["attributes"].get("block_texts", [])
    if texts:
        return float(texts[0])
    return float(dim["attributes"]["measurement"])

# Step 2 — Classify dimension direction
def classify_dimension(dim, tol=1e-6):
    a = dim["attributes"]["defpoint2"]
    b = dim["attributes"]["defpoint3"]
    
    if abs(a[0] - b[0]) < tol:
        return "vertical"     # measures Y distance
    elif abs(a[1] - b[1]) < tol:
        return "horizontal"   # measures X distance
    else:
        return "other"

# Step 3 — Snap dimension endpoints to nearest circle groups
def snap_to_nearest(point_coord, groups, axis_key):
    """Find the group with coordinate closest to point_coord"""
    if not groups:
        return None
    
    # Find the group with coordinate closest to point_coord
    return min(groups, key=lambda g: abs(g[axis_key] - point_coord))

def get_boundaries(entities):
    """Extract unique boundary coordinates from LINE entities."""
    h_boundaries = [] # Y-coordinates for horizontal boundaries
    v_boundaries = [] # X-coordinates for vertical boundaries
    
    for ent in entities:
        if ent["type"] == "LINE":
            start = ent["attributes"]["start"]
            end = ent["attributes"]["end"]
            
            # If Y is the same, it's a horizontal line (defines a Y boundary)
            if abs(start[1] - end[1]) < 1e-3:
                h_boundaries.append(start[1])
            # If X is the same, it's a vertical line (defines an X boundary)
            elif abs(start[0] - end[0]) < 1e-3:
                v_boundaries.append(start[0])
                
    return sorted(list(set(h_boundaries))), sorted(list(set(v_boundaries)))

# --- Integration into your snap logic ---

def snap_dimension_with_boundaries(dim, h_groups, v_groups, h_bounds, v_bounds):
    kind = classify_dimension(dim)
    p2 = dim["attributes"]["defpoint2"]
    p3 = dim["attributes"]["defpoint3"]
    
    # Combine circle groups with boundary coordinates
    # We create a unified list of 'targets' for the snapping function
    h_targets = h_groups + [{"y": b, "group_id": "BOUNDARY"} for b in h_bounds]
    v_targets = v_groups + [{"x": b, "group_id": "BOUNDARY"} for b in v_bounds]

    if kind == "vertical":
        # Vertical dimensions measure Y-distance
        start_node = snap_to_nearest(p2[1], h_targets, "y")
        end_node = snap_to_nearest(p3[1], h_targets, "y")
        return {"type": "v_dist", "from": start_node, "to": end_node}
    
    elif kind == "horizontal":
        # Horizontal dimensions measure X-distance
        start_node = snap_to_nearest(p2[0], v_targets, "x")
        end_node = snap_to_nearest(p3[0], v_targets, "x")
        return {"type": "h_dist", "from": start_node, "to": end_node}
    
    
def snap_dimension(dim, h_groups, v_groups):
    kind = classify_dimension(dim)
    val = get_dim_value(dim)
    
    p2 = dim["attributes"]["defpoint2"]
    p3 = dim["attributes"]["defpoint3"]
    
    # 确定我们要匹配的轴和目标组
    if kind == "vertical":
        # 垂直标注测量 Y 距离（行与行之间）
        axis_idx = 1
        target_groups = h_groups
        axis_key = "y"
        dim_type = "row"
    elif kind == "horizontal":
        # 水平标注测量 X 距离（列与列之间）
        axis_idx = 0
        target_groups = v_groups
        axis_key = "x"
        dim_type = "col"
    else:
        return None

    # 执行捕捉逻辑
    g_start = snap_to_nearest(p2[axis_idx], target_groups, axis_key)
    g_end = snap_to_nearest(p3[axis_idx], target_groups, axis_key)

    # 1. 解决 0 to 0 问题：检查是否捕捉到了同一个组
    if not g_start or not g_end or g_start["group_id"] == g_end["group_id"]:
        # print(f"Skipping dimension {dim['handle']}: snaps to same group {g_start['group_id'] if g_start else 'None'}")
        return None

    # 2. 解决反向约束问题：归一化 ID 顺序 (始终从小 ID 指向大 ID)
    id1 = g_start["group_id"]
    id2 = g_end["group_id"]
    
    if id1 > id2:
        # 如果是 4 -> 2，则翻转为 2 -> 4
        from_id, to_id = id2, id1
    else:
        from_id, to_id = id1, id2
        
    return {
        "type": dim_type,
        "i": from_id,
        "j": to_id,
        "value": val,
        "handle": dim["handle"]
    }

# Step 4 — Build the constraint graph
from collections import defaultdict
import json

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# Load data
dimensions = load_json(r"info\1202new\1202_export-topview.json")# translate coordinate is meaningless here;we can correct coordinate later

# Load the group file (contains both horizontal and vertical)
group_data = load_json(r"info\1221rewrite\1222-grouptop.json")

# Extract horizontal and vertical groups from the single file
horizontal_groups = group_data["horizontal"]  # These have "y" coordinates
vertical_groups = group_data["vertical"]      # These have "x" coordinates

print(f"Loaded {len(horizontal_groups)} horizontal groups (y-coordinates)")
print(f"Loaded {len(vertical_groups)} vertical groups (x-coordinates)")

# Debug: Print first few groups
print("\nFirst 3 horizontal groups:")
for i, group in enumerate(horizontal_groups[:3]):
    print(f"  Group {i}: id={group['group_id']}, y={group['y']}, circles={group['circle_ids']}")

print("\nFirst 3 vertical groups:")
for i, group in enumerate(vertical_groups[:3]):
    print(f"  Group {i}: id={group['group_id']}, x={group['x']}, circles={group['circle_ids']}")

row_constraints = []
col_constraints = []

# Filter only DIMENSION objects
dimension_objects = [d for d in dimensions if d["type"] == "DIMENSION"]
print(f"\nFound {len(dimension_objects)} dimension objects in the drawing")

for d in dimension_objects:
    c = snap_dimension(d, horizontal_groups, vertical_groups)
    if not c:
        continue
    
    print(f"Dimension {d['handle']}: type={c['type']}, i={c['i']}, j={c['j']}, value={c['value']}")
    
    if c["type"] == "row":
        row_constraints.append(c)
    else:
        col_constraints.append(c)

print(f"\nFound {len(row_constraints)} row constraints and {len(col_constraints)} column constraints")

# Step 5 — Solve the constraint graph
def solve_constraints(constraints):
    """Solve difference constraints: node_j - node_i = value"""
    graph = defaultdict(list)
    
    # Build undirected graph with edge weights
    for c in constraints:
        i, j, v = c["i"], c["j"], c["value"]
        graph[i].append((j, v))      # j = i + v
        graph[j].append((i, -v))     # i = j - v
    
    print(f"Graph has {len(graph)} nodes")
    
    coords = {}
    
    # Try to find a starting node
    if graph:
        # Start from the smallest node ID
        start_node = min(graph.keys())
        coords[start_node] = 0.0
        stack = [start_node]
        
        while stack:
            u = stack.pop()
            for v, dv in graph[u]:
                if v not in coords:
                    coords[v] = coords[u] + dv
                    stack.append(v)
    else:
        print("Warning: Empty graph")
    
    return coords

# Step 6 — Compute corrected canonical coordinates
if row_constraints:
    row_y = solve_constraints(row_constraints)
    print(f"\nRow coordinates (Y):")
    for node_id, y in sorted(row_y.items()):
        print(f"  Node {node_id}: y = {y}")
else:
    print("No row constraints found")
    row_y = {}

if col_constraints:
    col_x = solve_constraints(col_constraints)
    print(f"\nColumn coordinates (X):")
    for node_id, x in sorted(col_x.items()):
        print(f"  Node {node_id}: x = {x}")
else:
    print("No column constraints found")
    col_x = {}

# Step 7 — Create a grid from the coordinates
def create_grid(row_coords, col_coords):
    """Create a grid of points from row and column coordinates"""
    grid = {}
    
    # Sort coordinates
    sorted_rows = sorted(row_coords.items(), key=lambda x: x[1])
    sorted_cols = sorted(col_coords.items(), key=lambda x: x[1])
    
    print(f"\nCreating grid from {len(sorted_rows)} rows and {len(sorted_cols)} columns")
    
    # Create grid points
    for row_id, y in sorted_rows:
        for col_id, x in sorted_cols:
            point_id = f"R{row_id}_C{col_id}"
            grid[point_id] = {"x": x, "y": y, "row_id": row_id, "col_id": col_id}
    
    return grid


if row_y and col_x:
    grid = create_grid(row_y, col_x)
    print(f"Created grid with {len(grid)} points")
    
    # Show first few grid points
    print("\nFirst 5 grid points:")
    for i, (point_id, point) in enumerate(list(grid.items())[:5]):
        print(f"  {point_id}: x={point['x']:.1f}, y={point['y']:.1f}")

def save_corrected_coordinates(row_coords, col_coords, output_file="corrected_coordinates.json"):
    """Save all corrected coordinates to a JSON file"""
    output = {
        "row_coordinates": {str(k): float(v) for k, v in row_coords.items()},
        "column_coordinates": {str(k): float(v) for k, v in col_coords.items()}
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved all coordinates to {output_file}")
    print(f"  - {len(row_coords)} row coordinates")
    print(f"  - {len(col_coords)} column coordinates")

def save_grid_points(grid, output_file=r"info/1221rewrite/grid_points.json"):
    """Save all grid points to a JSON file"""
    output = {
        "grid_points": {
            point_id: {
                "x": float(point["x"]),
                "y": float(point["y"]),
                "row_id": point["row_id"],
                "col_id": point["col_id"]
            }
            for point_id, point in grid.items()
        }
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved all grid points to {output_file}")
    print(f"  - {len(grid)} grid points total")

def save_detailed_report(row_constraints, col_constraints, row_coords, col_coords, 
                         grid, output_file=r"info/1221rewrite/detailed_report.txt"):
    """Save a detailed text report of all data"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("DIMENSION CONSTRAINT ANALYSIS REPORT\n")
        f.write("=" * 60 + "\n\n")
        
        f.write(f"ROW CONSTRAINTS ({len(row_constraints)} total):\n")
        f.write("-" * 40 + "\n")
        for c in row_constraints:
            f.write(f"  Constraint: row_{c['i']} → row_{c['j']} = {c['value']} (handle: {c['handle']})\n")
        
        f.write(f"\nCOLUMN CONSTRAINTS ({len(col_constraints)} total):\n")
        f.write("-" * 40 + "\n")
        for c in col_constraints:
            f.write(f"  Constraint: col_{c['i']} → col_{c['j']} = {c['value']} (handle: {c['handle']})\n")
        
        f.write(f"\nSOLVED ROW COORDINATES ({len(row_coords)} rows):\n")
        f.write("-" * 40 + "\n")
        for node_id, y in sorted(row_coords.items()):
            f.write(f"  Row {node_id}: y = {y:.2f}\n")
        
        f.write(f"\nSOLVED COLUMN COORDINATES ({len(col_coords)} columns):\n")
        f.write("-" * 40 + "\n")
        for node_id, x in sorted(col_coords.items()):
            f.write(f"  Column {node_id}: x = {x:.2f}\n")
        
        f.write(f"\nGRID POINTS ({len(grid)} total):\n")
        f.write("-" * 40 + "\n")
        f.write("Format: R{row_id}_C{col_id}: (x, y)\n\n")
        
        # Sort grid points by row, then column
        sorted_points = sorted(grid.items(), 
                             key=lambda item: (item[1]["row_id"], item[1]["col_id"]))
        
        for point_id, point in sorted_points:
            f.write(f"  {point_id}: ({point['x']:.2f}, {point['y']:.2f})\n")
        
        # Add summary
        f.write(f"\n" + "=" * 60 + "\n")
        f.write("SUMMARY\n")
        f.write("=" * 60 + "\n")
        f.write(f"Total row constraints: {len(row_constraints)}\n")
        f.write(f"Total column constraints: {len(col_constraints)}\n")
        f.write(f"Total rows solved: {len(row_coords)}\n")
        f.write(f"Total columns solved: {len(col_coords)}\n")
        f.write(f"Total grid points: {len(grid)}\n")
    
    print(f"\n✓ Saved detailed report to {output_file}")

    # Save ALL data to files
if row_y and col_x:
    # 1. Save corrected coordinates
    save_corrected_coordinates(row_y, col_x, r"info/1221rewrite/corrected_coordinates.json")
    
    # 2. Save grid points
    save_grid_points(grid, r"info/1221rewrite/grid_points.json")
    
    # 3. Save detailed text report
    save_detailed_report(row_constraints, col_constraints, row_y, col_x, grid, r"info/1221rewrite/detailed_report.txt")
    