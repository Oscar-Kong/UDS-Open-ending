"""Load the cleaned UDS file and apply the hard filter once."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pipeline.hard_filter import BUCKET_LABELS, REASON_LABELS, classify

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "UDS_Cleaned.csv"

QUESTION = (
    "Do you feel Northeastern students have any advantages over "
    "non-Northeastern peers? Please explain."
)


@dataclass(frozen=True)
class Record:
    id: int
    text: str
    year: int
    college: str
    campus: str
    level: str
    degree: str
    words: int
    bucket: str
    reason: str
    stance: str | None
    normalized: str
    duplicate: bool

    def public(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "year": self.year,
            "college": self.college,
            "campus": self.campus,
            "level": self.level,
            "degree": self.degree,
            "words": self.words,
            "bucket": self.bucket,
            "bucket_label": BUCKET_LABELS[self.bucket],
            "reason": self.reason,
            "reason_label": REASON_LABELS[self.reason],
            "stance": self.stance,
            "duplicate": self.duplicate,
        }


def _blank(value: str | None) -> str:
    text = (value or "").strip()
    if text.lower() in {"", "nan", "none", "not available"}:
        return ""
    return text


def _pick(fieldnames: list[str], options: list[str]) -> str | None:
    lookup = {name.lower().strip(): name for name in fieldnames}
    for option in options:
        if option in lookup:
            return lookup[option]
    return None


def text_column(fieldnames: list[str]) -> str | None:
    """Find the open-ended comment column in an imported CSV."""
    chosen = _pick(
        fieldnames,
        ["cleaned_text", "response_text", "response", "comment", "text", "answer"],
    )
    if chosen:
        return chosen
    for name in fieldnames:
        lowered = name.lower()
        if "advantage" in lowered or "please explain" in lowered:
            return name
    return None


def load(path: Path = DATA_PATH) -> list[Record]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return load_reader(csv.DictReader(handle))


def load_reader(reader: csv.DictReader) -> list[Record]:
    fieldnames = list(reader.fieldnames or [])
    comment_field = text_column(fieldnames)
    if not comment_field:
        raise ValueError("The CSV needs a comment column, such as cleaned_text or response_text.")
    id_field = _pick(fieldnames, ["dummy id", "id", "response_id"])
    year_field = _pick(fieldnames, ["year"])
    college_field = _pick(fieldnames, ["college_desc", "college"])
    campus_field = _pick(fieldnames, ["campus_desc", "campus"])
    level_field = _pick(fieldnames, ["student_level_desc", "student_level", "level"])
    degree_field = _pick(fieldnames, ["degree_desc", "degree"])
    words_field = _pick(fieldnames, ["word_count"])

    records: list[Record] = []
    seen: set[str] = set()
    for index, row in enumerate(reader, start=1):
        text = _blank(row.get(comment_field))
        if not text:
            continue
        judged = classify(text)
        key = judged["normalized"]
        duplicate = False
        if judged["bucket"] != "exclude" and key:
            duplicate = key in seen
            seen.add(key)
        raw_id = _blank(row.get(id_field)) if id_field else ""
        try:
            row_id = int(float(raw_id)) if raw_id else index
        except ValueError:
            row_id = index
        raw_year = _blank(row.get(year_field)) if year_field else ""
        try:
            year = int(float(raw_year)) if raw_year else 0
        except ValueError:
            year = 0
        if words_field and _blank(row.get(words_field)):
            try:
                words = int(float(row.get(words_field) or 0))
            except ValueError:
                words = len(text.split())
        else:
            words = len(text.split())
        records.append(
            Record(
                id=row_id,
                text=text,
                year=year,
                college=_blank(row.get(college_field)) or "Not recorded" if college_field else "Not recorded",
                campus=_blank(row.get(campus_field)) or "Not recorded" if campus_field else "Not recorded",
                level=_blank(row.get(level_field)) or "Not recorded" if level_field else "Not recorded",
                degree=_blank(row.get(degree_field)) or "Not recorded" if degree_field else "Not recorded",
                words=words,
                bucket=judged["bucket"],
                reason=judged["reason"],
                stance=judged["stance"],
                normalized=judged["normalized"],
                duplicate=duplicate,
            )
        )
    if not records:
        raise ValueError("That CSV has no comment text to read.")
    return records


def facet(records: list[Record], field: str) -> list[dict]:
    counts: Counter[str] = Counter()
    for record in records:
        value = getattr(record, field) or ""
        counts[value or ""] += 1
    rows = []
    for value, count in counts.most_common():
        rows.append(
            {
                "value": value,
                "label": value or "Not recorded",
                "n": count,
            }
        )
    return rows


def select(
    records: list[Record],
    *,
    bucket: str = "",
    college: str = "",
    campus: str = "",
    level: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    q: str = "",
) -> list[Record]:
    needle = q.strip().lower()
    chosen: list[Record] = []
    for record in records:
        if bucket and record.bucket != bucket:
            continue
        if college and record.college != college:
            continue
        if campus and record.campus != campus:
            continue
        if level and record.level != level:
            continue
        if year_from is not None and record.year < year_from:
            continue
        if year_to is not None and record.year > year_to:
            continue
        if needle and needle not in record.text.lower():
            continue
        chosen.append(record)
    return chosen
