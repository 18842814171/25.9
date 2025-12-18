import json

# ---------- Load the 3 input files ----------
with open(r"info\1204-tagged-circles\1204-top_tagged.json", "r", encoding="utf-8") as f:
    top_data = json.load(f)

with open(r"info\1204-tagged-circles\1204_paired_circles_with_lines_front.json", "r", encoding="utf-8") as f:
    front_data = json.load(f)

with open(r"info\1204-tagged-circles\1204_paired_circles_with_lines_left.json", "r", encoding="utf-8") as f:
    left_data = json.load(f)

# ---------- Build lookup dictionaries ----------
front_lookup = {item["id"]: item for item in front_data}
left_lookup  = {item["id"]: item for item in left_data}

# ---------- Keep only CIRCLE entries from TOP ----------
top_circles = [
    item for item in top_data
    if item.get("type") == "CIRCLE"
       and "associated_label" in item.get("attributes", {})
]

# ---------- Merge into final structure ----------
output = []

for circle in top_circles:
    circle_id = int(circle["attributes"]["associated_label"])

    entry = {
        "circle_id": circle_id,
        "sources": []
    }

    # --- Add TOP source block ---
    top_block = circle.copy()
    top_block["source"] = "top"
    entry["sources"].append(top_block)

    # --- Add LEFT (if exists) ---
    if circle_id in left_lookup:
        left_block = left_lookup[circle_id].copy()
        left_block["source"] = "left"
        entry["sources"].append(left_block)

    # --- Add FRONT (if exists) ---
    if circle_id in front_lookup:
        front_block = front_lookup[circle_id].copy()
        front_block["source"] = "front"
        entry["sources"].append(front_block)

    output.append(entry)

# ---------- Save result ----------
with open("merged_output.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=4, ensure_ascii=False)

print("Done. Output saved to merged_output.json")
