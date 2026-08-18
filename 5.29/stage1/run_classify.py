"""
Train 0/1 layer classifier and visualize on DXF.

  python -m stage1.run_visualize --dxf 2026.1-2.dxf
  python -m stage1.run_visualize --features output/stage1/2026.1-2_layer_features.json --dxf 2026.1-2.dxf
  python -m stage1.run_visualize --features ... --dxf ... --labels labels/2026.1-2.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage1.layer_classifier import classify_from_features_file
from stage1.layer_features import compute_features_from_dxf, save_features
from stage1.visualize_layers import visualize_layer_classification


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(description="Classify corridor layers and visualize")
  parser.add_argument("--dxf", type=Path, required=True, help="DXF to draw")
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=Path("output/stage1"),
  )
  parser.add_argument("--labels", type=Path, default=None, help="Manual labels JSON")
  parser.add_argument("--threshold", type=float, default=0.5)
  parser.add_argument(
    "--window",
    nargs=4,
    type=float,
    metavar=("X1", "Y1", "X2", "Y2"),
  )
  args = parser.parse_args(argv)

  window = None
  if args.window:
    x1, y1, x2, y2 = args.window
    window = ((x1, y1), (x2, y2))

  args.output_dir.mkdir(parents=True, exist_ok=True)
  stem = args.dxf.stem.replace(" ", "_")

  print(f"Computing features from {args.dxf} ...")
  feats = compute_features_from_dxf(args.dxf, window_corners=window)
  feats_path = save_features(feats, args.output_dir / f"{stem}_layer_features.json")
  print(f"  → {feats_path}")

  model_path = args.output_dir / f"{stem}_layer_classifier.pkl"
  result = classify_from_features_file(
    feats_path,
    labels_path=args.labels,
    use_weak_labels=True,
    threshold=args.threshold,
    model_out=model_path,
  )

  pred_path = args.output_dir / f"{stem}_layer_predictions.json"
  with pred_path.open("w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
  print(f"Model → {model_path}")
  print(f"Predictions → {pred_path}")
  print(f"Training: {result['training']}")
  print(f"Predicted corridor layers: {result['n_predicted_corridor']} / {result['n_layers']}")

  pos = [n for n, p in result["predictions"].items() if p["label"] == 1]
  print("\nLayers labeled 1 (corridor):")
  for name in sorted(pos, key=lambda n: -result["predictions"][n]["probability"]):
    p = result["predictions"][name]["probability"]
    print(f"  {name!r}  P={p}")

  png_path = args.output_dir / f"{stem}_layer_classification.png"
  print(f"\nRendering {args.dxf} ...")
  visualize_layer_classification(
    args.dxf,
    result["predictions"],
    png_path,
    window_corners=window,
  )
  print(f"Figure → {png_path}")


if __name__ == "__main__":
  main()
