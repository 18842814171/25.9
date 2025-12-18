#Load data & extract TOP positions
import json

with open("merged_output_filled_grouped.json", "r", encoding="utf-8") as f:
    circles = json.load(f)

circle_index = {c["circle_id"]: c for c in circles}

top_pos = {}
for cid, c in circle_index.items():
    top = next(s for s in c["sources"] if s["source"] == "top")
    x, y, _ = top["attributes"]["center"]
    top_pos[cid] = (x, y)

#Line interpolation helpers
def lerp(a, b, t):
    return a + t * (b - a)

def interp_on_line(val, p1, p2, axis):
    """
    axis: 'x' or 'z'
    """
    if axis == "x":
        x1, y1, _ = p1
        x2, y2, _ = p2
        if abs(x2 - x1) < 1e-6:
            return y1
        t = (val - x1) / (x2 - x1)
        return lerp(y1, y2, t)

    if axis == "z":
        z1, y1, _ = p1
        z2, y2, _ = p2
        if abs(z2 - z1) < 1e-6:
            return y1
        t = (val - z1) / (z2 - z1)
        return lerp(y1, y2, t)

# Z inference from FRONT
def infer_z(cid):
    x, _ = top_pos[cid]
    c = circle_index[cid]

    # Direct FRONT
    for s in c["sources"]:
        if s["source"] == "front":
            line = s["line_data"] 
            p1 = line["attributes"]["start"]
            p2 = line["attributes"]["end"]
            return interp_on_line(x, p1, p2, axis="x")

    # Group FRONT
    if "group" in c:
        a, b = map(int, c["group"].split("-"))
        for k in (a, b):
            for s in circle_index[k]["sources"]:
                if s["source"] == "front":
                    line = s["line_data"]
                    p1 = line["attributes"]["start"]
                    p2 = line["attributes"]["end"]
                    return interp_on_line(x, p1, p2, axis="x")
    return None

# Y inference from LEFT
def infer_y(cid):
    z = infer_z(cid)
    c = circle_index[cid]

    # Direct LEFT
    for s in c["sources"]:
        if s["source"] == "left":
            line = s["line_data"]
            x1, _, _ = line["attributes"]["start"]
            return x1

    # Group LEFT
    if "group" in c:
        a, b = map(int, c["group"].split("-"))
        for k in (a, b):
            for s in circle_index[k]["sources"]:
                if s["source"] == "left":
                    line = s["line_data"]
                    x1, _, _ = line["attributes"]["start"]
                    return x1

    return None

#Assemble full XYZ
xyz_output = []

for cid in sorted(circle_index):
    x, _ = top_pos[cid]
    y = infer_y(cid)
    z = infer_z(cid)

    xyz_output.append({
        "circle_id": cid,
        "X": x,
        "Y": y,
        "Z": z,
        #"group": circle_index[cid].get("group")
    })

# Save result
with open("circles_xyz.json", "w", encoding="utf-8") as f:
    json.dump(xyz_output, f, indent=4, ensure_ascii=False)

print("XYZ reconstruction complete → circles_xyz.json")