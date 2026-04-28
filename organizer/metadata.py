from __future__ import annotations

from datetime import datetime
from pathlib import Path

from organizer.utils import sha256_file

try:
    from PIL import Image
except Exception:  # noqa: BLE001
    Image = None

try:
    from PyPDF2 import PdfReader
except Exception:  # noqa: BLE001
    PdfReader = None

try:
    from mutagen import File as MutagenFile
except Exception:  # noqa: BLE001
    MutagenFile = None


def _safe_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return None


def file_metadata(path: Path) -> dict:
    meta: dict = {"kind": "generic"}

    try:
        stat = path.stat()
        created = datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_ctime))
        modified = datetime.fromtimestamp(stat.st_mtime)
        meta.update({"created": created, "modified": modified, "size": stat.st_size})
    except Exception:  # noqa: BLE001
        pass

    suffix = path.suffix.lower()

    if Image and suffix in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}:
        try:
            with Image.open(path) as img:
                meta.update({"kind": "image", "width": img.width, "height": img.height, "format": img.format})
        except Exception:  # noqa: BLE001
            pass

    elif PdfReader and suffix == ".pdf":
        try:
            reader = PdfReader(str(path))
            docinfo = reader.metadata
            title = None
            try:
                title = getattr(docinfo, "title", None) or docinfo.get("/Title")
            except Exception:
                title = None
            meta.update({
                "kind": "pdf",
                "pages": len(reader.pages),
                "title": title,
            })
        except Exception:  # noqa: BLE001
            pass

    elif MutagenFile and suffix in {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv"}:
        try:
            audio = MutagenFile(str(path))
            info = getattr(audio, "info", None)
            if info and getattr(info, "length", None):
                meta.update({"kind": "media", "duration_seconds": round(float(info.length), 2)})
        except Exception:  # noqa: BLE001
            pass

    try:
        meta["sha256"] = sha256_file(path)
    except Exception:  # noqa: BLE001
        pass

    return meta


def preferred_metadata_date(meta: dict) -> datetime | None:
    for key in ("created", "modified"):
        value = meta.get(key)
        if isinstance(value, datetime):
            return value
    return None
