"""Step 3B configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AttachConfig:
  """Residual attach and RC linking thresholds (relative to median corridor width)."""

  endpoint_link_gap_scale: float = 1.5
  attach_tol_scale: float = 0.2

  median_corridor_width: float | None = None
  endpoint_link_gap: float = field(default=0.0, repr=False)
  attach_tol: float = field(default=0.0, repr=False)

  def to_json(self) -> dict[str, float]:
    out: dict[str, float] = {
      "endpoint_link_gap_scale": self.endpoint_link_gap_scale,
      "attach_tol_scale": self.attach_tol_scale,
    }
    if self.median_corridor_width is not None:
      out["median_corridor_width"] = self.median_corridor_width
    if self.endpoint_link_gap > 0:
      out["endpoint_link_gap"] = self.endpoint_link_gap
    if self.attach_tol > 0:
      out["attach_tol"] = self.attach_tol
    return out
