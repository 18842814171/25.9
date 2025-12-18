import json
import numpy as np
from typing import List, Dict, Any, Tuple
import re
import os
import math
from utils.dim_utils_1128 import load_entities, parse_dim_value,  is_slope_dimension, vector_distance_to_line ,calculate_line_orientation

# --- 1. GEOMETRY AND DATA UTILITIES ---
def find_entity_at_point(point: List[float], lines: List[Dict[str, Any]], tolerance: float = 10.0) -> Dict[str, Any]:
    target = np.array(point[:2])
    for entity in lines:
        start = np.array(entity["attributes"]["start"][:2])
        end = np.array(entity["attributes"]["end"][:2])
        if (np.linalg.norm(start - target) < tolerance or 
            np.linalg.norm(end - target) < tolerance):
            return entity
    return None

def find_nearest_line_for_slope(dim: Dict[str, Any], lines: List[Dict[str, Any]]) -> tuple:
    attrs = dim["attributes"]
    def_keys = ['defpoint', 'defpoint2', 'defpoint3', 'defpoint4', 'defpoint5']
    defpoints = [np.array(attrs[key][:2]) for key in def_keys if key in attrs and attrs[key] != [0.0, 0.0, 0.0]]
    if not defpoints:
        return None, 0.0
    avg_pt = np.mean(defpoints, axis=0)
    best_line = None
    min_dist = float('inf')
    for line in lines:
        l_start = np.array(line["attributes"]["start"][:2])
        l_end = np.array(line["attributes"]["end"][:2])
        dist = vector_distance_to_line(avg_pt, l_start, l_end)
        if dist < min_dist and dist < 200.0:
            min_dist = dist
            best_line = line
    if best_line:
        orient = calculate_line_orientation(best_line["attributes"]["start"], best_line["attributes"]["end"])
        if orient == "diagonal":
            slope_val = parse_dim_value(dim)
            return best_line, slope_val
    return None, 0.0

def find_best_line_for_length(dim: Dict[str, Any], lines: List[Dict[str, Any]], used_lines: set) -> tuple:
    attrs = dim["attributes"]
    dim_value = parse_dim_value(dim)
    val_for_check = attrs.get("measurement", dim_value)
    def_keys = ['defpoint', 'defpoint2', 'defpoint3', 'defpoint4', 'defpoint5']
    defpoints_list = [np.array(attrs[key][:2]) for key in def_keys if key in attrs and attrs[key] != [0.0, 0.0, 0.0]]
    if len(defpoints_list) < 2:
        return None, None
    candidates = []
    for line in lines:
        if line["handle"] in used_lines and dim_value >= np.linalg.norm(np.array(line["attributes"]["end"][:2]) - np.array(line["attributes"]["start"][:2])) * 0.5:
            continue
        l_start = np.array(line["attributes"]["start"][:2])
        l_end = np.array(line["attributes"]["end"][:2])
        line_len = np.linalg.norm(l_end - l_start)
        orient = calculate_line_orientation(l_start, l_end)
        best_seg_score = -float('inf')
        for i in range(len(defpoints_list)):
            for j in range(i+1, len(defpoints_list)):
                p1, p2 = defpoints_list[i], defpoints_list[j]
                dim_orient = calculate_line_orientation(p1, p2)
                if dim_orient != orient:
                    continue
                d1 = vector_distance_to_line(p1, l_start, l_end)
                d2 = vector_distance_to_line(p2, l_start, l_end)
                if d1 < 1000.0 and d2 < 1000.0:
                    seg_dist = np.linalg.norm(p1 - p2)
                    if abs(seg_dist -val_for_check) < 1000.0:
                        seg_score = 100 - (d1 + d2)/2 - abs(seg_dist - val_for_check)
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

def prepare_data(all_entities):
    """Filters entities and creates necessary lookup maps."""
    lines = [e for e in all_entities if e["type"] == "LINE"]
    dims = [e for e in all_entities if e["type"] == "DIMENSION"]
    line_map = {e["handle"]: e for e in lines}
    
    return lines, dims, line_map

def pass1_direct_snaps_and_slopes(dims, line_map, lines):
    pairings = {}
    used_dims = set()
    for dim in dims:
        if dim["handle"] in used_dims:
            continue
        attrs = dim["attributes"]
        dim_value = parse_dim_value(dim)
        val_for_check = attrs.get("measurement", dim_value)
        is_slope = is_slope_dimension(dim)
        connected_entities = set()
        for point_key in ['defpoint', 'defpoint2', 'defpoint3', 'defpoint4', 'defpoint5', 'defpoint6']:
            if point_key in attrs:
                point = attrs[point_key]
                if point == [0.0, 0.0, 0.0]:
                    continue
                entity = find_entity_at_point(point, lines)
                if entity:
                    connected_entities.add(entity["handle"])
        if connected_entities:
            used_dims.add(dim["handle"])
            for line_h in connected_entities:
                if line_h not in pairings:
                    pairings[line_h] = {'lengths': [], 'slope': None, 'notes': []}
                line = line_map[line_h]
                orient = calculate_line_orientation(line["attributes"]["start"], line["attributes"]["end"])
                if is_slope:
                    if orient == "diagonal" and pairings[line_h]['slope'] is None:
                        pairings[line_h]['slope'] = dim_value
                else:
                    pairings[line_h]['lengths'].append(dim_value)
                    pairings[line_h]['notes'].append(' (exact)')
    # Fallback for unpaired slopes
    for dim in [d for d in dims if is_slope_dimension(d) and d["handle"] not in used_dims]:
        best_line, slope_val = find_nearest_line_for_slope(dim, lines)
        if best_line:
            line_h = best_line["handle"]
            used_dims.add(dim["handle"])
            if line_h not in pairings:
                pairings[line_h] = {'lengths': [], 'slope': None, 'notes': []}
            if pairings[line_h]['slope'] is None:
                pairings[line_h]['slope'] = slope_val
    return pairings, used_dims

