"""图层同义词词典：关键词 → 三类（control_point / borehole / other）。

流程：排除无关图层后，用图层名（或图例标题文本）子串命中 families 关键词，直接定族。
多命中时取最长关键词。numeric_role_hints 仅区分孔口等数值细角色。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from utils.paths import project_root

_FAMILY_KEYS = ("control_point", "borehole")


def default_synonyms_path() -> Path:
    return project_root() / "stage1" / "layer_synonyms.json"


@lru_cache(maxsize=4)
def load_family_lexicon(
    path: str | None = None,
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """返回 (families, collar_hints)。"""
    p = Path(path) if path else default_synonyms_path()
    doc = json.loads(p.read_text(encoding="utf-8"))
    raw = doc.get("families") or {}
    families: dict[str, tuple[str, ...]] = {}
    for key in _FAMILY_KEYS:
        syns = [str(s).strip() for s in (raw.get(key) or []) if str(s).strip()]
        families[key] = tuple(sorted(set(syns), key=len, reverse=True))
    hints = doc.get("numeric_role_hints") or {}
    collar = [str(s).strip() for s in (hints.get("collar") or []) if str(s).strip()]
    collar_sorted = tuple(sorted(set(collar), key=len, reverse=True))
    return families, collar_sorted


def match_family(layer: str, path: str | None = None) -> str:
    """
    图层名 / 标题文本 → control_point / borehole / other。
    在所有族的关键词中取最长命中；同长则按 control_point → borehole 优先。
    """
    layer = layer or ""
    if not layer:
        return "other"
    families, _ = load_family_lexicon(path)
    best_tok = ""
    best_family = "other"
    for family in _FAMILY_KEYS:
        for tok in families.get(family) or ():
            if tok not in layer:
                continue
            if len(tok) > len(best_tok) or (
                len(tok) == len(best_tok) and best_family == "other"
            ):
                best_tok = tok
                best_family = family
            break
    return best_family


def is_collar_layer(layer: str, path: str | None = None) -> bool:
    """图层名是否暗示孔口标高（数值细角色 collar）。"""
    layer = layer or ""
    if not layer:
        return False
    _, collar_hints = load_family_lexicon(path)
    return any(tok in layer for tok in collar_hints)


def family_tokens(family: str, path: str | None = None) -> tuple[str, ...]:
    families, _ = load_family_lexicon(path)
    return families.get(family) or ()
