"""step1a 顶层配置：阈值仅在此定义，子模块不得另行设定。"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.paths import project_root


@dataclass
class Step1aConfig:
    default_stem: str = "2026.1-1"
    default_part_stem: str = "2026.1-1part"
    template_layer: str = "图例"

    # 图层排除名单：名称全等或含下列子串 → 强制「其他类」，且不进入标注关系图
    # （明显不属于测点 / 钻孔 / 煤层标注的装饰、地物、管线等）
    layer_exclude_names: tuple[str, ...] = ()
    layer_exclude_tokens: tuple[str, ...] = (
        "树",
        "灌木",
        "植被",
        "工业广场",
        "房屋",
        "地物",
        "电力线",
        "通信线",
        "河流",
        "格网",
        "通风设施",
        "采空区",
        "断层",
        "井田边界",
        "水源井",
        "小柱状",
        "消防",
    )

    symbol_probe_norm: float = 6.0
    field_radius_norm: float = 6.0
    search_radius_cap_norm: float = 8.0
    seed_max_len: int = 24
    fallback_char_height: float = 10.0

    # 标注关系图：文字与圆/块符号之间的邻接半径（字高倍数）
    adjacency_radius_norm: float = 5.0
    # 文字–文字：邻近边、朝向一致边（字高倍数 / 角度容差）
    text_proximity_norm: float = 3.0
    text_parallel_norm: float = 3.0
    text_parallel_angle_tol_deg: float = 5.0

    # 候选匹配：距离衰减两阶（相对识别规则中的搜索半径）
    distance_tier1_ratio: float = 0.9
    distance_tier2_ratio: float = 1.0
    distance_tier2_factor: float = 0.5
    # 一阶半径内文字组↔圆双向各保留最近 K 个，仅互选才连线
    match_top_k: int = 3

    # 完整测点候选：图层 / 距离 / 文字方向 三小分权重（须归一）
    score_weight_layer: float = 0.4
    score_weight_distance: float = 0.4
    score_weight_orientation: float = 0.2
    orientation_tolerance_deg: float = 25.0
    # 字–值 / 值–值绑定（测点）：配置值为下限（字高倍数）；实际上限由本图同类邻域距离统计推断
    bind_id_value_norm: float = 1.5
    bind_value_value_norm: float = 1.5
    bind_learn_probe_norm: float = 12.0
    bind_distance_percentile: float = 90.0
    #XJH系列：6，4；2026系列：3，2
    bind_id_value_cap_norm: float = 3.0
    bind_value_value_cap_norm: float = 2.0
    # 绑定组距离置信度：相对本图推断半径 R
    # 一阶 [0, tier1_ratio*R] 正常衰减；二阶 (tier1, R] 再乘 tier2_factor
    bind_tier1_ratio: float = 0.7
    bind_tier2_factor: float = 0.5
    # 密集区：候选对附近出现其它竞争编号/高程时惩罚；低于阈值的边不入组
    bind_density_penalty: float = 0.35
    min_bind_link_confidence: float = 0.35
    min_bind_group_confidence: float = 0.30
    # 测点：每编号最多收纳高程数（与 max_members.elevation 对齐意图）
    bind_max_values_per_id: int = 2
    # 字–线–字：line-like 长度相对邻近文字跨度的比值容差；距离用 id–值推断半径
    bind_line_length_ratio_lo: float = 0.5
    bind_line_length_ratio_hi: float = 2.5
    # 文字到分隔线中点的距离相对绑定半径的放宽倍数（标高常偏在线一端）
    bind_line_dist_slack: float = 1.25
    # 钻孔绑定：同族文字对等联结，不分编号/数值席位；半径为字高倍数
    borehole_bind_floor_norm: float = 2.5
    borehole_bind_cap_norm: float = 7.0
    # 孤立孔号并入最近煤厚/标高绑定组的最大距离（字高倍数）
    borehole_id_attach_norm: float = 7.0
    # 钻孔密集区：每个文字只保留最近 K 条高置信绑定边，抑制串成超大组
    borehole_bind_top_k: int = 3

    max_anchors_for_vote: int = 300
    vote_radius_norm: float = 8.0
    borehole_vote_radius_norm: float = 12.0
    min_layer_hits: int = 3
    min_role_purity: float = 0.55
    control_search_floor_norm: float = 3.0
    borehole_search_floor_norm: float = 10.0
    control_search_cap_norm: float = 7.0
    borehole_search_cap_norm: float = 18.0
    distance_percentile: float = 92.0

    # 最终过滤：候选多关联按 score_total 独占；低于此置信度的组丢弃
    min_final_confidence: float = 0.0
    # 与已入组孔号/测点号同文且距离 < 系数×字高 的孤立文字并入该组（避免再当巷道名）
    duplicate_id_text_norm: float = 1.5

    max_members: dict[str, int] = field(
        default_factory=lambda: {
            "point_id": 1,
            "elevation": 2,
            "borehole_id": 1,
            "collar": 1,
            "seam_value": 40,
        }
    )

    figure_dpi: int = 160
    figure_font_candidates: tuple[str, ...] = (
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "DengXian",
    )
    color_control_point: str = "#1f77b4"
    color_borehole: str = "#d62728"
    color_unassigned: str = "#cccccc"
    color_corridor: str = "#2ca02c"
    corridor_linewidth: float = 0.8
    corridor_json_template: str = "{stem}-巷道.json"
    # 核对图视野：按主体分位数裁切，避免远距飞点把整图挤到一角
    view_percentile_low: float = 1.0
    view_percentile_high: float = 99.0
    view_pad_ratio: float = 0.04

    def to_json(self) -> dict:
        data = asdict(self)
        data["figure_font_candidates"] = list(self.figure_font_candidates)
        data["layer_exclude_names"] = list(self.layer_exclude_names)
        data["layer_exclude_tokens"] = list(self.layer_exclude_tokens)
        return data


def step1a_dir() -> Path:
    return project_root() / "step1a"


def output_dir(out_dir: Path | str | None = None) -> Path:
    path = Path(out_dir) if out_dir is not None else (step1a_dir() / "output")
    if not path.is_absolute():
        path = project_root() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def retrieved_elements_graph_pkl(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-retrieved_elements_graph.pkl"


def retrieved_elements_graph_json(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-retrieved_elements_graph.json"


def bind_chains_png(stem: str, out_dir: Path | str | None = None) -> Path:
    """Script 0 stage check: id–value / value–value bind chains (pre-circle)."""
    return output_dir(out_dir) / f"{stem}-bind_chains.png"


def cluster_centers_png(stem: str, out_dir: Path | str | None = None) -> Path:
    """Script 3/4 stage check: identified cluster anchors (point-like centers)."""
    return output_dir(out_dir) / f"{stem}-cluster_centers.png"


def retrieval_templates_json(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-retrieval_templates.json"


def retrieval_rules_json(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-retrieval_rules.json"


def candidate_cluster_pkl(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-candidate_cluster.pkl"


def candidate_cluster_json(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-candidate_cluster.json"


def candidate_cluster_png(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-candidate_cluster.png"


def final_cluster_pkl(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-final_cluster.pkl"


def final_cluster_json(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-final_cluster.json"


def final_cluster_png(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-final_cluster.png"


def corridor_json(
    stem: str,
    cfg: Step1aConfig | None = None,
    *,
    base_dir: Path | str | None = None,
    path: Path | str | None = None,
) -> Path:
    if path is not None:
        p = Path(path)
        if not p.is_absolute():
            p = project_root() / p
        return p
    cfg = cfg or Step1aConfig()
    name = cfg.corridor_json_template.format(stem=stem)
    root = Path(base_dir) if base_dir is not None else project_root()
    if not root.is_absolute():
        root = project_root() / root
    return root / name
