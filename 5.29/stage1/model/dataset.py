"""Build labeled layer datasets from stage1 feature exports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from stage1.feature_vector import FEATURE_NAMES, layer_record_to_vector

from .labels import load_labels


@dataclass(frozen=True)
class LayerSample:
  drawing: str
  layer: str
  label: int
  vector: np.ndarray


@dataclass
class DatasetBuildReport:
  pairs: list[tuple[str, Path, Path]]
  samples: list[LayerSample]
  warnings: list[str]


def _stem_from_features_path(path: Path) -> str:
  name = path.name
  suffix = "_layer_features.json"
  if not name.endswith(suffix):
    raise ValueError(f"Expected *{suffix}, got {path.name}")
  return name[: -len(suffix)]


def discover_labeled_drawings(
  features_dir: Path,
  labels_dir: Path,
) -> list[tuple[str, Path, Path]]:
  """Return (stem, features_path, labels_path) for each labeled drawing."""
  pairs: list[tuple[str, Path, Path]] = []
  for feat_path in sorted(features_dir.glob("*_layer_features.json")):
    stem = _stem_from_features_path(feat_path)
    label_path = labels_dir / f"{stem}.json"
    if label_path.exists():
      pairs.append((stem, feat_path, label_path))
  return pairs


def _load_features(path: Path) -> dict[str, Any]:
  with path.open(encoding="utf-8") as f:
    return json.load(f)


def build_dataset(
  features_dir: Path,
  labels_dir: Path,
) -> DatasetBuildReport:
  pairs = discover_labeled_drawings(features_dir, labels_dir)
  if not pairs:
    raise ValueError(
      f"No labeled drawings found under {features_dir} + {labels_dir}"
    )

  samples: list[LayerSample] = []
  warnings: list[str] = []

  for stem, feat_path, label_path in pairs:
    features = _load_features(feat_path)
    labels = load_labels(label_path)
    layers = features.get("layers") or {}

    for label_name in labels:
      if label_name not in layers:
        warnings.append(
          f"{stem}: label {label_name!r} not found in {feat_path.name}"
        )

    labeled_in_features = {n for n in layers if n in labels}
    unlabeled = sorted(set(layers) - labeled_in_features)
    if unlabeled:
      warnings.append(
        f"{stem}: {len(unlabeled)} layer(s) without labels (excluded): "
        + ", ".join(unlabeled[:8])
        + ("..." if len(unlabeled) > 8 else "")
      )

    y_vals = set(labels.values())
    if y_vals != {0, 1}:
      warnings.append(f"{stem}: labels must include both 0 and 1")

    for layer_name in sorted(labeled_in_features):
      samples.append(
        LayerSample(
          drawing=stem,
          layer=layer_name,
          label=int(labels[layer_name]),
          vector=layer_record_to_vector(layers[layer_name]),
        )
      )

  if not samples:
    raise ValueError("No labeled layers matched feature files")

  pos = sum(s.label for s in samples)
  neg = len(samples) - pos
  if pos == 0 or neg == 0:
    raise ValueError(f"Need both classes; got {pos} positive, {neg} negative")

  return DatasetBuildReport(pairs=pairs, samples=samples, warnings=warnings)


def samples_to_arrays(
  samples: list[LayerSample],
) -> tuple[np.ndarray, np.ndarray, list[LayerSample]]:
  X = np.vstack([s.vector for s in samples])
  y = np.array([s.label for s in samples], dtype=int)
  return X, y, samples
