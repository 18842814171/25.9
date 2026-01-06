import ezdxf
from ezdxf import select
from ezdxf.math import Vec2
from typing import Dict, List, Any
import json

# 定义返回数据结构类型 (enhanced for blocks)
LayerData = Dict[str, Dict[str, List[Dict[str, Any]]]]  # {layer: {group_type: [entities]} } e.g., group_type='direct' or 'block:BlockName'
from utils.indep_json_1226 import json_indep_dim,json_indep_line,json_indep_arc,json_indep_circle,json_indep_hatch,json_indep_insert,json_indep_leader,json_indep_lwpolyline,json_indep_point,json_indep_polyline,json_indep_spline,json_indep_text,json_indep_mtext,filtered_entities_json_no_layer_or_group
from entities_1019 import define_window_by_corner_and_print, filter_msp,list_entity_from_msp,extract_entities_in_window_by_layer
import entities_1019
def extract_entity_attributes(entity: ezdxf.entities.DXFEntity, recurse_blocks: bool = True) -> List[Dict[str, Any]]:
    """
    根据实体类型尝试提取关键元数据。返回列表以支持块内多实体。
    
    参数:
        entity: ezdxf 实体对象。
        recurse_blocks: 是否递归解析INSERT块。
        
    返回:
        包含关键元数据的字典列表（块解析时返回多个）。
    """
    attributes_list = []
    
    entity_type = entity.dxftype()
    attributes = {
        'type': entity_type,
        'handle': entity.dxf.handle,
        'layer': entity.dxf.layer,  # Always include layer
    }

    # Skip MLINE entirely, handle TEXT/MTEXT separately
    if entity_type in ('MLINE'):
        return []
    
    if entity_type == 'DIMENSION':
              
        attributes=json_indep_dim(entity,attributes)

    elif entity_type == 'LINE':
        
        attributes=json_indep_line(entity,attributes)
        
    elif entity_type == 'ARC':
       
        attributes=json_indep_arc(entity,attributes)
        
    elif entity_type == 'CIRCLE':
        
        json_indep_circle(entity,attributes)
        
    elif entity_type == 'HATCH':
        
        attributes=json_indep_hatch(entity,attributes)

    elif entity_type == 'INSERT':
       
        attributes=json_indep_insert(entity,attributes)
        
    elif entity_type == 'LEADER':
        
        attributes=json_indep_leader(entity,attributes)
        
    elif entity_type == 'LWPOLYLINE':
        
        attributes=json_indep_lwpolyline(entity,attributes)
        
    elif entity_type == 'POINT':
        
        attributes=json_indep_point(entity,attributes)
        
    elif entity_type == 'POLYLINE':
        
        attributes=json_indep_polyline(entity,attributes)

    elif entity_type == 'SPLINE':
        
        attributes=json_indep_spline(entity,attributes)

    elif entity_type == 'TEXT':
                    
        attributes=json_indep_text(entity,attributes)

    elif entity_type == 'MTEXT':
        
        attributes=json_indep_mtext(entity,attributes)

    elif entity_type == 'INSERT':
        attributes=json_indep_insert(entity,attributes)
        if recurse_blocks:
            try:
                # Resolve and extract block contents
                block_def = entity.block()
                sub_entities = []
                for sub_entity in block_def:
                    sub_attributes = extract_entity_attributes(sub_entity, recurse_blocks=False)  # Avoid infinite recursion
                    sub_entities.extend(sub_attributes)
                if sub_entities:
                    attributes['sub_entities'] = sub_entities  # Nested list of block contents
                    attributes_list.extend(sub_entities)  # Flatten to main list for grouping
            except Exception as e:
                attributes['parse_error'] = f"Block resolution failed: {e}"
        attributes_list.append(attributes)  # Add the INSERT itself

    elif entity_type == 'OLE2FRAME':
        attributes['insert'] = tuple(entity.dxf.insert.xyz) if hasattr(entity.dxf, 'insert') else None
        attributes['source_filename'] = entity.dxf.source_filename if hasattr(entity.dxf, 'source_filename') else "N/A"

    # Default for unhandled types (e.g., future expansions)
    else:
        attributes['note'] = f"Unhandled type: {entity_type} - basic info only"

    if entity_type not in ('INSERT',):  # For non-INSERT, add to list
        attributes_list.append(attributes)

    return attributes_list  # Return list to support multi-entity from blocks


