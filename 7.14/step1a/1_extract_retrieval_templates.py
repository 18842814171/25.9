"""Script 1: `{stem}-图例.json` → retrieval_templates.json (standalone).

每种图例标题各自保留为独立 variant，不做同类合并。
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

STEP1A_DIR = Path(__file__).resolve().parent
_ROOT = STEP1A_DIR.parent
if str(STEP1A_DIR) not in sys.path:
    sys.path.insert(0, str(STEP1A_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.entity_json import exported_json_path, load_legend_annotation_records

from config import Step1aConfig, retrieval_templates_json
from geometry_fingerprint import dist, median_char_height, merge_unique, norm_radius
from graph_io import save_json_doc
from text_roles import (
    classify_caption_kind,
    clean_text,
    has_chinese,
    is_elevation_text,
)

CFG = Step1aConfig()


def find_seeds(entities: list[dict]) -> list[dict]:
    seeds = []
    for e in entities:
        if str(e.get("shape_type") or "") != "text":
            continue
        text = clean_text(e.get("text", ""))
        if not text or len(text) > CFG.seed_max_len:
            continue
        kind = classify_caption_kind(text)
        if kind is None:
            continue
        seeds.append({**e, "caption_kind": kind, "text": text})
    return seeds


def pick_symbol(seed: dict, entities: list[dict], max_dist: float) -> dict | None:
    cands = []
    for e in entities:
        if str(e.get("shape_type") or "") != "point-like":
            continue
        d = dist(seed, e)
        if d <= max_dist:
            cands.append((d, e))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    best_d, best = cands[0]
    return {**best, "dist": best_d}


def _legend_field_role(text: str, kind: str) -> str | None:
    """图例层无图层族信息：按标题 kind + 文字形态定角色。"""
    t = clean_text(text)
    if not t:
        return None
    if classify_caption_kind(t) is not None and has_chinese(t):
        return None
    if is_elevation_text(t):
        if kind == "control_point":
            return "elevation"
        return "collar" if "孔口" in t else "seam_value"
    if kind == "control_point":
        return "point_id"
    if kind == "borehole":
        return "borehole_id"
    return None


def sample_texts_around(
    symbol: dict, entities: list[dict], kind: str, max_dist: float, max_n: int = 6
) -> list[dict]:
    texts = []
    for e in entities:
        if str(e.get("shape_type") or "") != "text":
            continue
        d = dist(symbol, e)
        if d > max_dist or d < 1e-9:
            continue
        role = _legend_field_role(e.get("text", ""), kind)
        if role not in {
            "point_id",
            "borehole_id",
            "elevation",
            "collar",
            "seam_value",
        }:
            continue
        texts.append(
            {
                "text": clean_text(e.get("text", "")),
                "role": role,
                "dist": d,
                "dx": float(e["x"]) - float(symbol["x"]),
                "dy": float(e["y"]) - float(symbol["y"]),
                "char_height": float(e.get("char_height") or 0.0),
                "length": float(e.get("length") or 0.0),
                "x": float(e["x"]),
                "y": float(e["y"]),
            }
        )
    priority = {
        "point_id": 0,
        "borehole_id": 0,
        "elevation": 1,
        "collar": 1,
        "seam_value": 2,
    }
    texts.sort(key=lambda t: (priority.get(t["role"], 9), t["dist"]))
    caps = {
        "point_id": 1,
        "borehole_id": 1,
        "elevation": 2,
        "collar": 1,
        "seam_value": 3,
    }
    kept: list[dict] = []
    used: dict[str, int] = defaultdict(int)
    for t in texts:
        role = t["role"]
        if used[role] >= caps.get(role, 2):
            continue
        used[role] += 1
        kept.append(t)
        if len(kept) >= max_n:
            break
    return kept


def sample_separators(
    symbol: dict,
    field_texts: list[dict],
    entities: list[dict],
    char_h: float,
    max_dist: float,
) -> list[dict]:
    """记录符号邻域内 line-like：相对字高的长度、相对邻近文字的长度比与距离。"""
    if char_h <= 1e-12:
        return []
    anchors = field_texts or [
        {
            "x": float(symbol["x"]),
            "y": float(symbol["y"]),
            "text": "",
            "length": char_h,
            "char_height": char_h,
        }
    ]
    seps: list[dict] = []
    for e in entities:
        if str(e.get("shape_type") or "") != "line-like":
            continue
        if bool(e.get("closed")):
            continue
        line_len = float(e.get("length") or 0.0)
        if line_len <= 1e-12:
            continue
        d_sym = dist(symbol, e)
        if d_sym > max_dist:
            continue
        best = None
        for t in anchors:
            d = dist(e, t)
            span = float(t.get("length") or 0.0)
            if span <= 1e-12:
                span = float(t.get("char_height") or char_h) * max(
                    len(str(t.get("text") or "")), 1
                )
            if span <= 1e-12:
                continue
            cand = (d, t, span)
            if best is None or d < best[0]:
                best = cand
        if best is None:
            continue
        d_text, tnear, span = best
        seps.append(
            {
                "length_norm": round(line_len / char_h, 4),
                "dist_to_text_norm": round(d_text / char_h, 4),
                "dist_to_symbol_norm": round(d_sym / char_h, 4),
                "length_vs_text": round(line_len / span, 4),
                "near_text": tnear.get("text") or "",
                "near_role": tnear.get("role"),
            }
        )
    seps.sort(key=lambda s: (s["dist_to_text_norm"], s["dist_to_symbol_norm"]))
    return seps[:4]


def build_entry(seed: dict, entities: list[dict], char_h: float) -> dict | None:
    symbol = pick_symbol(seed, entities, CFG.symbol_probe_norm * char_h)
    if symbol is None:
        return None
    kind = seed["caption_kind"]
    samples = sample_texts_around(
        symbol, entities, kind, CFG.field_radius_norm * char_h
    )
    separators = sample_separators(
        symbol, samples, entities, char_h, CFG.field_radius_norm * char_h
    )

    r_norm = None
    block_name = None
    if symbol.get("radius") is not None:
        try:
            r_norm = norm_radius(float(symbol["radius"]), char_h)
        except (TypeError, ValueError):
            r_norm = None
    if symbol.get("block_name"):
        block_name = symbol.get("block_name")

    farthest = max((float(s["dist"]) for s in samples), default=symbol.get("dist", 0.0))
    search_radius_norm = min(farthest / max(char_h, 1e-6), CFG.search_radius_cap_norm)
    search_radius_norm = max(search_radius_norm, 4.0)
    if kind == "borehole":
        search_radius_norm = max(search_radius_norm, 8.0)
    if kind == "control_point":
        search_radius_norm = max(min(search_radius_norm, 9.0), 5.0)

    field_slots = []
    by_role: dict[str, list[dict]] = defaultdict(list)
    for t in samples:
        by_role[t["role"]].append(t)
    for role, items in by_role.items():
        dxs = [(i["dx"] / char_h) for i in items]
        dys = [(i["dy"] / char_h) for i in items]
        field_slots.append(
            {
                "role": role,
                "dx_norm": round(sum(dxs) / len(dxs), 4) if dxs else None,
                "dy_norm": round(sum(dys) / len(dys), 4) if dys else None,
                "examples": merge_unique([i.get("text") for i in items if i.get("text")])[
                    :5
                ],
            }
        )

    return {
        "caption": seed["text"],
        "kind": kind,
        "symbol": {
            "shape_type": "point-like",
            "block_name": block_name,
            "block_names": [block_name] if block_name else [],
            "radius_norm": r_norm,
            "radius_norms": [round(r_norm, 4)] if r_norm is not None else [],
            "x": float(symbol["x"]),
            "y": float(symbol["y"]),
            "dist_from_caption": round(float(symbol.get("dist") or 0.0), 4),
        },
        "sample_texts": [
            {k: v for k, v in t.items() if k not in {"x", "y", "length"}}
            for t in samples
        ],
        "fields": field_slots,
        "separators": separators,
        "search_radius_norm": round(search_radius_norm, 4),
    }


def pack_kind_variants(entries: list[dict], kind: str) -> dict:
    """每种标题一条 variant，禁止合并成单一模板。"""
    variants = [e for e in entries if e["kind"] == kind]
    captions = merge_unique([e["caption"] for e in variants])
    return {
        "kind": kind,
        "captions": captions,
        "variants": variants,
        "entry_count": len(variants),
    }


def mine_legend_entities(entities: list[dict]) -> dict:
    if not entities:
        raise RuntimeError("no legend annotation entities in legend JSON")
    char_h = median_char_height(entities, fallback=CFG.fallback_char_height)
    seeds = find_seeds(entities)
    entries = []
    for seed in seeds:
        entry = build_entry(seed, entities, char_h)
        if entry is not None:
            entries.append(entry)
    templates = {
        "control_point": pack_kind_variants(entries, "control_point"),
        "borehole": pack_kind_variants(entries, "borehole"),
    }
    return {
        "template_layer": CFG.template_layer,
        "legend_median_char_height": char_h,
        "seed_count": len(seeds),
        "entry_count": len(entries),
        "entries": entries,
        "templates": templates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mine legend templates from `{stem}-图例.json`"
    )
    parser.add_argument("--stem", type=str, default=CFG.default_stem)
    parser.add_argument(
        "--legend-json",
        type=str,
        default="",
        help="override path to legend export JSON",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="",
        help="directory of export JSON when --legend-json omitted",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="override product directory (default: step1a/output)",
    )
    args = parser.parse_args()
    out = args.output_dir or None
    in_dir = args.input_dir or None

    legend_path = (
        Path(args.legend_json)
        if args.legend_json
        else exported_json_path(args.stem, "legend", base_dir=in_dir)
    )
    entities, source_path = load_legend_annotation_records(
        args.stem,
        path=legend_path,
    )
    pack = mine_legend_entities(entities)
    pack = {
        "stem": args.stem,
        "source_legend_json": str(source_path.as_posix()),
        "step1a_config": CFG.to_json(),
        **pack,
    }

    out_json = retrieval_templates_json(args.stem, out)
    save_json_doc(pack, out_json)

    print(f"stem: {args.stem}")
    print(f"input: {source_path}")
    print(f"output_json: {out_json}")
    print(f"seeds: {pack['seed_count']} entries: {pack['entry_count']}")
    for kind, tmpl in pack["templates"].items():
        variants = tmpl.get("variants") or []
        print(f"  {kind}: captions={tmpl['captions']} variants={len(variants)}")
        for v in variants:
            seps = v.get("separators") or []
            print(
                f"    - {v['caption']}: "
                f"block={v['symbol'].get('block_name')} "
                f"r={v['symbol'].get('radius_norm')} "
                f"fields={len(v.get('fields') or [])} "
                f"separators={len(seps)} "
                f"R_norm={v['search_radius_norm']}"
            )


if __name__ == "__main__":
    main()
