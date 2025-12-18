import ezdxf
import json
from ezdxf import select
from ezdxf.math import Vec2
from indep_json_1022 import (  # Import all the helper functions
    json_indep_dim, json_indep_line, json_indep_arc, json_indep_circle,
    json_indep_hatch, json_indep_insert, json_indep_leader, json_indep_lwpolyline,
    json_indep_point, json_indep_polyline, json_indep_spline, json_indep_text,
    json_indep_mtext,filter_msp,list_entity_from_msp
)

    
def filtered_entities_json_no_layer_or_group_2(filtered_entities,doc=None):
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
            
            entity_info = {
                'handle': handle,
                'type': entity_type,
                'layer': layer,
                'attributes': {} # Entity-specific attributes go here
            }
            attributes = entity_info['attributes']
            
            # 2. Extract entity-specific attributes
            if entity_type == 'DIMENSION':
                dim_count += 1        
                attributes=json_indep_dim(entity,attributes)

            elif entity_type == 'LINE':
                line_count += 1
                attributes=json_indep_line(entity,attributes)
                
            elif entity_type == 'ARC':
                arc_count += 1
                attributes=json_indep_arc(entity,attributes)
                
            elif entity_type == 'CIRCLE':
                circle_count += 1
                attributes=json_indep_circle(entity,attributes)
                
            elif entity_type == 'HATCH':
                hatch_count += 1
                attributes=json_indep_hatch(entity,attributes)

            elif entity_type == 'INSERT':
                insert_count += 1
                if doc:  # If we have doc, try to extract text
                    attributes = json_indep_insert_with_text(entity, attributes, doc)
                else:  # No doc, just get basic INSERT info
                    attributes = json_indep_insert(entity, attributes)
                
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

def json_indep_insert_with_text(entity, attributes, doc):
    """Extract INSERT attributes, and if it contains text, extract that too."""
    # First get basic INSERT attributes
    attributes = json_indep_insert(entity, attributes)
    
    # Try to extract text from the block
    try:
        block_name = entity.dxf.name
        block = doc.blocks.get(block_name)  # This is why we need doc!
        
        if block:
            # Look for TEXT or MTEXT inside the block
            for sub_entity in block:
                if sub_entity.dxftype() == 'TEXT':
                    attributes['actual_text'] = sub_entity.dxf.text
                    break
                elif sub_entity.dxftype() == 'MTEXT':
                    attributes['actual_text'] = sub_entity.text
                    break
    except Exception as e:
        # If we can't extract text, that's OK - just keep INSERT attributes
        pass
    
    return attributes

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

def exec():
    
    # Export to JSON
    dxf_file_path = r"sepview-8\front.dxf"
    desired_types='LINE ARC CIRCLE DIMENSION HATCH INSERT LEADER  LWPOLYLINE POINT POLYLINE SPLINE TEXT MTEXT'
    
    # FIRST read the DXF file to get doc
    try:
        doc = ezdxf.readfile(dxf_file_path)
        print(f"Loaded DXF document with {len(doc.blocks)} blocks")
    except FileNotFoundError:
        print(f"Error: DXF file not found at {dxf_file_path}")
        return
    
    # Now get filtered entities using your existing functions
    filtered_msp = filter_msp(dxf_file_path, desired_types)
    filtered_entities = list_entity_from_msp(filtered_msp)
    
    
    
    # PASS doc to your processing function
    entities_data = filtered_entities_json_no_layer_or_group_2(filtered_entities, doc)
    
    output_filename = 'info/1204_export-front.json'
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(entities_data, f, indent=4, ensure_ascii=False)

    print(f"Exported {len(entities_data)} entities to {output_filename}")

if __name__=='__main__':
    exec()