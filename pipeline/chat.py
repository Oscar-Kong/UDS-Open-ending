"""Turn a grounded packet into a short chat reply.

With no model key, the reply is written from the hard-filter counts and
quotations. With a key, those same facts are handed to an OpenAI-compatible
chat endpoint and the model writes the short summary.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from pipeline.answer import answer
from pipeline.corpus import QUESTION, Record

SYSTEM = (
    "You answer questions about one Northeastern survey item for a university reader. "
    "Use only the numbers and quotations in the packet. Write 3 to 5 sentences. "
    "If support is insufficient, say the comments do not answer the question. "
    "Do not invent figures, themes, or quotations."
)


def reply(records: list[Record], message: str, settings: dict) -> dict:
    result = answer(records, message)
    if result.get("error"):
        return {"text": result["error"], "quotes": [], "source": "filter"}
    packet = _packet(result)
    key = (settings.get("api_key") or "").strip()
    if not key:
        return {**_template(result), "source": "filter"}
    try:
        text = _complete(message, packet, settings)
    except Exception as exc:  # noqa: BLE001 — surface a short failure, keep the grounded text
        grounded = _template(result)
        grounded["text"] += f"\n\nThe model call failed ({exc}). The summary above is from the filtered counts."
        grounded["source"] = "filter"
        return grounded
    return {"text": text, "quotes": packet["quotes"], "source": "model", "support": result.get("support")}


def _template(result: dict) -> dict:
    lines = [result.get("headline") or ""]
    paragraphs = result.get("paragraphs") or []
    if paragraphs:
        lines.append(paragraphs[0])
    if len(paragraphs) > 1 and result.get("mode") != "unsupported":
        lines.append(paragraphs[1])
    return {
        "text": "\n\n".join(line for line in lines if line),
        "quotes": _quotes(result),
        "support": result.get("support"),
    }


def _packet(result: dict) -> dict:
    slices = []
    for piece in result.get("slices") or []:
        slices.append(
            {
                "label": piece.get("label"),
                "n": piece.get("n"),
                "buckets": piece.get("buckets"),
                "stance": piece.get("stance"),
                "themes": piece.get("themes"),
            }
        )
    return {
        "survey_question": QUESTION,
        "support": result.get("support"),
        "scope": result.get("scope"),
        "headline": result.get("headline"),
        "paragraphs": result.get("paragraphs"),
        "slices": slices,
        "quotes": _quotes(result),
    }


def _quotes(result: dict) -> list[dict]:
    chosen = []
    for piece in result.get("slices") or []:
        for quote in piece.get("quotes") or []:
            chosen.append(
                {
                    "id": quote["id"],
                    "text": quote["text"],
                    "year": quote["year"],
                    "college": quote["college"],
                    "words": quote["words"],
                }
            )
            if len(chosen) == 3:
                return chosen
    return chosen


def _complete(message: str, packet: dict, settings: dict) -> str:
    base = (settings.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = settings.get("model") or "gpt-4o-mini"
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": "Question:\n" + message + "\n\nPacket:\n" + json.dumps(packet, ensure_ascii=False),
            },
        ],
    }
    request = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    return body["choices"][0]["message"]["content"].strip()
