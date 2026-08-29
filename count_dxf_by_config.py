"""按 JSON 配置统计 DXF 中指定图层、指定图元类型的数量，输出统计 JSON。

配置兼容现有导出 cfg（``line`` / ``text`` / ``facility`` / ``legend`` 段），
也支持自定义 ``categories`` 段。每段字段：

- ``layers``: 图层名子串列表（命中任一即计入）
- ``entity_types``: 图元类型列表；``null`` / 缺省 / ``[]`` = 不限类型
- ``exclude_layer_keywords``: 可选，从已命中图层中再排除

用法（在代码根目录）::

  python count_dxf_by_config.py --cfg test_input/已做/2系列/2_config.json --dxf 2026.1-2/2026.1-2.dxf
  python count_dxf_by_config.py --cfg 2026.1-1/config.json --dxf 2026.1-1/2026.1-1.dxf -o out.json
  python count_dxf_by_config.py --cfg XJH/config.json --dxf XJH/XJH2025.9.30.dxf -o out3.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent
_UTILS = _ROOT / "7.14" / "utils"
if str(_UTILS) not in sys.path:
  sys.path.insert(0, str(_UTILS))

from entities_filter import filter_msp, resolve_matching_layers  # noqa: E402

_EXPORT_SECTIONS = ("line", "text", "facility", "legend")


def _as_abs(path: Path | str, base: Path = _ROOT) -> Path:
  p = Path(path)
  return p if p.is_absolute() else (base / p)


def load_config(cfg_path: Path) -> dict[str, Any]:
  path = _as_abs(cfg_path)
  if not path.is_file():
    raise FileNotFoundError(f"config not found: {path}")
  return json.loads(path.read_text(encoding="utf-8"))


def resolve_dxf(cfg: dict[str, Any], dxf_arg: Path | None) -> Path:
  raw = dxf_arg if dxf_arg is not None else cfg.get("dxf_file_path")
  if not raw:
    raise ValueError("必须通过 --dxf 或配置中的 dxf_file_path 指定图纸")
  path = _as_abs(raw)
  if path.is_file():
    return path
  if path.suffix.lower() != ".dxf":
    for suf in (".dxf", ".DXF"):
      cand = path.with_suffix(suf) if path.suffix else Path(str(path) + suf)
      if cand.is_file():
        return cand
  raise FileNotFoundError(f"DXF not found: {path}")


def iter_categories(cfg: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
  """返回 (类别名, 段配置)。优先 ``categories``，否则用导出段。"""
  cats = cfg.get("categories") or cfg.get("counts")
  if isinstance(cats, dict) and cats:
    out: list[tuple[str, dict[str, Any]]] = []
    for name, section in cats.items():
      if not isinstance(section, dict):
        raise ValueError(f"categories.{name} 必须是对象")
      out.append((str(name), section))
    return out

  out = []
  for key in _EXPORT_SECTIONS:
    section = cfg.get(key)
    if isinstance(section, dict) and section.get("layers"):
      out.append((key, section))
  if not out:
    raise ValueError(
      "配置中未找到可统计段：需要 categories{}，"
      "或 line/text/facility/legend 且含非空 layers"
    )
  return out


def normalize_types(raw: Any) -> list[str] | None:
  if raw is None or raw == []:
    return None
  types = [str(t).upper() for t in raw if str(t).strip()]
  return types or None


def count_section(
  dxf: Path,
  *,
  layers: list[str],
  entity_types: list[str] | None,
  exclude_layer_keywords: list[str] | None = None,
) -> dict[str, Any]:
  excl = [str(k) for k in (exclude_layer_keywords or []) if str(k).strip()]
  matched = resolve_matching_layers(str(dxf), layers, excl)
  filtered = filter_msp(str(dxf), entity_types, layers, excl)
  type_counts = Counter(e.dxftype() for e in filtered)
  layer_counts = Counter(e.dxf.layer for e in filtered)
  return {
    "count": len(filtered),
    "layers_patterns": list(layers),
    "exclude_layer_keywords": excl,
    "entity_types": entity_types,
    "matched_layers": matched,
    "type_counts": dict(sorted(type_counts.items())),
    "layer_counts": dict(sorted(layer_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
  }


def count_dxf_by_config(
  cfg: dict[str, Any],
  dxf: Path,
  *,
  only: set[str] | None = None,
) -> dict[str, Any]:
  categories = iter_categories(cfg)
  by_cat: dict[str, Any] = {}
  total = 0
  for name, section in categories:
    if only is not None and name not in only:
      continue
    layers = section.get("layers") or []
    if not layers:
      raise ValueError(f"{name}.layers 不能为空")
    detail = count_section(
      dxf,
      layers=[str(x) for x in layers],
      entity_types=normalize_types(section.get("entity_types")),
      exclude_layer_keywords=section.get("exclude_layer_keywords") or [],
    )
    by_cat[name] = detail
    total += int(detail["count"])

  return {
    "dxf": str(dxf.as_posix()),
    "stem": dxf.stem,
    "by_category": by_cat,
    "category_total": total,
    "note": (
      "layers 为子串匹配；entity_types=null 表示不限类型；"
      "category_total 为各类 count 之和（图元若命中多类会被重复加总）"
    ),
  }


def main() -> None:
  parser = argparse.ArgumentParser(
    description="按 JSON 配置统计 DXF 指定图层/图元数量"
  )
  parser.add_argument("--cfg", "--config", dest="config", type=Path, required=True)
  parser.add_argument(
    "--dxf",
    type=Path,
    default=None,
    help="覆盖配置中的 dxf_file_path",
  )
  parser.add_argument(
    "--only",
    nargs="*",
    default=None,
    help="只统计这些类别名（如 line text facility）",
  )
  parser.add_argument(
    "-o",
    "--output",
    type=Path,
    default=None,
    help="输出 JSON 路径（默认 {stem}_layer_entity_stats.json）",
  )
  args = parser.parse_args()

  cfg_path = _as_abs(args.config)
  cfg = load_config(cfg_path)
  dxf = resolve_dxf(cfg, args.dxf)
  only = set(args.only) if args.only else None
  stats = count_dxf_by_config(cfg, dxf, only=only)
  stats["config"] = str(cfg_path.as_posix())

  out = args.output
  if out is None:
    out = _ROOT / f"{dxf.stem}_layer_entity_stats.json"
  else:
    out = _as_abs(out)
  out.parent.mkdir(parents=True, exist_ok=True)
  out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
  print(json.dumps(stats, ensure_ascii=False, indent=2))
  print(f"saved: {out}")


if __name__ == "__main__":
  main()
