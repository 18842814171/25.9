import ezdxf
from ezdxf import select
from ezdxf.math import Vec2
from typing import Dict, List, Any
import sys
#only dims and texts(why?)
# 定义返回数据结构类型 (enhanced for blocks)
LayerData = Dict[str, Dict[str, List[Dict[str, Any]]]]  # {layer: {group_type: [entities]} } e.g., group_type='direct' or 'block:BlockName'

def extract_entity_metadata(entity: ezdxf.entities.DXFEntity, recurse_blocks: bool = True) -> List[Dict[str, Any]]:
    """
    根据实体类型尝试提取关键元数据。返回列表以支持块内多实体。
    
    参数:
        entity: ezdxf 实体对象。
        recurse_blocks: 是否递归解析INSERT块。
        
    返回:
        包含关键元数据的字典列表（块解析时返回多个）。
    """
    metadata_list = []
    
    entity_type = entity.dxftype()
    metadata = {
        'type': entity_type,
        'handle': entity.dxf.handle,
        'layer': entity.dxf.layer,  # Always include layer
    }

    # Skip TEXT and MTEXT entirely
    if entity_type in ('MLINE'):
        return []

    # Type-specific extractions
    if entity_type == 'DIMENSION':
        try:
            metadata['dim_type'] = entity.dxf.dimtype
            metadata['content'] = entity.dxf.text if entity.dxf.text and entity.dxf.text != "<>" else "N/A"
            metadata['dim_measurement'] = entity.get_measurement() if hasattr(entity, 'get_measurement') else None

            # Always extract block text (for computed dims)
            block = entity.get_geometry_block()
            if block:
                block_texts = [text_ent.dxf.text for text_ent in block.query('TEXT MTEXT') if text_ent.dxf.text]
                if block_texts:
                    metadata['displayed_text'] = '; '.join(block_texts)  # e.g., "300"
                else:
                    metadata['displayed_text'] = "N/A (no text in block)"
                metadata['block_entities_count'] = len(block.query('*'))
            else:
                metadata['displayed_text'] = "N/A (no block)"

            # If content is N/A but displayed exists, prioritize displayed
            if metadata['content'] == "N/A" and metadata['displayed_text'] != "N/A":
                metadata['content'] = metadata['displayed_text']  # Merge for consistency
        except Exception as e:
                metadata['parse_error'] = f"Dimension parse failed: {e}"
               

    elif entity_type == 'LINE':
        metadata['start'] = tuple(entity.dxf.start.xyz)
        metadata['end'] = tuple(entity.dxf.end.xyz)

    elif entity_type == 'ARC':
        metadata['center'] = tuple(entity.dxf.center.xyz)
        metadata['radius'] = entity.dxf.radius
        metadata['start_angle'] = entity.dxf.start_angle
        metadata['end_angle'] = entity.dxf.end_angle

    elif entity_type == 'CIRCLE':
        metadata['center'] = tuple(entity.dxf.center.xyz)
        metadata['radius'] = entity.dxf.radius

    elif entity_type == 'HATCH':
        metadata['pattern_name'] = entity.dxf.pattern_name
        metadata['scale'] = entity.dxf.scale
        metadata['angle'] = entity.dxf.angle
        try:
            metadata['boundary_paths_count'] = len(entity.paths)
        except:
            metadata['boundary_paths_count'] = 0

    elif entity_type == 'LEADER':
        try:
            metadata['points'] = [tuple(p.xyz) for p in entity.dxf.vertexes] if hasattr(entity.dxf, 'vertexes')and entity.dxf.vertexes else []
        except:
            metadata['points'] = []

    elif entity_type == 'POINT':
        metadata['location'] = tuple(entity.dxf.location.xyz)

    elif entity_type == 'SPLINE':
        metadata['degree'] = entity.dxf.degree
        try:
            metadata['control_points'] = [tuple(p.xyz) for p in entity.control_points]
            metadata['fit_points_count'] = len(entity.fit_points) if hasattr(entity, 'fit_points') else 0
        except:
            metadata['control_points'] = []

    elif entity_type == 'LWPOLYLINE':
        metadata['closed'] = entity.closed
        try:
            points = [(p.x, p.y, p.z) for p in entity.points()]
            metadata['vertices'] = points[:5]  # Limit to first 5 for brevity
            metadata['vertex_count'] = len(points)
        except:
            metadata['vertex_count'] = 0

    elif entity_type == 'POLYLINE':
        metadata['closed'] = entity.closed
        metadata['vertex_count'] = len(list(entity.points()))

    elif entity_type == 'INSERT':
        metadata['insert'] = tuple(entity.dxf.insert.xyz)
        metadata['block_name'] = entity.dxf.name
        metadata['rotation'] = entity.dxf.rotation
        if recurse_blocks:
            try:
                # Resolve and extract block contents
                block_def = entity.block()
                sub_entities = []
                for sub_entity in block_def:
                    sub_metadata = extract_entity_metadata(sub_entity, recurse_blocks=False)  # Avoid infinite recursion
                    sub_entities.extend(sub_metadata)
                if sub_entities:
                    metadata['sub_entities'] = sub_entities  # Nested list of block contents
                    metadata_list.extend(sub_entities)  # Flatten to main list for grouping
            except Exception as e:
                metadata['parse_error'] = f"Block resolution failed: {e}"
        metadata_list.append(metadata)  # Add the INSERT itself

    elif entity_type == 'OLE2FRAME':
        metadata['insert'] = tuple(entity.dxf.insert.xyz) if hasattr(entity.dxf, 'insert') else None
        metadata['source_filename'] = entity.dxf.source_filename if hasattr(entity.dxf, 'source_filename') else "N/A"

    # Default for unhandled types (e.g., future expansions)
    else:
        metadata['note'] = f"Unhandled type: {entity_type} - basic info only"

    if entity_type not in ('INSERT',):  # For non-INSERT, add to list
        metadata_list.append(metadata)

    return metadata_list  # Return list to support multi-entity from blocks

