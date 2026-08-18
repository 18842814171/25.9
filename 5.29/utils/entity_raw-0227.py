import argparse
import ezdxf
import json
from pathlib import Path
from indep_json_1226 import (
    json_indep_line,
    json_indep_arc,
    json_indep_circle,
    json_indep_hatch,
    json_indep_insert,
    json_indep_leader,
    json_indep_lwpolyline,
    json_indep_point,
    json_indep_polyline,
    json_indep_spline,
    json_indep_text,
    json_indep_mtext,
    filter_msp,
    list_entity_from_msp,
    decode_mtext_escapes
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_export_config(config_path: Path | str) -> dict:
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def resolve_output_filename(template: str, dxf_path: Path) -> str:
    """将 output_filename 模板中的占位符替换为 DXF 相关信息。"""
    dxf_name = dxf_path.stem
    return (
        template.replace("{dxf_name}", dxf_name)
        .replace("{dxf_stem}", dxf_name)
        .replace("{dxf_file_path}", dxf_path.as_posix())
    )


def _resolve_path(raw: str | Path, base: Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = base / path
    return path


def resolve_export_settings(config: dict, mode: str | None = None) -> dict:
    export_mode = (mode or config.get("mode", "line")).lower()
    if export_mode not in {"line", "text", "facility", "legend"}:
        raise ValueError(
            f"mode 必须是 'line'、'text'、'facility' 或 'legend'，当前为: {export_mode}"
        )
    if export_mode not in config:
        raise ValueError(f"配置缺少 mode 段: {export_mode}")

    dxf_path = _resolve_path(config["dxf_file_path"], PROJECT_ROOT)
    section = config[export_mode]
    raw_types = section.get("entity_types", None)
    if raw_types is None or raw_types == []:
        desired_types = None
    else:
        desired_types = [str(t) for t in raw_types]
        if not desired_types:
            desired_types = None
    if "layers" not in section or not section.get("layers"):
        raise ValueError(f"配置缺少非空字段 {export_mode}.layers（按图层子串提取）")
    desired_layers = section["layers"]

    output_filename = resolve_output_filename(section["output_filename"], dxf_path)
    output_path = PROJECT_ROOT / output_filename

    return {
        "mode": export_mode,
        "dxf_file_path": str(dxf_path),
        "desired_types": desired_types,
        "desired_layers": desired_layers,
        "output_path": output_path,
    }


# =========================
# RAW GEOMETRY EXTRACTION
# =========================

def extract_entities_raw(filtered_entities, doc=None):
    """
    Extract DXF entities WITHOUT exploding geometry.
    Preserve drafting intent for view detection.
    """
    entities_data = []

    counts = {
        'LINE': 0,
        'ARC': 0,
        'CIRCLE': 0,
        'HATCH': 0,
        'INSERT': 0,
        'LEADER': 0,
        'LWPOLYLINE': 0,
        'POINT': 0,
        'POLYLINE': 0,
        'SPLINE': 0,
        'TEXT': 0,
        'MTEXT': 0,
    }
        # Debug: Track coordinate ranges
    coord_stats = {
        'min_x': float('inf'),
        'max_x': float('-inf'),
        'min_y': float('inf'),
        'max_y': float('-inf'),
        'entities_with_large_coords': []
    }
    for entity in filtered_entities:
        try:
            entity_type = entity.dxftype()
            handle = entity.dxf.handle
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0'

            entity_info = {
                'handle': handle,
                'type': entity_type,
                'layer': layer,
                'attributes': {}
            }

            attr = entity_info['attributes']

            if entity_type == 'LINE':
                attr = json_indep_line(entity, attr)
                if attr is None:
                    continue
                counts['LINE'] += 1
                                # Track coordinates
                for point in ['start', 'end']:
                    if point in attr:
                        x, y = attr[point][0], attr[point][1]
                        coord_stats['min_x'] = min(coord_stats['min_x'], x)
                        coord_stats['max_x'] = max(coord_stats['max_x'], x)
                        coord_stats['min_y'] = min(coord_stats['min_y'], y)
                        coord_stats['max_y'] = max(coord_stats['max_y'], y)
                        if abs(x) > 1000000 or abs(y) > 1000000:
                            coord_stats['entities_with_large_coords'].append(f"LINE {handle}: ({x:.2f}, {y:.2f})")

            elif entity_type == 'ARC':
                attr = json_indep_arc(entity, attr)
                counts['ARC'] += 1

            elif entity_type == 'CIRCLE':
                attr = json_indep_circle(entity, attr)
                counts['CIRCLE'] += 1
                if 'center' in attr:
                    x, y = attr['center'][0], attr['center'][1]
                    coord_stats['min_x'] = min(coord_stats['min_x'], x)
                    coord_stats['max_x'] = max(coord_stats['max_x'], x)
                    coord_stats['min_y'] = min(coord_stats['min_y'], y)
                    coord_stats['max_y'] = max(coord_stats['max_y'], y)
                    if abs(x) > 1000000 or abs(y) > 1000000:
                        coord_stats['entities_with_large_coords'].append(f"CIRCLE {handle}: center ({x:.2f}, {y:.2f})")

            elif entity_type == 'HATCH':
                attr = json_indep_hatch(entity, attr)
                counts['HATCH'] += 1

            elif entity_type == 'INSERT':
                attr = extract_insert_with_text(entity, attr, doc)
                counts['INSERT'] += 1

            elif entity_type == 'LEADER':
                attr = json_indep_leader(entity, attr)
                counts['LEADER'] += 1

            elif entity_type == 'LWPOLYLINE':
                attr = json_indep_lwpolyline(entity, attr)
                counts['LWPOLYLINE'] += 1
                if 'points' in attr:
                    for point in attr['points']:
                        if len(point) >= 2:
                            x, y = point[0], point[1]
                            coord_stats['min_x'] = min(coord_stats['min_x'], x)
                            coord_stats['max_x'] = max(coord_stats['max_x'], x)
                            coord_stats['min_y'] = min(coord_stats['min_y'], y)
                            coord_stats['max_y'] = max(coord_stats['max_y'], y)
                            if abs(x) > 1000000 or abs(y) > 1000000:
                                coord_stats['entities_with_large_coords'].append(f"LWPOLYLINE {handle}: point ({x:.2f}, {y:.2f})")
            
            elif entity_type == 'POINT':
                attr = json_indep_point(entity, attr)
                counts['POINT'] += 1
                if 'location' in attr:
                    x, y = attr['location'][0], attr['location'][1]
                    coord_stats['min_x'] = min(coord_stats['min_x'], x)
                    coord_stats['max_x'] = max(coord_stats['max_x'], x)
                    coord_stats['min_y'] = min(coord_stats['min_y'], y)
                    coord_stats['max_y'] = max(coord_stats['max_y'], y)
                    if abs(x) > 1000000 or abs(y) > 1000000:
                        coord_stats['entities_with_large_coords'].append(f"POINT {handle}: ({x:.2f}, {y:.2f})")
            
            elif entity_type == 'POLYLINE':
                attr = json_indep_polyline(entity, attr)
                counts['POLYLINE'] += 1

            elif entity_type == 'SPLINE':
                attr = json_indep_spline(entity, attr)
                counts['SPLINE'] += 1

            elif entity_type == 'TEXT':
                attr = json_indep_text(entity, attr)
                counts['TEXT'] += 1
                if 'insert_point' in attr:
                    x, y = attr['insert_point'][0], attr['insert_point'][1]
                    coord_stats['min_x'] = min(coord_stats['min_x'], x)
                    coord_stats['max_x'] = max(coord_stats['max_x'], x)
                    coord_stats['min_y'] = min(coord_stats['min_y'], y)
                    coord_stats['max_y'] = max(coord_stats['max_y'], y)
                    if abs(x) > 1000000 or abs(y) > 1000000:
                        coord_stats['entities_with_large_coords'].append(f"{entity_type} {handle}: ({x:.2f}, {y:.2f})")
            elif entity_type == 'MTEXT':
                attr = json_indep_mtext(entity, attr)
                counts['MTEXT'] += 1
                if 'insert_point' in attr:
                    x, y = attr['insert_point'][0], attr['insert_point'][1]
                    coord_stats['min_x'] = min(coord_stats['min_x'], x)
                    coord_stats['max_x'] = max(coord_stats['max_x'], x)
                    coord_stats['min_y'] = min(coord_stats['min_y'], y)
                    coord_stats['max_y'] = max(coord_stats['max_y'], y)
                    if abs(x) > 1000000 or abs(y) > 1000000:
                        coord_stats['entities_with_large_coords'].append(f"{entity_type} {handle}: ({x:.2f}, {y:.2f})")

            else:
                continue  # skip unsupported types

            entity_info['attributes'] =attr
            #entity_info['attributes'] = round_all_floats(attr, 3)
            entities_data.append(entity_info)

        except Exception as e:
            print(f"[WARN] Failed {entity.dxftype()} {handle}: {e}")

    print("\n--- RAW EXTRACTION SUMMARY ---")
    for k, v in counts.items():
        print(f"{k:12s}: {v}")

    print("\n--- COORDINATE RANGE DEBUG ---")
    print(f"X range: {coord_stats['min_x']:.2f} to {coord_stats['max_x']:.2f}")
    print(f"Y range: {coord_stats['min_y']:.2f} to {coord_stats['max_y']:.2f}")
    
    if coord_stats['entities_with_large_coords']:
        print(f"\nFound {len(coord_stats['entities_with_large_coords'])} entities with coordinates > 1,000,000:")
        for i, item in enumerate(coord_stats['entities_with_large_coords'][:10]):  # Show first 10
            print(f"  {item}")
        if len(coord_stats['entities_with_large_coords']) > 10:
            print(f"  ... and {len(coord_stats['entities_with_large_coords']) - 10} more")
    return entities_data


# =========================
# INSERT TEXT SAFE EXTRACTION
# =========================

def extract_insert_with_text(entity, attributes, doc):
    attributes = json_indep_insert(entity, attributes)

    if not doc:
        return attributes

    try:
        block = doc.blocks.get(entity.dxf.name)
        if not block:
            return attributes

        for sub in block:
            if sub.dxftype() == 'TEXT':
                attributes['actual_text'] = sub.dxf.text
                break
            elif sub.dxftype() == 'MTEXT':
                attributes['actual_text'] = decode_mtext_escapes(sub.text)
                break
    except Exception:
        pass

    return attributes

def round_all_floats(obj, ndigits=3):
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, (list, tuple)):
        return [round_all_floats(x, ndigits) for x in obj]
    if isinstance(obj, dict):
        return {k: round_all_floats(v, ndigits) for k, v in obj.items()}
    return obj
# =========================
# MAIN EXEC
# =========================

def exec(config_path: Path | str, mode: str | None = None):
    settings = resolve_export_settings(load_export_config(config_path), mode)
    dxf_file_path = settings["dxf_file_path"]
    desired_types = settings["desired_types"]
    desired_layers = settings["desired_layers"]
    output_path = Path(settings["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"配置文件: {config_path}")
    print(f"导出模式: {settings['mode']}")
    print(f"图元类型: {desired_types}")
    if desired_layers is None:
        print("图层: 全部")
    else:
        from entities_1019 import resolve_matching_layers

        print(f"图层子串: {desired_layers}")
        matched = resolve_matching_layers(dxf_file_path, desired_layers)
        print(f"命中图层 ({len(matched)}): {matched}")
    print(f"输出文件: {output_path}")

    try:
        doc = ezdxf.readfile(dxf_file_path)
        print(f"Loaded DXF with {len(doc.blocks)} blocks")
    except FileNotFoundError:
        print("DXF file not found")
        return

    filtered_msp = filter_msp(dxf_file_path, desired_types, desired_layers)
    filtered_entities = list_entity_from_msp(filtered_msp)

    entities_data = extract_entities_raw(filtered_entities, doc)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(entities_data, f, indent=4, ensure_ascii=False)

    print(f"\nExported {len(entities_data)} RAW entities → {output_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="从 DXF 导出 RAW 实体 JSON")
    parser.add_argument(
        "--cfg",
        "--config",
        dest="config",
        required=True,
        help="导出配置文件路径（必填，例如 utils/entity_export_config.json）；layers 按子串匹配图层名",
    )
    parser.add_argument(
        "--mode",
        choices=["line", "text", "facility", "legend"],
        default=None,
        help="覆盖配置文件中的 mode：line/text/facility/legend",
    )
    args = parser.parse_args()
    exec(config_path=args.config, mode=args.mode)
