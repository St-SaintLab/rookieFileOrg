from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from organizer.config import load_settings_from_file, merge_settings
from organizer.organizer import organize_upload_session, save_uploaded_folder
from organizer.utils import format_size

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(tempfile.gettempdir()) / "rookie_file_organizer"
UPLOAD_DIR = DATA_DIR / "uploads"
JOB_DIR = DATA_DIR / "jobs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
JOB_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")

_sessions: dict[str, dict] = {}
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/upload")
def api_upload():
    if "files[]" not in request.files:
        return jsonify({"ok": False, "error": "No folder files were uploaded."}), 400

    files = request.files.getlist("files[]")
    relative_paths = request.form.getlist("relative_paths[]")
    if not files:
        return jsonify({"ok": False, "error": "No files were found in the selected folder."}), 400
    if relative_paths and len(relative_paths) != len(files):
        return jsonify({"ok": False, "error": "Uploaded files and paths do not match."}), 400

    upload_id = uuid.uuid4().hex
    session_dir = UPLOAD_DIR / upload_id
    session_dir.mkdir(parents=True, exist_ok=True)

    try:
        info = save_uploaded_folder(
            upload_id=upload_id,
            session_dir=session_dir,
            files=files,
            relative_paths=relative_paths or None,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500

    with _lock:
        _sessions[upload_id] = info

    return jsonify(
        {
            "ok": True,
            "upload_id": upload_id,
            "folder_name": info["folder_name"],
            "size_bytes": info["size_bytes"],
            "size_label": format_size(info["size_bytes"]),
        }
    )


@app.post("/api/organize")
def api_organize():
    payload_raw = request.form.get("settings")
    upload_id = request.form.get("upload_id", "").strip()
    if not upload_id:
        return jsonify({"ok": False, "error": "Missing upload session."}), 400

    with _lock:
        session = _sessions.get(upload_id)
    if not session:
        return jsonify({"ok": False, "error": "Upload session expired or was not found."}), 404

    try:
        settings = json.loads(payload_raw or "{}")
    except json.JSONDecodeError:
        return jsonify({"ok": False, "error": "Settings JSON is invalid."}), 400

    config_file = request.files.get("config_file")
    if config_file and config_file.filename:
        try:
            file_settings = load_settings_from_file(config_file)
            settings = merge_settings(file_settings, settings)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": f"Config file error: {exc}"}), 400

    try:
        result = organize_upload_session(
            session=session,
            settings=settings,
            job_root=JOB_DIR,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500

    job_id = result["job_id"]
    with _lock:
        _jobs[job_id] = result

    return jsonify(
        {
            "ok": True,
            "job_id": job_id,
            "download_url": f"/api/download/{job_id}",
            "logs": result["logs"],
            "summary": result["summary"],
        }
    )


@app.get("/api/download/<job_id>")
def api_download(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Download not found."}), 404

    zip_path = Path(job["zip_path"])
    if not zip_path.exists():
        return jsonify({"ok": False, "error": "Zip file is missing."}), 404

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=zip_path.name,
        mimetype="application/zip",
    )


@app.get("/api/session/<upload_id>")
def api_session(upload_id: str):
    with _lock:
        session = _sessions.get(upload_id)
    if not session:
        return jsonify({"ok": False, "error": "Session not found."}), 404
    return jsonify({"ok": True, **session})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
