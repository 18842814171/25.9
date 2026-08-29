"""Script 2: retrieved_elements_graph + retrieval_templates → retrieval_rules.json."""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

STEP1A_DIR = Path(__file__).resolve().parent
if str(STEP1A_DIR) not in sys.path:
    sys.path.insert(0, str(STEP1A_DIR))

from config import (
    Step1aConfig,
    retrieved_elements_graph_pkl,
    retrieval_templates_json,
    retrieval_rules_json,
)
from geometry_fingerprint import (
    dist,
    median_char_height,
    percentile,
)
from graph_io import load_graph, load_json_doc, save_json_doc
from graph_nodes import annotation_records
from text_roles import (
    annotation_family,
    classify_text_role,
    is_borehole_layer,
    is_control_point_layer,
    is_point_id_candidate,
    role_allowed_for_cluster,
    seed_role_from_layer_name,
)

CFG = Step1aConfig()


def flatten_kind_template(tmpl: dict) -> dict:
    """variants 各自独立保留；symbol 仅保留形状抽象。"""
    variants = list(tmpl.get("variants") or [])
    if not variants:
        # 兼容旧版单模板（无 variants）
        return {
            "kind": tmpl.get("kind"),
            "captions": list(tmpl.get("captions") or []),
            "symbol": {"shape_type": "point-like"},
            "fields": list(tmpl.get("fields") or []),
            "separators": list(tmpl.get("separators") or []),
            "search_radius_norm": float(tmpl.get("search_radius_norm") or 7.0),
            "variants": [],
        }

    fields: list[dict] = []
    separators: list[dict] = []
    captions: list[str] = []
    radii_norm: list[float] = []
    for v in variants:
        cap = v.get("caption")
        if cap:
            captions.append(str(cap))
        for f in v.get("fields") or []:
            fields.append(f)
        for s in v.get("separators") or []:
            separators.append(s)
        try:
            radii_norm.append(float(v.get("search_radius_norm") or 0.0))
        except (TypeError, ValueError):
            pass

    search_radius_norm = max(radii_norm) if radii_norm else float(
        tmpl.get("search_radius_norm") or 7.0
    )
    return {
        "kind": tmpl.get("kind"),
        "captions": list(tmpl.get("captions") or captions),
        "symbol": {"shape_type": "point-like"},
        "fields": fields,
        "separators": separators,
        "search_radius_norm": search_radius_norm,
        "variants": variants,
    }


def is_symbol_anchor(ent: dict, tmpl: dict, kind: str, char_h: float) -> bool:
    """锚点：只认 point-like 形状抽象；块名/半径不参与判定。"""
    del tmpl, char_h
    if str(ent.get("shape_type") or "") != "point-like":
        return False
    layer = str(ent.get("layer") or "")
    if kind == "borehole" and is_control_point_layer(layer):
        return False
    if kind == "control_point" and annotation_family(layer) == "borehole":
        return False
    return True


def discover_control_point_likes(
    entities: list[dict], char_h: float, probe_radius: float
) -> list[dict]:
    texts = [
        e
        for e in entities
        if str(e.get("shape_type") or "") == "text"
    ]
    symbols = [e for e in entities if str(e.get("shape_type") or "") == "point-like"]
    found = []
    for c in symbols:
        has_id = False
        has_elev = False
        for t in texts:
            if dist(c, t) > probe_radius:
                continue
            role = classify_text_role(t.get("text", ""), t.get("layer", ""))
            if role == "point_id" or is_point_id_candidate(t.get("text", ""), t.get("layer", "")):
                has_id = True
            elif role == "elevation":
                has_elev = True
            if has_id and has_elev:
                found.append(c)
                break
        if len(found) >= CFG.max_anchors_for_vote:
            break
    return found


def _borehole_inserts_by_layer(entities: list[dict]) -> list[dict]:
    """图层名含「钻孔」且不含「名称」的 point-like（多为块参照）。"""
    out = []
    for e in entities:
        if str(e.get("shape_type") or "") != "point-like":
            continue
        layer = str(e.get("layer") or "")
        if "钻孔" in layer and "名称" not in layer:
            out.append(e)
    return out


def _control_point_symbols_by_layer(entities: list[dict]) -> list[dict]:
    """图层属控制点族的 point-like（永久/临时导线点等，不依赖半径档）。"""
    out = []
    for e in entities:
        if str(e.get("shape_type") or "") != "point-like":
            continue
        if is_control_point_layer(str(e.get("layer") or "")):
            out.append(e)
    return out


