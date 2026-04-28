from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

TYPE_GROUPS = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".svg"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".m4v"},
    "Audio": {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"},
    "Documents": {".doc", ".docx", ".txt", ".rtf", ".odt", ".pages"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "Code": {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".xml", ".c", ".cpp", ".cs", ".java", ".go", ".rb", ".php", ".sh"},
    "Spreadsheets": {".xls", ".xlsx", ".csv", ".ods"},
    "PDFs": {".pdf"},
}

DEFAULT_GROUP = "Others"


@dataclass
class FileContext:
    path: Path
    relative_path: str
    category: str
    created_date: datetime
    modified_date: datetime
    metadata_date: datetime | None
    size: int
    file_hash: str | None = None


def file_category(path: Path) -> str:
    return next((group for group, exts in TYPE_GROUPS.items() if path.suffix.lower() in exts), DEFAULT_GROUP)


def apply_custom_rules(path: Path, rules: list[dict]) -> str | None:
    name = path.name.lower()
    rel = str(path).lower()
    for rule in rules:
        keyword = str(rule.get("keyword", "")).strip().lower()
        target = str(rule.get("target", "")).strip()
        if keyword and target and (keyword in name or keyword in rel):
            return target
    return None


def get_sort_date(ctx: FileContext, basis: str) -> datetime:
    if basis == "creation":
        return ctx.created_date
    if basis == "metadata" and ctx.metadata_date:
        return ctx.metadata_date
    return ctx.modified_date


def date_folder(dt: datetime) -> str:
    return f"{dt:%Y/%m}"


def parse_rule_lines(text: str) -> list[dict]:
    rules: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" in line:
            keyword, target = line.split("=>", 1)
        elif "->" in line:
            keyword, target = line.split("->", 1)
        else:
            continue
        keyword = keyword.strip()
        target = target.strip()
        if keyword and target:
            rules.append({"keyword": keyword, "target": target})
    return rules


def duplicate_key(path: Path, criteria: list[str], size: int, file_hash: str | None) -> tuple:
    key = []
    if "name" in criteria:
        key.append(path.name.lower())
    if "size" in criteria:
        key.append(size)
    if "hash" in criteria:
        key.append(file_hash)
    return tuple(key)


def should_use_date_mode(settings: dict) -> bool:
    return str(settings.get("organization_mode", "type")) == "date"


def structured_name(
    original_name: str,
    category: str,
    index: int,
    ext: str,
    ctx_date: datetime | None,
    size: int,
    file_hash: str | None,
    pattern: str,
) -> str:
    stem = Path(original_name).stem
    mapping = {
        "category": category,
        "index": index,
        "original": stem,
        "stem": stem,
        "ext": ext,
        "date": ctx_date.strftime("%Y_%m_%d") if ctx_date else "unknown_date",
        "size": size,
        "hash": (file_hash or "")[:8],
    }

    def replace(match: re.Match[str]) -> str:
        key = match.group("key")
        fmt = match.group("fmt")
        value = mapping.get(key, "")
        if key == "index":
            num = int(value)
            if fmt:
                return format(num, fmt)
            return str(num)
        return str(value)

    def repl(match: re.Match[str]) -> str:
        key = match.group("key")
        fmt = match.group("fmt")
        if key == "index":
            num = int(mapping["index"])
            if fmt:
                return format(num, fmt)
            return str(num)
        return str(mapping.get(key, ""))

    # {index:03d} or {category}
    result = re.sub(r"\{(?P<key>[a-z_]+)(?::(?P<fmt>[^}]+))?\}", repl, pattern)
    if "{ext}" not in pattern and ext:
        result = f"{result}{ext}"
    return result


def choose_destination(
    settings: dict,
    ctx: FileContext,
    custom_target: str | None,
) -> list[str]:
    mode = str(settings.get("organization_mode", "type"))
    if custom_target:
        return [custom_target]
    if mode == "date":
        return [date_folder(get_sort_date(ctx, str(settings.get("date_basis", "modified"))))]
    if mode == "custom":
        return ["Custom"]
    return [ctx.category]
