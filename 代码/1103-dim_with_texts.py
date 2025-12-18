import ezdxf
import numpy as np
from typing import List, Dict, Any
from collections import defaultdict
import re

# Load DXF file (single source)
dxf_path = "sepview-8/top.dxf"
doc = ezdxf.readfile(dxf_path)
msp = doc.modelspace()

# Single-pass extraction: lines + dims
lines: List[Dict[str, Any]] = []
dims: List[Dict[str, Any]] = []
for e in msp:
    if e.dxftype() == 'LINE':
        lines.append({
            "type": "LINE",
            "handle": e.dxf.handle,
            "attributes": {
                "start": list(e.dxf.start),
                "end": list(e.dxf.end)
            }
        })
    elif e.dxftype() == 'DIMENSION':
        attrs = {}
        # Defpoints from DXF tags (skip zeros)
        def_keys = ['defpoint', 'defpoint2', 'defpoint3', 'defpoint4', 'defpoint5']
        for key in def_keys:
            pt = getattr(e.dxf, key, (0.0, 0.0, 0.0))
            if not np.allclose(pt, [0.0, 0.0, 0.0]):
                attrs[key] = list(pt)
        # Other attrs
        # Other attrs (corrected)
        attrs['measurement'] = getattr(e.dxf, 'actual_measurement', 0.0)  # Use actual_measurement
        attrs['text'] = getattr(e.dxf, 'text', '')  # Use text for override
        # block_texts: Use text if overridden, else str(measurement) for display approx
        text_val = e.dxf.text if e.dxf.text and e.dxf.text not in ['', '<>'] else str(attrs['measurement'])
        attrs['block_texts'] = [text_val]
        dims.append({
            "type": "DIMENSION",
            "handle": e.dxf.handle,
            "attributes": attrs
        })


# Enhance dims with geometry block texts (inside pair_dimensions_with_entities or after extraction)
for dim_ent in dims:  # dim_ent is dict; need original ezdxf entity
    # Fetch original entity (assume you store it in dict as 'entity')
    if 'entity' not in dim_ent:  # If not stored, fetch via handle
        dim_ent['entity'] = doc.entitydb[dim_ent['handle']]
    dimension = dim_ent['entity']
    print(f"Dimension {dimension.dxf.handle}:")
    print(f"  Type: {dimension.dimtype}")  # e.g., 0=linear, 4=radial
    print(f"  Measurement: {dimension.get_measurement()}")  # Computed from defpoints
    print(f"  Text Override: {dimension.dxf.text}")  # "<>", custom, or empty
    
    block = dimension.get_geometry_block()
    if block is None:
        print("  No geometry block.")
        continue
    embedded_texts = []
    for entity in block.query("TEXT MTEXT"):
        text = entity.dxf.text
        embedded_texts.append(text)
        print(f"  Embedded: {entity.dxftype()} '{text}'")

print(f"Loaded {len(lines)} lines and {len(dims)} dimensions from DXF (single pass).")

# Helper functions (unchanged from prior)
def parse_dim_value(dim: Dict[str, Any]) -> float:
    attrs = dim["attributes"]
    if attrs.get("embedded_texts"):
        for txt in attrs["embedded_texts"]:
            numbers = extract_numbers(txt)
            if numbers: return numbers[0]
    if attrs.get("block_texts") and attrs["block_texts"]:
        val_str = attrs["block_texts"][0].strip()
        numbers = extract_numbers(val_str)
        if numbers:
            return numbers[0]
    if attrs.get("text") and attrs["text"].strip():
        val_str = attrs["text"].strip()
        numbers = extract_numbers(val_str)
        if numbers:
            return numbers[0]
    return float(attrs.get("measurement", 0.0))

def extract_numbers(text: str) -> List[float]:
    numbers = re.findall(r'-?\d+\.?\d*', text)
    return [float(num) for num in numbers if num]

def is_slope_dimension(dim: Dict[str, Any]) -> bool:
    attrs = dim["attributes"]
    dim_text = str(attrs.get("text", "") + " " + " ".join(str(t) for t in attrs.get("block_texts", []))).lower()
    has_degree = ("°" in dim_text)
    has_slope_keyword = any(kw in dim_text for kw in ["dip", "slope", "angle", "°", "deg"])
    return has_degree or has_slope_keyword

