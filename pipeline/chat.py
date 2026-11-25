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
from pipeline.check_accuracy import score_output
from pipeline.corpus import QUESTION, Record

SYSTEM = (
    "You explain statistical findings from one Northeastern survey item. "
    "Separate passes already counted scope, stance, and reasons. "
    "Write one paragraph of 3 to 5 sentences that explains those findings for a university reader. "
    "Use only numbers that appear in the findings. "
    "If support is insufficient, write one sentence that the comments do not answer the question, and do not rank reasons. "
    "Do not add themes, percentages, or quotations. Quotations are shown separately. "
    "Do not use bullet points."
)

TITLE = (
    "Name one saved chat about a Northeastern survey. "
    "Use 4 to 7 words. Do not use quotation marks. Do not end with a period."
)


def reply(records: list[Record], message: str, settings: dict) -> dict:
    result = answer(records, message)
    if result.get("error"):
        return {"text": result["error"], "quotes": [], "source": "filter", "accuracy": None}
    findings = _findings(result)
    dashboard = _dashboard(result)
    result = {**result, "findings": findings, "dashboard": dashboard}
    packet = _packet(result)
    key = (settings.get("api_key") or "").strip()
    if not key:
        return _with_accuracy(_template(result), result, records, "Filtered counts")
    try:
        text = _complete(message, packet, settings)
    except Exception as exc:  # noqa: BLE001 — one retry already ran inside _complete
        grounded = _template(result)
        reason = _short_error(exc)
        note = f"The LLM did not respond ({reason}). This score is for the filtered summary."
        grounded["text"] += f"\n\nThe model call failed ({reason}). The summary above is from the filtered counts."
        return _with_accuracy(grounded, result, records, "Filtered counts", note)
    payload = {
        "text": text,
        "quotes": packet["quotes"],
        "source": "model",
        "support": result.get("support"),
        "findings": findings,
        "dashboard": result.get("dashboard"),
    }
    return _with_accuracy(payload, result, records, "LLM")


def _short_error(exc: Exception) -> str:
    text = str(exc)
    start = text.find("{")
    if start != -1:
        try:
            body = json.loads(text[start:])
        except json.JSONDecodeError:
            body = None
        if isinstance(body, dict):
            message = body.get("message") or body.get("error")
            if message:
                return str(message)
    return text


def _with_accuracy(payload: dict, result: dict, records: list[Record], source_label: str, note: str = "") -> dict:
    scored_text = payload["text"].split("\n\nThe model call failed", 1)[0]
    accuracy = score_output(result, scored_text, records)
    accuracy["source"] = source_label
    if note:
        accuracy["note"] = note
    payload["accuracy"] = accuracy
    return payload


def _template(result: dict) -> dict:
    return {
        "text": result.get("headline") or "",
        "quotes": _quotes(result),
        "source": "filter",
        "support": result.get("support"),
        "findings": result.get("findings") or [],
        "dashboard": result.get("dashboard"),
    }


def _packet(result: dict) -> dict:
    return {
        "survey_question": QUESTION,
        "support": result.get("support"),
        "scope": result.get("scope"),
        "findings": result.get("findings") or [],
        "quotes": _quotes(result),
    }


def _findings(result: dict) -> list[dict]:
    """Stat passes. The writer may use these figures and no others."""
    blocks = []
    show_reasons = result.get("support") != "insufficient"
    for piece in result.get("slices") or []:
        label = piece.get("label") or "All respondents"
        buckets = piece.get("buckets") or {}
        stance = piece.get("stance") or {}
        labeled = sum(stance.get(name, 0) for name in ("yes", "no", "mixed", "unsure"))
        yes_share = round(100 * stance.get("yes", 0) / labeled) if labeled else 0
        blocks.append(
            {
                "agent": "Scope",
                "label": label,
                "lines": [
                    f"{piece.get('n', 0):,} comments in this slice.",
                    (
                        f"{buckets.get('pass', 0):,} explanations, "
                        f"{buckets.get('label_only', 0):,} short reasons, "
                        f"{buckets.get('stance_only', 0):,} position-only."
                    ),
                ],
            }
        )
        blocks.append(
            {
                "agent": "Stance",
                "label": label,
                "lines": [
                    (
                        f"Where the opening position is clear ({labeled:,} comments), "
                        f"{yes_share}% say yes ({stance.get('yes', 0):,}), "
                        f"{stance.get('no', 0):,} say no, "
                        f"{stance.get('mixed', 0):,} are mixed, and "
                        f"{stance.get('unsure', 0):,} are unsure."
                    )
                ],
            }
        )
        if not show_reasons:
            continue
        lines = []
        for theme in (piece.get("themes") or [])[:4]:
            if not theme.get("explanations"):
                continue
            lines.append(
                f"{theme['label']}: {theme['explanations']:,} explanations "
                f"({theme.get('share', 0)}% of explanations), "
                f"plus {theme.get('short_labels', 0):,} short labels."
            )
        if lines:
            blocks.append({"agent": "Reasons", "label": label, "lines": lines})
    support = result.get("support") or "unknown"
    if support == "insufficient":
        evidence = "Support is insufficient. These comments do not answer the question."
    elif support == "thin":
        evidence = "Support is thin. Treat the reasons as illustrations, not a stable ranking."
    else:
        evidence = "Support is enough to summarize the leading reasons."
    blocks.append({"agent": "Evidence", "label": "All slices", "lines": [evidence]})
    return blocks


