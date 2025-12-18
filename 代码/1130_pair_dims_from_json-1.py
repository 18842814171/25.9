import json
import numpy as np
from typing import List, Dict, Any
from utils.dim_utils_1128 import load_entities, parse_dim_value, extract_numbers, is_slope_dimension, vector_distance_to_line, calculate_line_orientation


def find_entity_at_point(point: List[float], entities: List[Dict[str, Any]], tolerance: float = 1.0) -> Dict[str, Any]:
    """Find entity that has a vertex at or near the given point."""
    target = np.array(point[:2])
    
    for entity in entities:
        if entity["type"] == "LINE":
            start = np.array(entity["attributes"]["start"][:2])
            end = np.array(entity["attributes"]["end"][:2])
            
            # Check if dimension point snaps to line endpoints
            if (np.linalg.norm(start - target) < tolerance or 
                np.linalg.norm(end - target) < tolerance):
                return entity
        
        elif entity["type"] in ["LWPOLYLINE", "POLYLINE"]:
            vertices = entity["attributes"].get("vertices", [])
            for vertex in vertices:
                if np.linalg.norm(np.array(vertex[:2]) - target) < tolerance:
                    return entity
    
    return None

def pass1_direct_snaps_and_slopes(all_entities, tolerance=5.0):
    """Pair dimensions using direct snapping of definition points to line endpoints."""
    line_entities = [ent for ent in all_entities if ent["type"] == "LINE"]
    dim_entities = [ent for ent in all_entities if ent["type"] == "DIMENSION"]
    
    pairings = {}  # Line_h -> {'lengths': [], 'slope': None}
    used_dims = set()

    for dim in dim_entities:
        attrs = dim["attributes"]
        dim_value = parse_dim_value(dim)
        is_slope = is_slope_dimension(dim)
        connected_entities = set()
        
        # Check all definition points for a snap
        for point_key in ['defpoint', 'defpoint2', 'defpoint3', 'defpoint4']:
            if point_key in attrs and attrs[point_key] != [0.0, 0.0, 0.0]:
                entity = find_entity_at_point(attrs[point_key], line_entities, tolerance=tolerance)
                if entity:
                    connected_entities.add(entity["handle"])
        
        if connected_entities:
            used_dims.add(dim["handle"])
            for line_h in connected_entities:
                if line_h not in pairings: pairings[line_h] = {'lengths': [], 'slope': None}
                
                if is_slope and pairings[line_h]['slope'] is None:
                    pairings[line_h]['slope'] = dim_value
                elif not is_slope: # Direct length snap
                    pairings[line_h]['lengths'].append(dim_value)

    return pairings, used_dims


def find_best_line_for_length(dim: Dict[str, Any], lines: List[Dict[str, Any]], used_lines: set) -> tuple:
    """Find best line for length dim (as before, but allow partial multiples)."""
    attrs = dim["attributes"]
    dim_value = parse_dim_value(dim)
    
    def_keys = ['defpoint', 'defpoint2', 'defpoint3', 'defpoint4', 'defpoint5']
    defpoints_list = [np.array(attrs[key][:2]) for key in def_keys if key in attrs and attrs[key] != [0.0, 0.0, 0.0]]
    
    if len(defpoints_list) < 2:
        return None, None
    
    candidates = []
    for line in lines:
        if line["handle"] in used_lines and dim_value >= np.linalg.norm(np.array(line["attributes"]["end"][:2]) - np.array(line["attributes"]["start"][:2])) * 0.5:
            continue  # Block full lengths on used, allow partials
        l_start = np.array(line["attributes"]["start"][:2])
        l_end = np.array(line["attributes"]["end"][:2])
        line_len = np.linalg.norm(l_end - l_start)
        orient = calculate_line_orientation(l_start, l_end)
        
        # Best pair of points
        best_seg_score = -float('inf')
        for i in range(len(defpoints_list)):
            for j in range(i+1, len(defpoints_list)):
                p1, p2 = defpoints_list[i], defpoints_list[j]
                d1 = vector_distance_to_line(p1, l_start, l_end)
                d2 = vector_distance_to_line(p2, l_start, l_end)
                if d1 < 80.0 and d2 < 80.0:
                    seg_dist = np.linalg.norm(p1 - p2)
                    if abs(seg_dist - dim_value) < 30.0:
                        seg_score = 100 - (d1 + d2)/2 - abs(seg_dist - dim_value)
                        if seg_score > best_seg_score:
                            best_seg_score = seg_score
        
        if best_seg_score > -float('inf'):
            snaps = sum(1 for pt in defpoints_list if min(np.linalg.norm(pt - l_start), np.linalg.norm(pt - l_end)) < 10.0)
            orient_bonus = 20 if orient == "vertical" else 0
            partial_flag = " (partial)" if dim_value < line_len * 0.5 else ""
            score = best_seg_score + (50 if snaps > 0 else 0) + orient_bonus
            candidates.append((line, score, partial_flag))
    
    if not candidates:
        return None, None
    
    best_line, score, flag = max(candidates, key=lambda x: x[1])
    return best_line, (dim_value, score, flag)

