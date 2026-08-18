"""0/1 corridor-layer classifier (features only at inference)."""

from __future__ import annotations

import json
import pickle
import re
from pathlib import Path
from typing import Any

import numpy as np

from .feature_vector import FEATURE_NAMES, build_matrix, layer_record_to_vector

# Training-only weak labels (layer names — never used in predict())
_NEGATIVE_RE = re.compile(
  r"图框|图例|指北针|经纬|网格|坐标|标注|注记|封面|图签|"
  r"边界|矿界|等高|高程|水系|规划|设计|说明|文字|标题|"
  r"通风|水源|炸药|广场|电力|道路|铁路|煤柱|边界|设施|图$|布置图"
)


def weak_label_from_layer_name(layer_name: str) -> int | None:
  """
  Bootstrap labels for training when no manual file exists.
  Returns None if uncertain (excluded from training).
  """
  if "顶底板" in layer_name or "探水" in layer_name or "积水" in layer_name:
    return 0
  if _NEGATIVE_RE.search(layer_name):
    return 0
  # Strict positive: explicit roadway layer naming
  if re.search(r"\d{4}年巷道$", layer_name):
    return 1
  if layer_name in ("巷道", "巷道中心线", "巷道边线"):
    return 1
  if layer_name.endswith("巷道") and "布置" not in layer_name and "顶底板" not in layer_name:
    return 1
  return None


def load_manual_labels(path: Path) -> dict[str, int]:
  """
  JSON formats:
    {"corridor_layers": ["A", "B"], "non_corridor_layers": ["C"]}
    or {"layers": {"A": 1, "B": 0}}
  """
  with path.open(encoding="utf-8") as f:
    data = json.load(f)

  if "layers" in data:
    return {k: int(v) for k, v in data["layers"].items()}

  out: dict[str, int] = {}
  for name in data.get("corridor_layers", []):
    out[name] = 1
  for name in data.get("non_corridor_layers", []):
    out[name] = 0
  return out


def fit_classifier(
  features: dict[str, Any],
  labels_path: Path | None = None,
  use_weak_labels: bool = True,
) -> tuple[Any, list[str], dict[str, Any]]:
  from sklearn.linear_model import LogisticRegression
  from sklearn.preprocessing import StandardScaler
  from sklearn.pipeline import Pipeline

  layers = features["layers"]
  layer_names, X = build_matrix(layers)

  y_list: list[int] = []
  train_names: list[str] = []
  label_source = "manual"

  if labels_path and labels_path.exists():
    manual = load_manual_labels(labels_path)
    for name in layer_names:
      if name in manual:
        train_names.append(name)
        y_list.append(manual[name])
  elif use_weak_labels:
    label_source = "weak_layer_name"
    for name in layer_names:
      wl = weak_label_from_layer_name(name)
      if wl is not None:
        train_names.append(name)
        y_list.append(wl)
  else:
    raise ValueError("No labels file and use_weak_labels=False")

  if len(set(y_list)) < 2:
    raise ValueError(f"Need both classes for training; got {len(y_list)} samples")

  idx = [layer_names.index(n) for n in train_names]
  X_train = X[idx]
  y_train = np.array(y_list, dtype=int)

  clf = Pipeline(
    steps=[
      ("scaler", StandardScaler()),
      (
        "clf",
        LogisticRegression(
          class_weight="balanced",
          max_iter=2000,
          random_state=0,
        ),
      ),
    ]
  )
  clf.fit(X_train, y_train)

  meta = {
    "label_source": label_source,
    "n_train": len(y_train),
    "n_positive": int(y_train.sum()),
    "n_negative": int((1 - y_train).sum()),
    "feature_names": FEATURE_NAMES,
  }
  return clf, layer_names, meta


def predict_layers(
  clf: Any,
  features: dict[str, Any],
  threshold: float = 0.5,
) -> dict[str, dict[str, Any]]:
  layers = features["layers"]
  layer_names, X = build_matrix(layers)
  proba = clf.predict_proba(X)[:, 1]
  pred = (proba >= threshold).astype(int)

  return {
    name: {
      "label": int(pred[i]),
      "probability": round(float(proba[i]), 4),
    }
    for i, name in enumerate(layer_names)
  }


def save_model(clf: Any, meta: dict[str, Any], path: Path) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("wb") as f:
    pickle.dump({"model": clf, "meta": meta}, f)


def load_model(path: Path) -> tuple[Any, dict[str, Any]]:
  with path.open("rb") as f:
    blob = pickle.load(f)
  return blob["model"], blob["meta"]


def classify_from_features_file(
  features_path: Path,
  labels_path: Path | None = None,
  use_weak_labels: bool = True,
  threshold: float = 0.5,
  model_out: Path | None = None,
) -> dict[str, Any]:
  with features_path.open(encoding="utf-8") as f:
    features = json.load(f)

  clf, layer_names, meta = fit_classifier(
    features, labels_path=labels_path, use_weak_labels=use_weak_labels
  )
  predictions = predict_layers(clf, features, threshold=threshold)

  if model_out:
    save_model(clf, meta, model_out)

  n_pos = sum(1 for p in predictions.values() if p["label"] == 1)
  return {
    "source": features.get("source"),
    "threshold": threshold,
    "training": meta,
    "n_layers": len(predictions),
    "n_predicted_corridor": n_pos,
    "predictions": predictions,
  }