def define_window_by_corner_and_print(window_corners: tuple):
    # Define window
    corner1, corner2 = Vec2(window_corners[0]), Vec2(window_corners[1])
    window = select.Window(corner1, corner2)
    extmin = Vec2((min(corner1.x, corner2.x), min(corner1.y, corner2.y)))
    extmax = Vec2((max(corner1.x, corner2.x), max(corner1.y, corner2.y)))
    
    print(f"--- Window {extmin} to {extmax} ---")
    return window


from typing import Iterable, Any
def filter_msp(dxf_path:str,desired_types:str)-> Iterable[Any]:
    try:
        doc = ezdxf.readfile(dxf_path)
    except FileNotFoundError:
        print(f"错误: 文件未找到于 {dxf_path}")
        return {}
    except ezdxf.DXFStructureError as e:
        print(f"错误: DXF 文件结构错误: {e}")
        return {}

    msp = doc.modelspace()
    filtered_msp = msp.query(desired_types)
    
    return filtered_msp


from typing import Optional, Iterable
from ezdxf.query import EntityQuery
from ezdxf.entities import DXFEntity
from ezdxf import select
def list_entity_from_msp(
    msp: Iterable[DXFEntity] | EntityQuery,
    window: Optional[tuple[tuple[float, float], tuple[float, float]]] = None
) -> list[DXFEntity]:
    """Return entities in the given modelspace, optionally filtered by a bounding window."""
    
    if window is not None:
        all_entities_in_window = select.bbox_inside(window, msp)
        filtered_entities = list(all_entities_in_window)
    else:
        filtered_entities = list(msp)  # if no window, just take all
    
    return filtered_entities

