"""Shared text cleaning for DXF TEXT / MTEXT."""

from __future__ import annotations

import re

_MTEXT_PREFIX_RE = re.compile(r"^\\A\d+;")


def clean_text(raw: str) -> str:
    t = (raw or "").strip()
    t = _MTEXT_PREFIX_RE.sub("", t)
    t = t.replace("\\P", " ").replace("\n", " ").strip()
    return " ".join(t.split())


def plain_mtext(entity) -> str:
    try:
        return clean_text(entity.plain_text())
    except Exception:
        return clean_text(str(getattr(entity.dxf, "text", "") or ""))
