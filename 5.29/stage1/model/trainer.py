"""Train and persist sklearn corridor-layer classifiers."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from stage1.feature_vector import FEATURE_NAMES

SUPPORTED_MODELS = ("logistic", "random_forest")


def create_model(name: str) -> Any:
  if name == "logistic":
    return Pipeline(
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
  if name == "random_forest":
    return Pipeline(
      steps=[
        ("scaler", StandardScaler()),
        (
          "clf",
          RandomForestClassifier(
            n_estimators=200,
            class_weight="balanced_subsample",
            max_depth=8,
            min_samples_leaf=2,
            random_state=0,
          ),
        ),
      ]
    )
  raise ValueError(f"Unknown model {name!r}; choose from {SUPPORTED_MODELS}")


def train_model(
  X: np.ndarray,
  y: np.ndarray,
  model_name: str = "logistic",
) -> Any:
  if len(set(y.tolist())) < 2:
    raise ValueError("Training set must contain both corridor and non-corridor layers")
  clf = create_model(model_name)
  clf.fit(X, y)
  return clf


def save_model(
  clf: Any,
  path: Path,
  meta: dict[str, Any],
) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("wb") as f:
    pickle.dump({"model": clf, "meta": meta}, f)


def load_model(path: Path) -> tuple[Any, dict[str, Any]]:
  with path.open("rb") as f:
    blob = pickle.load(f)
  return blob["model"], blob["meta"]


def predict_proba(clf: Any, X: np.ndarray) -> np.ndarray:
  return clf.predict_proba(X)[:, 1]
