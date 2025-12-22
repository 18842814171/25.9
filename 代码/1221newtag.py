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

def associate_labels(circles: List[Dict[str, Any]], mtexts: List[Dict[str, Any]], threshold: float = 150.0) -> List[Dict[str, Any]]:
    # Filter for numeric labels only to avoid matching configuration text
    numeric_labels = [m for m in mtexts if m.get('attributes', {}).get('text', '').isdigit()]
    
    for circle_ent in circles:
        c_pos = circle_ent['attributes'].get('center')
        best_label = None
        min_dist = threshold
        
        for label_ent in numeric_labels:
            l_pos = label_ent['attributes'].get('insert_point')
            dist = distance(c_pos, l_pos)
            
            if dist < min_dist:
                min_dist = dist
                best_label = label_ent
        
        if best_label:
            circle_ent['attributes']['associated_label'] = best_label['attributes']['text']
            circle_ent['attributes']['label_handle'] = best_label['handle']
            print(f"Tagged {circle_ent['handle']} -> '{best_label['attributes']['text']}' (Dist: {min_dist:.1f})")
            
    return circles

def update_json(entities: List[Dict[str, Any]], output_filename: str):
    """Save updated entities back to JSON."""
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(entities, f, indent=4, ensure_ascii=False)
    print(f"\nUpdated entities saved to {output_filename}")

if __name__ == "__main__":
    # Ensure these paths match your environment
    input_file = r"info\1202new\1202_export-topview.json" 
    output_file = r"info\1221rewrite\1221-top_tagged_2.json"
    
    entities = load_entities(input_file)
    circles, mtexts = extract_circles_and_mtexts(entities)
    
    print(f"Processing {len(circles)} CIRCLEs and {len(mtexts)} MTEXTs...")
    
    # Using a larger threshold to ensure all circles are captured
    tagged_circles = associate_labels(circles, mtexts, threshold=500.0)
    
    update_json(entities, output_file)