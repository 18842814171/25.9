"""
Step 2A merge normalized geometry CLI.

Reads arc_line_normalize.json and unmodified_elements.json; writes normalized_geometry.json.

Example:
  python step2A/merge_normalized_geometry.py --stem part2-巷道
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

from stage2.io import load_json, save_json
from step2A.normalized_geometry import (
  merge_normalized_elements,
  normalized_geometry_to_json,
)
from step2A.paths import (
  arc_line_normalize_json,
  normalized_geometry_json,
  step2a_output_dir,
  unmodified_elements_json,
)


def export_merge_normalized_geometry(
  stem: str,
  *,
  output_dir: Path | None = None,
) -> dict:
  out = step2a_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  arc_path = arc_line_normalize_json(stem, out)
  unmod_path = unmodified_elements_json(stem, out)
  if not arc_path.is_file():
    raise FileNotFoundError(
      f"Missing {arc_path}; run step2A/arc_normalize.py first.",
    )
  if not unmod_path.is_file():
    raise FileNotFoundError(
      f"Missing {unmod_path}; run step2A/arc_normalize.py first.",
    )

  arc_doc = load_json(arc_path)
  unmod_doc = load_json(unmod_path)
  elements = merge_normalized_elements(arc_doc, unmod_doc)

  out_path = normalized_geometry_json(stem, out)
  save_json(normalized_geometry_to_json(elements, source_stem=stem), out_path)

  return {
    "elements": elements,
    "path": out_path,
    "clipped_count": len(arc_doc.get("elements") or []),
    "unmodified_line_count": sum(
      1 for e in (unmod_doc.get("elements") or [])
      if str(e.get("type", "")).upper() == "LINE"
    ),
  }


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Step 2A: arc_line_normalize + unmodified_elements → normalized_geometry.json",
  )
  parser.add_argument("--stem", required=True)
  parser.add_argument("--output", type=Path, default=None)
  args = parser.parse_args()

  result = export_merge_normalized_geometry(args.stem, output_dir=args.output)
  print(
    f"[step2A/merge_normalized_geometry] lines={len(result['elements'])} "
    f"(clipped={result['clipped_count']}, "
    f"unmodified_lines={result['unmodified_line_count']})",
  )
  print(f"[step2A/merge_normalized_geometry] → {result['path']}")


if __name__ == "__main__":
  main()
