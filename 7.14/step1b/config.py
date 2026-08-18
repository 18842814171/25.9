"""step1b 顶层配置：阈值仅在此定义，子模块不得另行设定。"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.paths import project_root


@dataclass
class Step1bConfig:
    default_stem: str = "2026.1-1part"

    # 挂接距离：在剔除明显离群点后，取候选最近距离的分位数作为阈值
    # 离群上界 = outlier_cap_width_factor × 图面中位巷道宽度
    outlier_cap_width_factor: float = 4.0
    attach_distance_percentile: float = 90.0
    # 样本不足或结构图缺失中位宽度时的回退：系数 × 中位宽度
    attach_distance_width_factor: float = 2.5
    attach_distance_fallback: float = 12.0

    # 仅向这些角色的中心线挂接
    attach_centerline_roles: tuple[str, ...] = ("corridor", "auxiliary")

    # 核对图
    figure_dpi: int = 160
    figure_font_candidates: tuple[str, ...] = (
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "DengXian",
    )
    color_centerline_corridor: str = "#2ca02c"
    color_centerline_auxiliary: str = "#9467bd"
    # 原始巷道图元（-巷道.json）
    color_corridor_entities: str = "#000000"
    # 残余结构：洞室与其它
    color_structure_niche: str = "#00BFFF"
    color_structure_other: str = "#bbbbbb"
    color_control_point: str = "#1f77b4"
    color_borehole: str = "#d62728"
    color_corridor_label: str = "#ff7f0e"
    color_attach_edge: str = "#444444"
    centerline_linewidth: float = 1.2
    structure_linewidth: float = 0.6
    structure_niche_linewidth: float = 0.9
    corridor_entity_linewidth: float = 0.8
    attach_edge_linewidth: float = 0.5
    corridor_json_template: str = "{stem}-巷道.json"

    def to_json(self) -> dict:
        data = asdict(self)
        data["attach_centerline_roles"] = list(self.attach_centerline_roles)
        data["figure_font_candidates"] = list(self.figure_font_candidates)
        return data


def step1b_dir() -> Path:
    return project_root() / "step1b"


def output_dir(out_dir: Path | str | None = None) -> Path:
    path = Path(out_dir) if out_dir is not None else (step1b_dir() / "output")
    if not path.is_absolute():
        path = project_root() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def step1a_output_dir(out_dir: Path | str | None = None) -> Path:
    if out_dir is not None:
        return output_dir(out_dir)
    return project_root() / "step1a" / "output"


def final_cluster_pkl(
    stem: str,
    *,
    step1a_out: Path | str | None = None,
) -> Path:
    return step1a_output_dir(step1a_out) / f"{stem}-final_cluster.pkl"


def structure_graph_with_texts_pkl(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-structure_graph_with_texts.pkl"


def structure_graph_with_texts_json(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-structure_graph_with_texts.json"


def structure_graph_with_texts_png(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-structure_graph_with_texts.png"
