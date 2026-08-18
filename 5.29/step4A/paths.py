"""Step 4A artefact path helpers (residual semantics + attached regions)."""

from __future__ import annotations

from pathlib import Path

OUTPUT_SUBDIR = "output"


def step4A_package_dir() -> Path:
  return Path(__file__).resolve().parent


def step4A_output_dir(output_dir: Path | None = None) -> Path:
  if output_dir is not None:
    return output_dir
  return step4A_package_dir() / OUTPUT_SUBDIR


def step3b_residual_graph_pkl(stem: str, step3b_dir: Path | None = None) -> Path:
  if step3b_dir is not None:
    return step3b_dir / f"{stem}_residual_graph.pkl"
  root = step4A_package_dir().parent
  return root / "step3B" / "output" / f"{stem}_residual_graph.pkl"


def centerline_graph_input_pkl(
  stem: str,
  centerline_dir: Path | None = None,
) -> Path:
  if centerline_dir is not None:
    return centerline_dir / f"{stem}_centerline_graph.pkl"
  root = step4A_package_dir().parent
  return root / "step3A" / "output" / f"{stem}_centerline_graph.pkl"


def residual_graph_semantic_pkl(
  stem: str,
  output_dir: Path | None = None,
) -> Path:
  return step4A_output_dir(output_dir) / f"{stem}_residual_graph_semantic.pkl"


def residual_graph_semantic_json(
  stem: str,
  output_dir: Path | None = None,
) -> Path:
  return step4A_output_dir(output_dir) / f"{stem}_residual_graph_semantic.json"


def attached_regions_json(stem: str, output_dir: Path | None = None) -> Path:
  return step4A_output_dir(output_dir) / f"{stem}_attached_regions.json"


def attached_regions_png(
  stem: str,
  output_dir: Path | None = None,
  *,
  label: bool = False,
) -> Path:
  prefix = "lb_" if label else ""
  return step4A_output_dir(output_dir) / f"{prefix}{stem}_attached_regions.png"