def _dashboard(result: dict) -> dict | None:
    """A chart or table for count, comparison, and reason questions. Refusals stay text."""
    mode = result.get("mode")
    support = result.get("support")
    if support == "insufficient" or mode not in {"stance", "compare", "themes"}:
        return None
    slices = result.get("slices") or []
    if mode == "compare" and len(slices) >= 2:
        return _compare_table(slices[:2], support)
    if mode == "stance" and slices:
        return _stance_bars(slices[0], support)
    if mode == "themes" and slices:
        return _reason_bars(slices[0], support)
    return None


def _stance_bars(piece: dict, support: str) -> dict | None:
    stance = piece.get("stance") or {}
    order = (("Yes", "yes"), ("No", "no"), ("Mixed", "mixed"), ("Unsure", "unsure"))
    labeled = sum(stance.get(key, 0) for _, key in order)
    if not labeled:
        return None
    rows = []
    for label, key in order:
        value = int(stance.get(key, 0))
        rows.append({"label": label, "value": value, "text": f"{value:,} · {_share(value, labeled)}%"})
    rows[max(range(len(rows)), key=lambda index: rows[index]["value"])]["lead"] = True
    note = f"Share of {labeled:,} comments with a clear opening position."
    if support == "thin":
        note += " This slice is thin."
    return {"kind": "bars", "title": "Opening position", "note": note, "rows": rows}


def _reason_bars(piece: dict, support: str) -> dict | None:
    themes = [theme for theme in (piece.get("themes") or []) if theme.get("explanations")][:4]
    if not themes:
        return None
    rows = [
        {
            "label": theme["label"],
            "value": int(theme["explanations"]),
            "text": f"{theme['explanations']:,} · {theme.get('share', 0)}%",
            "lead": index == 0,
        }
        for index, theme in enumerate(themes)
    ]
    label = piece.get("label") or "All respondents"
    title = "Reasons in the explanations" if label == "All respondents" else f"Reasons · {label}"
    note = "Share of explanations. A comment can name more than one reason."
    if support == "thin":
        note += " This slice is thin."
    return {"kind": "bars", "title": title, "note": note, "rows": rows}


def _compare_table(slices: list[dict], support: str) -> dict:
    columns = [piece.get("label") or "Group" for piece in slices]
    rows = [
        {"label": "Comments", "values": [f"{piece.get('n', 0):,}" for piece in slices]},
        {"label": "Explanations", "values": [f"{(piece.get('buckets') or {}).get('pass', 0):,}" for piece in slices]},
        {"label": "Yes", "values": [_yes_cell(piece) for piece in slices]},
        {"label": "No", "values": [f"{(piece.get('stance') or {}).get('no', 0):,}" for piece in slices]},
        {"label": "Leading reason", "values": [_lead_cell(piece) for piece in slices]},
    ]
    note = "One side is thin, so the gap may be the sample size." if support == "thin" else "Same survey item and the same hard filter on each group."
    return {"kind": "table", "title": f"{columns[0]} and {columns[1]}", "note": note, "columns": columns, "rows": rows}


def _yes_cell(piece: dict) -> str:
    stance = piece.get("stance") or {}
    labeled = sum(stance.get(name, 0) for name in ("yes", "no", "mixed", "unsure"))
    yes = int(stance.get("yes", 0))
    if not labeled:
        return f"{yes:,}"
    return f"{yes:,} · {_share(yes, labeled)}%"


def _lead_cell(piece: dict) -> str:
    for theme in piece.get("themes") or []:
        if theme.get("explanations"):
            return f"{theme['label']} · {theme['explanations']:,}"
    return "—"


def _share(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


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


def chat_title(question: str, answer: str, settings: dict) -> str | None:
    """A short sidebar name, written once the chat has been saved. One retry."""
    if not (settings.get("api_key") or "").strip():
        return None
    user = "Question:\n" + question.strip() + "\n\nAnswer:\n" + (answer or "").strip()[:600]
    try:
        text = _ask(TITLE, user, settings, max_tokens=32, timeout=45)
    except Exception:  # noqa: BLE001 — keep the question text when both tries fail
        return None
    return _tidy_title(text)


def _complete(message: str, packet: dict, settings: dict) -> str:
    user = "Question:\n" + message + "\n\nPacket:\n" + json.dumps(packet, ensure_ascii=False)
    return _ask(SYSTEM, user, settings, max_tokens=500, timeout=180)


def _ask(system: str, user: str, settings: dict, *, max_tokens: int, timeout: int) -> str:
    last: Exception | None = None
    for _attempt in range(2):
        try:
            return _post(system, user, settings, max_tokens=max_tokens, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 — the second try is the retry
            last = exc
    raise last if last else RuntimeError("The LLM did not respond.")


def _post(system: str, user: str, settings: dict, *, max_tokens: int, timeout: int) -> str:
    base = (settings.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = settings.get("model") or "gpt-4o-mini"
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if "dashlab" in base:
        payload["think"] = False
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    return _message_text(body)


def _tidy_title(text: str) -> str | None:
    line = text.strip().splitlines()[0] if text.strip() else ""
    line = " ".join(line.split()).strip(" \"'`“”")
    if line.endswith("."):
        line = line[:-1].rstrip()
    if len(line) < 3:
        return None
    if len(line) > 60:
        line = line[:57].rstrip() + "…"
    return line


def _message_text(body: dict) -> str:
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:240])
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if content:
            return str(content).strip()
    message = body.get("message")
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"]).strip()
    if isinstance(message, str) and message.strip():
        return message.strip()
    raise RuntimeError("The LLM response did not include a summary.")
