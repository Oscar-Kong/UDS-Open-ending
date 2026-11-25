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
import urllib.error
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pipeline.chat import chat_title, reply
from pipeline.corpus import QUESTION, load, load_reader
from pipeline.evaluate import FILTERED, REFERENCE, EvalStore, run_sample, scenario_by_id, scenarios
from pipeline.hard_filter import BUCKET_LABELS
from pipeline.history import ChatLog

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
MODEL_CACHE = DATA / "models.json"
DASH_MODELS = ("gemma4:31b", "nemotron3:33b", "qwen3.8:27b")


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
CHATS = ChatLog(DATA / "chats.json")
EVALS = EvalStore(DATA / "evals.json")


def load_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    env = load_env(ROOT / ".env")
    key = (
        env.get("LLM_API_KEY")
        or env.get("DASH_API_KEY")
        or env.get("ANTHROPIC_API_KEY")
        or env.get("CLAUDE_API_KEY")
        or ""
    )
    if key:
        settings["api_key"] = key
        settings["base_url"] = (
            env.get("LLM_BASE_URL")
            or env.get("ANTHROPIC_BASE_URL")
            or "https://api-llm.dashlab.studio/v1"
        ).rstrip("/")
        settings["model"] = env.get("LLM_MODEL") or env.get("ANTHROPIC_MODEL") or "gemma4:31b"
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


