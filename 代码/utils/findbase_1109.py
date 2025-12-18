# 1022-findbase-2.py  (works with BOTH old nested and new flat 1022 JSON)

import json
from typing import List, Tuple, Dict, Any, Iterable

from relocate_v1022 import extract_points_from_entity as extract_points_from_entity
# ----------------------------------------------------------------------
# 1.  Helper – normalise an entity to a dict that always has an
#     "attributes" sub-dict (the old format) **and** the flat fields.
# ----------------------------------------------------------------------
def _norm_entity(ent: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a view of the entity that guarantees:
        ent["attributes"]  → dict (may be empty)
        ent["layer"]       → str
        ent["type"]        → str
    The original dict is **not** modified.
    """
    # ---- old nested format ------------------------------------------------
    if "attributes" in ent and isinstance(ent["attributes"], dict):
        return ent

    # ---- new flat format --------------------------------------------------
    # All geometry fields are already at the top level.
    # Build a synthetic "attributes" dict that contains everything except
    # the meta-fields we keep at the top.
    meta = {"handle", "type", "layer", "group"}  # group may be missing
    attrs = {k: v for k, v in ent.items() if k not in meta}
    norm = {
        "handle": ent.get("handle", "???"),
        "type": ent.get("type", "UNKNOWN"),
        "layer": ent.get("layer", "0"),
        "attributes": attrs,
    }
    # optional group (kept for debugging)
    if "group" in ent:
        norm["group"] = ent["group"]
    return norm


# ----------------------------------------------------------------------
# 2.  Point extractor – **one** function for every entity type
# ----------------------------------------------------------------------
"""
def extract_points_from_entity(entity: Dict[str, Any]) -> List[Tuple[float, float]]:
   
    ent = _norm_entity(entity)                # <-- guarantees .attributes
    points: List[Tuple[float, float]] = []
    attrs = ent.get("attributes", {})

    # ----- single-point fields -------------------------------------------
    for field in ("start", "end", "center", "insert_point", "location"):
        val = attrs.get(field)
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            points.append((float(val[0]), float(val[1])))

    # ----- vertex lists --------------------------------------------------
    for field in ("vertices", "control_points"):
        lst = attrs.get(field)
        if isinstance(lst, list):
            for v in lst:
                if isinstance(v, (list, tuple)) and len(v) >= 2:
                    points.append((float(v[0]), float(v[1])))

    # ----- INSERT – old format may have a list of attribute dicts ----------
    if ent.get("type") == "INSERT":
        sub = attrs.get("attributes")          # may be a list (old format)
        if isinstance(sub, list):
            for a in sub:
                ins = a.get("insert")
                if isinstance(ins, (list, tuple)) and len(ins) >= 2:
                    points.append((float(ins[0]), float(ins[1])))

    # ----- remove exact duplicates (optional, keeps output tidy) ----------
    seen = set()
    uniq = []
    for p in points:
        key = (round(p[0], 6), round(p[1], 6))   # 1 µm tolerance
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq
"""

# ----------------------------------------------------------------------
# 3.  Public API – unchanged signature
# ----------------------------------------------------------------------
def find_corner_point(
    choice: str,
    json_filename: str,
    filter_layer: str = None,
    filter_types: List[str] = None,
) -> Tuple[float, float]:
    """
    Load JSON, (optionally) filter by layer / type, and return the requested
    corner of the bounding box.
    """
    with open(json_filename, "r", encoding="utf-8") as f:
        entities: List[Dict[str, Any]] = json.load(f)

    # ------------------------------------------------------------------
    # Debug: show what layers/types contain border-like objects
    # ------------------------------------------------------------------
    line_layers = {e.get("layer", "0") for e in entities
                   if e.get("type") in ("LINE", "LWPOLYLINE", "POLYLINE")}
    line_types = {e.get("type") for e in entities
                  if e.get("type") in ("LINE", "LWPOLYLINE", "POLYLINE")}
    print(f"Border layers: {sorted(line_layers)}")
    print(f"Border types : {sorted(line_types)}")

    all_points: List[Tuple[float, float]] = []

    for raw in entities:
        ent = _norm_entity(raw)                     # <-- normalise once

        # ---- structural sanity check (keeps old warnings) -------------
        if not all(k in ent for k in ("handle", "type", "layer")):
            print(f"Warning: Skipping malformed entity {ent.get('handle','?')}")
            continue

        # ---- optional filters -----------------------------------------
        if filter_layer and ent["layer"] != filter_layer:
            continue
        if filter_types and ent["type"] not in filter_types:
            continue

        pts = extract_points_from_entity(ent)
        #if pts:
            #print(f"  {ent['handle']} ({ent['type']}, {ent['layer']}): "
            #      f"{pts[:2]}{'...' if len(pts)>2 else ''}")
        all_points.extend(pts)

    if not all_points:
        raise ValueError(f"No points in {json_filename} after filtering.")

    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]

    corners = {
        "bl": (min(xs), min(ys)),
        "br": (max(xs), min(ys)),
        "ul": (min(xs), max(ys)),
        "ur": (max(xs), max(ys)),
    }
    corner = corners[choice.lower()]
    print(f"{choice.upper()} corner: {corner}")
    return corner

# 4.  Demo / CLI

if __name__ == "__main__":
    filename = "info/1202_export-front.json"
    choice = "bl"                    

    # ---- no filter ----------------------------------------------------
    try:
        p = find_corner_point(choice, filename)
        print(f" No filter → {p}")
    except Exception as e:
        print(f" No filter: {e}")

    # ---- filter only border geometry ----------------------------------
    try:
        p = find_corner_point(choice, filename,
                              filter_types=["LINE", "LWPOLYLINE", "POLYLINE"])
        print(f" Border-only → {p}")
    except Exception as e:
        print(f" Border-only: {e}")

    # ---- example with a specific layer (uncomment if you know it) -----
    # p = find_corner_point(choice, filename,
    #                       filter_layer="15104尾巷图",
    #                       filter_types=["LINE"])
    # print(f"→ Layer+border → {p}")
