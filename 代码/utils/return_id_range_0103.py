import json
import re
import numpy as np
from collections import defaultdict
from typing import List, Dict, Tuple, Any
from pair_circle_and_line_ids_0103 import load_entities, parse_ids,point_to_segment_distance,pair_circles_to_lines


def pair_circles_to_lines_multi(entities: List[Dict[str, Any]], threshold: float = 180.0) -> List[Dict[str, Any]]:
    """
    Pairs IDs with ALL lines within a threshold.
    This allows an ID to be paired with both the connection line and the slope.
    """
    lines = [ent for ent in entities if ent["type"] == "LINE"]
    mtexts = []
    
    # Parse MTEXT/INSERT entities
    for ent in entities:
        if ent["type"] in ["MTEXT", "INSERT"]:
            text = ent["attributes"].get("text", ent["attributes"].get("actual_text", ""))
            # Use regex to find IDs
            ids = [int(x) for x in re.findall(r'\d+', text)] 
            if ids:
                mtexts.append({"ids": ids, "point": np.array(ent["attributes"]["insert_point"][:2])})

    pairs = []
    for mtext in mtexts:
        p = mtext["point"]
        nearby_lines = []
        
        for line in lines:
            start = np.array(line["attributes"]["start"][:2])
            end = np.array(line["attributes"]["end"][:2])
            dist = point_to_segment_distance(p, start, end)
            
            if dist <= threshold:
                nearby_lines.append({
                    "handle": line["handle"],
                    "dist": dist,
                    "line_data": line
                })
        
        # Sort nearby lines by distance
        nearby_lines.sort(key=lambda x: x["dist"])
        
        for id_val in mtext["ids"]:
            pairs.append({
                "id": id_val,
                "nearest_lines": nearby_lines, # List of candidate lines
                "point": p.tolist()
            })
            
    return sorted(pairs, key=lambda x: x["id"])

def rebuild_id_groups_enhanced(paired_data: List[Dict[str, Any]]):
    """
    Rebuilds ID groups and returns:
    1. Consecutive groups
    2. Non-consecutive groups
    3. Singleton IDs
    """
    conn_to_ids = defaultdict(list)
    all_ids = set()
    
    for entry in paired_data:
        id_val = entry["id"]
        all_ids.add(id_val)
        # Look for connection lines (Layer '0') in the candidate list
        for nl in entry.get("nearest_lines", []):
            line_data = nl["line_data"]
            if line_data.get("layer") == "0":
                handle = line_data["handle"]
                conn_to_ids[handle].append(id_val)
    
    groups = []
    for ids in conn_to_ids.values():
        groups.append(sorted(set(ids)))
    
    # Identify IDs that weren't part of any connection line group
    grouped_ids = {id_val for group in groups for id_val in group}
    singleton_ids = sorted(all_ids - grouped_ids)
    for single in singleton_ids:
        groups.append([single])
    
    groups.sort(key=lambda g: g[0])
    
    # Classification for return
    result = {
        "consecutive_ranges": [],
        "non_consecutive_groups": [],
        "singletons": [],
        "all_ids_sorted": sorted(list(all_ids))
    }
    
    for group in groups:
        if len(group) == 1:
            result["singletons"].append(group[0])
        else:
            is_consecutive = all(group[i+1] == group[i] + 1 for i in range(len(group)-1))
            if is_consecutive:
                result["consecutive_ranges"].append(group)
            else:
                result["non_consecutive_groups"].append(group)
                
    return result

# Example Execution
if __name__ == "__main__":
    # Load your data
    with open(r"info\0102resolve\0102_export-front.json", "r", encoding='utf-8') as f:
        raw_data = json.load(f)
    
    # 1. Improved Pairing
    paired_results = pair_circles_to_lines_multi(raw_data)
    
    # 2. Rebuild and Return groups
    final_report = rebuild_id_groups_enhanced(paired_results)
    
    print(f"Total Unique IDs: {len(final_report['all_ids_sorted'])}")
    print(f"Non-consecutive groups found: {final_report['non_consecutive_groups']}")
    
    # Save the output
    with open(r"info\0103rebuild\0103_return_nonconsecutive.json", "w", encoding='utf-8') as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)