def pass2_partial_lengths(all_entities, used_dims, initial_pairings):
    """Pair remaining dimensions using proximity and value matching."""
    lines = [ent for ent in all_entities if ent["type"] == "LINE"]
    dims_remaining = [d for d in all_entities if d["type"] == "DIMENSION" and d["handle"] not in used_dims]
    
    # Initialize pairings with results from Pass 1
    pairings = initial_pairings.copy()
    
    # Track lines used for full lengths in Pass 1 to avoid conflicts
    used_lines_full = set(h for h, p in pairings.items() if p['lengths'])

    for dim in dims_remaining:
        if is_slope_dimension(dim): continue # Skip any unmatched slopes

        # find_best_line_for_length needs to be imported/defined from Script 1
        best_line, details = find_best_line_for_length(dim, lines, used_lines_full) 
        
        if best_line:
            length, score, flag = details
            line_h = best_line["handle"]
            
            if line_h not in pairings: pairings[line_h] = {'lengths': [], 'slope': None}
            
            # Append the length to the partial_lengths list
            pairings[line_h]['lengths'].append(length)
            
            if not "(partial)" in flag and not pairings[line_h]['lengths']:
                # Only mark used if it's a full length not yet matched
                used_lines_full.add(line_h)
            
    return pairings


# Execute
input_file =r"info\1128_export-leftview-f-fixed.json"
print(f"Loading from {input_file}...")
all_entities = load_entities(input_file)

line_count = sum(1 for e in all_entities if e["type"] == "LINE")
dim_count = sum(1 for e in all_entities if e["type"] == "DIMENSION")

print(f"Found: {line_count} lines, {dim_count} dimensions")

# 1. Execute Pass 1
initial_pairings, used_dims = pass1_direct_snaps_and_slopes(all_entities)
# 2. Execute Pass 2
final_pairings = pass2_partial_lengths(all_entities, used_dims, initial_pairings)
# Assuming 'all_entities', 'dim_count', and 'final_pairings' are available 
# after running Pass 1 and Pass 2.

# 3. Enhance Entities and Populate result_entities
result_entities = []
for ent in all_entities:
    ent_copy = ent.copy()
    if ent["type"] == "LINE" and ent["handle"] in final_pairings:
        attrs = ent_copy["attributes"]
        p = final_pairings[ent["handle"]]
        
        # Assign slope
        attrs["slope"] = p.get('slope')
        
        # Assign lengths (as partial_lengths list)
        if p['lengths']:
            # Store as a list of lengths
            attrs["partial_lengths"] = p['lengths'] 
        else:
            attrs["partial_lengths"] = None
        
        ent_copy["attributes"] = attrs # Update attributes
        
    result_entities.append(ent_copy)

# Statistics Calculation
total_paired = 0
lines_with_length = 0
lines_with_slope = 0

for p in final_pairings.values():
    # Count total dimensions paired
    total_paired += len(p['lengths'])
    if p['slope'] is not None:
        total_paired += 1
    
    # Count lines that have each type of dimension
    if p['lengths']:
        lines_with_length += 1
    if p['slope'] is not None:
        lines_with_slope += 1

# --- Your requested print summary begins here ---
print(f"\nFinal Results:")
print(f"Lines with length dimensions: {lines_with_length}")
print(f"Lines with slope dimensions: {lines_with_slope}")
print(f"Unused dimensions: {dim_count - total_paired}")
# --- Your requested print summary ends here ---

# Print enhanced lines summary (for verification)
print("\nEnhanced lines summary:")
for ent in result_entities:
    if ent["type"] == "LINE":
        attrs = ent["attributes"]
        pl = attrs.get("partial_lengths")
        slope = attrs.get("slope")
        if pl or slope:
            # Adjusting print format for the list of partial lengths
            length_output = pl
            if isinstance(pl, list):
                length_output = f"[{', '.join(map(str, pl))}]"
            
            print(f"Line {ent['handle']}: partial_lengths={length_output}, slope={slope}")
"""
Loading from info\1128_export-leftview-f-fixed.json...
Found: 15 lines, 11 dimensions

Final Results:
Lines with length dimensions: 2
Lines with slope dimensions: 5
Unused dimensions: -1

The negative number occurs because the two slope dimensions were paired multiple times to different lines in Pass 1, inflating the total_paired count:
$$\text{Total Paired} = (7 \text{ lengths}) + (6 \text{ slopes}) = 13$$$$\text{Unused} = 11 
(\text{Dim Count}) - 13 (\text{Total Paired}) = -2$$

Enhanced lines summary:
Line 36C: partial_lengths=None, slope=68.0
Line 36D: partial_lengths=[300.0, 300.0, 500.0, 500.0, 400.0, 500.0], slope=68.0     
Line 36F: partial_lengths=None, slope=68.0
Line 377: partial_lengths=None, slope=68.0
Line 378: partial_lengths=[300.0], slope=68.0
"""