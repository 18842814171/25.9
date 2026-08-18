"""Candidate-stage scoring: layer, distance decay, text orientation."""

from __future__ import annotations

import math

from config import Step1aConfig
from text_roles import is_control_point_layer

CFG = Step1aConfig()


def distance_decay_score(distance: float, search_radius: float) -> float | None:
    """
    Two-tier distance score relative to search_radius.
    Tier1 [0, tier1_ratio * R]: normal score.
    Tier2 (tier1, tier2_ratio * R]: score multiplied by tier2_factor.
    Beyond tier2: not a candidate (None).
    """
    radius = max(float(search_radius), 1e-6)
    tier1 = CFG.distance_tier1_ratio * radius
    tier2 = CFG.distance_tier2_ratio * radius
    d = float(distance)
    if d > tier2:
        return None
    # Linear falloff toward the outer rim of tier2 (normal base score).
    base = max(0.0, 1.0 - d / tier2)
    if d <= tier1:
        return base
    return base * CFG.distance_tier2_factor


def bind_distance_score(
    distance: float,
    bind_radius: float,
    *,
    cfg: Step1aConfig | None = None,
) -> float | None:
    """
    Bind-group distance confidence relative to inferred bind radius R.
    Tier1 [0, bind_tier1_ratio * R]: normal linear score 1 - d/R.
    Tier2 (tier1, R]: same base then * bind_tier2_factor.
    Beyond R: None (not a bind candidate).
    """
    cfg = cfg or CFG
    radius = max(float(bind_radius), 1e-6)
    tier1 = float(cfg.bind_tier1_ratio) * radius
    d = float(distance)
    if d > radius or d < 0.0:
        return None
    base = max(0.0, 1.0 - d / radius)
    if d <= tier1:
        return base
    return base * float(cfg.bind_tier2_factor)


def bind_density_factor(
    n_competitors: int,
    *,
    cfg: Step1aConfig | None = None,
) -> float:
    """
    Dense-area penalty: extra same-role competitors near a candidate pair
    lower confidence (n_competitors counts *other* rivals, not self).
    """
    cfg = cfg or CFG
    extra = max(0, int(n_competitors))
    if extra <= 0:
        return 1.0
    return 1.0 / (1.0 + float(cfg.bind_density_penalty) * float(extra))


def bind_link_confidence(
    *,
    distance: float,
    bind_radius: float,
    n_competitors: int = 0,
    orientation_ok: bool = True,
    cfg: Step1aConfig | None = None,
) -> float | None:
    """Combined bind-edge confidence; None means reject the link."""
    cfg = cfg or CFG
    if not orientation_ok:
        return None
    d_score = bind_distance_score(distance, bind_radius, cfg=cfg)
    if d_score is None:
        return None
    conf = float(d_score) * bind_density_factor(n_competitors, cfg=cfg)
    if conf < float(cfg.min_bind_link_confidence):
        return None
    return round(conf, 4)


def bind_group_confidence(link_scores: list[float]) -> float:
    """Group confidence = min link score (weakest edge dominates)."""
    if not link_scores:
        return 0.0
    return round(min(float(s) for s in link_scores), 4)


def layer_score(ent: dict, role: str, kind_rule: dict) -> float:
    """1.0 when layer maps to the role; partial credit for control-point family."""
    layer_roles = kind_rule.get("layer_roles") or {}
    layer = str(ent.get("layer") or "")
    if layer_roles.get(layer) == role:
        return 1.0
    if role in {"point_id", "elevation"} and is_control_point_layer(layer):
        return 0.85
    if role in {"borehole_id", "collar", "seam_value", "elevation"} and layer:
        # 图层未写入规则映射时的弱分
        return 0.35
    return 0.2


def _angle_diff_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two degrees in [0, 180]."""
    d = abs(float(a) - float(b)) % 360.0
    if d > 180.0:
        d = 360.0 - d
    return d


def orientation_score(members: list[dict]) -> float:
    """
    Consistency of text rotation among member texts.
    Single text → 1.0; larger angular spread → lower score.
    """
    rots = [
        float(m.get("rotation") or 0.0)
        for m in members
        if str(m.get("shape_type") or "") == "text"
    ]
    if len(rots) <= 1:
        return 1.0
    ref = rots[0]
    diffs = [_angle_diff_deg(ref, r) for r in rots[1:]]
    mean_diff = sum(diffs) / len(diffs)
    tol = max(float(CFG.orientation_tolerance_deg), 1e-6)
    return max(0.0, 1.0 - mean_diff / tol)


def member_total_score(
    *,
    layer: float,
    distance: float,
    orientation: float,
) -> float:
    w_l = float(CFG.score_weight_layer)
    w_d = float(CFG.score_weight_distance)
    w_o = float(CFG.score_weight_orientation)
    total_w = w_l + w_d + w_o
    if total_w <= 0:
        return 0.0
    return (w_l * layer + w_d * distance + w_o * orientation) / total_w


def cluster_total_score(member_scores: list[float], *, has_required_id: bool) -> float:
    if not member_scores or not has_required_id:
        return 0.0
    avg = sum(member_scores) / len(member_scores)
    return round(min(avg, 0.99), 3)
