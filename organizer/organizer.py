from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from organizer.classifier import (
    FileContext,
    apply_custom_rules,
    choose_destination,
    file_category,
    get_sort_date,
    parse_rule_lines,
    structured_name,
)
from organizer.config import DEFAULT_SETTINGS, merge_settings
from organizer.metadata import file_metadata, preferred_metadata_date
from organizer.utils import ensure_unique_name, format_size, now_iso, rel_parts, safe_filename


def save_uploaded_folder(upload_id: str, session_dir: Path, files, relative_paths: list[str] | None) -> dict:
    session_dir.mkdir(parents=True, exist_ok=True)

    root_name = None
    total_size = 0

    for idx, file in enumerate(files):
        rel_path = relative_paths[idx] if relative_paths else file.filename
        rel_path = rel_path or file.filename or f"file_{idx}"
        parts = rel_parts(rel_path)
        if not parts:
            parts = [safe_filename(file.filename or f"file_{idx}")]
        if root_name is None and len(parts) > 1:
            root_name = parts[0]
        total_size += int(getattr(file, "content_length", 0) or 0)

        target_path = session_dir.joinpath(*parts)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        file.save(target_path)
        if total_size == 0:
            try:
                total_size += target_path.stat().st_size
            except Exception:  # noqa: BLE001
                pass

    if root_name is None:
        root_name = "Uploaded Folder"

    return {
        "upload_id": upload_id,
        "session_dir": str(session_dir),
        "folder_name": root_name,
        "size_bytes": _folder_size(session_dir),
        "uploaded_at": now_iso(),
    }


def _folder_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except Exception:  # noqa: BLE001
                pass
    return total


def _normalize_settings(settings: dict) -> dict:
    merged = merge_settings(DEFAULT_SETTINGS, settings or {})
    merged.setdefault("categories_enabled", DEFAULT_SETTINGS["categories_enabled"].copy())
    merged.setdefault("duplicate_criteria", DEFAULT_SETTINGS["duplicate_criteria"][:])
    merged.setdefault("rename_pattern", DEFAULT_SETTINGS["rename_pattern"])
    merged.setdefault("custom_rules_text", "")
    merged.setdefault("organization_mode", "type")
    merged.setdefault("date_basis", "modified")
    merged.setdefault("recursive_scan", True)
    merged.setdefault("read_metadata", True)
    merged.setdefault("rename_enabled", True)
    merged.setdefault("duplicate_detection", True)
    return merged


