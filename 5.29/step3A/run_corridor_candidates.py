"""
Step 3A: parallel edges → corridor candidates (+ wall/centerline PNG).

Example:
  python step3A/run_corridor_candidates.py --stem part1-巷道
  python step3A/run_corridor_candidates.py --stem part1-巷道 --label
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from step3A.pipeline import run_corridor_candidates


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 3A: build corridor candidates from parallel graph",
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

  result = run_corridor_candidates(
    args.stem,
    step2b_dir=args.step2b,
    output_dir=args.output,
    vis=not args.no_vis,
    show_ids=args.label,
  )
  print(
    f"[step3A/candidates] pairs={result['pair_count']} "
    f"candidates={result['candidate_count']}",
  )
  for key, path in result["paths"].items():
    if path is not None:
      print(f"[step3A/candidates] → {path}")


if __name__ == "__main__":
  main()