def vector_distance_to_line(pt: np.ndarray, line_start: np.ndarray, line_end: np.ndarray) -> float:
    line_vec = line_end - line_start
    to_pt_vec = pt - line_start
    line_len = np.linalg.norm(line_vec)
    if line_len < 1e-6:
        return np.linalg.norm(to_pt_vec)
    norm_vec = line_vec / line_len
    proj = np.dot(to_pt_vec, norm_vec)
    proj = max(0, min(line_len, proj))
    closest = line_start + proj * norm_vec
    return np.linalg.norm(pt - closest)

# Corrected: find_best_line_for_dim (uses measured pts, typed logic, loose tol)
def find_best_line_for_dim(dim: Dict[str, Any], lines: List[Dict[str, Any]], used_lines: set) -> tuple:
    attrs = dim["attributes"]
    is_slope = is_slope_dimension(dim)
    dim_value = parse_dim_value(dim)
    
    # All defpoints
    def_keys = ['defpoint', 'defpoint2', 'defpoint3', 'defpoint4', 'defpoint5']
    defpoints_raw = [np.array(attrs[key][:2]) for key in def_keys if key in attrs and not np.allclose(attrs[key][:2], [0,0])]
    
    if not defpoints_raw or len(defpoints_raw) < 2:
        return None, None
    
    # Prioritize defpoint2/defpoint3 as measured points (skip offset defpoint)
    if len(defpoints_raw) >= 3:
        p1 = defpoints_raw[1]  # defpoint2
        p2 = defpoints_raw[2]  # defpoint3
    else:
        p1 = defpoints_raw[0]
        p2 = defpoints_raw[1]
    defpoints = defpoints_raw  # All for snaps
    
    candidates = []
    for line in lines:
        if line["handle"] in used_lines:
            continue
        l_start = np.array(line["attributes"]["start"][:2])
        l_end = np.array(line["attributes"]["end"][:2])
        line_vec = l_end - l_start
        line_len = np.linalg.norm(line_vec)
        pt_vec = p2 - p1
        meas_dist = np.linalg.norm(pt_vec)
        
        if abs(meas_dist - dim_value) > 100:  # Quick value filter
            continue
            
        d1 = vector_distance_to_line(p1, l_start, l_end)
        d2 = vector_distance_to_line(p2, l_start, l_end)
        
        # Length along line: both pts close + parallel
        if d1 < 100 and d2 < 100:
            cos_theta = abs(np.dot(line_vec, pt_vec) / (line_len * meas_dist + 1e-6))
            if cos_theta > 0.9:
                snaps = sum(1 for pt in defpoints if min(np.linalg.norm(pt - l_start), np.linalg.norm(pt - l_end)) < 50)
                score = 100 - (d1 + d2)/2 + (50 if snaps > 0 else 0)
                candidates.append((line, score, 'length'))
        
        # Spacing perp: one pt close + other offset by value + perpendicular
        if min(d1, d2) < 100 and abs(max(d1, d2) - meas_dist) < 50:
            cos_theta = abs(np.dot(line_vec, pt_vec) / (line_len * meas_dist + 1e-6))
            if cos_theta < 0.1:  # Perp
                snaps = sum(1 for pt in defpoints if min(np.linalg.norm(pt - l_start), np.linalg.norm(pt - l_end)) < 50)
                score = 100 - min(d1, d2) + (50 if snaps > 0 else 0)
                candidates.append((line, score, 'spacing'))
    
    if is_slope:
        # Slope: loosen snap
        for line in lines:
            if line["handle"] in used_lines:
                continue
            l_start = np.array(line["attributes"]["start"][:2])
            l_end = np.array(line["attributes"]["end"][:2])
            snaps = sum(1 for pt in defpoints if min(np.linalg.norm(pt - l_start), np.linalg.norm(pt - l_end)) < 50)
            if snaps >= 1:
                dx, dy = abs(l_end[0] - l_start[0]), abs(l_end[1] - l_start[1])
                is_diag = dx > 1.0 and dy > 1.0
                score = snaps * 20 + (50 if is_diag else -50)
                if score > 0:
                    candidates.append((line, score, 'slope'))
    
    if not candidates:
        return None, None
    
    best_line, best_score, dim_type = max(candidates, key=lambda x: x[1])
    return best_line, best_score

