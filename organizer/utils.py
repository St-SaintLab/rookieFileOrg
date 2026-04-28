from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

INVALID_CHARS = r'<>:"/\\|?*'
_invalid_re = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_component(value: str, replacement: str = "_") -> str:
    value = _invalid_re.sub(replacement, value or "")
    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip(". ")
    return value or "untitled"


def safe_filename(filename: str) -> str:
    path = Path(filename)
    stem = sanitize_component(path.stem)
    suffix = sanitize_component(path.suffix.lstrip(".")) if path.suffix else ""
    return f"{stem}.{suffix}" if suffix else stem


def ensure_unique_name(path: Path) -> Path:
    if not path.exists():
        return path
    base = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{base}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def format_size(num_bytes: int) -> str:
    value = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel_parts(path: str) -> list[str]:
    return [p for p in Path(path).parts if p not in ("", ".", "..")]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify_folder_name(value: str) -> str:
    value = sanitize_component(value)
    value = re.sub(r"\s+", "_", value)
    return value.lower()


def iter_files(root: Path) -> Iterable[Path]:
    for item in root.rglob("*"):
        if item.is_file():
            yield item
