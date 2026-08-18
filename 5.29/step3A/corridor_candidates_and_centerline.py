"""
Step 3A full pipeline: candidates + centerline graph + all PNGs.

Example:
  python step3A/run_step3a.py --stem part1-巷道
  python step3A/corridor_candidates_and_centerline.py --stem part1-巷道 --label
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from step3A.pipeline import run_step3a


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 3A: corridor candidates + centerline graph",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument("--step2b", type=Path, default=None)
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument("--no-vis", action="store_true")
  parser.add_argument("--no-auto-scale", action="store_true")
  parser.add_argument(
    "--label",
    action="store_true",
    help="draw CC*** labels; output as lb_{stem}_corridor_centerlines.png",
  )
  args = parser.parse_args()

  result = run_step3a(
    args.stem,
    step2b_dir=args.step2b,
    output_dir=args.output,
    auto_scale=not args.no_auto_scale,
    vis=not args.no_vis,
    show_ids=args.label,
  )
  scale = result.get("global_scale") or {}
  w = scale.get("median_corridor_width")
  width_msg = f" width_median={w:.2f}" if w else ""
  print(
    f"[step3A] pairs={result['pair_count']} candidates={result['candidate_count']} "
    f"centerline_edges={result['centerline_graph_edges']}{width_msg}",
  )
  for key, path in result["paths"].items():
    if path is not None:
      print(f"[step3A] → {path}")


if __name__ == "__main__":
  main()