def pass2_partial_lengths(dims, lines, used_dims, initial_pairings):
    pairings = initial_pairings.copy()
    used_lines = set()
    for dim in [d for d in dims if not is_slope_dimension(d) and d["handle"] not in used_dims]:
        best_line, details = find_best_line_for_length(dim, lines, used_lines)
        if best_line:
            length, score, flag = details
            line_h = best_line["handle"]
            used_dims.add(dim["handle"])
            if line_h not in pairings:
                pairings[line_h] = {'lengths': [], 'slope': None, 'notes': []}
            pairings[line_h]['lengths'].append(length)
            pairings[line_h]['notes'].append(flag)
            if "(partial)" not in flag:
                used_lines.add(line_h)
    return pairings

def process_results(all_entities, pairings):
    result_entities = []
    for ent in all_entities:
        ent_copy = ent.copy()
        if ent["type"] == "LINE" and ent["handle"] in pairings:
            attrs = ent_copy["attributes"]
            p = pairings[ent["handle"]]
            attrs["partial_lengths"] = p['lengths'] if len(p['lengths']) > 1 else p['lengths'][0] if p['lengths'] else None
            attrs["slope"] = p['slope']
            if any("(partial)" in n for n in p['notes']):
                attrs["note"] = " (multi-partial)"
            print(f"Enhanced {ent['handle']}: partial_lengths={attrs.get('partial_lengths')}, slope={p['slope']} {attrs.get('note', '')}")
        result_entities.append(ent_copy)
    # Stats
    total_paired = sum(len(p['lengths']) + (1 if p['slope'] is not None else 0) for p in pairings.values())
    lines_with_length = sum(1 for p in pairings.values() if p['lengths'])
    lines_with_slope = sum(1 for p in pairings.values() if p['slope'] is not None)
    dim_count = sum(1 for e in all_entities if e["type"] == "DIMENSION")
    unused = dim_count - total_paired
    stats = {
        "lines_with_length": lines_with_length,
        "lines_with_slope": lines_with_slope,
        "unused_dimensions": unused
    }
    return result_entities, stats

def pair_dimensions_with_entities_combined(all_entities):
    # 1. Data Preparation
    lines, dims, line_map = prepare_data(all_entities)

    # 2. Execute Pass 1 (Direct Snaps/Slopes)
    initial_pairings, used_dims = pass1_direct_snaps_and_slopes(dims, line_map, lines)

    # 3. Execute Pass 2 (Proximity/Partial Lengths)
    final_pairings = pass2_partial_lengths(dims, lines, used_dims, initial_pairings)

    # 4. Process and Report Results
    result_entities, stats = process_results(all_entities, final_pairings)
    
    return result_entities, stats,final_pairings

def main():
    input_file = r"info\1202-translated_front.json"
    print(f"Loading from {input_file}...")
    all_entities = load_entities(input_file)
    result_entities, stats ,final_pairings= pair_dimensions_with_entities_combined(all_entities)
    total_paired = sum(len(p['lengths']) + (1 if p['slope'] is not None else 0) for p in final_pairings.values())
    print(f"\nMade {total_paired} pairings")
    print("\nFinal Results:")
    print(f"Lines with length dimensions: {stats['lines_with_length']}")
    print(f"Lines with slope dimensions: {stats['lines_with_slope']}")
    print(f"Unused dimensions: {stats['unused_dimensions']}")
    os.makedirs("info", exist_ok=True)
    output_file = "info/1202_paired_front.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_entities, f, indent=2, ensure_ascii=False)
    print(f"Enhanced entities saved to: {output_file}")
    print("\nEnhanced lines summary:")
    for ent in result_entities:
        if ent["type"] == "LINE":
            attrs = ent["attributes"]
            pl = attrs.get("partial_lengths")
            slope = attrs.get("slope")
            note = attrs.get("note", "")
            if pl or slope is not None:
                print(f"Line {ent['handle']}: partial_lengths={pl}, slope={slope} {note}")

if __name__ == "__main__":
    main()


"""
require manual correction
Line 368: partial_lengths=1000.0, slope=None//line370 should be matched with 1000
Line 36D: partial_lengths=[300.0, 300.0, 500.0, 500.0, 400.0, 400.0, 500.0], slope=None (multi-partial)
Line 370: partial_lengths=1200.0, slope=None//should add 1000
Line 377: partial_lengths=None, slope=68.0
Line 378: partial_lengths=300.0, slope=68.0//the sloping line isn't annotated with 300
"""