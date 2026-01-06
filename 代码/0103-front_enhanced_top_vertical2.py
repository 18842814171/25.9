import json
from collections import defaultdict
from pathlib import Path

# =========================
# CONFIG
# =========================
TOP_TAGGED_FILE = r"info\1221rewrite\1221-top_tagged_2.json"
FRONT_PAIR_FILE = r"info\0103_pair_front.json"
OUTPUT_FILE = r"info\0103rebuild\0103rebuilt_vertical_groups.json"

X_MERGE_TOL = 1e-2  # tolerance for merging identical front X values


# =========================
# HELPERS
# =========================
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def almost_equal(a, b, tol=X_MERGE_TOL):
    return abs(a - b) <= tol


# =========================
# MAIN
# =========================
def rebuild_vertical_groups(top_tagged, front_pair):
    """
    Build vertical groups using FRONT view as authority.
    """

    # -------------------------------------------------
    # 1. Build mapping: label -> front line X
    # -------------------------------------------------
    label_to_front_x = {}
    label_to_front_line = {}

    for item in front_pair:
        # expected structure:
        # {
        #   "id": 9,
        #   "nearest_line": "3EA",
        #   "line_data": { "attributes": { "start": [x, y, z], "end": [...] } }
        # }

        label = str(item["id"])
        line = item.get("line_data")
        if not line:
            continue

        x = line["attributes"]["start"][0]
        label_to_front_x[label] = x
        label_to_front_line[label] = line["handle"]

    # -------------------------------------------------
    # 2. Collect circles by front X
    # -------------------------------------------------
    columns = []  # list of { x, circles[] }

    def find_or_create_column(x):
        for col in columns:
            if almost_equal(col["x"], x):
                return col
        new_col = {
            "x": x,
            "circles": []
        }
        columns.append(new_col)
        return new_col

    unassigned = []

    for ent in top_tagged:
        if ent["type"] != "CIRCLE":
            continue

        attrs = ent.get("attributes", {})
        label = attrs.get("associated_label")
        if not label:
            unassigned.append(ent)
            continue

        label = str(label)

        if label not in label_to_front_x:
            unassigned.append(ent)
            continue

        front_x = label_to_front_x[label]
        col = find_or_create_column(front_x)

        col["circles"].append({
            "handle": ent["handle"],
            "label": label,
            "label_handle": attrs.get("label_handle"),
            "front_line": label_to_front_line.get(label)
        })

    # -------------------------------------------------
    # 3. Sort columns left → right
    # -------------------------------------------------
    columns.sort(key=lambda c: c["x"])

    # assign group ids
    vertical_groups = []
    for idx, col in enumerate(columns):
        vertical_groups.append({
            "group_id": idx,
            "x": col["x"],
            "circles": col["circles"]
        })

    # -------------------------------------------------
    # 4. Assemble output
    # -------------------------------------------------
    result = {
        "vertical": vertical_groups
    }

    if unassigned:
        result["unassigned"] = [
            {
                "handle": e["handle"],
                "label": e.get("attributes", {}).get("associated_label")
            }
            for e in unassigned
        ]

    return result


# =========================
# ENTRY
# =========================
if __name__ == "__main__":
    top_tagged = load_json(TOP_TAGGED_FILE)
    front_pair = load_json(FRONT_PAIR_FILE)

    result = rebuild_vertical_groups(top_tagged, front_pair)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[OK] rebuilt vertical groups → {OUTPUT_FILE}")
    print(f"     columns: {len(result['vertical'])}")
    if "unassigned" in result:
        print(f"     unassigned circles: {len(result['unassigned'])}")
