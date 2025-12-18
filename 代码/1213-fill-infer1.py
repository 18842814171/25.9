import json
import math

# ---------------- Load ----------------
with open("1211combine3view_no_fix.json", "r", encoding="utf-8") as f:
    merged = json.load(f)

circle_index = {c["circle_id"]: c for c in merged}

# Extract TOP positions
top_pos = {}
for cid, entry in circle_index.items():
    top = next(s for s in entry["sources"] if s["source"] == "top")
    x, y, _ = top["attributes"]["center"]
    top_pos[cid] = (x, y)

# ---------------- Helpers ----------------
def has_source(cid, src):
    return any(s["source"] == src for s in circle_index[cid]["sources"])

def between(a, b, c, eps=1e-3):
    return min(a, c) - eps <= b <= max(a, c) + eps

# ---------------- Detect group segments ----------------
# Example result: { (39,31): [38,37,36,35,34,33,32] }

groups = {}

ids = sorted(top_pos.keys())

for i in ids:
    for j in ids:
        if i <= j:
            continue

        # both endpoints must have FRONT or LEFT
        if not (has_source(i, "front") and has_source(j, "front")):
            continue

        xi, yi = top_pos[i]
        xj, yj = top_pos[j]

        # same TOP row → FRONT group
        if abs(yi - yj) < 1e-3:
            interior = []
            for k in ids:
                if k in (i, j):
                    continue
                xk, yk = top_pos[k]
                if abs(yk - yi) < 1e-3 and between(xi, xk, xj):
                    if not has_source(k, "front"):
                        interior.append(k)

            if interior:
                groups[(max(i, j), min(i, j))] = interior

# ---------------- Apply group labels ----------------
grouped_ids = set()

for (a, b), members in groups.items():
    label = f"{a}-{b}"
    for cid in members:
        entry = circle_index[cid]
        entry["group"] = label
        entry["projection"] = "shared"
        grouped_ids.add(cid)

# ---------------- Nearest-neighbor inference ----------------
def nearest_same_y(cid, src):
    x0, y0 = top_pos[cid]
    best, dist = None, float("inf")
    for k, (x, y) in top_pos.items():
        if k == cid or not has_source(k, src):
            continue
        if abs(y - y0) < 1e-3:
            d = abs(x - x0)
            if d < dist:
                best, dist = k, d
    return best

def nearest_same_x(cid, src):
    x0, y0 = top_pos[cid]
    best, dist = None, float("inf")
    for k, (x, y) in top_pos.items():
        if k == cid or not has_source(k, src):
            continue
        if abs(x - x0) < 1e-3:
            d = abs(y - y0)
            if d < dist:
                best, dist = k, d
    return best

def deep_copy(obj):
    return json.loads(json.dumps(obj))

# ---------------- Fill truly missing only ----------------
for cid, entry in circle_index.items():

    if cid in grouped_ids:
        continue  # DO NOT INFER GROUP MEMBERS

    # LEFT
    if not has_source(cid, "left"):
        nb = nearest_same_y(cid, "left")
        if nb:
            block = next(s for s in circle_index[nb]["sources"] if s["source"] == "left")
            cp = deep_copy(block)
            cp["source"] = "left"
            cp["inferred_from"] = nb
            entry["sources"].append(cp)

    # FRONT
    if not has_source(cid, "front"):
        nb = nearest_same_x(cid, "front")
        if nb:
            block = next(s for s in circle_index[nb]["sources"] if s["source"] == "front")
            cp = deep_copy(block)
            cp["source"] = "front"
            cp["inferred_from"] = nb
            entry["sources"].append(cp)

# ---------------- Save ----------------
out = list(circle_index.values())
with open("merged_output_filled_grouped.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=4, ensure_ascii=False)

print("Done: merged_output_filled_grouped.json")
