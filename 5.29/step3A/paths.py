"""Step 3A artefact path helpers."""

from __future__ import annotations

from pathlib import Path

OUTPUT_SUBDIR = "output"


def step3a_package_dir() -> Path:
  return Path(__file__).resolve().parent


def step3a_output_dir(output_dir: Path | None = None) -> Path:
  if output_dir is not None:
    return output_dir
  return step3a_package_dir() / OUTPUT_SUBDIR


def corridor_candidates_json(stem: str, output_dir: Path | None = None) -> Path:
  return step3a_output_dir(output_dir) / f"{stem}_corridor_candidates.json"


def corridor_centerlines_png(
  stem: str,
  output_dir: Path | None = None,
  *,
  label: bool = False,
) -> Path:
  prefix = "lb_" if label else ""
  return step3a_output_dir(output_dir) / f"{prefix}{stem}_corridor_centerlines.png"


def centerline_graph_pkl(stem: str, output_dir: Path | None = None) -> Path:
  return step3a_output_dir(output_dir) / f"{stem}_centerline_graph.pkl"


def centerline_graph_json(stem: str, output_dir: Path | None = None) -> Path:
  return step3a_output_dir(output_dir) / f"{stem}_centerline_graph.json"


def centerline_graph_summary_json(stem: str, output_dir: Path | None = None) -> Path:
  return step3a_output_dir(output_dir) / f"{stem}_centerline_graph_summary.json"
