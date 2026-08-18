"""Step 3B residual_graph artefact path helpers."""

from __future__ import annotations

from pathlib import Path

OUTPUT_SUBDIR = "output"


def step3b_package_dir() -> Path:
  return Path(__file__).resolve().parent


def step3b_output_dir(output_dir: Path | None = None) -> Path:
  if output_dir is not None:
    return output_dir
  return step3b_package_dir() / OUTPUT_SUBDIR


def residual_graph_pkl(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_residual_graph.pkl"


def residual_graph_json(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_residual_graph.json"


def residual_graph_summary_json(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_residual_graph_summary.json"


def residual_graph_png(
  stem: str,
  output_dir: Path | None = None,
  *,
  label: bool = False,
) -> Path:
  prefix = "lb_" if label else ""
  return step3b_output_dir(output_dir) / f"{prefix}{stem}_residual_graph.png"


def residual_graph_tagged_pkl(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_residual_graph_tagged.pkl"


def residual_graph_tagged_json(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_residual_graph_tagged.json"


def secondary_wall_candidates_json(stem: str, output_dir: Path | None = None) -> Path:
  """Step 3B: residual stubs tagged as possible corridor walls."""
  return step3b_output_dir(output_dir) / f"{stem}_secondary_wall_candidates.json"


def secondary_wall_candidates_png(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_secondary_wall_candidates.png"


def residual_graph_resolved_pkl(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_residual_graph_resolved.pkl"


def residual_graph_resolved_json(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_residual_graph_resolved.json"


def centerline_fix_json(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_centerline_fix.json"


def centerline_fix_png(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_centerline_fix.png"


def centerline_graph_fixed_pkl(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_centerline_graph_fixed.pkl"


def centerline_graph_fixed_json(stem: str, output_dir: Path | None = None) -> Path:
  return step3b_output_dir(output_dir) / f"{stem}_centerline_graph_fixed.json"


def centerline_graph_input_pkl(
  stem: str,
  centerline_dir: Path | None = None,
) -> Path:
  """Read-only upstream centerline_graph.pkl (default: step3A/output)."""
  if centerline_dir is not None:
    return centerline_dir / f"{stem}_centerline_graph.pkl"
  root = step3b_package_dir().parent
  return root / "step3A" / "output" / f"{stem}_centerline_graph.pkl"
