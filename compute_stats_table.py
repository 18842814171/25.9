"""从各样本 xx_output/xx_pipeline_stats.json 汇总《统计表》可计算指标。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else None


def discover_pipeline_stats(root: Path) -> list[tuple[str, Path, dict[str, Any]]]:
    """查找 root 下形如 {stem}_output/{stem}_pipeline_stats.json 的文件。"""
    found: list[tuple[str, Path, dict[str, Any]]] = []
    for out_dir in root.rglob("*_output"):
        if not out_dir.is_dir():
            continue
        stem = out_dir.name[: -len("_output")]
        path = out_dir / f"{stem}_pipeline_stats.json"
        doc = load_json(path)
        if doc is None:
            continue
        found.append((stem, path, doc))

    def _stem_key(item: tuple[str, Path, dict[str, Any]]) -> tuple[int, str]:
        stem = item[0]
        return (0, f"{int(stem):06d}") if stem.isdigit() else (1, stem)

    return sorted(found, key=_stem_key)


def _num(v: Any) -> float:
    if isinstance(v, bool) or v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return 0.0


def _get(d: Any, *keys: str, default: Any = None) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def aggregate(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """对各样本 stats 做求和；宽度类字段另记均值。"""
    sum_paths: list[tuple[str, tuple[str, ...]]] = [
        # 表4-2-3
        ("并行图节点数", ("529-stage2", "parallel_graph_summary", "node_count")),
        ("并行图边数", ("529-stage2", "parallel_graph_summary", "edge_count")),
        ("并行图墙体段数", ("529-stage2", "parallel_graph_summary", "wall_count")),
        ("墙体端头stub数", ("529-stage2", "parallel_graph_summary", "stub_count")),
        ("并行图平行组数", ("529-stage2", "parallel_graph_summary", "parallel_group_count")),
        # 表4-3-2
        ("延伸的原有中心线", ("529-stage3", "centerline_fix", "corridor_extensions")),
        ("新生成中心线", ("529-stage3", "centerline_fix", "corridor_synthesized")),
        ("提升为主墙数promoted", ("529-stage3", "centerline_fix", "promoted_count")),
        ("延后处理数deferred", ("529-stage3", "centerline_fix", "deferred_count")),
        ("中心线图节点数", ("529-stage3", "centerline_graph_summary", "node_count")),
        ("中心线图边数", ("529-stage3", "centerline_graph_summary", "edge_count")),
        ("端点连接边数", ("529-stage3", "centerline_graph_summary", "endpoint_edge_count")),
        ("平行配对边数", ("529-stage3", "centerline_graph_summary", "parallel_edge_count")),
        ("中心线候选走廊数", ("529-stage3", "centerline_graph_summary", "corridor_count")),
        ("中心线平行组数", ("529-stage3", "centerline_graph_summary", "parallel_group_count")),
        # 表4-3-3
        ("辅巷道(语义)", ("529-stage4", "attached_regions", "semantic_counts", "AUXILIARY_CORRIDOR")),
        ("躲避洞(语义)", ("529-stage4", "attached_regions", "semantic_counts", "NICHE")),
        ("候选主墙(语义)", ("529-stage4", "attached_regions", "semantic_counts", "POSSIBLE_CORRIDOR_WALL")),
        ("未分类线段(语义)", ("529-stage4", "attached_regions", "semantic_counts", "UNCLASSIFIED")),
        ("残余结构stub数", ("529-stage3", "residual_graph_summary", "stub_count")),
        ("残余结构图边数", ("529-stage3", "residual_graph_summary", "edge_count")),
        ("stub-stub接触边", ("529-stage3", "residual_graph_summary", "edge_counts", "stub-stub-touch")),
        ("corridor-stub接触边", ("529-stage3", "residual_graph_summary", "edge_counts", "corridor-stub-touch")),
        ("stub-stub平行边", ("529-stage3", "residual_graph_summary", "edge_counts", "stub-stub-parallel")),
        ("corridor-stub平行边", ("529-stage3", "residual_graph_summary", "edge_counts", "corridor-stub-parallel")),
        ("最终结构节点", ("529-stage4", "structure_graph", "node_count")),
        ("最终结构边数", ("529-stage4", "structure_graph", "edge_count")),
        # role_counts（抽样真值，供 F1）
        ("主巷道corridor", ("714-stage1", "structure_with_texts", "role_counts", "corridor")),
        ("辅巷道auxiliary", ("714-stage1", "structure_with_texts", "role_counts", "auxiliary")),
        ("洞室niche", ("714-stage1", "structure_with_texts", "role_counts", "niche")),
        ("未分类unclassified", ("714-stage1", "structure_with_texts", "role_counts", "unclassified")),
        # 表4-4-3
        ("最终组", ("714-stage1", "final_cluster", "cluster_summary", "cluster_count")),
        ("最终控制点", ("714-stage1", "final_cluster", "cluster_summary", "by_type", "控制点")),
        ("最终钻孔", ("714-stage1", "final_cluster", "cluster_summary", "by_type", "钻孔")),
        ("删除重复成员关联记录", ("714-stage1", "final_cluster", "filter_stats", "memberships_dropped")),
        ("删除重复文字", ("714-stage1", "final_cluster", "filter_stats", "duplicate_texts_absorbed")),
        ("重新关联成员数", ("714-stage1", "final_cluster", "filter_stats", "members_rehomed")),
        ("未关联成员数", ("714-stage1", "final_cluster", "filter_stats", "members_unassigned")),
        ("候选成员未关联数", ("714-stage1", "final_cluster", "filter_stats", "candidate_members_unassigned")),
        # 表4-4-4
        ("成功关联的控制点", ("714-stage1", "structure_with_texts", "attach_summary", "attached", "控制点")),
        ("成功关联的钻孔", ("714-stage1", "structure_with_texts", "attach_summary", "attached", "钻孔")),
        ("成功关联的巷道名称", ("714-stage1", "structure_with_texts", "attach_summary", "attached", "巷道名称")),
        ("超阈值未关联", ("714-stage1", "structure_with_texts", "attach_summary", "skipped", "beyond_threshold")),
        ("缺失坐标未关联", ("714-stage1", "structure_with_texts", "attach_summary", "skipped", "missing_xy")),
        ("文本关联中心线候选数", ("714-stage1", "structure_with_texts", "attach_summary", "centerline_candidates")),
        ("endpoint-touch边", ("714-stage1", "structure_with_texts", "edge_counts", "endpoint-touch")),
        ("niche-connect边", ("714-stage1", "structure_with_texts", "edge_counts", "niche-connect")),
        ("crossbar-connect边", ("714-stage1", "structure_with_texts", "edge_counts", "crossbar-connect")),
        # 表4-4-6
        ("设施总数", ("714-stage2", "facility_graph", "facility_summary", "facility_count")),
        ("未分型设施", ("714-stage2", "facility_graph", "facility_summary", "by_type", "未分型")),
        ("行车风门", ("714-stage2", "facility_graph", "facility_summary", "by_type", "行车风门")),
        ("设施关联中心线候选数", ("714-stage2", "structure_with_facilities", "facility_attach_summary", "centerline_candidates")),
        ("超阈值未关联设施", ("714-stage2", "structure_with_facilities", "facility_attach_summary", "skipped", "beyond_threshold")),
        ("缺失坐标未关联设施", ("714-stage2", "structure_with_facilities", "facility_attach_summary", "skipped", "missing_xy")),
        ("设施ID冲突未关联", ("714-stage2", "structure_with_facilities", "facility_attach_summary", "skipped", "id_collision")),
    ]

    mean_paths: list[tuple[str, tuple[str, ...]]] = [
        ("估计巷道宽度均值", ("529-stage2", "parallel_graph_summary", "estimated_corridor_width")),
        ("中位巷道宽度约为", ("529-stage3", "centerline_graph_summary", "median_corridor_width")),
    ]

    sums: dict[str, float] = defaultdict(float)
    present: dict[str, int] = defaultdict(int)
    mean_acc: dict[str, list[float]] = defaultdict(list)

    attached_facility_total = 0.0
    for doc in docs:
        stats = doc.get("stats") or {}
        for label, path in sum_paths:
            v = _get(stats, *path)
            if v is None:
                continue
            sums[label] += _num(v)
            present[label] += 1
        for label, path in mean_paths:
            v = _get(stats, *path)
            if v is None:
                continue
            mean_acc[label].append(_num(v))
            present[label] += 1

        # 成功关联设施 = attached 各类之和
        attached = _get(
            stats,
            "714-stage2",
            "structure_with_facilities",
            "facility_attach_summary",
            "attached",
            default={},
        )
        if isinstance(attached, dict):
            attached_facility_total += sum(_num(x) for x in attached.values())
            present["成功关联设施"] += 1

    results: dict[str, Any] = {}
    for label, _ in sum_paths:
        if present[label]:
            results[label] = int(round(sums[label])) if sums[label] == int(sums[label]) else sums[label]
    for label, _ in mean_paths:
        xs = mean_acc[label]
        if xs:
            results[label] = round(sum(xs) / len(xs), 2)
    if present["成功关联设施"]:
        results["成功关联设施"] = int(round(attached_facility_total))
        results["未关联设施"] = int(
            results.get("设施总数", 0) - attached_facility_total
        )

    # 最终中心线（主+辅）≈ corridor + auxiliary
    if "主巷道corridor" in results and "辅巷道auxiliary" in results:
        results["最终中心线（主巷道+辅巷道）"] = (
            results["主巷道corridor"] + results["辅巷道auxiliary"]
        )

    return {"sums": results, "present_counts": dict(present)}


TABLE_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "表4-2-3  共线线段检测与合并相关统计数据（批处理汇总）",
        [
            "并行图节点数",
            "并行图边数",
            "并行图墙体段数",
            "墙体端头stub数",
            "并行图平行组数",
            "估计巷道宽度均值",
        ],
    ),
    (
        "表4-3-2  二次筛选巷道墙体统计数据（批处理汇总）",
        [
            "延伸的原有中心线",
            "新生成中心线",
            "提升为主墙数promoted",
            "延后处理数deferred",
            "中心线图节点数",
            "中心线图边数",
            "端点连接边数",
            "平行配对边数",
            "中心线候选走廊数",
            "中心线平行组数",
            "中位巷道宽度约为",
        ],
    ),
    (
        "表4-3-3  残余结构语义识别统计（批处理汇总）",
        [
            "辅巷道(语义)",
            "躲避洞(语义)",
            "候选主墙(语义)",
            "未分类线段(语义)",
            "主巷道corridor",
            "辅巷道auxiliary",
            "洞室niche",
            "未分类unclassified",
            "最终中心线（主巷道+辅巷道）",
            "最终结构节点",
            "残余结构stub数",
            "残余结构图边数",
            "stub-stub接触边",
            "corridor-stub接触边",
            "stub-stub平行边",
            "corridor-stub平行边",
            "最终结构边数",
        ],
    ),
    (
        "表4-4-3  最终标注结构图统计数据（批处理汇总）",
        [
            "最终组",
            "最终控制点",
            "最终钻孔",
            "删除重复成员关联记录",
            "删除重复文字",
            "重新关联成员数",
            "未关联成员数",
            "候选成员未关联数",
        ],
    ),
    (
        "表4-4-4  融合结构图统计数据（批处理汇总）",
        [
            "成功关联的控制点",
            "成功关联的钻孔",
            "成功关联的巷道名称",
            "超阈值未关联",
            "缺失坐标未关联",
            "文本关联中心线候选数",
            "endpoint-touch边",
            "niche-connect边",
            "crossbar-connect边",
        ],
    ),
    (
        "表4-4-6  融合结构图新增数据统计（批处理汇总）",
        [
            "设施总数",
            "成功关联设施",
            "未分型设施",
            "行车风门",
            "未关联设施",
            "设施关联中心线候选数",
            "超阈值未关联设施",
            "缺失坐标未关联设施",
            "设施ID冲突未关联",
        ],
    ),
]


def format_report(
    stems: list[str],
    paths: list[Path],
    agg: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("《统计表》批处理指标汇总")
    lines.append("=" * 40)
    lines.append(f"抽样样本数量\t{len(stems)}")
    lines.append(f"样本列表\t{', '.join(stems)}")
    lines.append("")
    lines.append("数据来源")
    lines.append("-" * 40)
    for stem, path in zip(stems, paths):
        lines.append(f"  {stem}\t{path}")
    lines.append("")

    results = agg["sums"]
    for title, keys in TABLE_SECTIONS:
        lines.append(title)
        lines.append("统计对象\t数量")
        for key in keys:
            if key in results:
                lines.append(f"{key}\t{results[key]}")
            else:
                lines.append(f"{key}\t(无数据)")
        lines.append("")

    lines.append("说明")
    lines.append("-" * 40)
    lines.append("计数类指标：各样本求和；宽度类指标：各样本算术平均。")
    lines.append("表4-2-1/4-2-2/4-4-1/4-4-5 等依赖整图中间产物，不在 pipeline_stats 中，本脚本不计算。")
    lines.append("role_counts（corridor/auxiliary/niche/巷道名称）可作为抽样真值 GT，供 F1 计算。")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="汇总 xx_output/xx_pipeline_stats.json，计算《统计表》批处理指标"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="搜索根目录（默认当前目录，递归查找 *_output/*_pipeline_stats.json）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="写出汇总文本路径（默认打印到 stdout；建议 统计表_批处理汇总.txt）",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="可选：写出机器可读 JSON 汇总",
    )
    args = parser.parse_args()

    root = args.root
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()

    items = discover_pipeline_stats(root)
    if not items:
        raise SystemExit(f"未找到任何 *_pipeline_stats.json（root={root}）")

    stems = [s for s, _, _ in items]
    paths = [p for _, p, _ in items]
    docs = [d for _, _, d in items]
    agg = aggregate(docs)
    report = format_report(stems, paths, agg)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"[compute_stats_table] -> {args.out}")
    else:
        print(report)

    if args.json_out:
        payload = {
            "sample_count": len(stems),
            "stems": stems,
            "sources": [str(p) for p in paths],
            "metrics": agg["sums"],
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        with args.json_out.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[compute_stats_table] json -> {args.json_out}")


if __name__ == "__main__":
    main()
