"""Matplotlib axis helpers."""

from __future__ import annotations

import matplotlib.pyplot as plt


def apply_plot_bounds(ax: plt.Axes, bounds: list[tuple[float, float]]) -> None:
  if not bounds:
    return
  xs = [p[0] for p in bounds]
  ys = [p[1] for p in bounds]
  pad_x = max((max(xs) - min(xs)) * 0.02, 1.0)
  pad_y = max((max(ys) - min(ys)) * 0.02, 1.0)
  ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
  ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)
