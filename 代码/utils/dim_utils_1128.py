# dim_utils.py
import json
import numpy as np
import re
from typing import List, Dict, Any

# Shared functions (identical in both scripts)
def load_entities(filename: str) -> list:
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_dim_value(dim: Dict[str, Any]) -> float:
    """Extract dimension value - prioritize text over measurement."""
    attrs = dim["attributes"]
    
    # First try: block_texts (most reliable)
    if attrs.get("block_texts") and attrs["block_texts"]:
        val_str = attrs["block_texts"][0].strip()
        # Extract numbers from text (e.g., "68°" -> 68.0)
        numbers = extract_numbers(val_str)
        if numbers:
            return numbers[0]
    
    # Second try: text attribute
    if attrs.get("text") and attrs["text"].strip():
        val_str = attrs["text"].strip()
        numbers = extract_numbers(val_str)
        if numbers:
            return numbers[0]
    
    # Fallback: measurement
    return attrs.get("measurement", 0.0)

def extract_numbers(text: str) -> List[float]:
    """Extract numbers from text, handling degree symbols and other non-numeric characters."""
    import re
    # Find all numbers (integers and decimals)
    numbers = re.findall(r'-?\d+\.?\d*', text)
    return [float(num) for num in numbers]

def is_slope_dimension(dim: Dict[str, Any]) -> bool:
    # First: trust DXF semantics
    if is_angular_dim(dim):
        return True

    # Fallback: text-based heuristic
    attrs = dim["attributes"]
    dim_text = attrs.get("text", "").lower()
    block_texts = attrs.get("block_texts", [])

    has_degree = (
        "°" in dim_text or
        any("°" in str(text) for text in block_texts)
    )
    has_slope_keyword = any(
        kw in dim_text for kw in ("dip", "slope", "angle")
    )

    return has_degree or has_slope_keyword

def vector_distance_to_line(pt: np.ndarray, line_start: np.ndarray, line_end: np.ndarray) -> float:
    """Perp distance from point to line segment."""
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

def calculate_line_orientation(start: np.ndarray, end: np.ndarray) -> str:
    """Horizontal, vertical, or diagonal."""
    dx, dy = abs(end[0] - start[0]), abs(end[1] - start[1])
    if dx < 1.0: return "vertical"
    if dy < 1.0: return "horizontal"
    return "diagonal"

def is_angular_dim(dim: Dict[str, Any]) -> bool:
    """
    DXF dimtype is bitmasked.
    Bit 2 (value 2) indicates angular dimension.
    """
    dimtype = dim["attributes"].get("dimtype")
    if dimtype is None:
        return False
    return (dimtype & 2) != 0

def point_to_infinite_line_distance(p, l0, d):
    v = p - l0
    proj = np.dot(v, d) * d
    return np.linalg.norm(v - proj)


def classify_direction(d: np.ndarray) -> str:
    dx, dy = abs(d[0]), abs(d[1])
    if dx < 0.3:
        return "vertical"
    if dy < 0.3:
        return "horizontal"
    return "diagonal"

def fit_line_pca(points: np.ndarray):
    mean = points.mean(axis=0)
    _, _, vh = np.linalg.svd(points - mean)
    d = vh[0]
    return mean, d / np.linalg.norm(d)

def local_label_orientation(label, labels, radius=400):
    neighbors = [
        l["point"] for l in labels
        if np.linalg.norm(l["point"] - label["point"]) < radius
    ]
    if len(neighbors) < 2:
        return None
    _, d = fit_line_pca(np.array(neighbors))
    return classify_direction(d)