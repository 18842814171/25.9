"""Load manual corridor labels (train-time only)."""

from __future__ import annotations

import json
from pathlib import Path


def load_labels(path: Path) -> dict[str, int]:
  """
  JSON formats:
    {"corridor_layers": ["A"], "non_corridor_layers": ["B"]}
    {"layers": {"A": 1, "B": 0}}
  """
  with path.open(encoding="utf-8") as f:
    data = json.load(f)

  if "layers" in data:
    return {k: int(v) for k, v in data["layers"].items()}

  out: dict[str, int] = {}
  for name in data.get("corridor_layers", []):
    out[name] = 1
  for name in data.get("non_corridor_layers", []):
    out[name] = 0
  return out