def extract_entities_in_window_by_layer(dxf_path: str, window_corners: tuple) -> LayerData:
    """
    从 DXF 文件的 Modelspace 中提取窗口内的实体及其元数据，按图层和块分组。
    
    参数:
        dxf_path: DXF 文件路径。
        window_corners: ((x1,y1), (x2,y2)) 窗口对角点。
        
    返回:
        嵌套字典：{layer: {group: [entities]}} where group='direct' or 'block:BlockName'
    """
    desired_types='LINE ARC CIRCLE DIMENSION HATCH INSERT LEADER  LWPOLYLINE POINT POLYLINE SPLINE TEXT MTEXT'
    filtered_msp = filter_msp(dxf_path,desired_types)
    # Select all entities in window (bbox_inside handles iteration safely)
    window=define_window_by_corner_and_print(window_corners)
    
    filtered_entities = list_entity_from_msp(filtered_msp,window)
    
    # Initialize grouped data
    layer_data: LayerData = {}

    # Process filtered entities
    for entity in filtered_entities:
        metadata_list = extract_entity_metadata(entity, recurse_blocks=True)
        layer_name = entity.dxf.layer
        
        if layer_name not in layer_data:
            layer_data[layer_name] = {}
        
        for metadata in metadata_list:
            group_key = 'direct' if 'block_name' not in metadata else f"block:{metadata['block_name']}"
            if group_key not in layer_data[layer_name]:
                layer_data[layer_name][group_key] = []
            layer_data[layer_name][group_key].append(metadata)
    
    return layer_data

# -------------------- Usage --------------------
def exec():
    dxf_file_path = r"D:\大创\25.9\图纸\dxf\附图8：炮眼布置及装药结构图.dxf"
    window_corners = ((583500, 658300), (586000, 654300))  # 右上角
    #window_corners = ((578300, 658330), (583200, 654700)) #左上角
    #output_file='info/e8-1019-左上角.txt'
    output_file='info/e8-1019-右上角.txt'
    original_stdout = sys.stdout
    with open(output_file, 'w', encoding='utf-8') as f:
        sys.stdout = f
        
        # Extract from window
        all_layer_data = extract_entities_in_window_by_layer(dxf_file_path, window_corners)

        # Print results
        if all_layer_data:
            total_entities = sum(sum(len(group) for group in layer.values()) for layer in all_layer_data.values())
            print(f"成功从文件 '{dxf_file_path}' 的窗口中提取 {total_entities} 个实体（排除MLINE）。")
            
            for layer, groups in all_layer_data.items():
                print(f"\n图层: '{layer}'")
                for group_key, entities in groups.items():
                    print(f"  分组: {group_key} (共 {len(entities)} 个实体)")
                    # Print first 5 entities' details
                    for i, entity_data in enumerate(entities):
                        print(f"    [{i+1}] Type: {entity_data.get('type')}, Handle: {entity_data.get('handle')}")
                        if 'dim_measurement' in entity_data:
                            print(f"        Dim Measurement: {entity_data['dim_measurement']}, Type: {entity_data.get('dim_type', 'N/A')}")
                        if 'content' in entity_data and entity_data['content'] != 'N/A':
                            print(f"        Content: \"{entity_data['content']}\"")
                        if 'displayed_text' in entity_data and entity_data['displayed_text'] != 'N/A (no text in block)':
                            print(f"        Displayed Text: {entity_data['displayed_text']}")
                        if 'center' in entity_data:
                            print(f"        Center: {entity_data['center']}, Radius: {entity_data.get('radius', 'N/A')}")
                        if 'start' in entity_data:
                            print(f"        Start: {entity_data['start']}, End: {entity_data.get('end', 'N/A')}")
                        
                        if 'sub_entities' in entity_data:
                            print(f"        Sub-Entities Count: {len(entity_data['sub_entities'])}")
                        if 'vertex_count' in entity_data:
                            print(f"        Vertex Count: {entity_data['vertex_count']}")
                        else:
                            print(f"        Key Attrs: { {k: v for k, v in entity_data.items() if k not in ['type', 'handle', 'layer'] } }")
        else:
            print("未找到窗口内实体。")

    sys.stdout = original_stdout
    print(f"输出已保存到{output_file} 文件中")

if __name__=='__main__':
    exec()
"""
Primary types (base 0-6):
Value   Meaning
0   Rotated/arbitrary linear
1   Aligned linear
2   Angular
3   Diameter
4   Radius
5   Angular 3-point
6   Ordinate

Flags added to base:
Bit Value   Meaning
32  Anonymous block (dim-specific)
64  Ordinate subtype (X-type if set)
128 User-defined text position
Your 32 = base 0 + flag 32 (common for linear dims in recent DXFs)."""