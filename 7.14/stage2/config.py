"""stage2 顶层配置：阈值仅在此定义，子模块不得另行设定。"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.paths import project_root


@dataclass
class Stage2Config:
    default_stem: str = "2026.1-1"
    facility_layer: str = "通风设施"
    template_layer: str = "图例"
    fallback_char_height: float = 10.0

    # 从根目录 elements JSON 筛选的图元类型（含块参照与填充）
    primitive_entity_types: tuple[str, ...] = (
        "LINE",
        "LWPOLYLINE",
        "POLYLINE",
        "ARC",
        "CIRCLE",
        "HATCH",
        "INSERT",
        "TEXT",
        "MTEXT",
    )

    # 端点连接（初始建图）：相对设施尺寸中位数
    endpoint_join_tol_factor: float = 0.35
    endpoint_join_tol_floor: float = 0.5
    # 无开端点的图元（填充、块、圆、字）并入最近线划的半径系数
    orphan_near_tol_factor: float = 1.2
    orphan_near_tol_floor: float = 1.5

    # 单组成员数上限（防止图框等大片连通）
    max_cluster_members: int = 40

    # 关联（与第一阶段乙同类统计规则）
    outlier_cap_width_factor: float = 4.0
    attach_distance_percentile: float = 90.0
    attach_distance_width_factor: float = 2.5
    attach_distance_fallback: float = 12.0
    attach_centerline_roles: tuple[str, ...] = ("corridor", "auxiliary")

    figure_dpi: int = 160
    figure_font_candidates: tuple[str, ...] = (
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "DengXian",
    )
    color_centerline: str = "#2ca02c"
    color_centerline_auxiliary: str = "#9467bd"
    color_structure_niche: str = "#00BFFF"
    color_structure_other: str = "#bbbbbb"
    color_attach_edge: str = "#444444"
    color_corridor: str = "#000000"
    color_control_point: str = "#1f77b4"
    color_borehole: str = "#d62728"
    color_corridor_label: str = "#ff7f0e"
    color_primitive: str = "#cccccc"
    corridor_linewidth: float = 0.8
    corridor_json_template: str = "{stem}-巷道.json"
    color_facility_default: str = "#e377c2"
    centerline_linewidth: float = 1.0
    attach_edge_linewidth: float = 0.5
    facility_marker_size: float = 10.0
    facility_stroke_linewidth: float = 1.6
    facility_hatch_alpha: float = 0.55

    def to_json(self) -> dict:
        data = asdict(self)
        data["primitive_entity_types"] = list(self.primitive_entity_types)
        data["attach_centerline_roles"] = list(self.attach_centerline_roles)
        data["figure_font_candidates"] = list(self.figure_font_candidates)
        return data


def stage2_dir() -> Path:
    return Path(__file__).resolve().parent


def output_dir(out_dir: Path | str | None = None) -> Path:
    path = Path(out_dir) if out_dir is not None else (stage2_dir() / "output")
    if not path.is_absolute():
        path = project_root() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def corridor_json(
    stem: str,
    cfg: Stage2Config | None = None,
    *,
    base_dir: Path | str | None = None,
    path: Path | str | None = None,
) -> Path:
    if path is not None:
        p = Path(path)
        if not p.is_absolute():
            p = project_root() / p
        return p
    cfg = cfg or Stage2Config()
    name = cfg.corridor_json_template.format(stem=stem)
    repo_root = project_root()
    workspace_root = repo_root.parent
    root = Path(base_dir) if base_dir is not None else repo_root
    if not root.is_absolute():
        root = repo_root / root
    candidates = [
        root / name,
        repo_root / name,
        workspace_root / name,
        workspace_root / "test_input" / name,
        repo_root / name,
        workspace_root / "7.14" / name,
        workspace_root / "5.29" / name,
        workspace_root / "5.29" / "step2A" / "raw" / name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def facility_primitives_graph_pkl(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-facility_primitives_graph.pkl"


def facility_primitives_graph_json(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-facility_primitives_graph.json"


def facility_graph_pkl(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-facility_graph.pkl"


def facility_graph_json(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-facility_graph.json"


def facility_graph_png(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-facility_graph.png"


def structure_graph_with_facilities_pkl(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-structure_graph_with_facilities.pkl"


def structure_graph_with_facilities_json(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-structure_graph_with_facilities.json"


def structure_graph_with_facilities_png(stem: str, out_dir: Path | str | None = None) -> Path:
    return output_dir(out_dir) / f"{stem}-structure_graph_with_facilities.png"
