# layer_json_1020.py
import json
import sys
import ezdxf
from typing import List, Dict, Any

# -------------------------------------------------
# 1. Import everything we need from 1022
# -------------------------------------------------
from indep_json_1022 import (
    filtered_entities_json_no_layer_or_group,
)
from entities_1019 import (
    filter_msp,
    define_window_by_corner_and_print,
    list_entity_from_msp,
)

# -------------------------------------------------
# 2. Optional: expand INSERT blocks (kept for compatibility)
# -------------------------------------------------
def _expand_insert(entity: Any, doc: Any) -> List[Dict[str, Any]]:
    """Return a list with the INSERT itself + all entities inside its block."""
    result = []
    # INSERT itself
    insert_info = {
        "handle": entity.dxf.handle,
        "type": "INSERT",
        "layer": entity.dxf.layer,
        "attributes": {
            "block_name": entity.dxf.name,
            "insert_point": list(entity.dxf.insert.xyz),
            "scale": list(entity.dxf.scale) if hasattr(entity.dxf, "scale") else [1, 1, 1],
            "rotation": entity.dxf.rotation,
        },
    }
    result.append(insert_info)

    # Block contents (if any)
    try:
        block = entity.block()
        if block:
            for sub in block:
                sub_data = filtered_entities_json_no_layer_or_group([sub])[0]  # reuse 1022 logic
                sub_data["attributes"]["_block_parent"] = entity.dxf.handle
                result.append(sub_data)
    except Exception as e:
        insert_info["attributes"]["block_error"] = str(e)

    return result


# -------------------------------------------------
# 3. Main routine – build layered JSON
# -------------------------------------------------
def build_layered_json(
    dxf_path: str,
    window_corners: tuple,
    expand_blocks: bool = False,
) -> Dict[str, Any]:
    """
    Returns the same JSON structure as the original 1020 script,
    but using the helpers from 1022.
    """
    # ---- step 1: get modelspace filtered by type ----
    desired_types = (
        "LINE ARC CIRCLE DIMENSION HATCH INSERT LEADER "
        "LWPOLYLINE POINT POLYLINE SPLINE TEXT MTEXT"
    )
    msp = filter_msp(dxf_path, desired_types)

    # ---- step 2: window selection ----
    window = define_window_by_corner_and_print(window_corners)
    entities = list_entity_from_msp(msp, window)

    # ---- step 3: convert to JSON dicts (1022) ----
    flat = filtered_entities_json_no_layer_or_group(entities)

    # ---- step 4: (optional) expand INSERT blocks ----
    if expand_blocks:
        doc = ezdxf.readfile(dxf_path)
        expanded = []
        for ent in entities:
            if ent.dxftype() == "INSERT":
                expanded.extend(_expand_insert(ent, doc))
            else:
                expanded.append(next(e for e in flat if e["handle"] == ent.dxf.handle))
        flat = expanded

   # ---- step 5: group by layer → group (clean entities) ----
    layer_data: Dict[str, Dict[str, List[Dict]]] = {}

    for item in flat:
        layer_name = item["layer"]
        group_name = item.get("group", "direct")

        # This is your entity_json — clean and flat
        entity_json = {
            "handle": item["handle"],
            "type": item["type"],
            **item["attributes"]
        }

        layer_data.setdefault(layer_name, {}).setdefault(group_name, []).append(entity_json)

    # ---- step 6: build final clean JSON ----
    total = sum(len(ents) for layer in layer_data.values() for ents in layer.values())

    json_out = {
        "total_entities": total,
        "layers": [
            {
                "name": lname,
                "groups": [
                    {"name": gname, "entities": ents}
                    for gname, ents in groups.items()
                ]
            }
            for lname, groups in layer_data.items()
        ]
    }
    
    return json_out


# -------------------------------------------------
# 4. Execution block (unchanged paths – adjust as needed)
# -------------------------------------------------
if __name__ == "__main__":
    dxf_file_path = r"D:\大创\25.9\图纸\dxf\附图8：炮眼布置及装药结构图.dxf"
    # right-top corner
    window_corners = ((583500, 658300), (586000, 654300))
    # left-top corner (uncomment the line you need)
    # window_corners = ((578300, 658330), (583200, 654700))

    output_file = "info/e8-1020-right-top.json"

    json_data = build_layered_json(dxf_file_path, window_corners, expand_blocks=False)#递归提取：改为true

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)

    print(f"输出已保存到 {output_file}")
    print(f"总共提取了 {json_data['total_entities']} 个实体")