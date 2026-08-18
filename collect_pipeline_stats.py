from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {"value": data}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def inject_stats(path: Path, stats: dict[str, Any]) -> None:
    doc = load_json(path)
    if doc is None:
        return
    doc["stats"] = stats
    graph = doc.get("graph")
    if isinstance(graph, dict):
        graph["stats"] = stats
    save_json(path, doc)


def expected_paths(stem: str, out_root: Path) -> dict[str, Path]:
    return {
        "final_cluster": out_root / "714-stage1" / f"{stem}-final_cluster.json",
        "structure_with_texts": out_root / "714-stage1" / f"{stem}-structure_graph_with_texts.json",
        "facility_graph": out_root / "714-stage2" / f"{stem}-facility_graph.json",
        "structure_with_facilities": out_root / "714-stage2" / f"{stem}-structure_graph_with_facilities.json",
        "parallel_graph_summary": out_root
        / "529-stage2"
        / "step2B"
        / "output"
        / f"{stem}_parallel_graph_summary.json",
        "centerline_summary": out_root
        / "529-stage3"
        / "step3A"
        / "output"
        / f"{stem}_centerline_graph_summary.json",
        "residual_summary": out_root
        / "529-stage3"
        / "step3B"
        / "output"
        / f"{stem}_residual_graph_summary.json",
        "centerline_fix": out_root
        / "529-stage3"
        / "step3B"
        / "output"
        / f"{stem}_centerline_fix.json",
        "attached_regions": out_root / "529-stage4" / f"{stem}_attached_regions.json",
        "structure_graph": out_root / "529-stage4" / f"{stem}_structure_graph.json",
    }


def has_any_stage_artifact(stem: str, out_root: Path) -> bool:
    return any(p.is_file() for p in expected_paths(stem, out_root).values())


def build_stats(stem: str, out_root: Path) -> dict[str, Any]:
    p = expected_paths(stem, out_root)
    docs = {k: load_json(v) for k, v in p.items()}

    final_graph = (docs["final_cluster"] or {}).get("graph", {})
    final_summary = {
        "cluster_summary": final_graph.get("cluster_summary", {}),
        "filter_stats": final_graph.get("filter_stats", {}),
    }

    text_graph = (docs["structure_with_texts"] or {}).get("graph", {})
    text_summary = {
        "attach_summary": text_graph.get("attach_summary", {}),
        "role_counts": text_graph.get("role_counts", {}),
        "edge_counts": text_graph.get("edge_counts", {}),
    }

    facility_graph = (docs["facility_graph"] or {}).get("graph", {})
    facility_summary = {
        "facility_summary": facility_graph.get("facility_summary", {}),
    }

    fused_graph = (docs["structure_with_facilities"] or {}).get("graph", {})
    facility_attach_summary = {
        "facility_attach_summary": fused_graph.get("facility_attach_summary", {}),
    }

    parallel_summary = docs["parallel_graph_summary"] or {}
    centerline_summary = docs["centerline_summary"] or {}
    residual_summary = docs["residual_summary"] or {}
    centerline_fix = docs["centerline_fix"] or {}
    attached_regions = docs["attached_regions"] or {}
    structure_graph = docs["structure_graph"] or {}

    stage_714_1 = {
        "final_cluster": final_summary,
        "structure_with_texts": text_summary,
    }
    stage_714_2 = {
        "facility_graph": facility_summary,
        "structure_with_facilities": facility_attach_summary,
    }
    stage_529_2 = {
        "parallel_graph_summary": {
            "node_count": parallel_summary.get("node_count"),
            "edge_count": parallel_summary.get("edge_count"),
            "wall_count": parallel_summary.get("wall_count"),
            "stub_count": parallel_summary.get("stub_count"),
            "parallel_group_count": parallel_summary.get("parallel_group_count"),
            "estimated_corridor_width": parallel_summary.get("estimated_corridor_width"),
        }
    }
    stage_529_3 = {
        "centerline_graph_summary": {
            "node_count": centerline_summary.get("node_count"),
            "edge_count": centerline_summary.get("edge_count"),
            "endpoint_edge_count": centerline_summary.get("endpoint_edge_count"),
            "parallel_edge_count": centerline_summary.get("parallel_edge_count"),
            "corridor_count": centerline_summary.get("corridor_count"),
            "parallel_group_count": centerline_summary.get("parallel_group_count"),
            "median_corridor_width": centerline_summary.get("median_corridor_width"),
        },
        "residual_graph_summary": {
            "node_count": residual_summary.get("node_count"),
            "edge_count": residual_summary.get("edge_count"),
            "stub_count": residual_summary.get("stub_count"),
            "wall_count": residual_summary.get("wall_count"),
            "edge_counts": residual_summary.get("edge_counts"),
        },
        "centerline_fix": {
            "promoted_count": centerline_fix.get("promoted_count"),
            "deferred_count": centerline_fix.get("deferred_count"),
            "corridor_extensions": centerline_fix.get("corridor_extensions"),
            "corridor_synthesized": centerline_fix.get("corridor_synthesized"),
        },
    }
    stage_529_4 = {
        "attached_regions": {
            "stub_count": attached_regions.get("stub_count"),
            "semantic_counts": attached_regions.get("semantic_counts", {}),
        },
        "structure_graph": {
            "kind": structure_graph.get("kind"),
            "node_count": len(structure_graph.get("nodes") or []),
            "edge_count": len(structure_graph.get("edges") or []),
        },
    }

    # 回填各产物 stats 字段
    inject_stats(p["final_cluster"], final_summary)
    inject_stats(p["structure_with_texts"], text_summary)
    inject_stats(p["facility_graph"], facility_summary)
    inject_stats(p["structure_with_facilities"], facility_attach_summary)
    inject_stats(p["parallel_graph_summary"], stage_529_2["parallel_graph_summary"])
    inject_stats(p["centerline_summary"], stage_529_3["centerline_graph_summary"])
    inject_stats(p["residual_summary"], stage_529_3["residual_graph_summary"])
    inject_stats(p["centerline_fix"], stage_529_3["centerline_fix"])
    inject_stats(p["attached_regions"], stage_529_4["attached_regions"])
    inject_stats(p["structure_graph"], stage_529_4["structure_graph"])

    return {
        "stem": stem,
        "stats": {
            "529-stage2": stage_529_2,
            "529-stage3": stage_529_3,
            "529-stage4": stage_529_4,
            "714-stage1": stage_714_1,
            "714-stage2": stage_714_2,
        },
    }


