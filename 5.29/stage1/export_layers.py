"""Compact JSON export for selected layers only (avoids one huge file)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import select

from .dxf_inventory import _window_from_corners

EXPORT_TYPES = frozenset({
  "LINE", "LWPOLYLINE", "ARC", "POLYLINE", "TEXT", "MTEXT", "DIMENSION", "LEADER",
})


def _entity_to_dict(entity, doc) -> dict[str, Any] | None:
  """Minimal primitive dict compatible with 0-巷道几何信息图谱.py."""
  et = entity.dxftype()
  if et not in EXPORT_TYPES:
    return None

  layer = entity.dxf.layer.strip() if hasattr(entity.dxf, "layer") else "0"
  handle = entity.dxf.handle
  attr: dict[str, Any] = {}

  if et == "LINE":
    attr["start"] = list(entity.dxf.start.xyz)
    attr["end"] = list(entity.dxf.end.xyz)
  elif et == "LWPOLYLINE":
    attr["points"] = [list(p) for p in entity.get_points(format="xyseb")]
    attr["closed"] = entity.closed
  elif et == "ARC":
    attr["center"] = list(entity.dxf.center.xyz)
    attr["radius"] = float(entity.dxf.radius)
    attr["start_angle"] = float(entity.dxf.start_angle)
    attr["end_angle"] = float(entity.dxf.end_angle)
    try:
      attr["start"] = list(entity.start_point.xyz)
      attr["end"] = list(entity.end_point.xyz)
    except Exception:
      pass
  elif et == "TEXT":
    attr["text"] = entity.dxf.text
    attr["insert_point"] = list(entity.dxf.insert.xyz)
    attr["height"] = float(entity.dxf.height)
    attr["rotation"] = float(entity.dxf.rotation)
  elif et == "MTEXT":
    attr["text"] = entity.text
    attr["insert_point"] = list(entity.dxf.insert.xyz)
    attr["char_height"] = float(entity.dxf.char_height)
    attr["rotation"] = float(entity.dxf.rotation)
  elif et == "LEADER":
    attr["vertices"] = [list(v.xyz) for v in entity.vertices]
  elif et == "DIMENSION":
    attr["text"] = entity.dxf.text
    attr["dimtype"] = entity.dxf.dimtype
    try:
      attr["measurement"] = entity.get_measurement()
    except Exception:
      pass
  else:
    return None

  return {"handle": handle, "type": et, "layer": layer, "attributes": _round_floats(attr)}


def _round_floats(obj: Any, ndigits: int = 3) -> Any:
  if isinstance(obj, float):
    if math.isfinite(obj):
      return round(obj, ndigits)
    return obj
  if isinstance(obj, list):
    return [_round_floats(x, ndigits) for x in obj]
  if isinstance(obj, dict):
    return {k: _round_floats(v, ndigits) for k, v in obj.items()}
  return obj


def export_layers_to_json(
  dxf_path: str | Path,
  layer_names: list[str],
  out_path: str | Path,
  window_corners: tuple | None = None,
) -> Path:
  dxf_path = Path(dxf_path)
  out_path = Path(out_path)
  out_path.parent.mkdir(parents=True, exist_ok=True)

  layer_set = set(layer_names)
  doc = ezdxf.readfile(str(dxf_path))
  msp = doc.modelspace()

  if window_corners is not None:
    win = _window_from_corners(window_corners)
    entities = select.bbox_inside(win, msp)
  else:
    entities = msp

  data = []
  for entity in entities:
    layer = entity.dxf.layer.strip() if hasattr(entity.dxf, "layer") else "0"
    if layer not in layer_set:
      continue
    row = _entity_to_dict(entity, doc)
    if row:
      data.append(row)

  with out_path.open("w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

  return out_path
