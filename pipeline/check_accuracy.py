"""Check that an answer stays inside the filtered comments.

The grounded packet is the source of truth. This script checks that packet
on a few questions, and can also check a written summary against it.

    python3 pipeline/check_accuracy.py
    python3 pipeline/check_accuracy.py --llm
    python3 pipeline/check_accuracy.py --question "What is the main reason students feel they have an advantage?" --text "Students name co-op in 8,909 explanations."
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.answer import answer
from pipeline.corpus import load

CASES = [
    {
        "question": "What is the main reason students feel they have an advantage?",
        "support": "enough",
        "lead": "coop",
        "quotes": True,
    },
    {
        "question": "How many say yes, and how many say no?",
        "support": "enough",
        "mode": "stance",
        "quotes": True,
    },
    {
        "question": "How do undergraduate and graduate students differ?",
        "support": "enough",
        "slices": 2,
        "quotes": True,
    },
    {
        "question": "Where do students say there is no real advantage?",
        "support": "enough",
        "lead": "parity",
        "quotes": True,
    },
    {
        "question": "What is the average starting salary?",
        "support": "insufficient",
        "quotes": False,
    },
    {
        "question": "What do law students in 2016 say about their advantage?",
        "support": "insufficient",
        "quotes": False,
    },
]

REFUSAL = (
    "don't answer",
    "do not answer",
    "does not answer",
    "not enough",
    "aren't enough",
    "insufficient",
    "cannot say",
    "can't say",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check answer accuracy against the filtered comments.")
    parser.add_argument("--llm", action="store_true", help="Also score a live LLM summary for each question.")
    parser.add_argument("--question", help="Score one question instead of the built-in list.")
    parser.add_argument("--text", help="Score this summary against the question's packet.")
    args = parser.parse_args()

    records = load()
    by_id = {record.id: record for record in records}
    cases = CASES
    if args.question:
        cases = [{"question": args.question, "quotes": None}]

    failures = 0
    for case in cases:
        result = answer(records, case["question"])
        problems = check_packet(result, by_id, case)
        text = args.text
        source = "pasted"
        if args.llm and not text:
            text, source = live_summary(records, case["question"])
            if source == "error":
                problems.append("LLM was not scored: " + _first_line(text))
                text = None
        if text:
            problems.extend(check_summary(text, result))
        status = "pass" if not problems else "fail"
        if problems:
            failures += 1
        label = "llm" if source == "model" else ("summary" if args.text else "packet")
        print(f"{status:4}  {label:7}  {case['question']}")
        for problem in problems:
            print(f"        {problem}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


def check_packet(result: dict, by_id: dict, case: dict) -> list[str]:
    problems = []
    expected = case.get("support")
    if expected and result.get("support") != expected:
        problems.append(f"support is {result.get('support')}, expected {expected}")
    if case.get("mode") and result.get("mode") != case["mode"]:
        problems.append(f"mode is {result.get('mode')}, expected {case['mode']}")
    slices = result.get("slices") or []
    if case.get("slices") and len(slices) != case["slices"]:
        problems.append(f"{len(slices)} slices, expected {case['slices']}")
    if case.get("lead"):
        themes = (slices[0].get("themes") if slices else None) or []
        lead = themes[0]["id"] if themes else None
        if lead != case["lead"]:
            problems.append(f"leading theme is {lead}, expected {case['lead']}")
    quotes = [quote for piece in slices for quote in piece.get("quotes") or []]
    if case.get("quotes") is True and not quotes:
        problems.append("expected quotations, found none")
    if case.get("quotes") is False and quotes:
        problems.append("expected no quotations")
    for quote in quotes:
        record = by_id.get(quote.get("id"))
        if record is None:
            problems.append(f"quote id {quote.get('id')} is not in the file")
            continue
        if record.bucket != "pass":
            problems.append(f"quote id {quote.get('id')} is {record.bucket}, not an explanation")
        shown = str(quote.get("text") or "").rstrip("…").strip()
        if shown and not record.text.startswith(shown[:80]):
            problems.append(f"quote id {quote.get('id')} does not match the comment text")
    return problems


def score_output(result: dict, text: str, records) -> dict:
    """Checks for the chat panel. Numbers, quotations, and the refusal line."""
    by_id = {record.id: record for record in records}
    quotes = [quote for piece in result.get("slices") or [] for quote in piece.get("quotes") or []]
    quote_problems = check_packet(result, by_id, {"quotes": None})
    quote_problems = [item for item in quote_problems if item.startswith("quote")]
    if quotes and not quote_problems:
        quotations = {"ok": True, "label": "Quotations", "detail": "Each quotation matches an explanation in the file."}
    elif quote_problems:
        quotations = {"ok": False, "label": "Quotations", "detail": quote_problems[0][:1].upper() + quote_problems[0][1:] + "."}
    else:
        quotations = {"ok": True, "label": "Quotations", "detail": "No quotation is shown for this answer."}

    number_problems = [
        item for item in check_summary(text, result) if item.startswith("number")
    ]
    if number_problems:
        numbers = {"ok": False, "label": "Numbers", "detail": number_problems[0][:1].upper() + number_problems[0][1:] + "."}
    else:
        numbers = {"ok": True, "label": "Numbers", "detail": "Every number in the summary is in the filtered counts."}

    slice_problems = [
        item for item in check_summary(text, result) if not item.startswith("number") and "quotation" not in item
    ]
    if slice_problems:
        fit = {"ok": False, "label": "Slice", "detail": slice_problems[0][:1].upper() + slice_problems[0][1:] + "."}
    elif result.get("support") == "insufficient":
        fit = {"ok": True, "label": "Slice", "detail": "The summary says these comments do not answer."}
    else:
        fit = {"ok": True, "label": "Slice", "detail": "The summary does not refuse a slice that has enough comments."}

    checks = [numbers, quotations, fit]
    return {"ok": all(item["ok"] for item in checks), "checks": checks}


def check_summary(text: str, result: dict) -> list[str]:
    problems = []
    lowered = text.lower()
    refused = any(phrase in lowered for phrase in REFUSAL)
    support = result.get("support")
    if support == "insufficient" and not refused:
        problems.append("the slice is insufficient, but the summary does not say so")
    if support == "enough" and any(phrase in lowered for phrase in ("don't answer", "do not answer", "does not answer")):
        problems.append("the slice has enough comments, but the summary refuses the question")

    allowed = _numbers(result)
    for blob in [result.get("headline"), *(result.get("paragraphs") or [])]:
        allowed.update(_numbers_in_text(blob or ""))
    for block in result.get("findings") or []:
        for line in block.get("lines") or []:
            allowed.update(_numbers_in_text(line))
    for number in _numbers_in_text(text):
        if number not in allowed:
            problems.append(f"number {number:,} is not in the packet")

    quotes = [quote.get("text") or "" for piece in result.get("slices") or [] for quote in piece.get("quotes") or []]
    for span in re.findall(r"[\"“](.{24,}?)[\"”]", text):
        snippet = span.rstrip("…").strip()
        if not any(snippet[:80] in quote for quote in quotes):
            problems.append("a quotation is not one of the packet quotations")
    return problems


def live_summary(records, question: str) -> tuple[str | None, str]:
    from app import load_settings
    from pipeline.chat import reply

    settings = load_settings()
    if not settings.get("api_key"):
        return "The summary cannot be checked because no LLM key is set.", "error"
    outcome = reply(records, question, settings)
    text = outcome.get("text") or ""
    if outcome.get("source") != "model" or "The model call failed" in text:
        return text, "error"
    return text, "model"


def _first_line(text: str | None) -> str:
    line = (text or "no reply").strip().splitlines()
    return line[-1] if line else "no reply"


def _numbers(node) -> set[int]:
    found: set[int] = set()

    def walk(value) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, int):
            found.add(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(node)
    return found


def _numbers_in_text(text: str) -> list[int]:
    values = []
    for match in re.finditer(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{2,}%|\b\d{2,}\b", text):
        raw = match.group().replace(",", "").rstrip("%")
        values.append(int(raw))
    return values


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        sys.stdout = None
        raise SystemExit(1)