def prepare_json_from_all_layer_data(dxf_path,window_corners):
    all_layer_data=extract_entities_in_window_by_layer(dxf_path,window_corners)
    json_data = {
        "total_entities": sum(sum(len(group) for group in layer.values()) for layer in all_layer_data.values()),
        "layers": []
    }

    for layer_name, groups in all_layer_data.items():
        layer_info = {
            "layer": layer_name,
            "groups": []
        }
        
        for group_key, entities in groups.items():
            group_info = {
                "group": group_key,
                "entities": []
            }
            
            for entity_data in entities:
                # Format entity for JSON output
                entity_json = {
                    "handle": entity_data.get('handle'),
                    "type": entity_data.get('type'),
                    "layer": entity_data.get('layer'),
                    "group": group_key,
                    "attributes": {}
                }
                
                # Add type-specific attributes (avoid overlapping with base fields)
                attrs = entity_json["attributes"]
                
                # Common attributes
                if 'color' in entity_data:
                    attrs['color'] = entity_data['color']
                if 'linetype' in entity_data:
                    attrs['linetype'] = entity_data['linetype']
                
                # Type-specific attributes
                entity_type = entity_data.get('type')
                
                if entity_type == 'DIMENSION':
                    if 'dim_measurement' in entity_data:
                        attrs['measurement'] = entity_data['dim_measurement']
                    if 'content' in entity_data and entity_data['content'] != 'N/A':
                        attrs['text'] = entity_data['content']
                    if 'dim_type' in entity_data:
                        attrs['dim_type'] = entity_data['dim_type']
                        
                if entity_type in ['LINE']:
                    if 'start' in entity_data:
                        attrs['start'] = entity_data['start']
                    if 'end' in entity_data:
                        attrs['end'] = entity_data['end']
                        
                elif entity_type in ['ARC', 'CIRCLE']:
                    if 'center' in entity_data:
                        attrs['center'] = entity_data['center']
                    if 'radius' in entity_data:
                        attrs['radius'] = entity_data['radius']
                    if entity_type == 'ARC':
                        if 'start_angle' in entity_data:
                            attrs['start_angle'] = entity_data['start_angle']
                        if 'end_angle' in entity_data:
                            attrs['end_angle'] = entity_data['end_angle']
                            
                elif entity_type in ['LWPOLYLINE', 'POLYLINE']:
                    if 'vertex_count' in entity_data:
                        attrs['vertex_count'] = entity_data['vertex_count']
                    if 'closed' in entity_data:
                        attrs['closed'] = entity_data['closed']
                        
                elif entity_type == 'HATCH':
                    if 'pattern_name' in entity_data:
                        attrs['pattern_name'] = entity_data['pattern_name']
                    if 'boundary_paths_count' in entity_data:
                        attrs['boundary_paths_count'] = entity_data['boundary_paths_count']
                        
                elif entity_type == 'SPLINE':
                    if 'degree' in entity_data:
                        attrs['degree'] = entity_data['degree']
                    if 'fit_points_count' in entity_data:
                        attrs['fit_points_count'] = entity_data['fit_points_count']
                        
                elif entity_type == 'INSERT':
                    if 'block_name' in entity_data:
                        attrs['block_name'] = entity_data['block_name']
                    if 'sub_entities' in entity_data:
                        attrs['sub_entities_count'] = len(entity_data['sub_entities'])
                elif entity_type in ['TEXT', 'MTEXT']:
                    if 'text_content' in entity_data:
                        attrs['text_content'] = entity_data['text_content']        
                # Add any other attributes not already included
                for key, value in entity_data.items():
                    if key not in ['handle', 'type', 'layer', 'group'] and key not in attrs:
                        attrs[key] = value
                
                group_info["entities"].append(entity_json)
            
            layer_info["groups"].append(group_info)
        
        json_data["layers"].append(layer_info)
    print(json.dumps(json_data, ensure_ascii=False, indent=2))
    return json_data
# -------------------- Usage --------------------
dxf_file_path = r"D:\大创\25.9\图纸\dxf\附图8：炮眼布置及装药结构图.dxf"
window_corners = ((583500, 658300), (586000, 654300))  # 右上角
output_file='info/e8-1019-右上角.json'
window_corners = ((578300, 658330), (583200, 654700)) #左上角
#output_file='info/e8-1019-左上角.json'


import sys
# Write JSON output using the original stdout approach
original_stdout = sys.stdout
with open(output_file, 'w', encoding='utf-8') as f:
    sys.stdout = f
    json_data=prepare_json_from_all_layer_data(dxf_file_path,window_corners)
sys.stdout = original_stdout
print(f"输出已保存到 {output_file} 文件中")
print(f"总共提取了 {json_data['total_entities']} 个实体")