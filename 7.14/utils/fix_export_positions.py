"""将导出 JSON 中异常 INSERT 位置改为 DXF 变换后的显示位置（包围盒中心）。

原因：部分块的 insert 基点在百万级，块内几何经缩放/旋转后画在正常图幅；
CAD 窗口看到的是变换结果，导出若直接写 insert 会留下飞点。本脚本按句柄回读
DXF，用 ezdxf 包围盒中心（已含插入点、比例、旋转）写回 JSON。

用法（仓库根目录；须先有对应 mode 的导出 JSON；--config 必填）：
  python utils/fix_export_positions.py --config ../../test_input/2016_config.json --mode text
  python utils/fix_export_positions.py --config ../../test_input/2016_config.json --mode text --dxf_file_path dxf/2026.1-1part.dxf
  python utils/fix_export_positions.py --config ../../test_input/2016_config.json --mode all --coord-threshold 100000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_UTILS = Path(__file__).resolve().parent
_ROOT = _UTILS.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import ezdxf
import ezdxf.bbox as ezbbox

from utils.entity_export import (
    load_export_config,
    resolve_export_settings,
)
from utils.entity_json import exported_json_path

MODES = ("text", "facility", "legend", "line")


def _resolve_dxf(config: dict, dxf_file_path: str | None) -> Path:
    settings = resolve_export_settings(config, mode="text", dxf_file_path=dxf_file_path)
    path = Path(settings["dxf_file_path"])
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _is_extreme(x: float, y: float, threshold: float) -> bool:
    return abs(x) > threshold or abs(y) > threshold


def _xy_from_attributes(attrs: dict) -> tuple[float, float] | None:
    for key in ("insert_point", "center", "location"):
        p = attrs.get(key)
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            return float(p[0]), float(p[1])
    if "start" in attrs and "end" in attrs:
        s, e = attrs["start"], attrs["end"]
        return (float(s[0]) + float(e[0])) * 0.5, (float(s[1]) + float(e[1])) * 0.5
    return None


def build_display_centers(dxf_path: Path) -> dict[str, tuple[float, float, float]]:
    """handle → (x, y, z) from transformed entity bbox center."""
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    out: dict[str, tuple[float, float, float]] = {}
    for entity in msp:
        handle = str(entity.dxf.handle)
        try:
            box = ezbbox.extents([entity])
            c = box.center
            out[handle] = (float(c.x), float(c.y), float(getattr(c, "z", 0.0) or 0.0))
        except Exception:
            continue
    return out


def fix_entities(
    entities: list[dict],
    centers: dict[str, tuple[float, float, float]],
    *,
    threshold: float,
    entity_types: set[str] | None,
) -> tuple[int, list[dict]]:
    """Rewrite extreme position fields; return (fix_count, change_log)."""
    fixed = 0
    log: list[dict] = []
    for ent in entities:
        et = str(ent.get("type") or "")
        if entity_types is not None and et not in entity_types:
            continue
        handle = str(ent.get("handle") or "")
        attrs = ent.get("attributes")
        if not isinstance(attrs, dict):
            continue
        xy = _xy_from_attributes(attrs)
        if xy is None or not _is_extreme(xy[0], xy[1], threshold):
            continue
        center = centers.get(handle)
        if center is None:
            log.append(
                {
                    "handle": handle,
                    "type": et,
                    "layer": ent.get("layer"),
                    "status": "no_bbox",
                    "old": [xy[0], xy[1]],
                }
            )
            continue
        cx, cy, cz = center
        if _is_extreme(cx, cy, threshold):
            log.append(
                {
                    "handle": handle,
                    "type": et,
                    "layer": ent.get("layer"),
                    "status": "bbox_still_extreme",
                    "old": [xy[0], xy[1]],
                    "bbox": [cx, cy],
                }
            )
            continue

        old = [xy[0], xy[1]]
        if "insert_point" in attrs and isinstance(attrs["insert_point"], list):
            z = float(attrs["insert_point"][2]) if len(attrs["insert_point"]) > 2 else cz
            attrs["insert_point_raw"] = list(attrs["insert_point"])
            attrs["insert_point"] = [cx, cy, z]
        elif "center" in attrs and isinstance(attrs["center"], list):
            z = float(attrs["center"][2]) if len(attrs["center"]) > 2 else cz
            attrs["center_raw"] = list(attrs["center"])
            attrs["center"] = [cx, cy, z]
        elif "location" in attrs and isinstance(attrs["location"], list):
            z = float(attrs["location"][2]) if len(attrs["location"]) > 2 else cz
            attrs["location_raw"] = list(attrs["location"])
            attrs["location"] = [cx, cy, z]
        else:
            continue

        fixed += 1
        log.append(
            {
                "handle": handle,
                "type": et,
                "layer": ent.get("layer"),
                "status": "fixed",
                "old": old,
                "new": [cx, cy],
            }
        )
    return fixed, log


def fix_json_file(
    json_path: Path,
    centers: dict[str, tuple[float, float, float]],
    *,
    threshold: float,
    entity_types: set[str] | None,
) -> tuple[int, list[dict]]:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"expected entity list: {json_path}")
    fixed, log = fix_entities(
        data, centers, threshold=threshold, entity_types=entity_types
    )
    if fixed:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    return fixed, log


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix extreme INSERT positions in root export JSON via DXF bbox"
    )
    parser.add_argument(
        "--cfg",
        "--config",
        dest="config",
        required=True,
        help="导出配置文件路径（必填，不许留空/默认）",
    )
    parser.add_argument(
        "--dxf_file_path",
        "--dxf",
        dest="dxf_file_path",
        default=None,
        help="DXF path (override config); used to compute display centers",
    )
    parser.add_argument(
        "--mode",
        choices=[*MODES, "all"],
        default="text",
        help="which root JSON to fix (default: text)",
    )
    parser.add_argument(
        "--coord-threshold",
        type=float,
        default=1.0e5,
        help="flag |x| or |y| above this as extreme (default: 1e5)",
    )
    parser.add_argument(
        "--types",
        type=str,
        default="INSERT",
        help="comma-separated entity types to fix (default: INSERT)",
    )
    args = parser.parse_args()

    config = load_export_config(args.config)
    dxf_path = _resolve_dxf(config, args.dxf_file_path)
    # 用配置里的图纸名推 stem；若命令行覆盖了 dxf，则以该文件 stem 为准
    stem = dxf_path.stem
    type_set = {t.strip() for t in args.types.split(",") if t.strip()} or None

    modes = list(MODES) if args.mode == "all" else [args.mode]
    print(f"dxf: {dxf_path}")
    print(f"stem: {stem}")
    print(f"threshold: {args.coord_threshold}")
    print(f"types: {sorted(type_set) if type_set else 'all'}")

    print("computing display centers from DXF …")
    centers = build_display_centers(dxf_path)
    print(f"bbox centers: {len(centers)}")

    total = 0
    for mode in modes:
        json_path = exported_json_path(stem, mode, config_path=args.config)
        if not json_path.is_file():
            print(f"skip {mode}: not found {json_path}")
            continue
        fixed, log = fix_json_file(
            json_path,
            centers,
            threshold=float(args.coord_threshold),
            entity_types=type_set,
        )
        total += fixed
        print(f"{mode}: fixed {fixed} → {json_path}")
        for row in log:
            if row["status"] != "fixed":
                print(f"  WARN {row}")
            else:
                print(
                    f"  {row['handle']} {row['type']} "
                    f"{row['old']} → {row['new']}"
                )

    print(f"done, total fixed: {total}")
    if total:
        print("re-run stage scripts that consume the fixed JSON (e.g. step1a/0).")


if __name__ == "__main__":
    main()
