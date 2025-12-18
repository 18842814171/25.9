import json
import math
import re
import numpy as np
from typing import List, Dict, Tuple,Any
def load_entities(filename: str) -> list:
    """Load JSON entities from file."""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_ids(text: str) -> List[int]:
    """Extract integers from text, handling commas and ranges like '31-39'."""
    parts = [p.strip() for p in re.split(r'[,\s\u3001]+', text)]  # Split by comma or space
    ids = []
    for part in parts:
        if '-' in part:
            range_parts = [int(x) for x in part.split('-') if x.isdigit()]
            if len(range_parts) == 2:
                ids.extend(range_parts)
        elif part.isdigit():
            ids.append(int(part))
    return sorted(set(ids))  # Unique, sorted

def point_to_segment_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Distance from point P to segment AB (2D)."""
    v = b - a
    w = p - a
    vv = np.dot(v, v)
    if vv == 0:  # Degenerate to point
        return np.linalg.norm(p - a)
    proj = max(0, min(1, np.dot(w, v) / vv))
    c = a + proj * v
    return np.linalg.norm(p - c)

def pair_circles_to_lines(entities: List[Dict[str, Any]]) -> Tuple[int, List[Dict[str, Any]]]:
    """Pair circle IDs to nearest lines using handles, append full line data, return count and list."""
    lines: Dict[str, Dict[str, Any]] = {}  # handle -> full line dict
    mtexts = []
    
    for ent in entities:
        if ent["type"] == "LINE":
            handle = ent["handle"]
            lines[handle] = ent  # Store full line data
        elif ent["type"] in ["MTEXT", "INSERT"]:  # Handle both MTEXT and INSERT
            # For MTEXT, get text from "text" attribute
            # For INSERT, get text from "actual_text" attribute
            if ent["type"] == "MTEXT":
                text = ent["attributes"]["text"]
                point = np.array(ent["attributes"]["insert_point"][:2])
            elif ent["type"] == "INSERT":
                text = ent["attributes"].get("actual_text", "")
                point = np.array(ent["attributes"]["insert_point"][:2])
            
            ids = parse_ids(text)
            if ids:  # Only if valid IDs
                mtexts.append({"ids": ids, "point": point})
    
    pairs = []
    for mtext in mtexts:
        p = mtext["point"]
        min_dist = float('inf')
        nearest_handle = None
        for handle, line in lines.items():
            start = np.array(line["attributes"]["start"][:2])
            end = np.array(line["attributes"]["end"][:2])
            dist = point_to_segment_distance(p, start, end)
            if dist < min_dist:
                min_dist = dist
                nearest_handle = handle
        
        if nearest_handle:  # Pair if found
            line_data = lines[nearest_handle]
            for id_val in mtext["ids"]:
                pairs.append({
                    "id": id_val,
                    "nearest_line": nearest_handle,
                    "line_data": line_data
                })
    
    unique_paired_ids = len(set(p["id"] for p in pairs))
    return unique_paired_ids, sorted(pairs, key=lambda x: x["id"])

def exec():
    # Execute and output JSON
    input_file=r"info\1204_export-front_enhanced-dim.json"
    output_file="info/1204_paired_circles_with_lines_front.json"
    data=load_entities(input_file)
    count, paired_circles = pair_circles_to_lines(data)
    print(f"Total paired circles: {count}")
    print("\nPaired Circles Data:")
    import sys
    original_stdout = sys.stdout
    with open (output_file,'w',encoding='utf-8') as f:
        sys.stdout=f
        print(json.dumps(paired_circles, indent=2, ensure_ascii=False))

    sys.stdout = original_stdout
    print("output saved:",output_file)

if __name__=='__main__':
    exec()