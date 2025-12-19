import json
from typing import Dict, Any, List, Tuple
import math

def distance(p1: List[float], p2: List[float]) -> float:
    """Euclidean distance between two 2D points."""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def load_entities(filename: str) -> List[Dict[str, Any]]:
    """Load JSON entities from file."""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_circles_and_mtexts(entities: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Separate CIRCLE and MTEXT entities."""
    circles = [ent for ent in entities if ent.get('type') == 'CIRCLE']
    mtexts = [ent for ent in entities if ent.get('type') == 'MTEXT']
    return circles, mtexts

def associate_labels(circles: List[Dict[str, Any]], mtexts: List[Dict[str, Any]], threshold: float = 300.0) -> List[Dict[str, Any]]:
    """
    Associate nearest MTEXT to each CIRCLE if within threshold distance.
    Adds 'associated_label' (text) and 'label_handle' to circle's 'attributes'.
    """
    # Extract positions and texts for quick lookup
    circle_centers = [(i, ent['attributes']['center'][:2], ent) for i, ent in enumerate(circles)]
    mtext_info = [(ent['attributes']['insert_point'][:2], ent['attributes']['text'], ent['handle']) for ent in mtexts]
    
    for _, center, circle_ent in circle_centers:
        min_dist = float('inf')
        nearest_label = None
        nearest_handle = None
        
        for mpos, text, handle in mtext_info:
            dist = distance(center, mpos)
            dx = abs(center[0] - mpos[0])
            dy = abs(center[1] - mpos[1])

            # labels are usually closer vertically than horizontally
           # HARD geometric gate (engineering rule)
            if dy > 80 or dx > 200:
                continue 

            dist = math.hypot(dx, dy)

            if dist < min_dist and dist < threshold:
                min_dist = dist
                nearest_label = text
                nearest_handle = handle
        
        # Add to circle's attributes
        attrs = circle_ent['attributes']
        attrs['associated_label'] = nearest_label
        attrs['label_distance'] = min_dist if nearest_label else None
        attrs['label_handle'] = nearest_handle if nearest_label else None
        
        if nearest_label:
            print(f"Associated CIRCLE {circle_ent['handle']} with label '{nearest_label}' at dist {min_dist:.1f}")
        else:
            print(f"No nearby label for CIRCLE {circle_ent['handle']}")
    
    return circles

def update_json(entities: List[Dict[str, Any]], output_filename: str):
    """Save updated entities back to JSON."""
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(entities, f, indent=4, ensure_ascii=False)
    print(f"Updated entities saved to {output_filename}")

# Usage
if __name__ == "__main__":
    input_file = r"info\1204-translated_top.json"
    output_file = r'info\1204-tagged-circles\1204-top_tagged.json'
    
    entities = load_entities(input_file)
    circles, mtexts = extract_circles_and_mtexts(entities)
    
    print(f"Found {len(circles)} CIRCLEs and {len(mtexts)} MTEXTs.")
    
    tagged_circles = associate_labels(circles, mtexts, threshold=150.0)  # Adjust threshold if needed
    
    # Replace original circles in entities
    circle_handles = {c['handle'] for c in circles}
    for ent in entities:
        if ent['handle'] in circle_handles:
            # Update with tagged version (but since we modified in place, it's already updated)
            pass
    
    update_json(entities, output_file)
    
    # Optional: Print sample tagged circle
    if tagged_circles:
        sample = tagged_circles[0:4]
        print("\nSample tagged CIRCLE:")
        print(json.dumps(sample, indent=2, ensure_ascii=False))