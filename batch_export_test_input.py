"""从 DXF 导出巷道/文字/设施（及可选图例）JSON，默认写入 test_input。

用法（在代码根目录；--cfg 必填，不许留空/默认）：
  # 整图：指定 --src，通常加 --with-legend
  python batch_export_test_input.py --src 2026.1-1 --cfg test_input/2016_config.json --with-legend

  # 局部图：不传 --src，遍历 test_input/*.dxf
  python batch_export_test_input.py --cfg test_input/2016_config.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent
EXPORT_ROOT = CODE_ROOT / "7.14"
UTILS = EXPORT_ROOT / "utils"
if str(UTILS) not in sys.path:
    sys.path.insert(0, str(UTILS))
if str(EXPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPORT_ROOT))

from entity_export import exec as export_exec  # noqa: E402
from temp_clean_text_export import clean_text_export  # noqa: E402

MODES = ("line", "text", "facility")
MODES_WITH_LEGEND = ("line", "text", "facility", "legend")


def _as_abs(path: Path, base: Path = CODE_ROOT) -> Path:
    return path if path.is_absolute() else (base / path)


def resolve_src_dxf(src: str | Path) -> Path:
    """解析 --src：相对代码根的路径（可省略 .dxf），兼试 test_input/{图号}.dxf。"""
    raw = Path(str(src).replace("\\", "/"))
    rel = raw
    if rel.suffix.lower() == ".dxf":
        rel = rel.with_suffix("")

    candidates = [
        _as_abs(Path(f"{rel}.dxf")),
        _as_abs(Path(f"{rel}.DXF")),
        CODE_ROOT / "test_input" / f"{rel.name}.dxf",
        CODE_ROOT / "test_input" / f"{rel.name}.DXF",
    ]
    if raw.is_absolute() and raw.is_file():
        return raw
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(
        f"Missing DXF for --src={src}; tried: "
        + ", ".join(str(c) for c in candidates)
    )


def list_test_input_dxf(input_dir: Path, stem: str | None = None) -> list[Path]:
    if stem:
        candidates = [input_dir / f"{stem}.dxf", input_dir / f"{stem}.DXF"]
        found = [p for p in candidates if p.is_file()]
        if not found:
            raise FileNotFoundError(f"DXF not found for stem={stem} under {input_dir}")
    else:
        found = sorted(input_dir.glob("*.dxf")) + sorted(input_dir.glob("*.DXF"))

    uniq: dict[str, Path] = {}
    for p in found:
        uniq[p.resolve().as_posix().lower()] = p
    return list(uniq.values())


def export_one(
    dxf: Path,
    output_dir: Path,
    config: Path,
    *,
    with_legend: bool = False,
) -> None:
    stem = dxf.stem
    modes = MODES_WITH_LEGEND if with_legend else MODES
    print(f"\n===== export {stem} ({', '.join(modes)}) =====")
    for mode in modes:
        export_exec(
            config_path=config,
            mode=mode,
            dxf_file_path=dxf,
            output_dir=output_dir,
        )
    # 文字 JSON：去掉巷道描边，并为 INSERT 补 bbox/radius
    text_json = output_dir / f"{stem}-文字.json"
    if text_json.is_file():
        summary = clean_text_export(
            text_json,
            dxf,
            out_path=text_json,
            dry_run=False,
            backup=False,
        )
        dropped = sum(summary["dropped_strokes"].values())
        print(
            f"[clean_text] {stem}: {summary['before']} → {summary['after']} "
            f"(dropped_strokes={dropped}, insert_bbox={summary['insert_bbox_enriched']})"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export line/text/facility JSON; --src=整图，否则遍历 test_input"
    )
    parser.add_argument(
        "--cfg",
        "--config",
        dest="config",
        type=Path,
        required=True,
        help="导出配置文件路径（必填，不许留空/默认；如 test_input/2016_config.json）；layers 按子串匹配",
    )
    parser.add_argument(
        "--src",
        type=str,
        default="",
        help="整图 DXF 路径（相对代码根，可省略 .dxf）；省略则遍历 test_input",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=CODE_ROOT / "test_input",
        help="局部图扫描目录（仅在未传 --src 时使用；默认 ./test_input）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="JSON 输出目录（默认: test_input）",
    )
    parser.add_argument(
        "--stem",
        type=str,
        default="",
        help="仅导出 test_input 中指定图号（仅在未传 --src 时有效）",
    )
    parser.add_argument(
        "--with-legend",
        action="store_true",
        help="同时导出图例 JSON（整图专用；局部图勿用）",
    )
    args = parser.parse_args()

    config = _as_abs(args.config)
    if not config.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config}")

    output_dir = args.output_dir if args.output_dir is not None else CODE_ROOT / "test_input"
    output_dir = _as_abs(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.src:
        dxfs = [resolve_src_dxf(args.src)]
        print(f"模式: 整图 --src={args.src} → {dxfs[0]}")
    else:
        input_dir = _as_abs(args.input_dir)
        if not input_dir.is_dir():
            raise FileNotFoundError(f"Missing folder: {input_dir}")
        dxfs = list_test_input_dxf(input_dir, args.stem or None)
        print(f"模式: 遍历 {input_dir}（{len(dxfs)} 个 DXF）")

    if not dxfs:
        raise FileNotFoundError("no DXF to export")

    for dxf in dxfs:
        export_one(dxf, output_dir, config, with_legend=args.with_legend)

    print(f"\nDone. JSON → {output_dir}")


if __name__ == "__main__":
    main()
