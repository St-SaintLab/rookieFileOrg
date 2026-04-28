from __future__ import annotations

import configparser
import io
import json
from pathlib import Path

try:
    import yaml
except Exception:  # noqa: BLE001
    yaml = None


DEFAULT_SETTINGS = {
    "organization_mode": "type",
    "rename_enabled": True,
    "rename_pattern": "{category}_{index:03d}{ext}",
    "duplicate_detection": True,
    "duplicate_criteria": ["name", "size", "hash"],
    "date_basis": "modified",
    "recursive_scan": True,
    "read_metadata": True,
    "custom_rules_text": "",
    "categories_enabled": {
        "Images": True,
        "Videos": True,
        "Audio": True,
        "Documents": True,
        "Archives": True,
        "Code": True,
        "Spreadsheets": True,
        "PDFs": True,
        "Others": True,
    },
}


def merge_settings(base: dict, override: dict) -> dict:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def load_settings_from_file(file_storage) -> dict:
    name = (file_storage.filename or "").lower()
    raw = file_storage.read()
    if not raw:
        raise ValueError("Config file is empty.")

    if name.endswith(".json"):
        return json.loads(raw.decode("utf-8"))

    if name.endswith((".yml", ".yaml")):
        if not yaml:
            raise ValueError("PyYAML is not installed.")
        return yaml.safe_load(raw.decode("utf-8")) or {}

    if name.endswith(".ini"):
        parser = configparser.ConfigParser()
        parser.read_file(io.StringIO(raw.decode("utf-8")))
        result: dict = {}
        for section in parser.sections():
            result[section] = dict(parser[section])
        result.update(dict(parser["DEFAULT"]))
        return result

    raise ValueError("Supported config formats are .json, .yaml, .yml, and .ini.")
