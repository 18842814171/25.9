"""Per-layer statistical features from DXF (streaming) or existing JSON."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ezdxf
import numpy as np
from ezdxf import select

from .dxf_inventory import _window_from_corners
from .geometry import (
  LayerGeomAccumulator,
  Segment,
  _unit,
  segments_from_primitive,
  summarize_geometry,
)

GEOM_TYPES = frozenset({"LINE", "LWPOLYLINE", "ARC", "POLYLINE"})
TEXT_TYPES = frozenset({"TEXT", "MTEXT"})
ANNOT_TYPES = frozenset({"DIMENSION", "LEADER"})


@dataclass
class LayerMetaAccumulator:
  entity_count: int = 0
  type_counts: dict = field(default_factory=lambda: defaultdict(int))
  text_count: int = 0
  text_heights: list = field(default_factory=list)
  dim_count: int = 0
  leader_count: int = 0
  leader_lengths: list = field(default_factory=list)

  def add_entity(self, etype: str) -> None:
    self.entity_count += 1
    self.type_counts[etype] += 1


def _update_text_meta(acc: LayerMetaAccumulator, entity) -> None:
  et = entity.dxftype()
  if et == "TEXT":
    acc.text_count += 1
    if hasattr(entity.dxf, "height"):
      acc.text_heights.append(float(entity.dxf.height))
  elif et == "MTEXT":
    acc.text_count += 1
    if hasattr(entity.dxf, "char_height"):
      acc.text_heights.append(float(entity.dxf.char_height))


def _leader_length(entity) -> float:
  try:
    verts = [v.xyz for v in entity.vertices]
    if len(verts) < 2:
      return 0.0
    total = 0.0
    for i in range(len(verts) - 1):
      a = np.array(verts[i][:2], dtype=float)
      b = np.array(verts[i + 1][:2], dtype=float)
      total += float(np.linalg.norm(b - a))
    return total
  except Exception:
    return 0.0


def _segments_from_dxf_entity(entity) -> list[Segment]:
  et = entity.dxftype()
  segs: list[Segment] = []

  if et == "LINE":
    s = np.array(entity.dxf.start.xyz[:2], dtype=float)
    e = np.array(entity.dxf.end.xyz[:2], dtype=float)
    length = float(np.linalg.norm(e - s))
    segs.append(Segment(s, e, (s + e) / 2, length, _unit(e - s), "line"))
  elif et == "LWPOLYLINE":
    pts = [np.array(p[:2], dtype=float) for p in entity.get_points(format="xy")]
    for k in range(len(pts) - 1):
      s, e = pts[k], pts[k + 1]
      length = float(np.linalg.norm(e - s))
      segs.append(Segment(s, e, (s + e) / 2, length, _unit(e - s), "line"))
  elif et == "ARC":
    try:
      s = np.array(entity.start_point.xyz[:2], dtype=float)
      e = np.array(entity.end_point.xyz[:2], dtype=float)
    except Exception:
      c = np.array(entity.dxf.center.xyz[:2], dtype=float)
      r = float(entity.dxf.radius)
      sa = math.radians(entity.dxf.start_angle)
      ea = math.radians(entity.dxf.end_angle)
      s = c + r * np.array([math.cos(sa), math.sin(sa)])
      e = c + r * np.array([math.cos(ea), math.sin(ea)])
    length = float(np.linalg.norm(e - s))
    segs.append(Segment(s, e, (s + e) / 2, length, _unit(e - s), "arc"))
  elif et == "POLYLINE":
    verts = [np.array(v.dxf.location.xyz[:2], dtype=float) for v in entity.vertices]
    for k in range(len(verts) - 1):
      s, e = verts[k], verts[k + 1]
      length = float(np.linalg.norm(e - s))
      segs.append(Segment(s, e, (s + e) / 2, length, _unit(e - s), "line"))

  return segs


def _summarize_meta(acc: LayerMetaAccumulator, bbox_area: float | None) -> dict[str, Any]:
  heights = acc.text_heights
  leader_lens = acc.leader_lengths
  return {
    "entity_count": acc.entity_count,
    "type_counts": dict(acc.type_counts),
    "text_count": acc.text_count,
    "mean_text_height": round(float(np.mean(heights)), 3) if heights else 0.0,
    "text_density": round(acc.text_count / bbox_area, 6) if bbox_area and bbox_area > 0 else 0.0,
    "dimension_count": acc.dim_count,
    "leader_count": acc.leader_count,
    "mean_leader_length": round(float(np.mean(leader_lens)), 3) if leader_lens else 0.0,
  }


def _layer_bbox_area(layer_entities: list) -> float | None:
  xmin = ymin = float("inf")
  xmax = ymax = float("-inf")
  for entity in layer_entities:
    try:
      ext = entity.get_bbox()
      if not ext:
        continue
      xmin = min(xmin, ext.extmin.x)
      ymin = min(ymin, ext.extmin.y)
      xmax = max(xmax, ext.extmax.x)
      ymax = max(ymax, ext.extmax.y)
    except Exception:
      continue
  if xmin == float("inf"):
    return None
  return max((xmax - xmin) * (ymax - ymin), 1.0)


def compute_features_from_dxf(
  dxf_path: str | Path,
  window_corners: tuple[tuple[float, float], tuple[float, float]] | None = None,
  geom_types: set[str] | None = None,
) -> dict[str, Any]:
  """Stream DXF once; build per-layer feature records."""
  dxf_path = Path(dxf_path)
  gtypes = geom_types or GEOM_TYPES
  scan_types = gtypes | TEXT_TYPES | ANNOT_TYPES

  doc = ezdxf.readfile(str(dxf_path))
  msp = doc.modelspace()

  if window_corners is not None:
    win = _window_from_corners(window_corners)
    entities = list(select.bbox_inside(win, msp))
  else:
    entities = list(msp)

  geom_acc: dict[str, LayerGeomAccumulator] = defaultdict(LayerGeomAccumulator)
  meta_acc: dict[str, LayerMetaAccumulator] = defaultdict(LayerMetaAccumulator)
  layer_entities: dict[str, list] = defaultdict(list)

  for entity in entities:
    et = entity.dxftype()
    if et not in scan_types:
      continue
    layer = entity.dxf.layer.strip() if hasattr(entity.dxf, "layer") else "0"
    meta_acc[layer].add_entity(et)
    layer_entities[layer].append(entity)

    if et in TEXT_TYPES:
      _update_text_meta(meta_acc[layer], entity)
    elif et == "DIMENSION":
      meta_acc[layer].dim_count += 1
    elif et == "LEADER":
      meta_acc[layer].leader_count += 1
      meta_acc[layer].leader_lengths.append(_leader_length(entity))

    if et in gtypes:
      for seg in _segments_from_dxf_entity(entity):
        geom_acc[layer].add(seg, entity_type=et)

  features_by_layer: dict[str, Any] = {}
  for layer in sorted(meta_acc.keys(), key=lambda L: meta_acc[L].entity_count, reverse=True):
    area = _layer_bbox_area(layer_entities[layer])
    geom = summarize_geometry(geom_acc[layer])
    meta = _summarize_meta(meta_acc[layer], area)
    features_by_layer[layer] = {
      "layer": layer,
      "geometry": geom,
      "annotation": meta,
    }

  return {
    "source": str(dxf_path.resolve()),
    "window": window_corners,
    "n_layers": len(features_by_layer),
    "layers": features_by_layer,
  }


def compute_features_from_json(json_path: str | Path) -> dict[str, Any]:
  """Same feature schema from flat primitive JSON (e.g. region0.json)."""
  json_path = Path(json_path)
  with json_path.open(encoding="utf-8") as f:
    primitives = json.load(f)

  geom_acc: dict[str, LayerGeomAccumulator] = defaultdict(LayerGeomAccumulator)
  meta_acc: dict[str, LayerMetaAccumulator] = defaultdict(LayerMetaAccumulator)

  for prim in primitives:
    layer = (prim.get("layer") or "0").strip()
    et = prim.get("type", "")
    meta_acc[layer].add_entity(et)

    if et in TEXT_TYPES:
      attrs = prim.get("attributes") or {}
      meta_acc[layer].text_count += 1
      h = attrs.get("height") or attrs.get("char_height")
      if h is not None:
        meta_acc[layer].text_heights.append(float(h))
    elif et == "DIMENSION":
      meta_acc[layer].dim_count += 1
    elif et == "LEADER":
      meta_acc[layer].leader_count += 1
      verts = (prim.get("attributes") or {}).get("vertices") or []
      if len(verts) >= 2:
        total = 0.0
        for i in range(len(verts) - 1):
          a = np.array(verts[i][:2], dtype=float)
          b = np.array(verts[i + 1][:2], dtype=float)
          total += float(np.linalg.norm(b - a))
        meta_acc[layer].leader_lengths.append(total)

    if et in GEOM_TYPES:
      for seg in segments_from_primitive(prim):
        geom_acc[layer].add(seg, entity_type=et)

  features_by_layer = {}
  for layer in sorted(meta_acc.keys(), key=lambda L: meta_acc[L].entity_count, reverse=True):
    geom = summarize_geometry(geom_acc[layer])
    meta = _summarize_meta(meta_acc[layer], None)
    features_by_layer[layer] = {
      "layer": layer,
      "geometry": geom,
      "annotation": meta,
    }

  return {
    "source": str(json_path.resolve()),
    "window": None,
    "n_layers": len(features_by_layer),
    "layers": features_by_layer,
  }


def save_features(features: dict[str, Any], out_path: str | Path) -> Path:
  out_path = Path(out_path)
  out_path.parent.mkdir(parents=True, exist_ok=True)
  with out_path.open("w", encoding="utf-8") as f:
    json.dump(features, f, ensure_ascii=False, indent=2)
  return out_path
