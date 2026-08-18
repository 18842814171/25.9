"""清洗文字导出 JSON：滤掉巷道描边，并为 INSERT 补真实包围盒。

INSERT 常规导出只写 insert/scale/rotation；本步骤读 DXF，用 bbox.extents
写入 attributes，并把等效半径写成 radius，供 shape_abstract / 锚点匹配使用。

同时从文字 JSON 中剔除巷道图层上的描边（LINE/LWPOLYLINE/…），
保留测点/导线点等符号层上的闭合加宽多段线。避免短巷道段被抽象成
point-like 抢控制点/钻孔锚点。

由 ``batch_export_test_input.py`` 在文字导出后自动调用；亦可单独运行：
  python 7.14/utils/temp_clean_text_export.py --stem 1
  python 7.14/utils/temp_clean_text_export.py --stem 1 --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

_UTILS = Path(__file__).resolve().parent
_STEP = _UTILS.parent
_REPO = _STEP.parent
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

import ezdxf
import ezdxf.bbox as ezbbox

# 字/块/圆/点一律保留
_KEEP_TYPES = frozenset({"TEXT", "MTEXT", "INSERT", "CIRCLE", "POINT"})
# 描边类：仅当落在巷道图层时剔除（测点层上的闭合加宽多段线是真符号，要留）
_STROKE_TYPES = frozenset(
    {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "SPLINE", "HATCH", "SOLID", "TRACE"}
)
_ROADWAY_LAYER_TOKENS = (
    "已掘",
    "巷道填充",
    "设计巷道",
    "年内巷道",
    "年巷道填充",
    "年巷道",  # 如 2018年巷道
)
_SYMBOL_LAYER_TOKENS = (
    "导线点",
    "控制点",
    "测点",
    "离散点",
    "钻孔",
    "孔号",
    "孔口",
    "GPS",
    "验收",
    "煤层",
    "煤厚",
    "巷道名称",
    "联巷名称",
)


def _is_roadway_stroke(ent: dict) -> bool:
    """巷道描边：描边类型 + 巷道图层，且不是测点/钻孔等符号层。"""
    et = str(ent.get("type") or "")
    if et not in _STROKE_TYPES:
        return False
    layer = str(ent.get("layer") or "")
    if any(tok in layer for tok in _SYMBOL_LAYER_TOKENS):
        return False
    if layer == "巷道" or any(tok in layer for tok in _ROADWAY_LAYER_TOKENS):
        return True
    # 其它未知描边也丢掉，避免再混进锚点池
    return True


def _default_text_json(stem: str) -> Path:
    return _REPO / "test_input" / f"{stem}-文字.json"


def _default_dxf(stem: str) -> Path:
    return _REPO / "test_input" / f"{stem}.dxf"


def _load_entities(path: Path) -> list[dict]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        ents = doc.get("entities")
        if isinstance(ents, list):
            return ents
    raise ValueError(f"unexpected JSON shape: {path}")


def _filter_roadway_strokes(entities: list[dict]) -> tuple[list[dict], Counter]:
    """丢掉巷道层描边；保留字/块/圆/点，以及测点层上的符号多段线。"""
    kept: list[dict] = []
    dropped = Counter()
    for ent in entities:
        et = str(ent.get("type") or "")
        if et in _KEEP_TYPES:
            kept.append(ent)
            continue
        if _is_roadway_stroke(ent):
            layer = str(ent.get("layer") or "")
            dropped[f"{et}@{layer}"] += 1
            continue
        kept.append(ent)
    return kept, dropped


def _enrich_inserts_from_dxf(entities: list[dict], dxf_path: Path) -> tuple[int, int]:
    """为 INSERT 写入 bbox / 等效 radius；返回 (enriched, failed)。"""
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    by_handle: dict[str, object] = {}
    for entity in msp.query("INSERT"):
        by_handle[str(entity.dxf.handle)] = entity

    enriched = 0
    failed = 0
    for ent in entities:
        if str(ent.get("type") or "") != "INSERT":
            continue
        handle = str(ent.get("handle") or "")
        attrs = ent.get("attributes")
        if not isinstance(attrs, dict):
            continue
        entity = by_handle.get(handle)
        if entity is None:
            failed += 1
            continue
        try:
            box = ezbbox.extents([entity])
        except Exception:
            failed += 1
            continue
        if not box.has_data:
            failed += 1
            continue
        ext = box.extmin, box.extmax
        min_x, min_y = float(ext[0].x), float(ext[0].y)
        max_x, max_y = float(ext[1].x), float(ext[1].y)
        cx = float(box.center.x)
        cy = float(box.center.y)
        w = max(max_x - min_x, 0.0)
        h = max(max_y - min_y, 0.0)
        # 等效半径：外接框半对角线，比 max_side/2 更接近块的视觉尺度
        radius = 0.5 * (w * w + h * h) ** 0.5
        attrs["bbox"] = [min_x, min_y, max_x, max_y]
        attrs["bbox_center"] = [cx, cy, float(getattr(box.center, "z", 0.0) or 0.0)]
        attrs["bbox_w"] = w
        attrs["bbox_h"] = h
        attrs["radius"] = radius
        attrs["bbox_from_dxf"] = True
        enriched += 1
    return enriched, failed


def clean_text_export(
    text_json: Path,
    dxf_path: Path,
    *,
    out_path: Path | None = None,
    dry_run: bool = False,
    backup: bool = True,
) -> dict:
    entities = _load_entities(text_json)
    before = len(entities)
    by_type_before = Counter(str(e.get("type") or "?") for e in entities)

    kept, dropped = _filter_roadway_strokes(entities)
    enriched, failed = _enrich_inserts_from_dxf(kept, dxf_path)

    summary = {
        "input": str(text_json),
        "dxf": str(dxf_path),
        "before": before,
        "after": len(kept),
        "dropped_strokes": dict(dropped),
        "insert_bbox_enriched": enriched,
        "insert_bbox_failed": failed,
        "types_before": dict(by_type_before),
        "types_after": dict(Counter(str(e.get("type") or "?") for e in kept)),
    }

    if dry_run:
        summary["wrote"] = None
        return summary

    dest = out_path or text_json
    dest.parent.mkdir(parents=True, exist_ok=True)
    if backup and dest.resolve() == text_json.resolve() and text_json.is_file():
        bak = text_json.with_suffix(text_json.suffix + ".pre_clean.bak")
        shutil.copy2(text_json, bak)
        summary["backup"] = str(bak)
    dest.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["wrote"] = str(dest)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="清洗文字 JSON（滤巷道描边 + INSERT 真实 bbox）"
    )
    parser.add_argument("--stem", type=str, default="", help="图号，如 4-1")
    parser.add_argument("--text-json", type=str, default="", help="文字 JSON 路径")
    parser.add_argument("--dxf", type=str, default="", help="对应 DXF 路径")
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="输出路径（默认覆盖文字 JSON，并写 .pre_clean.bak）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="覆盖原文件时不写 bak",
    )
    args = parser.parse_args()

    if args.text_json:
        text_json = Path(args.text_json)
        if not text_json.is_absolute():
            text_json = _REPO / text_json
    elif args.stem:
        text_json = _default_text_json(args.stem)
    else:
        raise SystemExit("需要 --stem 或 --text-json")

    if args.dxf:
        dxf_path = Path(args.dxf)
        if not dxf_path.is_absolute():
            dxf_path = _REPO / dxf_path
    elif args.stem:
        dxf_path = _default_dxf(args.stem)
    else:
        dxf_path = text_json.with_name(text_json.name.replace("-文字.json", ".dxf"))
        if not dxf_path.is_file():
            dxf_path = text_json.with_suffix(".dxf")

    if not text_json.is_file():
        raise FileNotFoundError(text_json)
    if not dxf_path.is_file():
        raise FileNotFoundError(dxf_path)

    out_path = Path(args.out) if args.out else None
    if out_path is not None and not out_path.is_absolute():
        out_path = _REPO / out_path

    summary = clean_text_export(
        text_json,
        dxf_path,
        out_path=out_path,
        dry_run=bool(args.dry_run),
        backup=not args.no_backup,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
