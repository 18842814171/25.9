"""Fast DXF inventory: entity counts per layer and type (no JSON export)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import select
from ezdxf.math import Vec2

DEFAULT_SCAN_TYPES = frozenset({
  "LINE", "LWPOLYLINE", "ARC", "POLYLINE", "CIRCLE",
  "TEXT", "MTEXT", "DIMENSION", "LEADER", "POINT", "INSERT",
})


def _window_from_corners(corners: tuple[tuple[float, float], tuple[float, float]]):
  c1, c2 = Vec2(corners[0]), Vec2(corners[1])
  return select.Window(c1, c2)


def scan_dxf_inventory(
  dxf_path: str | Path,
  desired_types: set[str] | None = None,
  window_corners: tuple[tuple[float, float], tuple[float, float]] | None = None,
) -> dict[str, Any]:
  """
  Single pass over modelspace. Returns compact inventory dict.
  """
  dxf_path = Path(dxf_path)
  types = set(desired_types) if desired_types else set(DEFAULT_SCAN_TYPES)

  doc = ezdxf.readfile(str(dxf_path))
  msp = doc.modelspace()

  if window_corners is not None:
    win = _window_from_corners(window_corners)
    entities = list(select.bbox_inside(win, msp))
  else:
    entities = list(msp)

  by_layer: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
  total = 0
  xmin = ymin = float("inf")
  xmax = ymax = float("-inf")

  for entity in entities:
    et = entity.dxftype()
    if et not in types:
      continue
    layer = entity.dxf.layer.strip() if hasattr(entity.dxf, "layer") else "0"
    by_layer[layer][et] += 1
    total += 1

    try:
      ext = entity.get_bbox()
      if ext:
        xmin = min(xmin, ext.extmin.x)
        ymin = min(ymin, ext.extmin.y)
        xmax = max(xmax, ext.extmax.x)
        ymax = max(ymax, ext.extmax.y)
    except Exception:
      pass

  layers_sorted = sorted(
    by_layer.keys(),
    key=lambda L: sum(by_layer[L].values()),
    reverse=True,
  )

  return {
    "source": str(dxf_path.resolve()),
    "total_entities_scanned": total,
    "n_layers": len(by_layer),
    "bbox": None if xmin == float("inf") else {
      "min": [round(xmin, 3), round(ymin, 3)],
      "max": [round(xmax, 3), round(ymax, 3)],
    },
    "layers": {
      layer: dict(by_layer[layer]) for layer in layers_sorted
    },
  }


def save_inventory(inventory: dict[str, Any], out_path: str | Path) -> Path:
  out_path = Path(out_path)
  out_path.parent.mkdir(parents=True, exist_ok=True)
  with out_path.open("w", encoding="utf-8") as f:
    json.dump(inventory, f, ensure_ascii=False, indent=2)
  return out_path