def collect_anchors(entities: list[dict], tmpl: dict, kind: str, char_h: float) -> list[dict]:
    matched = [e for e in entities if is_symbol_anchor(e, tmpl, kind, char_h)]
    if kind == "borehole":
        # 图例块名与本图不一致时，按图层回收钻孔符号
        by_id = {str(e["id"]): e for e in matched}
        for e in _borehole_inserts_by_layer(entities):
            by_id.setdefault(str(e["id"]), e)
        matched = list(by_id.values())
        if matched:
            return matched[: CFG.max_anchors_for_vote]
        soft = []
        for e in entities:
            if str(e.get("shape_type") or "") != "text":
                continue
            if classify_text_role(e.get("text", ""), e.get("layer", "")) == "borehole_id":
                soft.append(e)
        return soft[: CFG.max_anchors_for_vote]
    if kind == "control_point":
        # 图例多档圆 + 本图「导线点」图层一并保留（大档不中仍可用小档/图层回收）
        by_id = {str(e["id"]): e for e in matched}
        for e in _control_point_symbols_by_layer(entities):
            by_id.setdefault(str(e["id"]), e)
        matched = list(by_id.values())
        if matched:
            return matched[: CFG.max_anchors_for_vote]
        return discover_control_point_likes(
            entities, char_h, CFG.vote_radius_norm * char_h
        )[: CFG.max_anchors_for_vote]
    if matched:
        return matched[: CFG.max_anchors_for_vote]
    return []


def _seed_borehole_layer_roles(entities: list[dict]) -> dict[str, str]:
    """图层名直接定角色，不依赖文字形态。"""
    seeded: dict[str, str] = {}
    for e in entities:
        if str(e.get("shape_type") or "") != "text":
            continue
        layer = str(e.get("layer") or "")
        if not layer or layer == CFG.template_layer:
            continue
        if layer in seeded:
            continue
        role = seed_role_from_layer_name(layer)
        if role is None:
            continue
        if annotation_family(layer) != "borehole":
            continue
        seeded[layer] = role
    return seeded


def vote_layer_roles(
    anchors: list[dict],
    entities: list[dict],
    kind: str,
    vote_radius: float,
) -> tuple[dict[str, str], dict[str, int], list[float], Counter]:
    texts = [e for e in entities if str(e.get("shape_type") or "") == "text"]
    layer_role_counts: dict[str, Counter] = defaultdict(Counter)
    distances: list[float] = []
    role_counts: Counter = Counter()

    for anchor in anchors:
        local: list[tuple[float, dict, str]] = []
        for t in texts:
            d = dist(anchor, t)
            if d > vote_radius:
                continue
            layer = str(t.get("layer") or "")
            # 测点投票不要吃掉煤层/钻孔图层；钻孔投票不要吃掉控制点图层
            if kind == "control_point" and is_borehole_layer(layer):
                continue
            if kind == "borehole" and is_control_point_layer(layer):
                continue
            role = classify_text_role(t.get("text", ""), layer)
            if not role_allowed_for_cluster(kind, role):
                continue
            if not layer or layer == CFG.template_layer:
                continue
            local.append((d, t, role))
        by_role: dict[str, list[tuple[float, dict, str]]] = defaultdict(list)
        for item in local:
            by_role[item[2]].append(item)
        kept = []
        caps = dict(CFG.max_members)
        for role, items in by_role.items():
            items.sort(key=lambda x: x[0])
            kept.extend(items[: caps.get(role, 2)])
        for d, t, role in kept:
            layer = str(t.get("layer") or "")
            layer_role_counts[layer][role] += 1
            distances.append(d)
            role_counts[role] += 1

    layer_roles: dict[str, str] = {}
    layer_scores: dict[str, int] = {}
    for layer, counts in layer_role_counts.items():
        total = sum(counts.values())
        if total < CFG.min_layer_hits:
            continue
        role, n = counts.most_common(1)[0]
        if n / total >= CFG.min_role_purity:
            layer_roles[layer] = role
            layer_scores[layer] = total

    # 钻孔：投票常因单层样本少而得不到 layer_roles，用图层名补全
    if kind == "borehole":
        for layer, role in _seed_borehole_layer_roles(entities).items():
            if layer not in layer_roles:
                layer_roles[layer] = role
                layer_scores[layer] = max(layer_scores.get(layer, 0), 1)
    return layer_roles, layer_scores, distances, role_counts


