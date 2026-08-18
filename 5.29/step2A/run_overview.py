"""
Step 2A overview PNG CLI.

Run after merge_normalized_geometry.py (normalized LINE list is required).

Example:
  python step2A/run_overview.py --stem 2026.1-1part-巷道
  python step2A/run_overview.py --stem 2026.1-1part-巷道 --label
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage2.io import load_json
from step2A.paths import (
  arc_bend_json,
  normalized_geometry_json,
  square_bend_json,
  step2a_output_dir,
  step2a_overall_png,
)
from step2A.visualize import visualize_step2a_overall


def export_overview(
  stem: str,
  output_dir: Path | None = None,
  *,
  show_labels: bool = False,
) -> Path:
  out = step2a_output_dir(output_dir)

  geo_path = normalized_geometry_json(stem, out)
  square_path = square_bend_json(stem, out)
  arc_bend_path = arc_bend_json(stem, out)

  if not geo_path.is_file():
    raise FileNotFoundError(
      f"Missing {geo_path}; run step2A/merge_normalized_geometry.py first.",
    )

  square_doc = load_json(square_path) if square_path.is_file() else None
  arc_bend_doc = load_json(arc_bend_path) if arc_bend_path.is_file() else None

  png_path = step2a_overall_png(stem, out, label=show_labels)
  visualize_step2a_overall(
    load_json(geo_path),
    square_doc,
    arc_bend_doc,
    png_path,
    show_labels=show_labels,
    title=f"Step 2A overall ({stem})",
  )
  return png_path


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 2A: render step2a_overall.png from normalized geometry + bends",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument(
    "--label",
    action="store_true",
    help="draw bend id labels; output as lb_{stem}_step2a_overall.png",
  )
  args = parser.parse_args()

  png_path = export_overview(args.stem, args.output, show_labels=args.label)
  print(f"[step2A/overview] → {png_path}")


if __name__ == "__main__":
  main()