# Corrected: pair_dimensions_with_entities (multi-pairing, no used_lines exclusivity)
def pair_dimensions_with_entities(lines: List[Dict[str, Any]], dims: List[Dict[str, Any]]) -> tuple:
    used_dims = set()  # Dims unique only
    line_to_dims: Dict[str, List[str]] = defaultdict(list)
    dim_to_lines: Dict[str, List[str]] = defaultdict(list)
    
    print(f"Processing {len(dims)} dims and {len(lines)} lines...")
    
    # Slopes first
    for dim in [d for d in dims if is_slope_dimension(d)]:
        if dim["handle"] in used_dims:
            continue
        best_line, score = find_best_line_for_dim(dim, lines, set())  # No used_lines
        if best_line and score > 0:
            used_dims.add(dim["handle"])
            line_h = best_line["handle"]
            line_to_dims[line_h].append(dim["handle"])
            dim_to_lines[dim["handle"]].append(line_h)
            print(f"Paired slope dim {dim['handle']} to line {line_h} (score: {score:.1f})")
    
    # Lengths/spacing next
    for dim in [d for d in dims if not is_slope_dimension(d)]:
        if dim["handle"] in used_dims:
            continue
        best_line, score = find_best_line_for_dim(dim, lines, set())
        if best_line and score > 20:  # Higher for linear
            used_dims.add(dim["handle"])
            line_h = best_line["handle"]
            line_to_dims[line_h].append(dim["handle"])
            dim_to_lines[dim["handle"]].append(line_h)
            print(f"Paired length/spacing dim {dim['handle']} to line {line_h} (score: {score:.1f})")
    
    print(f"\nMade {sum(len(ds) for ds in line_to_dims.values())} total pairings ({len(line_to_dims)} lines)")
    return line_to_dims, dim_to_lines

# Register APPIDs
doc.appids.add("RELATED_DIMS")
doc.appids.add("RELATED_GEOMETRY")
print("Registered APPIDs: RELATED_DIMS, RELATED_GEOMETRY")

# Pairing + XDATA attachment
line_to_dims, dim_to_lines = pair_dimensions_with_entities(lines, dims)

attached_pairs = 0
for line_h, dim_hs in line_to_dims.items():
    line_e = doc.entitydb[line_h]
    xdata = [(1000, f"DIM:{dh}") for dh in dim_hs]
    line_e.set_xdata("RELATED_DIMS", xdata)
    print(f"Attached RELATED_DIMS to LINE {line_h}: {dim_hs}")
    attached_pairs += len(dim_hs)

for dim_h, line_hs in dim_to_lines.items():
    if dim_h in doc.entitydb:
        dim_e = doc.entitydb[dim_h]
        xdata = [(1000, f"LINE:{lh}") for lh in line_hs]
        dim_e.set_xdata("RELATED_GEOMETRY", xdata)
        print(f"Attached RELATED_GEOMETRY to DIM {dim_h}: {line_hs}")
        attached_pairs += len(line_hs)
    else:
        print(f"Warning: DIM {dim_h} not in entitydb")

print(f"Attached {attached_pairs} total relations.")

# Save
output_path = "top_view_with_handles_corrected.dxf"
doc.saveas(output_path)
print(f"Saved to: {output_path}")

# Verification (reload + print)
try:
    doc = ezdxf.readfile(output_path)
    print("Reloaded successfully.")
    print(f"APPIDs: {[appid.dxf.name for appid in doc.appids]}")
except Exception as e:
    print(f"Reload error: {e}")
    exit(1)

msp = doc.modelspace()
print("\nXDATA Verification:")
for entity in msp:
    if hasattr(entity, 'has_xdata'):
        if entity.has_xdata("RELATED_DIMS"):
            data = entity.get_xdata("RELATED_DIMS")
            print(f"{entity.dxftype()} ({entity.dxf.handle}) RELATED_DIMS → {data}")
        if entity.has_xdata("RELATED_GEOMETRY"):
            data = entity.get_xdata("RELATED_GEOMETRY")
            print(f"{entity.dxftype()} ({entity.dxf.handle}) RELATED_GEOMETRY → {data}")

print("\nExample Traversal (LINES → DIMS):")
for entity in msp:
    if entity.dxftype() == 'LINE' and entity.has_xdata("RELATED_DIMS"):
        data = entity.get_xdata("RELATED_DIMS")
        dim_handles = [v[1].split(":")[1] for v in data if isinstance(v[1], str) and ":" in v[1]]
        related_dims = [f"{doc.entitydb[h].dxftype()} ({h})" for h in dim_handles if h in doc.entitydb]
        print(f"LINE {entity.dxf.handle} → Related DIMS: {', '.join(related_dims)}")

print("Verification complete.")