"""Step 2B artefact path helpers."""

from __future__ import annotations

from pathlib import Path

OUTPUT_SUBDIR = "output"


def step2b_package_dir() -> Path:
  return Path(__file__).resolve().parent


def step2b_output_dir(output_dir: Path | None = None) -> Path:
  if output_dir is not None:
    return output_dir
  return step2b_package_dir() / OUTPUT_SUBDIR


def wall_segment_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_wall_segment.json"


def straight_wall_geometry_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_straight_wall_geometry.json"


def residual_geometry_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_residual_geometry.json"


def straight_wall_png(
  stem: str,
  output_dir: Path | None = None,
  *,
  label: bool = False,
) -> Path:
  prefix = "lb_" if label else ""
  return step2b_output_dir(output_dir) / f"{prefix}{stem}_straight_wall.png"


def corridors_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_corridors.json"


def main_corridor_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_main_corridor.json"


def parallel_graph_pkl(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_parallel_graph.pkl"


def parallel_graph_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_parallel_graph.json"


def parallel_graph_png(
  stem: str,
  output_dir: Path | None = None,
  *,
  label: bool = False,
) -> Path:
  prefix = "lb_" if label else ""
  return step2b_output_dir(output_dir) / f"{prefix}{stem}_parallel_graph.png"


def parallel_graph_summary_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_parallel_graph_summary.json"


def corridors_png(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_corridors.png"


def corridor_network_pkl(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_corridor_network.pkl"


def corridor_network_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_corridor_network.json"


def corridor_network_png(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_corridor_network.png"


def centerline_graph_pkl(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_centerline_graph.pkl"


def centerline_graph_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_centerline_graph.json"


def centerline_graph_summary_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_centerline_graph_summary.json"


def centerline_graph_png(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_centerline_graph.png"


def centerline_graph_annotated_pkl(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_centerline_graph_annotated.pkl"


def centerline_graph_annotated_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_centerline_graph_annotated.json"


def global_scale_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2b_output_dir(output_dir) / f"{stem}_global_scale.json"
