import ezdxf
from ezdxf import select
from ezdxf.math import Vec2
from typing import Dict, List, Any
import json
import re
# 定义返回数据结构类型 (enhanced for blocks)
LayerData = Dict[str, Dict[str, List[Dict[str, Any]]]]  # {layer: {group_type: [entities]} } e.g., group_type='direct' or 'block:BlockName'
from entities_1019 import filter_msp, list_entity_from_msp

def decode_mtext_escapes(s: str) -> str:
    if not s:
        return s

    def repl(match):
        codepoint = int(match.group(1), 16)
        return chr(codepoint)

    return re.sub(r'\\U\+([0-9A-Fa-f]{4})', repl, s)
    
def json_indep_dim(dim, attributes):
    measurement = dim.get_measurement() if hasattr(dim, 'get_measurement') else 'N/A'
    attributes['measurement'] = measurement
    attributes['text'] = dim.dxf.text
    attributes['dimtype'] = dim.dxf.dimtype
    block = dim.get_geometry_block()
    block_texts = []

    if block:
        for e in block:
            if e.dxftype() == 'TEXT':
                block_texts.append(e.dxf.text)

            elif e.dxftype() == 'MTEXT':
                raw = e.text  # this is a string with DXF escapes
                block_texts.append(decode_mtext_escapes(raw))

        attributes['block_texts'] = block_texts
    else:
        attributes['block_texts'] = None

    return attributes

def json_indep_line(entity, attributes, desired_linetypes=None, desired_layers=None):
    attributes['start'] = list(entity.dxf.start.xyz)
    attributes['end'] = list(entity.dxf.end.xyz)
    attributes['linetype'] = entity.dxf.linetype  # NEW
    
    # Apply filters
    if desired_linetypes and entity.dxf.linetype not in desired_linetypes:
        return None
    if desired_layers and entity.dxf.layer not in desired_layers:
        return None
        
    return attributes

def json_indep_arc(entity,attributes):
    attributes['center'] = list(entity.dxf.center.xyz)
    attributes['radius'] = entity.dxf.radius
    attributes['start_angle'] = entity.dxf.start_angle
    attributes['end_angle'] = entity.dxf.end_angle
    return attributes

def json_indep_circle(entity,attributes):
    attributes['center'] = list(entity.dxf.center.xyz)
    attributes['radius'] = entity.dxf.radius
    return attributes

def json_indep_hatch(entity,attributes):
    attributes['pattern_name'] = entity.dxf.pattern_name
    attributes['solid_fill'] = entity.dxf.solid_fill
    attributes['num_boundary_paths'] = len(entity.paths) if hasattr(entity, 'paths') and entity.paths else 0
    attributes['scale'] = entity.dxf.scale
    attributes['angle'] = entity.dxf.angle
    return attributes            

def json_indep_insert(entity,attributes):
    attributes['block_name'] = entity.dxf.name
    attributes['insert_point'] = list(entity.dxf.insert.xyz)
    attributes['scale'] = list(entity.dxf.scale) if hasattr(entity.dxf, 'scale') else [1,1,1]
    attributes['rotation'] = entity.dxf.rotation
    return attributes

def json_indep_leader(entity,attributes):
    attributes['vertices'] = [list(v.xyz) for v in entity.vertices]
    return attributes

def json_indep_lwpolyline(entity,attributes):
    # Store points as a list of (x, y) tuples or lists
    attributes['vertices'] = [list(v[:2]) for v in entity.get_points('xy')]
    attributes['closed'] = entity.closed
    return attributes

def json_indep_point(entity,attributes):
    attributes['location'] = list(entity.dxf.location.xyz)
    return attributes

def json_indep_polyline(entity,attributes):
    # 3D polyline vertices
    attributes['vertices'] = [list(v.dxf.location.xyz) for v in entity.vertices]
    attributes['closed'] = entity.closed
    return attributes
                
def json_indep_spline(entity,attributes):
    attributes['control_points'] = [list(p.xyz) for p in entity.control_points]
    attributes['degree'] = entity.dxf.degree
    knots = getattr(entity, 'knots', None)
    if knots:
         attributes['knots'] = list(knots)
    return attributes

def json_indep_text(entity,attributes):
    attributes['text'] = entity.dxf.text
    attributes['insert_point'] = list(entity.dxf.insert.xyz)
    attributes['height'] = entity.dxf.height
    attributes['rotation'] = entity.dxf.rotation
    return attributes

def json_indep_mtext(entity,attributes):
    attributes['text'] = entity.text
    attributes['insert_point'] = list(entity.dxf.insert.xyz)
    attributes['char_height'] = entity.dxf.char_height
    attributes['rotation'] = entity.dxf.rotation
     
    return attributes
    
def filtered_entities_json_no_layer_or_group(filtered_entities,doc=None,desired_linetypes=None,desired_layers=None):
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
                attributes = json_indep_line(entity, attributes, desired_linetypes, desired_layers)
                if attributes is None:
                    continue  # Skip this entity
                line_count += 1
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
    # Export to JSON
    dxf_file_path = r"D:\大创\25.9\代码\sepview-8\front.dxf"
    #window_corners = ((583500, 658300), (586000, 654300))  # 右上角
    desired_types='LINE'

    filtered_msp = filter_msp(dxf_file_path,desired_types)# Select all entities in window (bbox_inside handles iteration safely)
    #window=define_window_by_corner_and_print(window_corners)
    filtered_entities = list_entity_from_msp(filtered_msp)
    output_filename = 'info/0104groupfront/testlines_export-front-indep.json'

    entities_data=filtered_entities_json_no_layer_or_group(filtered_entities)
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(entities_data, f, indent=4, ensure_ascii=False)

    print(f"Exported {len(entities_data)} entities to {output_filename}")

if __name__=='__main__':
    exec()