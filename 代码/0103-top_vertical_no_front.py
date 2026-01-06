import json
import numpy as np
import os

# ===============================
# Configuration
# ===============================
X_TOLERANCE = 5.0   # mm, adjust if needed
MIN_CIRCLES_PER_COLUMN = 1


# ===============================
# Utilities
# ===============================
def load_entities(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_circle(e):
    return e["type"] == "CIRCLE"


from utils.dim_utils_1128 import calculate_line_orientation


# ===============================
# Core: X clustering
# ===============================
def cluster_x_objects(objs, tol):
    """
    objs: list of dicts with key 'x'
    """
    objs = sorted(objs, key=lambda o: o["x"])
    clusters = []

    for obj in objs:
        placed = False
        for c in clusters:
            if abs(c["x"] - obj["x"]) <= tol:
                c["items"].append(obj)
                # update centroid
                c["x"] = np.mean([i["x"] for i in c["items"]])
                placed = True
                break

        if not placed:
            clusters.append({
                "x": obj["x"],
                "items": [obj]
            })

    return clusters

# ===============================
# Public API
# ===============================
def rebuild_vertical_groups(entities, tol=X_TOLERANCE):
    """
    Build vertical (X) groups from tagged circles.
    """
    samples = []

    for e in entities:
        if not is_circle(e):
            continue

        attrs = e["attributes"]
        cx = attrs["center"][0]

        samples.append({
            "x": cx,
            "handle": e["handle"],
            "label": attrs.get("associated_label"),
            "label_handle": attrs.get("label_handle")
        })

    if not samples:
        return []

    clusters = cluster_x_objects(samples, tol)

    vertical_groups = []
    for i, c in enumerate(clusters):
        if len(c["items"]) < MIN_CIRCLES_PER_COLUMN:
            continue

        vertical_groups.append({
            "group_id": i,
            "x": round(c["x"], 6),
            "circles": [
                {
                    "handle": item["handle"],
                    "label": item["label"],
                    "label_handle": item["label_handle"]
                }
                for item in c["items"]
            ]
        })

    return vertical_groups

# ===============================
# CLI entry
# ===============================
def main():
    input_file = r"info\1221rewrite\1221-top_tagged_2.json"
    output_file = r"info\0103rebuild\0103vertical.json"

    print(f"Loading entities from {input_file}")
    entities = load_entities(input_file)

    vertical = rebuild_vertical_groups(entities)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"vertical": vertical}, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(vertical)} vertical groups → {output_file}")


if __name__ == "__main__":
    main()
