"""Saved chat threads.

One JSON file on this machine. The chat view reads it back after a restart.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class ChatLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def list_public(self) -> list[dict]:
        with self._lock:
            chats = self._read()
        chats.sort(key=lambda item: item.get("updated") or "", reverse=True)
        return [
            {
                "id": chat.get("id"),
                "title": chat.get("title") or "New chat",
                "model": chat.get("model") or "",
                "updated": chat.get("updated") or "",
                "n": len(chat.get("messages") or []),
            }
            for chat in chats
        ]

    def get(self, chat_id: str) -> dict | None:
        with self._lock:
            for chat in self._read():
                if chat.get("id") == chat_id:
                    return chat
        return None

    def append_turn(self, chat_id: str | None, user_text: str, assistant: dict, model: str) -> dict:
        with self._lock:
            chats = self._read()
            chat = None
            if chat_id:
                for item in chats:
                    if item.get("id") == chat_id:
                        chat = item
                        break
            now = _now()
            if chat is None:
                chat = {
                    "id": uuid.uuid4().hex[:12],
                    "title": _title(user_text),
                    "model": model,
                    "created": now,
                    "updated": now,
                    "messages": [],
                }
                chats.append(chat)
            if not chat.get("title") or chat.get("title") == "New chat":
                chat["title"] = _title(user_text)
            chat["model"] = model or chat.get("model") or ""
            chat["updated"] = now
            chat.setdefault("messages", []).append({"role": "user", "content": user_text, "at": now})
            chat["messages"].append(
                {
                    "role": "assistant",
                    "content": assistant.get("text") or "",
                    "quotes": assistant.get("quotes") or [],
                    "accuracy": assistant.get("accuracy"),
                    "findings": assistant.get("findings") or [],
                    "dashboard": assistant.get("dashboard"),
                    "source": assistant.get("source") or "",
                    "model": model,
                    "at": now,
                }
            )
            self._write(_trim(chats))
            return chat

    def set_title(self, chat_id: str, title: str) -> dict | None:
        clean = " ".join(title.split()).strip()
        if not clean:
            return None
        with self._lock:
            chats = self._read()
            for chat in chats:
                if chat.get("id") == chat_id:
                    chat["title"] = clean
                    chat["title_source"] = "model"
                    self._write(chats)
                    return chat
        return None

    def delete(self, chat_id: str) -> bool:
        with self._lock:
            chats = self._read()
            kept = [chat for chat in chats if chat.get("id") != chat_id]
            if len(kept) == len(chats):
                return False
            self._write(kept)
            return True

    def _read(self) -> list:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        chats = payload.get("chats") if isinstance(payload, dict) else None
        return list(chats) if isinstance(chats, list) else []

    def _write(self, chats: list) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps({"chats": chats}, ensure_ascii=False, indent=2), encoding="utf-8")


def _trim(chats: list) -> list:
    chats.sort(key=lambda item: item.get("updated") or "", reverse=True)
    return chats[:50]


def _title(text: str) -> str:
    clean = " ".join(text.split())
    if len(clean) <= 72:
        return clean or "New chat"
    return clean[:69].rstrip() + "…"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
