"""仓库根路径与相对路径解析。"""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_under_root(path_str: str | Path) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = project_root() / path
    return path
