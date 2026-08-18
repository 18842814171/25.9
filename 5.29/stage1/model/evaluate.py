"""Metrics and leave-one-drawing-out cross-validation."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
  accuracy_score,
  confusion_matrix,
  f1_score,
  precision_score,
  recall_score,
)

from stage1.feature_vector import FEATURE_NAMES

from .dataset import LayerSample, samples_to_arrays
from .trainer import predict_proba, train_model


def _layer_predictions(
  samples: list[LayerSample],
  y_true: np.ndarray,
  y_pred: np.ndarray,
  y_proba: np.ndarray,
) -> list[dict[str, Any]]:
  rows: list[dict[str, Any]] = []
  for i, sample in enumerate(samples):
    rows.append(
      {
        "drawing": sample.drawing,
        "layer": sample.layer,
        "true_label": int(y_true[i]),
        "pred_label": int(y_pred[i]),
        "probability": round(float(y_proba[i]), 4),
        "correct": bool(y_true[i] == y_pred[i]),
      }
    )
  return rows


def evaluate_model(
  clf: Any,
  samples: list[LayerSample],
  threshold: float = 0.5,
) -> dict[str, Any]:
  X, y_true, _ = samples_to_arrays(samples)
  y_proba = predict_proba(clf, X)
  y_pred = (y_proba >= threshold).astype(int)

  cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
  tn, fp, fn, tp = cm.ravel()

  return {
    "threshold": threshold,
    "n_samples": len(samples),
    "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
    "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
    "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
    "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
    "confusion_matrix": {
      "tn": int(tn),
      "fp": int(fp),
      "fn": int(fn),
      "tp": int(tp),
    },
    "predictions": _layer_predictions(samples, y_true, y_pred, y_proba),
  }


def leave_one_out_cv(
  samples: list[LayerSample],
  model_name: str = "logistic",
  threshold: float = 0.5,
) -> dict[str, Any]:
  drawings = sorted({s.drawing for s in samples})
  if len(drawings) < 2:
    raise ValueError("Leave-one-out CV needs at least 2 labeled drawings")

  folds: list[dict[str, Any]] = []
  all_test_samples: list[LayerSample] = []

  for held_out in drawings:
    train_samples = [s for s in samples if s.drawing != held_out]
    test_samples = [s for s in samples if s.drawing == held_out]
    all_test_samples.extend(test_samples)

    X_train, y_train, _ = samples_to_arrays(train_samples)
    clf = train_model(X_train, y_train, model_name=model_name)
    fold_eval = evaluate_model(clf, test_samples, threshold=threshold)
    fold_eval["held_out_drawing"] = held_out
    fold_eval["n_train"] = len(train_samples)
    fold_eval["n_test"] = len(test_samples)
    folds.append(fold_eval)

  # Aggregate metrics on all held-out predictions (out-of-sample)
  y_true = np.array([s.label for s in all_test_samples], dtype=int)
  y_pred = np.array(
    [p["pred_label"] for fold in folds for p in fold["predictions"]],
    dtype=int,
  )

  return {
    "model": model_name,
    "threshold": threshold,
    "n_drawings": len(drawings),
    "n_samples": len(all_test_samples),
    "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
    "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
    "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
    "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
    "folds": folds,
    "feature_names": FEATURE_NAMES,
  }