def organize_upload_session(session: dict, settings: dict, job_root: Path) -> dict:
    session_dir = Path(session["session_dir"])
    if not session_dir.exists():
        raise FileNotFoundError("Missing source folder.")

    settings = _normalize_settings(settings)
    rules = parse_rule_lines(settings.get("custom_rules_text", ""))

    job_id = os.urandom(8).hex()
    job_dir = job_root / job_id
    organized_dir = job_dir / "organized"
    logs: list[dict] = []
    organized_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    root = session_dir
    files = list(root.rglob("*")) if settings.get("recursive_scan", True) else [p for p in root.iterdir()]
    files = [p for p in files if p.is_file()]

    if not files:
        raise FileNotFoundError("No files found in the uploaded folder.")

    metadata_map: dict[Path, dict] = {}
    for path in files:
        try:
            metadata_map[path] = file_metadata(path) if settings.get("read_metadata", True) else {}
        except Exception as exc:  # noqa: BLE001
            metadata_map[path] = {}
            logs.append(_log("metadata_error", path, None, f"Metadata read failed: {exc}"))

    seen_duplicates = {}
    duplicate_criteria = settings.get("duplicate_criteria") or []
    category_counters = defaultdict(int)
    date_counters = defaultdict(int)

    for path in files:
        try:
            meta = metadata_map.get(path, {})
            category = file_category(path)
            custom_target = apply_custom_rules(path, rules) if rules else None

            created = meta.get("created") or datetime.fromtimestamp(path.stat().st_ctime)
            modified = meta.get("modified") or datetime.fromtimestamp(path.stat().st_mtime)
            metadata_date = preferred_metadata_date(meta) if settings.get("read_metadata", True) else None

            ctx = FileContext(
                path=path,
                relative_path=str(path.relative_to(root)),
                category=category,
                created_date=created,
                modified_date=modified,
                metadata_date=metadata_date,
                size=int(meta.get("size") or path.stat().st_size),
                file_hash=meta.get("sha256"),
            )

            dest_parts = choose_destination(settings, ctx, custom_target)
            if settings.get("organization_mode") == "type":
                if not settings.get("categories_enabled", {}).get(category, True):
                    dest_parts = ["Others"]

            dup_key = None
            if settings.get("duplicate_detection"):
                dup_key = tuple(
                    [
                        ctx.path.name.lower() if "name" in duplicate_criteria else None,
                        ctx.size if "size" in duplicate_criteria else None,
                        ctx.file_hash if "hash" in duplicate_criteria else None,
                    ]
                )
                if dup_key in seen_duplicates:
                    dest_parts = ["Duplicates"]
                    _copy_item(path, root, organized_dir, dest_parts, path.name, logs, duplicate=True)
                    continue
                seen_duplicates[dup_key] = path

            index_key = tuple(dest_parts)
            if settings.get("organization_mode") == "date":
                date_counters[index_key] += 1
                index = date_counters[index_key]
            else:
                category_counters[index_key] += 1
                index = category_counters[index_key]

            ext = path.suffix.lower()
            filename = path.name
            if settings.get("rename_enabled", True):
                filename = structured_name(
                    original_name=path.name,
                    category=category,
                    index=index,
                    ext=ext,
                    ctx_date=get_sort_date(ctx, str(settings.get("date_basis", "modified"))),
                    size=ctx.size,
                    file_hash=ctx.file_hash,
                    pattern=str(settings.get("rename_pattern") or "{category}_{index:03d}{ext}"),
                )
            _copy_item(path, root, organized_dir, dest_parts, filename, logs)
        except PermissionError as exc:
            logs.append(_log("permission_error", path, None, str(exc), error=True))
        except FileNotFoundError as exc:
            logs.append(_log("missing_file", path, None, str(exc), error=True))
        except OSError as exc:
            logs.append(_log("os_error", path, None, str(exc), error=True))
        except Exception as exc:  # noqa: BLE001
            logs.append(_log("unexpected_error", path, None, str(exc), error=True))

    _write_logs(job_dir, logs, session, settings)

    zip_path = job_dir / f"{session['folder_name']}_organized.zip"
    _zip_folder(organized_dir, zip_path)

    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "zip_path": str(zip_path),
        "organized_dir": str(organized_dir),
        "logs": logs,
        "summary": {
            "uploaded_folder": session["folder_name"],
            "uploaded_size": format_size(session["size_bytes"]),
            "files_processed": len(files),
            "zip_name": zip_path.name,
        },
    }


def _copy_item(src: Path, root: Path, organized_dir: Path, dest_parts: list[str], filename: str, logs: list[dict], duplicate: bool = False) -> None:
    dest_dir = organized_dir.joinpath(*dest_parts)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = ensure_unique_name(dest_dir / safe_filename(filename))
    shutil.copy2(src, dest)
    logs.append(
        _log(
            "duplicate" if duplicate else "copied",
            src,
            dest,
            "Duplicate detected and routed to Duplicates." if duplicate else "File organized successfully.",
        )
    )


def _log(action: str, old_path: Path | None, new_path: Path | None, message: str, error: bool = False) -> dict:
    return {
        "timestamp": now_iso(),
        "action": action,
        "old_path": str(old_path) if old_path else "",
        "new_path": str(new_path) if new_path else "",
        "message": message,
        "error": error,
    }


def _write_logs(job_dir: Path, logs: list[dict], session: dict, settings: dict) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "logs.json").write_text(json.dumps(logs, indent=2), encoding="utf-8")

    lines = [
        f"Folder: {session['folder_name']}",
        f"Size: {format_size(session['size_bytes'])}",
        f"Settings: {json.dumps(settings, indent=2)}",
        "",
    ]
    for entry in logs:
        lines.append(
            f"[{entry['timestamp']}] {entry['action']} | {entry['old_path']} -> {entry['new_path']} | {entry['message']}"
        )
    (job_dir / "logs.txt").write_text("\n".join(lines), encoding="utf-8")


def _zip_folder(folder: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in folder.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(folder).as_posix())
