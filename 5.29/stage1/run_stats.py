"""
Stage 1 Step 1 CLI: inventory + per-layer features + corridor-layer ranking.

Usage (from stage1 directory):
  python run_stats.py --dxf ../dxf/2026.1-3.dxf
  .venv\\Scripts\\python.exe -m stage1.run_stage1 --json region0.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage1.dxf_inventory import save_inventory, scan_dxf_inventory
from stage1.export_layers import export_layers_to_json
from stage1.layer_features import (
  compute_features_from_dxf,
  compute_features_from_json,
  save_features,
)
from stage1.layer_scorer import rank_layers


def _stem_from_source(path: Path) -> str:
  return path.stem.replace(" ", "_")


def run(
  dxf: Path | None,
  json_path: Path | None,
  output_dir: Path,
  top_k: int,
  window: tuple | None,
  export_top: bool,
) -> None:
  output_dir.mkdir(parents=True, exist_ok=True)

  if dxf is not None:
    stem = _stem_from_source(dxf)
    print(f"[1/4] Statistics: {dxf}")
    inv = scan_dxf_inventory(dxf, window_corners=window)
    inv_path = save_inventory(inv, output_dir / f"{stem}_layer_statistics.json")
    print(f"      → {inv_path} ({inv['n_layers']} layers, {inv['total_entities_scanned']} entities)")

    print(f"[2/4] Layer features (streaming DXF)...")
    feats = compute_features_from_dxf(dxf, window_corners=window)
    feats_path = save_features(feats, output_dir / f"{stem}_layer_features.json")
    print(f"      → {feats_path}")

    source_for_export = dxf
  elif json_path is not None:
    stem = _stem_from_source(json_path)
    print(f"[1/4] Skip inventory (JSON input)")
    print(f"[2/4] Layer features from JSON...")
    feats = compute_features_from_json(json_path)
    feats_path = save_features(feats, output_dir / f"{stem}_layer_features.json")
    print(f"      → {feats_path}")
    source_for_export = None
  else:
    raise ValueError("Provide --dxf or --json")

  print(f"[3/4] Rank layers (rule-based, no layer names)...")
  ranking = rank_layers(feats, top_k=top_k)
  rank_path = output_dir / f"{stem}_layer_ranking.json"
  with rank_path.open("w", encoding="utf-8") as f:
    json.dump(ranking, f, ensure_ascii=False, indent=2)
  print(f"      → {rank_path}")

  print("\n--- Top corridor layer candidates ---")
  for i, row in enumerate(ranking["ranked"][:top_k], 1):
    sig = row.get("signals") or {}
    count_r = sig.get("count_ratio", 0.0)
    length_r = sig.get("length_ratio", 0.0)
    print(
      f"  {i}. {row['layer']!r}  score={row['score']}  "
      f"count_ratio={count_r}  length_ratio={length_r}"
    )

  if export_top and source_for_export is not None:
    print(f"\n[4/4] Export compact JSON for top-{top_k} layers...")
    layers = ranking["recommended_layers"]
    out_json = output_dir / f"{stem}_corridor_layers.json"
    export_layers_to_json(source_for_export, layers, out_json, window_corners=window)
    mb = out_json.stat().st_size / (1024 * 1024)
    print(f"      → {out_json} ({mb:.2f} MB)")
  else:
    print("\n[4/4] Skip export (use --export-top with --dxf to write corridor_layers.json)")


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(description="Stage 1: layer statistics and ranking")
  src = parser.add_mutually_exclusive_group(required=True)
  src.add_argument("--dxf", type=Path, help="Path to DXF file")
  src.add_argument("--json", type=Path, help="Path to flat primitives JSON")
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=Path("output/stage1"),
    help="Output directory (default: output/stage1)",
  )
  parser.add_argument("--top-k", type=int, default=5, help="Top-k layers to recommend")
  parser.add_argument(
    "--window",
    nargs=4,
    type=float,
    metavar=("X1", "Y1", "X2", "Y2"),
    help="Optional bbox window in drawing units",
  )
  parser.add_argument(
    "--export-top",
    action="store_true",
    help="Export compact JSON for top-k ranked layers (DXF input only)",
  )
  args = parser.parse_args(argv)

  window = None
  if args.window:
    x1, y1, x2, y2 = args.window
    window = ((x1, y1), (x2, y2))

  run(
    dxf=args.dxf,
    json_path=args.json,
    output_dir=args.output_dir,
    top_k=args.top_k,
    window=window,
    export_top=args.export_top,
  )


if __name__ == "__main__":
  main()
