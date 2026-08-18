"""Rule-based corridor-layer ranking (no layer name as input).

Score = share of drawing-wide line entities (count) + share of line length,
with entity-type weights: LINE > LWPOLYLINE/POLYLINE > ARC.
Text / annotation is ignored.
"""

from __future__ import annotations

from typing import Any

# Higher weight = more corridor-like drawing primitive
LINE_TYPE_WEIGHTS: dict[str, float] = {
  "LINE": 1.0,
  "LWPOLYLINE": 0.7,
  "POLYLINE": 0.7,
  "ARC": 0.4,
}

LINE_TYPES = frozenset(LINE_TYPE_WEIGHTS)


def _type_counts(record: dict[str, Any]) -> dict[str, int]:
  a = record.get("annotation") or {}
  raw = a.get("type_counts") or {}
  return {k: int(v) for k, v in raw.items() if k in LINE_TYPES and int(v) > 0}


def _length_by_type(record: dict[str, Any]) -> dict[str, float]:
  g = record.get("geometry") or {}
  raw = g.get("length_by_type")
  if isinstance(raw, dict) and raw:
    return {k: float(v) for k, v in raw.items() if k in LINE_TYPES and float(v) > 0}
  # Fallback for older feature files without length_by_type:
  # attribute all length to the dominant line type by count, else LWPOLYLINE.
  total = float(g.get("total_length") or 0.0)
  if total <= 0:
    return {}
  counts = _type_counts(record)
  if not counts:
    return {"LWPOLYLINE": total}
  dominant = max(counts.items(), key=lambda kv: (LINE_TYPE_WEIGHTS[kv[0]] * kv[1], kv[1]))[0]
  return {dominant: total}


def _weighted_count(counts: dict[str, int]) -> float:
  return sum(LINE_TYPE_WEIGHTS[t] * c for t, c in counts.items())


def _weighted_length(lengths: dict[str, float]) -> float:
  return sum(LINE_TYPE_WEIGHTS[t] * L for t, L in lengths.items())


def _score_one(
  layer_name: str,
  record: dict[str, Any],
  global_w_count: float,
  global_w_length: float,
) -> dict[str, Any]:
  counts = _type_counts(record)
  lengths = _length_by_type(record)
  w_count = _weighted_count(counts)
  w_length = _weighted_length(lengths)

  if w_count <= 0 and w_length <= 0:
    return {
      "layer": layer_name,
      "score": 0.0,
      "is_candidate": False,
      "reason": "no_line_entities",
    }

  count_ratio = (w_count / global_w_count) if global_w_count > 0 else 0.0
  length_ratio = (w_length / global_w_length) if global_w_length > 0 else 0.0
  score = count_ratio + length_ratio

  return {
    "layer": layer_name,
    "score": round(score, 6),
    "is_candidate": score > 0.0 and (sum(counts.values()) >= 10 or w_length > 0),
    "signals": {
      "count_ratio": round(count_ratio, 6),
      "length_ratio": round(length_ratio, 6),
      "weighted_count": round(w_count, 3),
      "weighted_length": round(w_length, 3),
      "type_counts": counts,
      "length_by_type": {k: round(v, 3) for k, v in lengths.items()},
    },
  }


def rank_layers(
  features: dict[str, Any],
  top_k: int = 5,
) -> dict[str, Any]:
  layers = features.get("layers") or {}

  per_layer_counts = {name: _type_counts(rec) for name, rec in layers.items()}
  per_layer_lengths = {name: _length_by_type(rec) for name, rec in layers.items()}
  global_w_count = sum(_weighted_count(c) for c in per_layer_counts.values())
  global_w_length = sum(_weighted_length(L) for L in per_layer_lengths.values())

  scored = [
    _score_one(name, rec, global_w_count, global_w_length)
    for name, rec in layers.items()
  ]
  scored.sort(key=lambda x: x["score"], reverse=True)

  candidates = [s for s in scored if s.get("is_candidate")]
  top = scored[:top_k]

  return {
    "source": features.get("source"),
    "top_k": top_k,
    "scoring": {
      "method": "weighted_line_count_and_length_share",
      "type_weights": dict(LINE_TYPE_WEIGHTS),
      "formula": "score = count_ratio + length_ratio (no text)",
      "global_weighted_count": round(global_w_count, 3),
      "global_weighted_length": round(global_w_length, 3),
    },
    "ranked": scored,
    "candidates": candidates,
    "recommended_layers": [s["layer"] for s in top],
    "corridor_layer_guess": top[0]["layer"] if top else None,
  }
