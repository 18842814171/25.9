import json
import numpy as np
from typing import List, Dict, Any
import re
def load_entities(filename: str) -> list:
    """Load JSON entities from file."""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_ids(text: str) -> List[int]:
    """Extract integers from text, handling commas and ranges like '31-39'."""
    parts = [p.strip() for p in re.split(r'[,\s\u3001]+', text)]
    ids = []
    for part in parts:
        if '-' in part:
            range_parts = [int(x) for x in part.split('-') if x.isdigit()]
            if len(range_parts) == 2:
                start, end = sorted(range_parts)
                ids.extend(range(start, end + 1))
        elif part.isdigit():
            ids.append(int(part))
    return sorted(set(ids))

def point_to_segment_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Distance from point P to segment AB (2D)."""
    v = b - a
    w = p - a
    vv = np.dot(v, v)
    if vv == 0:
        return np.linalg.norm(p - a)
    proj = max(0, min(1, np.dot(w, v) / vv))
    closest = a + proj * v
    return np.linalg.norm(p - closest)

def pair_circles_to_lines(entities: List[Dict[str, Any]], max_dist: float = 100.0) -> tuple[int, List[Dict[str, Any]]]:
    """Pair circle IDs to all sufficiently close lines, appending full line data to a list."""
    lines: Dict[str, Dict[str, Any]] = {}
    mtexts = []
    
    for ent in entities:
        if ent["type"] == "LINE":
            handle = ent["handle"]
            lines[handle] = ent
        elif ent["type"] in ["MTEXT", "INSERT"]:
            if ent["type"] == "MTEXT":
                text = ent["attributes"]["text"]
                point = np.array(ent["attributes"]["insert_point"][:2])
            elif ent["type"] == "INSERT":
                text = ent["attributes"].get("actual_text", "")
                point = np.array(ent["attributes"]["insert_point"][:2])
            
            ids = parse_ids(text)
            if ids:
                mtexts.append({"ids": ids, "point": point})
    
    pairs = []
    
    for mtext in mtexts:
        p = mtext["point"]
        nearest_lines_data = []
        
        for handle, line in lines.items():
            start = np.array(line["attributes"]["start"][:2])
            end = np.array(line["attributes"]["end"][:2])
            dist = point_to_segment_distance(p, start, end)
            if dist <= max_dist:
                nearest_lines_data.append({
                    "nearest_line_handle": handle,
                    "distance": round(dist, 2),
                    "line_data": line
                })
        
        # Sort by distance ascending
        nearest_lines_data.sort(key=lambda x: x["distance"])
        
        for id_val in mtext["ids"]:
            pairs.append({
                "id": id_val,
                "nearest_lines": nearest_lines_data  # List of all close lines with data
            })
    
    unique_paired_ids = len(set(p["id"] for p in pairs if p["nearest_lines"]))
    return unique_paired_ids, sorted(pairs, key=lambda x: x["id"])

def exec():
    input_file = r"info\0102resolve\0102_export-front.json"
    output_file = r"info\0103rebuild\0103_pair_front.json"
    data = load_entities(input_file)
    count, paired_circles = pair_circles_to_lines(data, max_dist=150.0)
    print(f"Total paired circles: {count}")
    
    import sys
    original_stdout = sys.stdout
    with open(output_file, 'w', encoding='utf-8') as f:
        sys.stdout = f
        json.dump(paired_circles, f, indent=2, ensure_ascii=False)
    
    sys.stdout = original_stdout
    print("Output saved:", output_file)

if __name__ == '__main__':
    exec()