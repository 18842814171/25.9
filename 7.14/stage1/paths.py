"""Stage1 stem-based paths. Resolved from project root (7.14), not process cwd."""

from __future__ import annotations

from pathlib import Path

IN_SUBDIR = "in"
OUTPUT_SUBDIR = "output"


def project_root() -> Path:
    """Repository root: parent of stage1/."""
    return Path(__file__).resolve().parents[1]


def stage1_dir() -> Path:
    return project_root() / "stage1"


def stage1_in_dir() -> Path:
    return stage1_dir() / IN_SUBDIR


def stage1_output_dir(output_dir: Path | None = None) -> Path:
    if output_dir is not None:
        return output_dir
    return stage1_dir() / OUTPUT_SUBDIR


def text_export_json(stem: str) -> Path:
    return stage1_in_dir() / f"{stem}-文字.json"


def text_structure_graph_pkl(stem: str, output_dir: Path | None = None) -> Path:
    return stage1_output_dir(output_dir) / f"{stem}-text_structure_graph.pkl"


def text_structure_graph_json(stem: str, output_dir: Path | None = None) -> Path:
    return stage1_output_dir(output_dir) / f"{stem}-text_structure_graph.json"


def text_final_cluster_pkl(stem: str, output_dir: Path | None = None) -> Path:
    return stage1_output_dir(output_dir) / f"{stem}-text_final_cluster.pkl"


def text_final_cluster_json(stem: str, output_dir: Path | None = None) -> Path:
    return stage1_output_dir(output_dir) / f"{stem}-text_final_cluster.json"


def text_final_cluster_png(stem: str, output_dir: Path | None = None) -> Path:
    return stage1_output_dir(output_dir) / f"{stem}-text_final_cluster.png"


def layer_synonyms_json() -> Path:
    return stage1_dir() / "layer_synonyms.json"
