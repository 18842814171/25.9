"""
Predict corridor layers on a feature file using the trained ML model.

  python -m stage1.model.run_predict --features stage1/output/stage1/2-main_layer_features.json
  python -m stage1.model.run_predict --features ... --dxf dxf/2-main.dxf
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage1.feature_vector import build_matrix
from stage1.model.trainer import load_model, predict_proba
from stage1.visualize_layers import visualize_layer_classification


def _resolve_path(path: Path) -> Path:
  """Resolve paths relative to project root when run from stage1/ etc."""
  if path.is_absolute() and path.exists():
    return path
  for candidate in (path, _ROOT / path, _ROOT / "stage1" / path):
    if candidate.exists():
      return candidate.resolve()
  return path


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(description="Predict corridor layers (ML model)")
  parser.add_argument("--features", type=Path, required=True)
  parser.add_argument(
    "--model-path",
    type=Path,
    default=_ROOT / "stage1" / "model" / "output" / "corridor_classifier.pkl",
  )
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=_ROOT / "stage1" / "model" / "output",
  )
  parser.add_argument("--dxf", type=Path, default=None, help="Optional DXF for PNG")
  parser.add_argument("--threshold", type=float, default=None)
  args = parser.parse_args(argv)

  features_path = _resolve_path(args.features)
  model_path = _resolve_path(args.model_path)
  dxf_path = _resolve_path(args.dxf) if args.dxf else None

  clf, meta = load_model(model_path)
  threshold = args.threshold if args.threshold is not None else meta.get("threshold", 0.5)

  with features_path.open(encoding="utf-8") as f:
    features = json.load(f)

  layer_names, X = build_matrix(features["layers"])
  proba = predict_proba(clf, X)
  pred = (proba >= threshold).astype(int)

  predictions = {
    name: {
      "label": int(pred[i]),
      "probability": round(float(proba[i]), 4),
    }
    for i, name in enumerate(layer_names)
  }

  stem = features_path.name.replace("_layer_features.json", "")
  args.output_dir.mkdir(parents=True, exist_ok=True)
  out_path = args.output_dir / f"{stem}_predictions.json"
  result = {
    "source": features.get("source"),
    "model_path": str(model_path),
    "model_type": meta.get("model_type"),
    "threshold": threshold,
    "n_layers": len(predictions),
    "n_predicted_corridor": int(pred.sum()),
    "predictions": predictions,
  }
  with out_path.open("w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
  print(f"Predictions → {out_path}")
  print(f"Corridor layers ({result['n_predicted_corridor']}):")
  for name in sorted(
    (n for n, p in predictions.items() if p["label"] == 1),
    key=lambda n: -predictions[n]["probability"],
  ):
    print(f"  {name!r}  P={predictions[name]['probability']}")

  if dxf_path:
    png_path = args.output_dir / f"{stem}_classification.png"
    visualize_layer_classification(dxf_path, predictions, png_path)
    print(f"Figure → {png_path}")


if __name__ == "__main__":
  main()
