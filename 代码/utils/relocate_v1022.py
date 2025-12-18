import json
from typing import Dict, Any, List
"""
bl
BASE_X =   578512.1557570857
BASE_Y = 655203.0339410042"""


def extract_points_from_entity(entity: Dict[str, Any]) -> List[tuple]:
    """Helper to extract points (used only if needed for verification; not for translation)."""
    points = []
    attrs = entity.get('attributes', {})
    for field in ['start', 'end', 'center', 'insert_point', 'location']:
        if field in attrs and isinstance(attrs[field], list) and len(attrs[field]) >= 2:
            points.append((float(attrs[field][0]), float(attrs[field][1])))
    if 'vertices' in attrs and isinstance(attrs['vertices'], list):
        for v in attrs['vertices']:
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                points.append((float(v[0]), float(v[1])))
    if 'control_points' in attrs and isinstance(attrs['control_points'], list):
        for cp in attrs['control_points']:
            if isinstance(cp, (list, tuple)) and len(cp) >= 2:
                points.append((float(cp[0]), float(cp[1])))
    if entity.get('type') == 'INSERT' and 'attributes' in attrs and isinstance(attrs.get('attributes'), list):
        for attr in attrs['attributes']:
            if 'insert' in attr and attr['insert'] is not None and isinstance(attr['insert'], (list, tuple)) and len(attr['insert']) >= 2:
                points.append((float(attr['insert'][0]), float(attr['insert'][1])))
    return points

def translate_point(choice,p: list, dx: float, dy: float) -> list:
    """Translate a point list [x, y, z] in place and return it."""
    if not isinstance(p, list) or len(p) < 2:
        return p  # Invalid point, return as-is
    old_x = float(p[0])
    old_y = float(p[1])
    if choice == "bl":
        p[0] = float(p[0]) - dx
        p[1] = float(p[1]) - dy
    elif choice == "br":
        # Bottom-right origin for section view: flip x for positive y_build leftward, map y_rect to z_build
        # x_build fixed at 0 (section position; adjust if needed to a specific value like plan section x)
        p[0] = 0.0
        p[1] = dx - old_x  # y_build = dx (max_x_rect) - old_x_rect (>=0 from right edge)
        # Ensure z exists; map translated y_rect to z_build
        if len(p) >= 3:
            p[2] = old_y - dy
    elif choice == "ul":
        p[0] = float(p[0]) - dx
        p[1] = float(p[1]) - dy
    elif choice == "ur":
        p[0] = float(p[0]) - dx
        p[1] = float(p[1]) - dy
    else:
        raise ValueError(f"Invalid choice '{choice}'. Use 'bl', 'br', 'ul', or 'ur'.")       
        
    return p

def translate_entity(choice,entity: Dict[str, Any], dx: float, dy: float):
    """Translate all position fields in the entity's 'attributes'."""
    attrs = entity['attributes']
    
    # Simple vector fields
    for field in ['start', 'end', 'center', 'insert_point', 'location']:
        if field in attrs:
            attrs[field] = translate_point(choice,attrs[field], dx, dy)
    
    # List of points: vertices, control_points
    for field in ['vertices', 'control_points']:
        if field in attrs and isinstance(attrs[field], list):
            attrs[field] = [translate_point(choice,v, dx, dy) for v in attrs[field]]
    dimension_fields = [
    'defpoint', 'defpoint2', 'defpoint3', 'defpoint4', 'defpoint5', 'text_midpoint'
    ]

    for field in dimension_fields:
        if field in attrs:
            attrs[field] = translate_point(choice, attrs[field], dx, dy)

    # For INSERT: nested attributes' insert points
    if entity.get('type') == 'INSERT' and 'attributes' in attrs and isinstance(attrs['attributes'], list):
        for attr in attrs['attributes']:
            if 'insert' in attr and attr['insert'] is not None:
                attr['insert'] = translate_point(choice,attr['insert'], dx, dy)

def exec():
    input_file=r"info\1202new\1202_export-topview.json"
    with open(input_file, 'r', encoding='utf-8') as f:
        left_entities = json.load(f)

    # Apply translation to all entities in left.json using hardcoded base
    X_BASE_LEFT=2399.694675989819
    Y_BASE_LEFT=1354.744905680244
    X_BASE_TOP=1787.971342025363
    Y_BASE_TOP=925.6371636171406
    X_BASE_FRONT=2183.970720627192
    Y_BASE_FRONT=701.7315894178118
    choice="bl" 
    for ent in left_entities:
        #translate_entity(choice,ent,X_BASE_TOP, Y_BASE_TOP)
        translate_entity(choice,ent,X_BASE_FRONT, Y_BASE_FRONT)
        #translate_entity(choice,ent,X_BASE_LEFT, Y_BASE_LEFT)
    # Save updated data
    output_file = 'info/1204-translated_top.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(left_entities, f, indent=4, ensure_ascii=False)

    print(f"Processed {len(left_entities)} entities.")
    
    print(f"Saved to {output_file}")

    # Optional: Print sample (first entity)
    if left_entities:
        sample = left_entities[0]
        print("\nSample translated entity:")
        print(json.dumps(sample, indent=2, ensure_ascii=False))

if __name__=='__main__':
    exec()