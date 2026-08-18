"""step1a-4：候选簇按得分独占归属，输出最终簇图并绘制带巷道核对图。

用法（在仓库根目录）：
  python step1a/4_final_clusters.py --stem 2026.1-1part
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from config import (
    Step1aConfig,
    candidate_cluster_pkl,
    cluster_centers_png,
    corridor_json,
    final_cluster_json,
    final_cluster_pkl,
    final_cluster_png,
)
from filter_candidates import filter_candidates_to_final
from graph_io import load_graph, save_graph
from graph_nodes import annotation_records
from visualize_clusters import (
    clusters_for_visualize,
    load_corridor_entities,
    visualize,
    visualize_cluster_centers,
)

CFG = Step1aConfig()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter candidate clusters to exclusive final memberships by score"
    )
    parser.add_argument("--stem", type=str, default=CFG.default_part_stem)
    parser.add_argument(
        "--pkl",
        type=str,
        default="",
        help="override input candidate_cluster.pkl",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="override product directory (default: step1a/output)",
    )
    parser.add_argument(
        "--corridor-json",
        type=str,
        default="",
        help="override corridor geometry JSON for visualize",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="",
        help="directory for corridor JSON when --corridor-json omitted",
    )
    parser.add_argument(
        "--no-png",
        action="store_true",
        help="skip final_cluster verification PNG",
    )
    args = parser.parse_args()
    out = args.output_dir or None
    in_dir = args.input_dir or None

    in_path = Path(args.pkl) if args.pkl else candidate_cluster_pkl(args.stem, out)
    if not in_path.is_file():
        raise FileNotFoundError(f"candidate graph not found: {in_path}")

    graph = load_graph(in_path)
    if str(graph.graph.get("matching_stage") or "") == "final":
        print("warning: input already matching_stage=final; filtering again")

    filtered, stats = filter_candidates_to_final(graph, CFG)
    filtered.graph["stem"] = args.stem
    filtered.graph["step1a_config"] = CFG.to_json()
    filtered.graph["graph_name"] = "final_cluster"

    out_pkl = final_cluster_pkl(args.stem, out)
    out_json = final_cluster_json(args.stem, out)
    save_graph(filtered, out_pkl, out_json)

    template_layer = str(filtered.graph.get("template_layer") or CFG.template_layer)
    entities = annotation_records(filtered, exclude_layers={template_layer})
    clusters = clusters_for_visualize(filtered)

    if not args.no_png:
        corr_path = corridor_json(
            args.stem,
            CFG,
            base_dir=in_dir,
            path=args.corridor_json or None,
        )
        if not corr_path.is_file():
            raise FileNotFoundError(f"corridor file not found: {corr_path}")
        corridors = load_corridor_entities(corr_path)
        print(f"corridor: {corr_path} ({len(corridors)} entities)")

        out_png = final_cluster_png(args.stem, out)
        try:
            visualize(
                clusters,
                entities,
                out_png,
                corridors=corridors,
                title="final_cluster (final)",
                cfg=CFG,
            )
            print(f"png: {out_png}")
        except Exception as exc:
            print(f"visualize skipped: {exc}")

        centers_png = cluster_centers_png(args.stem, out)
        try:
            visualize_cluster_centers(
                filtered,
                centers_png,
                corridors=corridors,
                title="cluster_centers（识别出的锚点）",
                cfg=CFG,
            )
            print(f"cluster_centers_png: {centers_png}")
        except Exception as exc:
            print(f"cluster_centers visualize skipped: {exc}")

    print(f"input:  {in_path}")
    print(f"output: {out_pkl}")
    print(f"matching_stage: final")
    print(
        f"clusters: {stats['input_clusters']} candidate → "
        f"{stats['output_clusters']} final {stats['by_type']}"
    )
    print(f"memberships_dropped: {stats.get('memberships_dropped')}")
    print(f"clusters_dropped: {stats.get('clusters_dropped')}")
    print(f"members_rehomed: {stats.get('members_rehomed')}")
    print(f"members_unassigned: {stats.get('members_unassigned')}")
    print(f"duplicate_texts_absorbed: {stats.get('duplicate_texts_absorbed')}")
    if stats.get("candidate_members_unassigned"):
        print(
            f"warning: candidate_members_unassigned="
            f"{stats.get('candidate_members_unassigned')}"
        )
    for c in clusters:
        seen: set[str] = set()
        uniq: list[str] = []
        for m in c["members"]:
            text = m.get("text")
            if not text or text in seen:
                continue
            mid = m["id"]
            if filtered.nodes.get(mid, {}).get("duplicate_of"):
                continue
            seen.add(text)
            uniq.append(text)
       # print(
        #    f"  {c['cluster_type']} conf={c['confidence']} {uniq[:8]}"
        #)


if __name__ == "__main__":
    main()
