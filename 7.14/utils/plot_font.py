"""Matplotlib CJK font setup."""

from __future__ import annotations

from typing import Sequence


def setup_cjk_font(candidates: Sequence[str]) -> str | None:
    """Set matplotlib sans-serif to the first available candidate. Return name or None."""
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for name in candidates:
        try:
            path = font_manager.findfont(name, fallback_to_default=False)
            if path:
                plt.rcParams["font.sans-serif"] = [name]
                plt.rcParams["axes.unicode_minus"] = False
                return str(name)
        except Exception:
            continue
    return None
