import json
import math

# ---------------------------
# Load merged_output.json
# ---------------------------
with open("1211combine3view_no_fix.json", "r", encoding="utf-8") as f:
    merged = json.load(f)

# Build quick index:
circle_index = {item["circle_id"]: item for item in merged}

# Extract TOP geometry for easy neighbor matching:
top_positions = {}
for cid, entry in circle_index.items():
    top_block = next(s for s in entry["sources"] if s["source"] == "top")
    x, y, _ = top_block["attributes"]["center"]
    top_positions[cid] = (x, y)


# ------------------------------------------------
# Helper: find nearest circle with same y (for LEFT)
# ------------------------------------------------
def find_nearest_same_y(target_id):
    xt, yt = top_positions[target_id]
    best = None
    best_dist = float("inf")

    for cid, (x, y) in top_positions.items():
        if cid == target_id:
            continue
        if abs(y - yt) < 1e-3:          # same row (LEFT view collapses X)
            dist = abs(x - xt)
            if dist < best_dist and has_left(cid):
                best = cid
                best_dist = dist

    return best


# -------------------------------------------------
# Helper: find nearest circle with same x (for FRONT)
# -------------------------------------------------
def find_nearest_same_x(target_id):
    xt, yt = top_positions[target_id]
    best = None
    best_dist = float("inf")

    for cid, (x, y) in top_positions.items():
        if cid == target_id:
            continue
        if abs(x - xt) < 1e-3:          # same column (FRONT view collapses Y)
            dist = abs(y - yt)
            if dist < best_dist and has_front(cid):
                best = cid
                best_dist = dist

    return best


# -------------------------------------
# Helper flags: does circle have source?
# -------------------------------------
def has_left(cid):
    entry = circle_index[cid]
    return any(s["source"] == "left" for s in entry["sources"])

def has_front(cid):
    entry = circle_index[cid]
    return any(s["source"] == "front" for s in entry["sources"])


# ---------------------------------------------------
# Fill missing LEFT based on nearest same-y neighbor
# ---------------------------------------------------
def fill_missing_left(circle_id):
    neighbor = find_nearest_same_y(circle_id)
    if neighbor is None:
        print(f"[WARN] No LEFT neighbor found for circle {circle_id}")
        return

    # Copy neighbor’s LEFT geometry
    src = circle_index[neighbor]
    left_block = next(s for s in src["sources"] if s["source"] == "left")
    copied = json.loads(json.dumps(left_block))  # deep copy
    copied["source"] = "left"

    # Append to missing circle
    circle_index[circle_id]["sources"].append(copied)
    print(f"[OK] LEFT inferred for circle {circle_id} from {neighbor}")


# -----------------------------------------------------
# Fill missing FRONT based on nearest same-x neighbor
# -----------------------------------------------------
def fill_missing_front(circle_id):
    neighbor = find_nearest_same_x(circle_id)
    if neighbor is None:
        print(f"[WARN] No FRONT neighbor found for circle {circle_id}")
        return

    # Copy neighbor’s FRONT geometry
    src = circle_index[neighbor]
    front_block = next(s for s in src["sources"] if s["source"] == "front")
    copied = json.loads(json.dumps(front_block))  # deep copy
    copied["source"] = "front"

    # Append to missing circle
    circle_index[circle_id]["sources"].append(copied)
    print(f"[OK] FRONT inferred for circle {circle_id} from {neighbor}")


# ------------------------------------------------
# Detect missing LEFT and FRONT
# ------------------------------------------------
missing_left = []
missing_front = []

for cid, entry in circle_index.items():
    if not has_left(cid):
        missing_left.append(cid)
    if not has_front(cid):
        missing_front.append(cid)

print("Missing LEFT:", missing_left)
print("Missing FRONT:", missing_front)


# ------------------------------------------------
# Fill all missing LEFT
# ------------------------------------------------
for cid in missing_left:
    fill_missing_left(cid)

# ------------------------------------------------
# Fill all missing FRONT
# ------------------------------------------------
for cid in missing_front:
    fill_missing_front(cid)


# -----------------------------------------------
# Save updated file
# -----------------------------------------------
output = list(circle_index.values())
with open("merged_output_filled.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=4, ensure_ascii=False)

print("\nDone! Output saved to merged_output_filled.json")

"""
Finds circles missing LEFT → finds nearest neighbor with same TOP y and copies its LEFT line_data

Finds circles missing FRONT → finds nearest neighbor with same TOP x and copies its FRONT line_data

Inserts inferred/fake LEFT or FRONT blocks with "source": "left" / "source": "front"
"""