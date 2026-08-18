"""Step 2A normalized geometry merge (arc clips + unmodified LINE/LWPOLYLINE)."""

from __future__ import annotations

import math
from typing import Any


def _expand_lwpolyline(row: dict[str, Any]) -> list[dict[str, Any]]:
  """Expand a LWPOLYLINE primitive into individual LINE segments.

  Each segment inherits the parent handle as ``{handle}_seg{k}`` and
  skips zero-length segments and arc-bulge spans (non-zero bulge).
  """
  attrs = row.get("attributes", {})
  points = attrs.get("points", [])
  if not points:
    return []

  handle = str(row.get("handle", "unknown"))
  layer = row.get("layer") or attrs.get("layer")
  elevation = attrs.get("elevation", 0.0)
  closed = attrs.get("closed", False)

  pt_list = list(points)
  if closed:
    pt_list = pt_list + [pt_list[0]]

  segments: list[dict[str, Any]] = []
  for k in range(len(pt_list) - 1):
    p0 = pt_list[k]
    p1 = pt_list[k + 1]
    bulge = float(p0[4]) if len(p0) > 4 else 0.0
    if bulge != 0.0:
      continue
    x0, y0 = float(p0[0]), float(p0[1])
    x1, y1 = float(p1[0]), float(p1[1])
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-8:
      continue
    seg: dict[str, Any] = {
      "handle": f"{handle}_seg{k}",
      "type": "LINE",
      "attributes": {
        "start": [x0, y0, elevation],
        "end": [x1, y1, elevation],
      },
    }
    if layer is not None:
      seg["layer"] = layer
    segments.append(seg)
  return segments


def merge_normalized_elements(
  arc_lines_doc: dict[str, Any],
  unmodified_doc: dict[str, Any],
) -> list[dict[str, Any]]:
  """
  Merge arc_line_normalize and unmodified_elements into one LINE list.

  Clipped lines take precedence when the same handle appears in both inputs.
  LWPOLYLINE primitives are expanded into individual LINE segments.
  Non-LINE / non-LWPOLYLINE primitives (e.g. retained ARC) are omitted.
  """
  merged: dict[str, dict[str, Any]] = {}
  for row in arc_lines_doc.get("elements") or []:
    if str(row.get("type", "")).upper() != "LINE":
      continue
    merged[str(row["handle"])] = row

  for row in unmodified_doc.get("elements") or []:
    typ = str(row.get("type", "")).upper()
    if typ == "LINE":
      handle = str(row["handle"])
      if handle not in merged:
        merged[handle] = row
    elif typ == "LWPOLYLINE":
      for seg in _expand_lwpolyline(row):
        handle = str(seg["handle"])
        if handle not in merged:
          merged[handle] = seg

  return [merged[h] for h in sorted(merged)]


def normalized_geometry_to_json(
  elements: list[dict[str, Any]],
  *,
  source_stem: str,
) -> dict[str, Any]:
  return {
    "kind": "normalized_geometry",
    "schema_version": 1,
    "source_stem": source_stem,
    "elements": elements,
  }
