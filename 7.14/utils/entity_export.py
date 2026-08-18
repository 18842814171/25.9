"""从 DXF 按 entity_export_config.json 导出 RAW 图元 JSON（仓库内唯一直接读 DXF 的入口）。

组织方式对齐 5.29/utils：各 mode 的 entity_types、layers、output_filename 均在配置中；
本脚本不硬编码图元类型列表。

用法（在仓库根目录）：
  python utils/entity_export.py --cfg utils/entity_export_config.json --mode text
  python utils/entity_export.py --cfg utils/entity_export_config.json --mode text --dxf_file_path dxf/2026.1-1part.dxf
  python utils/entity_export.py --cfg utils/entity_export_config.json --mode line
  python utils/entity_export.py --cfg utils/entity_export_config.json --mode facility
  python utils/entity_export.py --cfg utils/entity_export_config.json --mode legend

配置中 layers 为子串模式：图层名包含任一子串即导出（例如「巷道」匹配「2010年巷道」）。
可选 exclude_layer_keywords：在已命中 layers 的图层中，再去掉名称含这些关键词的图层。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_UTILS = Path(__file__).resolve().parent
_ROOT = _UTILS.parent
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import ezdxf

from entities_filter import filter_msp, list_entity_from_msp, resolve_matching_layers
from indep_json import (
    decode_mtext_escapes,
    json_indep_arc,
    json_indep_circle,
    json_indep_hatch,
    json_indep_insert,
    json_indep_leader,
    json_indep_line,
    json_indep_lwpolyline,
    json_indep_mtext,
    json_indep_point,
    json_indep_polyline,
    json_indep_spline,
    json_indep_text,
)
from ocs_normalize import normalize_attributes_to_wcs

PROJECT_ROOT = _ROOT


def load_export_config(config_path: Path | str) -> dict:
    if config_path is None or str(config_path).strip() == "":
        raise ValueError("必须指定导出配置文件路径（--cfg / --config），不允许默认或留空")
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"导出配置不存在: {path}")
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


def resolve_export_settings(
    config: dict,
    mode: str | None = None,
    dxf_file_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    output_filename: str | None = None,
) -> dict:
    export_mode = (mode or config.get("mode", "line")).lower()
    if export_mode not in {"line", "text", "facility", "legend"}:
        raise ValueError(
            f"mode 必须是 'line'、'text'、'facility' 或 'legend'，当前为: {export_mode}"
        )

    raw = dxf_file_path if dxf_file_path is not None else config["dxf_file_path"]
    dxf_path = Path(raw)
    if not dxf_path.is_absolute():
        dxf_path = PROJECT_ROOT / dxf_path
    if not dxf_path.is_file() and not str(dxf_path).lower().endswith(".dxf"):
        candidate = Path(str(dxf_path) + ".dxf")
        if candidate.is_file():
            dxf_path = candidate

    section = config[export_mode]
    raw_types = section.get("entity_types", None)
    # null / 缺省 / 空列表 → 不限图元类型
    if raw_types is None or raw_types == []:
        desired_types = None
    else:
        desired_types = [str(t) for t in raw_types]
        if not desired_types:
            desired_types = None

    if "layers" not in section or not section.get("layers"):
        # text/legend 等也必须按配置图层提取；不再默认全图层
        if export_mode in {"text", "line", "facility", "legend"}:
            raise ValueError(
                f"配置缺少非空字段 {export_mode}.layers（按图层子串提取）"
            )
    desired_layers = section["layers"]
    raw_exclude = section.get("exclude_layer_keywords") or []
    exclude_layer_keywords = [str(k) for k in raw_exclude if str(k).strip()]

    name_template = output_filename or section["output_filename"]
    resolved_name = resolve_output_filename(name_template, dxf_path)
    out_base = Path(output_dir) if output_dir is not None else PROJECT_ROOT
    if not out_base.is_absolute():
        out_base = PROJECT_ROOT / out_base
    output_path = out_base / resolved_name

    return {
        "mode": export_mode,
        "dxf_file_path": str(dxf_path),
        "desired_types": desired_types,
        "desired_layers": desired_layers,
        "exclude_layer_keywords": exclude_layer_keywords,
        "output_path": output_path,
    }


def extract_insert_with_text(entity, attributes, doc):
    attributes = json_indep_insert(entity, attributes)
    if not doc:
        return attributes
    try:
        block = doc.blocks.get(entity.dxf.name)
        if not block:
            return attributes
        for sub in block:
            if sub.dxftype() == "TEXT":
                attributes["actual_text"] = sub.dxf.text
                break
            if sub.dxftype() == "MTEXT":
                attributes["actual_text"] = decode_mtext_escapes(sub.text)
                break
    except Exception:
        pass
    return attributes


def extract_entities_raw(filtered_entities, doc=None):
    """Extract DXF entities WITHOUT exploding geometry."""
    entities_data = []
    counts = {
        "LINE": 0,
        "ARC": 0,
        "CIRCLE": 0,
        "HATCH": 0,
        "INSERT": 0,
        "LEADER": 0,
        "LWPOLYLINE": 0,
        "POINT": 0,
        "POLYLINE": 0,
        "SPLINE": 0,
        "TEXT": 0,
        "MTEXT": 0,
    }
    ocs_normalized = 0
    for entity in filtered_entities:
        try:
            entity_type = entity.dxftype()
            handle = entity.dxf.handle
            layer = entity.dxf.layer if hasattr(entity.dxf, "layer") else "0"
            entity_info = {
                "handle": handle,
                "type": entity_type,
                "layer": layer,
                "attributes": {},
            }
            attr = entity_info["attributes"]

            if entity_type == "LINE":
                attr = json_indep_line(entity, attr)
                if attr is None:
                    continue
                counts["LINE"] += 1
            elif entity_type == "ARC":
                attr = json_indep_arc(entity, attr)
                counts["ARC"] += 1
            elif entity_type == "CIRCLE":
                attr = json_indep_circle(entity, attr)
                counts["CIRCLE"] += 1
            elif entity_type == "HATCH":
                attr = json_indep_hatch(entity, attr)
                counts["HATCH"] += 1
            elif entity_type == "INSERT":
                attr = extract_insert_with_text(entity, attr, doc)
                counts["INSERT"] += 1
            elif entity_type == "LEADER":
                attr = json_indep_leader(entity, attr)
                counts["LEADER"] += 1
            elif entity_type == "LWPOLYLINE":
                attr = json_indep_lwpolyline(entity, attr)
                counts["LWPOLYLINE"] += 1
            elif entity_type == "POINT":
                attr = json_indep_point(entity, attr)
                counts["POINT"] += 1
            elif entity_type == "POLYLINE":
                attr = json_indep_polyline(entity, attr)
                counts["POLYLINE"] += 1
            elif entity_type == "SPLINE":
                attr = json_indep_spline(entity, attr)
                counts["SPLINE"] += 1
            elif entity_type == "TEXT":
                attr = json_indep_text(entity, attr)
                counts["TEXT"] += 1
            elif entity_type == "MTEXT":
                attr = json_indep_mtext(entity, attr)
                counts["MTEXT"] += 1
            else:
                continue

            attr = normalize_attributes_to_wcs(entity, attr)
            if attr is not None and attr.get("ocs_normalized"):
                ocs_normalized += 1
                print(
                    f"[ocs] normalized {entity_type} handle={handle} "
                    f"extrusion_original={attr.get('extrusion_original')}"
                )

            entity_info["attributes"] = attr
            entities_data.append(entity_info)
        except Exception as e:
            print(f"[WARN] Failed {entity.dxftype()} {getattr(entity.dxf, 'handle', '?')}: {e}")

    print("\n--- RAW EXTRACTION SUMMARY ---")
    for k, v in counts.items():
        print(f"{k:12s}: {v}")
    if ocs_normalized:
        print(f"ocs_normalized: {ocs_normalized}")
    return entities_data


def exec(
    config_path: Path | str,
    mode: str | None = None,
    dxf_file_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    output_filename: str | None = None,
):
    settings = resolve_export_settings(
        load_export_config(config_path),
        mode,
        dxf_file_path=dxf_file_path,
        output_dir=output_dir,
        output_filename=output_filename,
    )
    dxf_file_path = settings["dxf_file_path"]
    desired_types = settings["desired_types"]
    desired_layers = settings["desired_layers"]
    exclude_layer_keywords = settings.get("exclude_layer_keywords") or []
    output_path = settings["output_path"]

    print(f"导出模式: {settings['mode']}")
    print(f"图纸: {dxf_file_path}")
    print(f"图元类型: {'不限' if desired_types is None else desired_types}")
    if desired_layers is None:
        print("图层: 全部")
    else:
        print(f"图层子串: {desired_layers}")
        if exclude_layer_keywords:
            print(f"排除关键词: {exclude_layer_keywords}")
        matched = resolve_matching_layers(
            dxf_file_path, desired_layers, exclude_layer_keywords
        )
        print(f"命中图层 ({len(matched)}): {matched}")
    print(f"输出文件: {output_path}")

    try:
        doc = ezdxf.readfile(dxf_file_path)
        print(f"Loaded DXF with {len(doc.blocks)} blocks")
    except FileNotFoundError:
        print(f"DXF file not found: {dxf_file_path}")
        return

    filtered_msp = filter_msp(
        dxf_file_path,
        desired_types,
        desired_layers,
        exclude_layer_keywords,
    )
    filtered_entities = list_entity_from_msp(filtered_msp)
    entities_data = extract_entities_raw(filtered_entities, doc)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entities_data, f, indent=4, ensure_ascii=False)

    print(f"\nExported {len(entities_data)} RAW entities → {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 DXF 导出 RAW 实体 JSON")
    parser.add_argument(
        "--cfg",
        "--config",
        dest="config",
        required=True,
        help="导出配置文件路径（必填，不许留空/默认）；layers 按子串匹配图层名",
    )
    parser.add_argument(
        "--mode",
        choices=["line", "text", "facility", "legend"],
        default=None,
        help="覆盖配置文件中的 mode：line=巷道，text=文字，facility=设施，legend=图例",
    )
    parser.add_argument(
        "--dxf_file_path",
        "--dxf",
        dest="dxf_file_path",
        default=None,
        help="覆盖配置中的图纸路径（相对仓库根或绝对路径；可省略 .dxf 后缀）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="覆盖默认写出目录（默认仓库根）；文件名仍由配置模板决定",
    )
    parser.add_argument(
        "--output-filename",
        type=str,
        default=None,
        help="覆盖配置中的 output_filename 模板（可含 {dxf_name}）",
    )
    args = parser.parse_args()
    exec(
        config_path=args.config,
        mode=args.mode,
        dxf_file_path=args.dxf_file_path,
        output_dir=args.output_dir,
        output_filename=args.output_filename,
    )
