"""Step 2A directory and artefact path helpers."""

from __future__ import annotations

from pathlib import Path

RAW_SUBDIR = "raw"
OUTPUT_SUBDIR = "output"


def step2a_package_dir() -> Path:
  return Path(__file__).resolve().parent


def step2a_raw_dir(output_dir: Path | None = None) -> Path:
  base = step2a_package_dir() if output_dir is None else output_dir.parent
  if output_dir is not None and output_dir.name == RAW_SUBDIR:
    return output_dir
  return base / RAW_SUBDIR


def step2a_output_dir(output_dir: Path | None = None) -> Path:
  if output_dir is not None:
    return output_dir
  return step2a_package_dir() / OUTPUT_SUBDIR


def resolve_step2a_artifacts_dir(path: Path) -> Path:
  """Resolve Step 2A output directory from explicit path or repo defaults."""
  path = path.resolve()
  if path.name == OUTPUT_SUBDIR and path.parent.name == "step2A":
    return path
  default = step2a_output_dir()
  if path in (default.parent.parent, default.parent.parent / "stage2"):
    return default
  return path


def step2a_dir(stage2_root: Path | None = None) -> Path:
  if stage2_root is not None:
    return resolve_step2a_artifacts_dir(stage2_root)
  return step2a_output_dir()


def raw_geo_json(stem: str, raw_dir: Path | None = None) -> Path:
  return step2a_raw_dir(raw_dir) / f"{stem}.json"


def init_graph_pkl(stem: str, raw_dir: Path | None = None) -> Path:
  return step2a_raw_dir(raw_dir) / f"{stem}_init-graph.pkl"


def init_graph_json(stem: str, raw_dir: Path | None = None) -> Path:
  return step2a_raw_dir(raw_dir) / f"{stem}_init-graph.json"


def square_bend_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2a_output_dir(output_dir) / f"{stem}_square_bend.json"


def arc_bend_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2a_output_dir(output_dir) / f"{stem}_arc_bend.json"


def arc_line_normalize_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2a_output_dir(output_dir) / f"{stem}_arc_line_normalize.json"


def unmodified_elements_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2a_output_dir(output_dir) / f"{stem}_unmodified_elements.json"


def normalized_geometry_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2a_output_dir(output_dir) / f"{stem}_normalized_geometry.json"


def normalized_graph_pkl(stem: str, output_dir: Path | None = None) -> Path:
  return step2a_output_dir(output_dir) / f"{stem}_normalized_graph.pkl"


def normalized_graph_json(stem: str, output_dir: Path | None = None) -> Path:
  return step2a_output_dir(output_dir) / f"{stem}_normalized_graph.json"


def step2a_overall_png(
  stem: str,
  output_dir: Path | None = None,
  *,
  label: bool = False,
) -> Path:
  prefix = "lb_" if label else ""
  return step2a_output_dir(output_dir) / f"{prefix}{stem}_step2a_overall.png"
