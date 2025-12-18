import json
import numpy as np
from typing import List, Dict, Any
import re
import os

def load_entities(input_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_dim_value(dim):
    attrs = dim["attributes"]
    if attrs.get("text"):
        val = re.sub(r'[° ]', '', attrs["text"])
        try:
            return float(val)
        except:
            pass
    if attrs.get("block_texts") and attrs["block_texts"]:
        try:
            return float(attrs["block_texts"][0])
        except:
            pass
    return attrs.get("measurement", 0.0)

def is_slope_dimension(dim):
    return '°' in dim["attributes"].get("text", "")

def vector_distance_to_line(point, line_start, line_end):
    point = np.array(point)
    line_start = np.array(line_start)
    line_end = np.array(line_end)
    line_vec = line_end - line_start
    if np.linalg.norm(line_vec) == 0:
        return np.linalg.norm(point - line_start)
    proj_len = np.dot(point - line_start, line_vec) / np.dot(line_vec, line_vec)
    proj_len = np.clip(proj_len, 0, 1)
    closest = line_start + proj_len * line_vec
    return np.linalg.norm(point - closest)

def calculate_line_orientation(l_start, l_end):
    dx = abs(l_end[0] - l_start[0])
    dy = abs(l_end[1] - l_start[1])
    epsilon = 1e-6
    if dx < epsilon:
        return "vertical"
    if dy < epsilon:
        return "horizontal"
    return "diagonal"

def find_entity_at_point(point: List[float], entities: List[Dict[str, Any]], tolerance: float = 10.0) -> Dict[str, Any]:
    target = np.array(point[:2])
    for entity in entities:
        if entity["type"] == "LINE":
            start = np.array(entity["attributes"]["start"][:2])
            end = np.array(entity["attributes"]["end"][:2])
            if (np.linalg.norm(start - target) < tolerance or 
                np.linalg.norm(end - target) < tolerance):
                return entity
        elif entity["type"] in ["LWPOLYLINE", "POLYLINE"]:
            vertices = entity["attributes"].get("vertices", [])
            for vertex in vertices:
                if np.linalg.norm(np.array(vertex[:2]) - target) < tolerance:
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

def pair_dimensions_with_entities_combined(all_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lines = [ent for ent in all_entities if ent["type"] == "LINE"]
    dims = [ent for ent in all_entities if ent["type"] == "DIMENSION"]
    handle_to_line = {line["handle"]: line for line in lines}
    used_dims = set()
    pairings = {}
    print(f"Processing {len(dims)} dims and {len(lines)} lines...")
    for dim in dims:
        if dim["handle"] in used_dims:
            continue
        attrs = dim["attributes"]
        dim_value = parse_dim_value(dim)
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
                line = handle_to_line[line_h]
                orient = calculate_line_orientation(line["attributes"]["start"], line["attributes"]["end"])
                if is_slope:
                    if orient == "diagonal" and pairings[line_h]['slope'] is None:
                        pairings[line_h]['slope'] = dim_value
                else:
                    pairings[line_h]['lengths'].append(dim_value)
                    pairings[line_h]['notes'].append(' (exact)')
    for dim in [d for d in dims if is_slope_dimension(d) and d["handle"] not in used_dims]:
        best_line, slope_val = find_nearest_line_for_slope(dim, lines)
        if best_line:
            line_h = best_line["handle"]
            used_dims.add(dim["handle"])
            if line_h not in pairings:
                pairings[line_h] = {'lengths': [], 'slope': None, 'notes': []}
            if pairings[line_h]['slope'] is None:
                pairings[line_h]['slope'] = slope_val
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
    print(f"\nMade {sum(len(p['lengths']) + (1 if p['slope'] is not None else 0) for p in pairings.values())} pairings")
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
    return result_entities, pairings

def execute():
    input_file = r"info\1128_export-leftview-f-fixed.json"
    print(f"Loading from {input_file}...")
    all_entities = load_entities(input_file)
    line_count = sum(1 for e in all_entities if e["type"] == "LINE")
    dim_count = sum(1 for e in all_entities if e["type"] == "DIMENSION")
    print(f"Found: {line_count} lines, {dim_count} dimensions")
    result_entities, pairings = pair_dimensions_with_entities_combined(all_entities)
    total_paired = sum(len(p['lengths']) + (1 if p['slope'] is not None else 0) for p in pairings.values())
    lines_with_length = sum(1 for p in pairings.values() if p['lengths'])
    lines_with_slope = sum(1 for p in pairings.values() if p['slope'] is not None)
    print(f"\nFinal Results:")
    print(f"Lines with length dimensions: {lines_with_length}")
    print(f"Lines with slope dimensions: {lines_with_slope}")
    print(f"Unused dimensions: {dim_count - total_paired}")
    os.makedirs("info", exist_ok=True)
    output_file = "info/1026_paired_combined_fixed.json"
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

if __name__=='__main__':
    execute()