"""Chat frontend for the UDS advantage-question comments.

Run from the repo root:

    python3 app.py

Then open http://127.0.0.1:8787
"""

from __future__ import annotations

import csv
import io
import json
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from pipeline.chat import reply
from pipeline.corpus import QUESTION, load, load_reader
from pipeline.hard_filter import BUCKET_LABELS

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = ROOT / "data"
SETTINGS_PATH = DATA / "model.json"
HOST = "127.0.0.1"
PORT = 8787

DEFAULT_SETTINGS = {
    "api_key": "",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
}


LIBRARY_PATH = DATA / "library.csv"
LIBRARY_META = DATA / "library.json"


class Library:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        if LIBRARY_PATH.is_file() and LIBRARY_META.is_file():
            meta = json.loads(LIBRARY_META.read_text(encoding="utf-8"))
            self.name = meta.get("name") or "upload.csv"
            self.records = load(LIBRARY_PATH)
        else:
            self.name = "UDS_Cleaned.csv"
            self.records = load()

    def snapshot(self):
        with self._lock:
            return self.name, self.records

    def replace(self, name: str, text: str) -> dict:
        reader = csv.DictReader(io.StringIO(text))
        records = load_reader(reader)
        DATA.mkdir(exist_ok=True)
        LIBRARY_PATH.write_text(text, encoding="utf-8")
        LIBRARY_META.write_text(json.dumps({"name": name}), encoding="utf-8")
        with self._lock:
            self.name = name
            self.records = records
        return status(name, records)


LIBRARY = Library()


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.is_file():
        stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        settings.update({key: stored.get(key, settings[key]) for key in settings})
    return settings


def save_settings(incoming: dict) -> dict:
    current = load_settings()
    if incoming.get("clear_key"):
        current["api_key"] = ""
    elif str(incoming.get("api_key") or "").strip():
        current["api_key"] = str(incoming["api_key"]).strip()
    if incoming.get("base_url"):
        current["base_url"] = str(incoming["base_url"]).strip().rstrip("/")
    if incoming.get("model"):
        current["model"] = str(incoming["model"]).strip()
    DATA.mkdir(exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(current), encoding="utf-8")
    return public_settings(current)


def public_settings(settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    return {
        "has_key": bool(settings.get("api_key")),
        "base_url": settings.get("base_url") or DEFAULT_SETTINGS["base_url"],
        "model": settings.get("model") or DEFAULT_SETTINGS["model"],
    }


def status(name: str, records) -> dict:
    counts = Counter(record.bucket for record in records)
    preview = []
    for record in records[:12]:
        if record.bucket == "exclude":
            continue
        preview.append(record.public())
        if len(preview) == 8:
            break
    return {
        "name": name,
        "question": QUESTION,
        "n": len(records),
        "buckets": {bucket: counts[bucket] for bucket in BUCKET_LABELS},
        "bucket_labels": BUCKET_LABELS,
        "preview": preview,
        "model": public_settings(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "UDSChat/0.2"

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/library":
            name, records = LIBRARY.snapshot()
            self._json(status(name, records))
            return
        if path == "/api/settings":
            self._json(public_settings())
            return
        self._file(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 20_000_000:
            self._json({"error": "That file is too large."}, 400)
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "Send JSON."}, 400)
            return
        if path == "/api/chat":
            message = str(body.get("message") or "").strip()
            if not message:
                self._json({"error": "Type a question first."}, 400)
                return
            _, records = LIBRARY.snapshot()
            self._json(reply(records, message, load_settings()))
            return
        if path == "/api/library":
            csv_text = str(body.get("csv") or "")
            name = Path(str(body.get("name") or "upload.csv")).name
            if not csv_text.strip():
                self._json({"error": "Choose a CSV file."}, 400)
                return
            try:
                self._json(LIBRARY.replace(name, csv_text))
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
            return
        if path == "/api/settings":
            self._json(save_settings(body))
            return
        self._json({"error": "Not found"}, 404)

    def _file(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.split("?", 1)[0].lstrip("/")
        target = (WEB / relative).resolve()
        if WEB not in target.parents and target != WEB:
            self._json({"error": "Not found"}, 404)
            return
        if not target.is_file():
            self._json({"error": "Not found"}, 404)
            return
        kind = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(target.suffix, "application/octet-stream")
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    name, records = LIBRARY.snapshot()
    print(f"Library: {name} ({len(records):,} comments)")
    print(f"Open http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
