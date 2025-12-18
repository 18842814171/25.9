import ezdxf
import json
from ezdxf import select
from ezdxf.math import Vec2
from indep_json_1022 import (  # Import all the helper functions
    json_indep_dim, json_indep_line, json_indep_arc, json_indep_circle,
    json_indep_hatch, json_indep_insert, json_indep_leader, json_indep_lwpolyline,
    json_indep_point, json_indep_polyline, json_indep_spline, json_indep_text,
    json_indep_mtext
)


def json_dim_pos_enhanced(dim,attributes):
    # First get basic dimension data from 1022
    attributes = json_indep_dim(dim, attributes)
    # ADD THESE CRITICAL GROUP CODES FOR ENTITY LINKING:
    # Definition points that snap to geometry
    if hasattr(dim.dxf, 'defpoint'):  # Point 10
        attributes['defpoint'] = list(dim.dxf.defpoint.xyz)
    if hasattr(dim.dxf, 'defpoint2'):  # Point 13 - often snaps to entity
        attributes['defpoint2'] = list(dim.dxf.defpoint2.xyz)
    if hasattr(dim.dxf, 'defpoint3'):  # Point 14 - often snaps to entity  
        attributes['defpoint3'] = list(dim.dxf.defpoint3.xyz)
    if hasattr(dim.dxf, 'defpoint4'):  # Point 15 - for some dimension types
        attributes['defpoint4'] = list(dim.dxf.defpoint4.xyz)
    if hasattr(dim.dxf, 'defpoint5'):  # Point 16 - for some dimension types
        attributes['defpoint5'] = list(dim.dxf.defpoint5.xyz)
    if hasattr(dim.dxf, 'defpoint6'):  # Point 17
        attributes['defpoint6'] = list(dim.dxf.defpoint6.xyz)
    # Text position
    if hasattr(dim.dxf, 'text_midpoint'):
        attributes['text_midpoint'] = list(dim.dxf.text_midpoint.xyz)
    # Dimension type info
    attributes['dimtype'] = dim.dxf.dimtype
    
    return attributes

def entities_data_info(filtered_entities,group_lookup):
    entities_data = []
    # Initialize counts
    line_count, arc_count, circle_count, dim_count, hatch_count, insert_count, leader_count, lwpline_count, point_count, polyline_count, spline_count, text_count, mtext_count = 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0

    # Iterate over selected entities
    for entity in filtered_entities:
        try:
            entity_type = entity.dxftype()
            handle = entity.dxf.handle
            
            # 1. Extract common information
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0'
            group_name = group_lookup.get(handle, None) # Look up group name
            
            entity_info = {
                'handle': handle,
                'type': entity_type,
                'layer': layer,
                'group': group_name,
                'attributes': {} # Entity-specific attributes go here
            }
            attributes = entity_info['attributes']
            
            # 2. Extract entity-specific attributes
            if entity_type == 'DIMENSION':
                dim_count += 1
                attributes=json_dim_pos_enhanced(entity,attributes)
                
                
            elif entity_type == 'LINE':
                line_count += 1
                attributes = json_indep_line(entity, attributes)
                
            elif entity_type == 'ARC':
                arc_count += 1
                attributes = json_indep_arc(entity, attributes)
                
            elif entity_type == 'CIRCLE':
                circle_count += 1
                attributes = json_indep_circle(entity, attributes)
            
            elif entity_type == 'HATCH':
                hatch_count += 1
                attributes=json_indep_hatch(entity,attributes)

            elif entity_type == 'INSERT':
                insert_count += 1
                attributes=json_indep_insert(entity,attributes)
                
            elif entity_type == 'LEADER':
                leader_count += 1
                attributes=json_indep_leader(entity,attributes)
                
            elif entity_type == 'LWPOLYLINE':
                lwpline_count += 1
                attributes=json_indep_lwpolyline(entity,attributes)
                
            elif entity_type == 'POINT':
                point_count += 1
                attributes=json_indep_point(entity,attributes)
                
            elif entity_type == 'POLYLINE':
                polyline_count += 1
                attributes=json_indep_polyline(entity,attributes)

            elif entity_type == 'SPLINE':
                spline_count += 1
                attributes=json_indep_spline(entity,attributes)

            elif entity_type == 'TEXT':
                text_count += 1                
                attributes=json_indep_text(entity,attributes)

            elif entity_type == 'MTEXT':
                mtext_count += 1
                attributes=json_indep_mtext(entity,attributes)

            
            # Append the structured info
            entities_data.append(entity_info)
            
        except Exception as e:
            print(f"Error on {entity.dxftype()} {handle}: {e} (skipping)")

    print(f"\n--- Summary ---")
    print(f"Processed: {line_count} LINEs, {arc_count} ARCs, {circle_count} CIRCLEs, {dim_count} DIMs, {hatch_count} HATCHes, {insert_count} INSERTs, {leader_count} LEADERs, {lwpline_count} LWPOLYLINEs, {point_count} POINTs, {polyline_count} POLYLINEs, {spline_count} SPLINEs, {text_count} TEXTs, {mtext_count} MTEXTs")

    return entities_data

def exec():
    filename = r"sepview-8\front.dxf"
    try:
        doc = ezdxf.readfile(filename)
    except FileNotFoundError:
        print(f"Error: DXF file not found at {filename}.")

    msp = doc.modelspace()

    # Select entities
    desired_types = 'LINE ARC CIRCLE DIMENSION HATCH INSERT LEADER LWPOLYLINE POINT POLYLINE SPLINE TEXT MTEXT'
    filtered_msp = msp.query(desired_types)
    filtered_entities = list(filtered_msp)

    # DEBUG: Specifically check for MTEXT
    mtexts = [e for e in filtered_entities if e.dxftype() == 'MTEXT']
    print(f"DEBUG: Found {len(mtexts)} MTEXT entities")
    for mtext in mtexts:
        print(f"DEBUG MTEXT: Handle: {mtext.dxf.handle}, Text: {repr(mtext.text)}")

    # Pre-process group information
    group_lookup = {}
    for group in doc.groups:
        for entity_ref in group:
            if hasattr(entity_ref, 'dxf') and hasattr(entity_ref.dxf, 'handle'):
                group_lookup[entity_ref.dxf.handle] = group.dxf.name
    entities_data = entities_data_info(filtered_entities,group_lookup)
    output_filename = 'info/1204_export-front.json'
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(entities_data, f, indent=4, ensure_ascii=False)

    print(f"Exported {len(entities_data)} entities to {output_filename}")

if __name__=='__main__':
    exec()