def _stem_sort_key(stem: str) -> tuple[int, str]:
    return (0, f"{int(stem):06d}") if stem.isdigit() else (1, stem)


def discover_output_dirs(root: Path) -> list[tuple[str, Path]]:
    """仅发现 root 下一层形如 {stem}_output 且含阶段产物的目录（不递归）。"""
    found: list[tuple[str, Path]] = []
    for out_dir in sorted(root.glob("*_output")):
        if not out_dir.is_dir():
            continue
        stem = out_dir.name[: -len("_output")]
        if not stem:
            continue
        resolved = out_dir.resolve()
        if not has_any_stage_artifact(stem, resolved):
            continue
        found.append((stem, resolved))
    return sorted(found, key=lambda item: (_stem_sort_key(item[0]), str(item[1])))


def collect_one(stem: str, out_root: Path) -> dict[str, Any]:
    payload = build_stats(stem, out_root)
    out_path = out_root / f"{stem}_pipeline_stats.json"
    save_json(out_path, payload)
    print(f"[stats] {stem} -> {out_path}")
    return {
        "stem": stem,
        "output_root": str(out_root),
        "pipeline_stats": str(out_path),
        "stats": payload["stats"],
    }


def collect_all(root: Path, summary_path: Path) -> dict[str, Any]:
    drawings: list[dict[str, Any]] = []
    for stem, out_root in discover_output_dirs(root):
        drawings.append(collect_one(stem, out_root))
    summary = {
        "root": str(root.resolve()),
        "drawing_count": len(drawings),
        "drawings": drawings,
    }
    save_json(summary_path, summary)
    print(f"[summary] {len(drawings)} drawings -> {summary_path}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Collect and inject pipeline stats. "
            "With no args: discover ./xx_output (non-recursive) and write ./output_summary.json"
        )
    )
    parser.add_argument("--stem", default=None, help="drawing stem (single-drawing mode)")
    parser.add_argument(
        "--output-root",
        default=None,
        type=Path,
        help="{stem}_output directory (single-drawing mode)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="search root for *_output (batch mode; default: cwd)",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=None,
        help="merged summary path (batch mode; default: ./output_summary.json)",
    )
    args = parser.parse_args()

    if (args.stem is None) ^ (args.output_root is None):
        parser.error("single-drawing mode requires both --stem and --output-root")

    if args.stem is not None and args.output_root is not None:
        out_root = args.output_root
        if not out_root.is_absolute():
            out_root = (Path.cwd() / out_root).resolve()
        collect_one(args.stem, out_root)
        return

    root = args.root if args.root is not None else Path.cwd()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    summary_path = (
        args.summary_out
        if args.summary_out is not None
        else Path.cwd() / "output_summary.json"
    )
    if not summary_path.is_absolute():
        summary_path = (Path.cwd() / summary_path).resolve()
    collect_all(root, summary_path)


if __name__ == "__main__":
    main()