def list_models(settings: dict) -> dict:
    current = settings.get("model") or DEFAULT_SETTINGS["model"]
    names: list[str] = []
    error = ""
    key = (settings.get("api_key") or "").strip()
    base = (settings.get("base_url") or "").rstrip("/")
    if key and base:
        request = urllib.request.Request(
            base + "/models",
            headers={"Authorization": f"Bearer {key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = json.loads(response.read().decode("utf-8"))
            names = _model_names(body)
        except urllib.error.HTTPError as exc:
            error = f"The model list did not load (HTTP {exc.code})."
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            error = "The model list did not load. Check the endpoint in Library."
    elif not key:
        error = "Save an LLM key in Library to load the model list."
    if names and not error:
        _save_model_cache(base, names)
    elif error and key:
        cached = _load_model_cache(base)
        if cached:
            names = cached
            error += " Showing the last list saved on this machine."
        elif "dashlab" in base:
            names = list(DASH_MODELS)
            error += " Showing the names recorded for this endpoint."
    if current and current not in names:
        names.insert(0, current)
    names = _unique(names)
    return {"models": names, "model": current, "error": error}


def _model_names(body: dict | list) -> list[str]:
    if isinstance(body, list):
        rows = body
    elif isinstance(body, dict):
        rows = body.get("data") or body.get("models") or []
    else:
        rows = []
    names = []
    for item in rows:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("id") or item.get("name")
            if name:
                names.append(str(name).strip())
    return names


def _save_model_cache(base: str, names: list[str]) -> None:
    if not base or not names:
        return
    DATA.mkdir(exist_ok=True)
    MODEL_CACHE.write_text(json.dumps({"base_url": base, "models": names}), encoding="utf-8")


def _load_model_cache(base: str) -> list[str]:
    if not MODEL_CACHE.is_file():
        return []
    try:
        payload = json.loads(MODEL_CACHE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict) or payload.get("base_url") != base:
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    return [str(name) for name in models if str(name).strip()]


def _unique(names: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _clean_models(incoming) -> list[dict] | str:
    if not isinstance(incoming, list) or not incoming:
        return "Choose at least one model."
    if len(incoming) > 4:
        return "Choose up to four models."
    chosen = []
    for item in incoming:
        if isinstance(item, str):
            name = item.strip()
            use_model = name != FILTERED
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            use_model = bool(item.get("use_model")) and name != FILTERED
        else:
            continue
        if not name:
            continue
        if not use_model:
            name = FILTERED
        chosen.append({"name": name, "use_model": use_model})
    if not chosen:
        return "Choose at least one model."
    deduped = []
    seen = set()
    for item in chosen:
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        deduped.append(item)
    return deduped


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
    server_version = "UDSChat/0.3"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/api/library":
            name, records = LIBRARY.snapshot()
            self._json(status(name, records))
            return
        if path == "/api/settings":
            self._json(public_settings())
            return
        if path == "/api/models":
            self._json(list_models(load_settings()))
            return
        if path == "/api/chats":
            chat_id = (query.get("id") or [""])[0]
            if chat_id:
                chat = CHATS.get(chat_id)
                if chat is None:
                    self._json({"error": "That chat is not saved."}, 404)
                    return
                self._json(chat)
                return
            self._json({"chats": CHATS.list_public()})
            return
        if path == "/api/evals":
            run_id = (query.get("id") or [""])[0]
            if run_id:
                run = EVALS.get(run_id)
                if run is None:
                    self._json({"error": "That evaluation is not saved."}, 404)
                    return
                self._json(run)
                return
            self._json(
                {
                    "reference": REFERENCE,
                    "task": "uds-advantage",
                    "solver": "pipeline.chat.reply",
                    "scorers": [
                        {"name": "numbers", "label": "Numbers", "detail": "Every number in the summary is in the filtered counts."},
                        {"name": "quotations", "label": "Quotations", "detail": "Each quotation matches an explanation in the file."},
                        {"name": "slice", "label": "Slice", "detail": "An insufficient slice is refused, and a supported slice is not."},
                    ],
                    "scenarios": scenarios(),
                    "runs": EVALS.list_public(),
                }
            )
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
            settings = load_settings()
            model = str(body.get("model") or "").strip() or settings.get("model") or ""
            if model and model != settings.get("model"):
                settings = save_settings({"model": model})
                settings = load_settings()
            elif model:
                settings = {**settings, "model": model}
            _, records = LIBRARY.snapshot()
            outcome = reply(records, message, settings)
            chat_id = str(body.get("chat_id") or "").strip() or None
            saved = CHATS.append_turn(chat_id, message, outcome, settings.get("model") or model)
            if len(saved.get("messages") or []) == 2:
                title = chat_title(message, outcome.get("text") or "", settings)
                if title:
                    renamed = CHATS.set_title(saved["id"], title)
                    if renamed:
                        saved = renamed
            self._json({
                **outcome,
                "chat_id": saved["id"],
                "model": settings.get("model") or model,
                "title": saved.get("title") or "",
            })
            return
        if path == "/api/chats":
            if str(body.get("action") or "") != "delete":
                self._json({"error": "Not found"}, 404)
                return
            chat_id = str(body.get("id") or "").strip()
            if not CHATS.delete(chat_id):
                self._json({"error": "That chat is not saved."}, 404)
                return
            self._json({"chats": CHATS.list_public()})
            return
        if path == "/api/evals":
            action = str(body.get("action") or "")
            if action == "start":
                chosen = _clean_models(body.get("models"))
                if isinstance(chosen, str):
                    self._json({"error": chosen}, 400)
                    return
                self._json(EVALS.start(chosen))
                return
            if action == "sample":
                run_id = str(body.get("id") or "").strip()
                scenario_id = str(body.get("scenario") or "").strip()
                if scenario_by_id(scenario_id) is None:
                    self._json({"error": "That question is not in the evaluation set."}, 400)
                    return
                model = str(body.get("model") or "").strip()
                use_model = bool(body.get("use_model")) and model != FILTERED
                if use_model and not model:
                    self._json({"error": "Choose a model."}, 400)
                    return
                settings = load_settings()
                if use_model and not settings.get("api_key"):
                    self._json({"error": "Save an LLM key in Library before scoring a model."}, 400)
                    return
                _, records = LIBRARY.snapshot()
                try:
                    sample = run_sample(
                        records,
                        scenario_id,
                        settings,
                        model=model or FILTERED,
                        use_model=use_model,
                    )
                except KeyError:
                    self._json({"error": "That question is not in the evaluation set."}, 400)
                    return
                run = EVALS.add_sample(run_id, sample)
                if run is None:
                    self._json({"error": "That evaluation is not saved."}, 404)
                    return
                self._json({"sample": sample, "run": EVALS.summary(run)})
                return
            self._json({"error": "Not found"}, 404)
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
