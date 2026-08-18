"""
Train corridor-layer classifier on all manually labeled drawings.

  python -m stage1.model.run_train
  python -m stage1.model.run_train --model random_forest
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage1.feature_vector import FEATURE_NAMES
from stage1.model.dataset import build_dataset, samples_to_arrays
from stage1.model.evaluate import leave_one_out_cv
from stage1.model.trainer import SUPPORTED_MODELS, save_model, train_model


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(description="Train ML corridor-layer classifier")
  parser.add_argument(
    "--features-dir",
    type=Path,
    default=_ROOT / "stage1" / "output" / "stage1",
    help="Directory with *_layer_features.json",
  )
  parser.add_argument(
    "--labels-dir",
    type=Path,
    default=_ROOT / "labels",
    help="Directory with {stem}.json label files (auto-matched to features)",
  )
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=_ROOT / "stage1" / "model" / "output",
  )
  parser.add_argument(
    "--model",
    choices=SUPPORTED_MODELS,
    default="logistic",
    help="Sklearn model type",
  )
  parser.add_argument("--threshold", type=float, default=0.5)
  args = parser.parse_args(argv)

  report = build_dataset(args.features_dir, args.labels_dir)
  for w in report.warnings:
    print(f"WARNING: {w}")

  X, y, samples = samples_to_arrays(report.samples)
  drawings = sorted({s.drawing for s in samples})
  print(f"Dataset: {len(samples)} labeled layers from {len(drawings)} drawing(s)")
  print(f"  positive={int(y.sum())}, negative={int(len(y) - y.sum())}")
  for stem, feat_path, label_path in report.pairs:
    n = sum(1 for s in samples if s.drawing == stem)
    print(f"  {stem}: {n} layers  ({feat_path.name} + {label_path.name})")

  cv = leave_one_out_cv(
    report.samples,
    model_name=args.model,
    threshold=args.threshold,
  )
  print(
    f"\nLeave-one-drawing-out CV ({args.model}): "
    f"acc={cv['accuracy']}  P={cv['precision']}  R={cv['recall']}  F1={cv['f1']}"
  )
  for fold in cv["folds"]:
    print(
      f"  held-out {fold['held_out_drawing']!r}: "
      f"acc={fold['accuracy']}  P={fold['precision']}  R={fold['recall']}  "
      f"({fold['n_test']} test layers)"
    )

  clf = train_model(X, y, model_name=args.model)
  meta = {
    "model_type": args.model,
    "threshold": args.threshold,
    "feature_names": FEATURE_NAMES,
    "drawings": drawings,
    "n_train_layers": len(samples),
    "n_positive": int(y.sum()),
    "n_negative": int(len(y) - y.sum()),
    "label_source": "manual",
    "trained_at": datetime.now(timezone.utc).isoformat(),
    "cv": cv,
  }

  args.output_dir.mkdir(parents=True, exist_ok=True)
  model_path = args.output_dir / "corridor_classifier.pkl"
  save_model(clf, model_path, meta)
  print(f"\nModel → {model_path}")

  cv_path = args.output_dir / "cv_report.json"
  with cv_path.open("w", encoding="utf-8") as f:
    json.dump(cv, f, ensure_ascii=False, indent=2)
  print(f"CV report → {cv_path}")


if __name__ == "__main__":
  main()
