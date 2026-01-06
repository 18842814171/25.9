import json
from collections import defaultdict

# --- UTILITY HELPERS ---

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_dim_value(dim):
    """Normalize dimension value from block_texts or measurement."""
    texts = dim["attributes"].get("block_texts", [])
    return float(texts[0]) if texts else float(dim["attributes"]["measurement"])

def classify_dimension(dim, tol=1e-6):
    """Determine if a dimension is 'vertical' or 'horizontal'."""
    p2, p3 = dim["attributes"]["defpoint2"], dim["attributes"]["defpoint3"]
    if abs(p2[0] - p3[0]) < tol: return "vertical"   # Measures Y
    if abs(p2[1] - p3[1]) < tol: return "horizontal" # Measures X
    return "other"

def create_grid(row_coords, col_coords):
    """Create a grid of points from row and column coordinates"""
    grid = {}
    
    # Sort coordinates
    sorted_rows = sorted(row_coords.items(), key=lambda x: (x[1], str(x[0])))
    sorted_cols = sorted(col_coords.items(), key=lambda x: (x[1], str(x[0])))
    
    print(f"\nCreating grid from {len(sorted_rows)} rows and {len(sorted_cols)} columns")
    
    # Create grid points
    for row_id, y in sorted_rows:
        for col_id, x in sorted_cols:
            point_id = f"R{row_id}_C{col_id}"
            grid[point_id] = {"x": x, "y": y, "row_id": row_id, "col_id": col_id}
    
    return grid

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
        for node_id, y in sorted(row_coords.items(), key=lambda item: str(item[0])):
            f.write(f"  Row {node_id}: y = {y:.2f}\n")
        
        f.write(f"\nSOLVED COLUMN COORDINATES ({len(col_coords)} columns):\n")
        f.write("-" * 40 + "\n")
        for node_id, x in sorted(col_coords.items(), key=lambda item: str(item[0])):
            f.write(f"  Column {node_id}: x = {x:.2f}\n")
        
        f.write(f"\nGRID POINTS ({len(grid)} total):\n")
        f.write("-" * 40 + "\n")
        f.write("Format: R{row_id}_C{col_id}: (x, y)\n\n")
        
        # Sort grid points by row, then column
        sorted_points = sorted(grid.items(), 
                             key=lambda item: (str(item[1]["row_id"]), str(item[1]["col_id"])))
        
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


# --- CORE LOGIC MODULES ---

def extract_boundaries(entities):
    """Identify boundary lines from the DXF/JSON entities."""
    h_bounds, v_bounds = [], []
    for ent in entities:
        if ent["type"] == "LINE":
            s, e = ent["attributes"]["start"], ent["attributes"]["end"]
            if abs(s[1] - e[1]) < 1e-3: h_bounds.append(s[1]) # Horizontal Line -> Y boundary
            elif abs(s[0] - e[0]) < 1e-3: v_bounds.append(s[0]) # Vertical Line -> X boundary
    return sorted(list(set(h_bounds))), sorted(list(set(v_bounds)))

def build_snap_targets(circle_groups, boundary_coords, axis_key):
    """
    Unify circle groups and boundaries into a single list of snap targets.
    Boundaries are assigned a special group_id 'B_coord'.
    """
    targets = []
    # Add existing circle groups
    for g in circle_groups:
        targets.append({"id": g["group_id"], "coord": g[axis_key]})
    # Add boundaries as pseudo-groups
    for b in boundary_coords:
        targets.append({"id": f"BOUNDARY_{b}", "coord": b})
    return targets

def snap_to_nearest(val, targets):
    """Find the target whose coordinate is closest to val."""
    if not targets: return None
    return min(targets, key=lambda t: abs(t["coord"] - val))

def process_dimension(dim, h_targets, v_targets):
    """Snap a dimension to targets and return a constraint."""
    kind = classify_dimension(dim)
    val = get_dim_value(dim)
    p2, p3 = dim["attributes"]["defpoint2"], dim["attributes"]["defpoint3"]

    if kind == "vertical":
        t_start = snap_to_nearest(p2[1], h_targets)
        t_end = snap_to_nearest(p3[1], h_targets)
        dtype = "row"
    elif kind == "horizontal":
        t_start = snap_to_nearest(p2[0], v_targets)
        t_end = snap_to_nearest(p3[0], v_targets)
        dtype = "col"
    else:
        return None

    if not t_start or not t_end or t_start["id"] == t_end["id"]:
        return None

    # Normalize ID order to prevent direction conflicts
    ids = sorted([t_start["id"], t_end["id"]], key=lambda x: str(x))
    return {"type": dtype, "i": ids[0], "j": ids[1], "value": val, "handle": dim["handle"]}

# --- GRAPH SOLVER ---

def solve_constraints(constraints):
    graph = defaultdict(list)
    for c in constraints:
        graph[c["i"]].append((c["j"], c["value"]))
        graph[c["j"]].append((c["i"], -c["value"]))
    
    coords = {}
    if not graph: return coords
    
    # Start anchor
    start_node = min(graph.keys(), key=lambda x: str(x))
    coords[start_node] = 0.0
    stack = [start_node]
    
    while stack:
        u = stack.pop()
        for v, dv in graph[u]:
            if v not in coords:
                coords[v] = coords[u] + dv
                stack.append(v)
    return coords

# --- MAIN EXECUTION ---

def main():
    # 1. Load Data
    entities = load_json(r"info/1202new/1202_export-topview.json")
    group_data = load_json(r"info/1221rewrite/1222-grouptop.json")
    
    # 2. Setup Targets (Circles + Boundaries)
    h_bounds, v_bounds = extract_boundaries(entities)
    h_targets = build_snap_targets(group_data["horizontal"], h_bounds, "y")
    v_targets = build_snap_targets(group_data["vertical"], v_bounds, "x")
    
    # 3. Process Dimensions
    row_constraints, col_constraints = [], []
    for d in [ent for ent in entities if ent["type"] == "DIMENSION"]:
        c = process_dimension(d, h_targets, v_targets)
        if c:
            (row_constraints if c["type"] == "row" else col_constraints).append(c)
            print(f"Snapped {d['handle']}: {c['i']} -> {c['j']} ({c['value']})")

       
    # 4. Solve and Save
    row_y = solve_constraints(row_constraints)
    col_x = solve_constraints(col_constraints)
    if row_y and col_x:
        save_corrected_coordinates(row_y, col_x, r"info/1221rewrite/corrected_coordinates.json")
    
    # 2. Save grid points
        grid = create_grid(row_y, col_x)
        save_grid_points(grid, r"info/1221rewrite/grid_points.json")
    
    # 3. Save detailed text report
        save_detailed_report(row_constraints, col_constraints, row_y, col_x, grid, r"info/1221rewrite/detailed_report.txt")
    
    # [Insert your existing save functions here to output JSON/Reports]
    print(f"Solved {len(row_y)} row nodes and {len(col_x)} column nodes.")

if __name__ == "__main__":
    main()