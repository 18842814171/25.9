"""
Evaluate a trained model or run cross-validation only.

  python -m stage1.model.run_evaluate
  python -m stage1.model.run_evaluate --model random_forest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage1.model.dataset import build_dataset
from stage1.model.evaluate import evaluate_model, leave_one_out_cv
from stage1.model.trainer import SUPPORTED_MODELS, load_model


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(description="Evaluate corridor-layer classifier")
  parser.add_argument(
    "--features-dir",
    type=Path,
    default=_ROOT / "stage1" / "output" / "stage1",
  )
  parser.add_argument(
    "--labels-dir",
    type=Path,
    default=_ROOT / "labels",
  )
  parser.add_argument(
    "--model-path",
    type=Path,
    default=_ROOT / "stage1" / "model" / "output" / "corridor_classifier.pkl",
    help="Saved model (for in-sample sanity check)",
  )
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=_ROOT / "stage1" / "model" / "output",
  )
  parser.add_argument(
    "--model",
    choices=SUPPORTED_MODELS,
    default=None,
    help="Model for LOO-CV (default: read from saved model meta)",
  )
  parser.add_argument("--threshold", type=float, default=0.5)
  args = parser.parse_args(argv)

  report = build_dataset(args.features_dir, args.labels_dir)
  for w in report.warnings:
    print(f"WARNING: {w}")

  model_name = args.model
  if model_name is None and args.model_path.exists():
    _, meta = load_model(args.model_path)
    model_name = meta.get("model_type", "logistic")
  if model_name is None:
    model_name = "logistic"

  cv = leave_one_out_cv(
    report.samples,
    model_name=model_name,
    threshold=args.threshold,
  )
  print(f"Leave-one-drawing-out CV ({model_name})")
  print(f"  accuracy={cv['accuracy']}  precision={cv['precision']}")
  print(f"  recall={cv['recall']}  f1={cv['f1']}")

  for fold in cv["folds"]:
    print(f"\n--- Held out: {fold['held_out_drawing']} ---")
    wrong = [p for p in fold["predictions"] if not p["correct"]]
    for p in fold["predictions"]:
      mark = "OK" if p["correct"] else "MISS"
      print(
        f"  [{mark}] {p['layer']!r}: true={p['true_label']} "
        f"pred={p['pred_label']} P={p['probability']}"
      )
    if not wrong:
      print("  (all correct)")

  args.output_dir.mkdir(parents=True, exist_ok=True)
  eval_path = args.output_dir / "evaluation_report.json"
  payload = {"cross_validation": cv}
  if args.model_path.exists():
    clf, meta = load_model(args.model_path)
    payload["in_sample"] = evaluate_model(
      clf, report.samples, threshold=args.threshold
    )
    payload["model_meta"] = meta
  with eval_path.open("w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
  print(f"\nReport → {eval_path}")


if __name__ == "__main__":
  main()