def build_rulepack(templates_doc: dict, entities: list[dict]) -> dict:
    char_h = median_char_height(
        entities, fallback=float(templates_doc.get("legend_median_char_height") or CFG.fallback_char_height)
    )
    templates = templates_doc["templates"]
    kinds = {}
    scores: dict[str, dict[str, int]] = {}
    for kind in ("control_point", "borehole"):
        tmpl = flatten_kind_template(templates[kind])
        vote_norm = (
            CFG.borehole_vote_radius_norm if kind == "borehole" else CFG.vote_radius_norm
        )
        vote_radius = vote_norm * char_h
        anchors = collect_anchors(entities, tmpl, kind, char_h)
        layer_roles, layer_scores, distances, role_counts = vote_layer_roles(
            anchors, entities, kind, vote_radius
        )
        scores[kind] = layer_scores
        if distances:
            learned_r = percentile(distances, CFG.distance_percentile)
            floor = (
                CFG.control_search_floor_norm * char_h
                if kind == "control_point"
                else CFG.borehole_search_floor_norm * char_h
            )
            search_radius = max(learned_r * 1.15, floor)
        else:
            search_radius = float(tmpl.get("search_radius_norm") or 7.0) * char_h
        cap = (
            CFG.control_search_cap_norm * char_h
            if kind == "control_point"
            else CFG.borehole_search_cap_norm * char_h
        )
        search_radius = min(search_radius, cap)
        r_norm = search_radius / max(char_h, 1e-6)

        kinds[kind] = {
            "kind": kind,
            "captions": tmpl.get("captions") or [],
            "symbol": {"shape_type": "point-like"},
            "fields": tmpl.get("fields") or [],
            "separators": tmpl.get("separators") or [],
            "variants": tmpl.get("variants") or [],
            "search_radius": round(search_radius, 4),
            "search_radius_norm": round(r_norm, 4),
            "layer_roles": layer_roles,
            "anchor_count": len(anchors),
            "role_counts": dict(role_counts),
            "max_members": dict(CFG.max_members),
        }

    shared = set(scores.get("control_point", {})) & set(scores.get("borehole", {}))
    for layer in shared:
        # 钻孔族图层一律归钻孔，不和测点抢
        if is_borehole_layer(layer):
            kinds["control_point"]["layer_roles"].pop(layer, None)
            continue
        if is_control_point_layer(layer):
            kinds["borehole"]["layer_roles"].pop(layer, None)
            continue
        c_score = scores["control_point"].get(layer, 0)
        b_score = scores["borehole"].get(layer, 0)
        if b_score >= c_score:
            kinds["control_point"]["layer_roles"].pop(layer, None)
        if c_score > b_score:
            kinds["borehole"]["layer_roles"].pop(layer, None)

    return {
        "source_dxf": templates_doc.get("source_dxf"),
        "median_char_height": char_h,
        "step1a_config": CFG.to_json(),
        "kinds": kinds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap retrieval_rules to a standalone JSON file")
    parser.add_argument("--stem", type=str, default=CFG.default_stem)
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="override product directory (default: step1a/output)",
    )
    parser.add_argument(
        "--graph-pkl",
        type=str,
        default="",
        help="override retrieved_elements_graph.pkl",
    )
    parser.add_argument(
        "--templates-json",
        type=str,
        default="",
        help="override retrieval_templates.json",
    )
    args = parser.parse_args()
    out = args.output_dir or None

    graph_path = (
        Path(args.graph_pkl)
        if args.graph_pkl
        else retrieved_elements_graph_pkl(args.stem, out)
    )
    templates_path = (
        Path(args.templates_json)
        if args.templates_json
        else retrieval_templates_json(args.stem, out)
    )
    graph = load_graph(graph_path)
    templates_doc = load_json_doc(templates_path)
    if not isinstance(templates_doc, dict) or "templates" not in templates_doc:
        raise RuntimeError(f"invalid retrieval_templates: {templates_path}")

    template_layer = str(graph.graph.get("template_layer") or CFG.template_layer)
    entities = annotation_records(graph, exclude_layers={template_layer})
    print(f"entities: {len(entities)}")
    pack = build_rulepack(templates_doc, entities)
    if not pack.get("source_dxf"):
        pack["source_dxf"] = graph.graph.get("source_dxf")
    pack["stem"] = args.stem

    out_json = retrieval_rules_json(args.stem, out)
    save_json_doc(pack, out_json)

    print(f"input_graph: {graph_path}")
    print(f"input_templates: {templates_path}")
    print(f"output_json: {out_json}")
    print(f"median_char_height: {pack['median_char_height']}")
    for kind, info in pack["kinds"].items():
        n_var = len(info.get("variants") or [])
        n_sep = len(info.get("separators") or [])
        print(
            f"  {kind}: anchors={info['anchor_count']} "
            f"variants={n_var} separators={n_sep} "
            f"R={info['search_radius']:.2f} layers={len(info['layer_roles'])}"
        )
        for layer, role in sorted(info["layer_roles"].items(), key=lambda x: x[0]):
            print(f"    {layer} -> {role}")


if __name__ == "__main__":
    main()
