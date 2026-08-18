"""Step 4B artefact path helpers (structure graph)."""

from __future__ import annotations

from pathlib import Path

OUTPUT_SUBDIR = "output"


def step4B_package_dir() -> Path:
  return Path(__file__).resolve().parent


def step4B_output_dir(output_dir: Path | None = None) -> Path:
  if output_dir is not None:
    return output_dir
  return step4B_package_dir() / OUTPUT_SUBDIR


def step4A_residual_graph_semantic_pkl(
  stem: str,
  step4A_dir: Path | None = None,
) -> Path:
  """Read-only input: step4A output semantic residual graph."""
  if step4A_dir is not None:
    return step4A_dir / f"{stem}_residual_graph_semantic.pkl"
  root = step4B_package_dir().parent
  return root / "step4A" / "output" / f"{stem}_residual_graph_semantic.pkl"


def centerline_graph_fixed_pkl(
  stem: str,
  step3b_dir: Path | None = None,
) -> Path:
  """Read-only input: step3B output fixed centerline graph."""
  if step3b_dir is not None:
    return step3b_dir / f"{stem}_centerline_graph_fixed.pkl"
  root = step4B_package_dir().parent
  return root / "step3B" / "output" / f"{stem}_centerline_graph_fixed.pkl"


def structure_graph_pkl(
  stem: str,
  output_dir: Path | None = None,
) -> Path:
  return step4B_output_dir(output_dir) / f"{stem}_structure_graph.pkl"


def structure_graph_json(
  stem: str,
  output_dir: Path | None = None,
) -> Path:
  return step4B_output_dir(output_dir) / f"{stem}_structure_graph.json"


def structure_graph_png(
  stem: str,
  output_dir: Path | None = None,
  *,
  label: bool = False,
) -> Path:
  prefix = "lb_" if label else ""
  return step4B_output_dir(output_dir) / f"{prefix}{stem}_structure_graph.png"

