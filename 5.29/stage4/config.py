"""Stage 4 threshold configuration (relative to median corridor width)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Stage4Config:
  """Stage 4 stub 语义分类阈值与尺度倍数。"""

  # 平行腿长判定倍数：stub 长度 ≥ parallel_length_scale × 平行边宽度 时视为“长腿”。
  # ========================== 重要 ==================================
  #   这是 2.7
  # ==================================================================
  # 用于横档（AUXILIARY_CORRIDOR）双长腿判定，以及 niche 三连链中排除横档形长腿对。
  # 平行边宽度取自 stub-stub-parallel 边的 width；缺失时回退 median_corridor_width。
  parallel_length_scale: float = 2.3

  # 腿长比较的浮点容差，避免 length ≈ threshold 时因舍入误判短腿/长腿。
  length_tol: float = 1e-4

  # 规则命中（niche / 可能巷壁 / 横档）时写入节点的 semantic_confidence。
  default_confidence: float = 0.95

  # 四条规则均未命中（UNCLASSIFIED）时的 semantic_confidence。
  unclassified_confidence: float = 0.0

  # 运行时由中心线图 global_scale 解析填入，作为平行边宽度的全局回退值（米）。
  # 不手写绝对长度；腿长阈值始终与 parallel_length_scale 相乘得到。
  median_corridor_width: float | None = None

  def apply_global_scale(self, scale: dict[str, float]) -> None:
    w = scale.get("median_corridor_width")
    if w is not None:
      self.median_corridor_width = float(w)

  def to_json(self) -> dict[str, float]:
    out: dict[str, float] = {
      "parallel_length_scale": self.parallel_length_scale,
      "length_tol": self.length_tol,
      "default_confidence": self.default_confidence,
      "unclassified_confidence": self.unclassified_confidence,
    }
    if self.median_corridor_width is not None:
      out["median_corridor_width"] = self.median_corridor_width
    return out
