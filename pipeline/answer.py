"""Grounded answers from the hard-filtered corpus.

No generative model is called. Counts, keyword cues, and quotations are
taken from the slice the question (and the on-screen filters) select.
That is the retrieval half of the later LLM stage, with the writing half
left as a template so the claims stay checkable.
"""

from __future__ import annotations

import re

from pipeline.corpus import QUESTION, Record
from pipeline.hard_filter import FUNCTION, normalize

# Patterns run on normalized text. Short theme words are whole tokens so
# "intern" does not match "internal".
THEMES: list[tuple[str, str, list[str]]] = [
    ("coop", "Co-op and internships", [r"\bcoops?\b", r"\binterns?\b", r"\binternships?\b"]),
    (
        "experience",
        "Work or industry experience",
        [r"\bwork experience\b", r"\breal world\b", r"\bhands on\b", r"\bindustry\b"],
    ),
    (
        "network",
        "Network and alumni",
        [r"\bnetworks?\b", r"\bnetworking\b", r"\balumni\b", r"\bconnections?\b"],
    ),
    (
        "reputation",
        "Name and reputation",
        [r"\breputation\b", r"\bprestigious\b", r"\bbrand\b", r"\bname recognition\b", r"\bopens doors\b"],
    ),
    (
        "career",
        "Hiring and the resume",
        [r"\bresume\b", r"\brecruit\w*\b", r"\bcareer services\b", r"\bcareer fair\b", r"\bjob offers?\b"],
    ),
    (
        "place",
        "Place and other campuses",
        [r"\bglobal campuses?\b", r"\binternational\b", r"\blocation\b", r"\bin boston\b"],
    ),
    (
        "parity",
        "No real difference",
        [
        r"\bno (real )?advantages?\b",
        r"\bno difference\b",
        r"\bnot unique\b",
        r"\bdoesnt matter\b",
        r"\bdont care\b",
        r"\bthe same as\b",
        r"\bnothing special\b",
        r"\bno better\b",
        ],
    ),
    (
        "cost",
        "Cost, time, or stress",
        [r"\btuition\b", r"\bexpensive\b", r"\bdebt\b", r"\bburnout\b", r"\bstress\w*\b"],
    ),
    (
        "faculty",
        "Faculty and courses",
        [r"\bprofessors?\b", r"\bfaculty\b", r"\bcoursework\b", r"\bcurriculum\b"],
    ),
]

COMPILED = [
    (theme_id, label, [re.compile(pattern) for pattern in patterns])
    for theme_id, label, patterns in THEMES
]

REVIEW = {
    "coop": (
        "Split co-op comments into three piles before anyone acts on them: "
        "co-op as the advantage, co-op missed or shortened, and co-op that was fine but not the main reason."
    ),
    "reputation": (
        "Check whether the Northeastern name is the advantage students name when they are not talking about co-op, and in which colleges."
    ),
    "parity": (
        "Read the comments that say there is no real difference on their own. They are a finding, not leftovers around the co-op story."
    ),
    "network": (
        "Ask whether network means alumni, classmates, or employers. In these comments the word is doing more than one job."
    ),
    "cost": (
        "Where cost or stress shows up, keep it attached to the advantage it qualifies. It is not a separate survey item."
    ),
    "experience": (
        "Work experience and co-op are easy to double-count. Treat experience-only comments separately when co-op is not named."
    ),
}

COLLEGES = [
    ("Khoury Coll of Comp Sciences", ["khoury", "computer science", "ccis"]),
    ("College of Engineering", ["college of engineering", "engineering"]),
    ("D'Amore-McKim School Business", ["damore", "mckim", "business school"]),
    ("Bouve College of Hlth Sciences", ["bouve", "health sciences", "health science"]),
    ("Coll of Soc Sci & Humanities", ["cssh", "social sciences", "social science", "humanities"]),
    ("Coll of Arts, Media & Design", ["camd", "arts media", "media and design"]),
    ("Coll of Professional Studies", ["professional studies", "cps"]),
    ("College of Science", ["college of science"]),
    ("School of Law", ["school of law", "law school"]),
]

CAMPUSES = [
    ("Boston", "boston"),
    ("Seattle, WA", "seattle"),
    ("Toronto, Canada", "toronto"),
    ("Vancouver, Canada", "vancouver"),
    ("Silicon Valley, CA", "silicon valley"),
    ("Charlotte, NC", "charlotte"),
    ("Portland, Maine", "portland"),
    ("Oakland, CA", "oakland"),
]

META_WORDS = {
    "advantage",
    "advantages",
    "student",
    "students",
    "northeastern",
    "neu",
    "peer",
    "peers",
    "feel",
    "feeling",
    "why",
    "reason",
    "reasons",
    "comment",
    "comments",
    "say",
    "says",
    "said",
    "think",
    "difference",
    "differences",
    "compare",
    "comparison",
    "college",
    "colleges",
    "year",
    "years",
    "graduate",
    "graduates",
    "undergraduate",
    "undergrad",
    "undergrads",
    "explain",
    "explanation",
    "explanations",
    "theme",
    "themes",
    "main",
    "most",
    "many",
    "people",
    "response",
    "responses",
    "versus",
    "differ",
    "different",
    "group",
    "groups",
    "across",
    "what",
    "how",
    "when",
    "where",
    "which",
    "who",
    "did",
    "does",
    "about",
    "over",
    "their",
    "there",
    "these",
    "those",
    "this",
    "that",
    "from",
    "with",
    "have",
    "has",
    "into",
    "between",
    "than",
    "your",
    "they",
    "them",
    "any",
    "some",
    "more",
    "other",
    "others",
    "non",
    "after",
    "before",
    "since",
    "through",
    "until",
    "during",
    "really",
    "actually",
    "describe",
    "described",
    "mention",
    "mentioned",
    "show",
    "tell",
    "give",
    "percent",
    "percentage",
    "share",
    "often",
    "yes",
    "no",
}

METHOD = (
    "Hard filter, then counts and keyword cues. No generative model is called. "
    "Headcounts include every respondent. Quotations are explanatory comments only, "
    "and repeated wording is quoted once."
)

FOLLOWUPS = [
    "What advantages do students actually describe?",
    "How many say yes, no, or that they are unsure?",
    "How do Engineering and Khoury comments differ?",
    "What do undergraduate and graduate students say differently?",
    "What changed in the reasons after 2020?",
    "Where do students say there is no real advantage?",
    "What do students say about the Northeastern name and reputation?",
    "What do 2024 and 2025 graduates say about co-op?",
]


def answer(
    records: list[Record],
    question: str,
    *,
    college: str = "",
    campus: str = "",
    level: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
) -> dict:
    text = (question or "").strip()
    if not text:
        return {
            "error": "Ask a question about the advantage comments.",
        }
    parsed = _parse(text)
    spec = {
        "colleges": [college] if college else parsed["colleges"],
        "levels": [level] if level else parsed["levels"],
        "campus": campus or parsed["campus"],
        "year_from": year_from if year_from is not None else parsed["year_from"],
        "year_to": year_to if year_to is not None else parsed["year_to"],
    }
    # A dropdown choice replaces the groups parsed out of the sentence.
    if college:
        spec["colleges"] = [college]
    if level:
        spec["levels"] = [level]

    groups = _groups(spec, parsed)
    slices = [_summarize(_apply(records, group), group["label"]) for group in groups]
    mode = _mode(text, parsed, spec, slices)
    focus = _focus_themes(parsed["normalized"])
    residual = parsed["residual"]

    if mode == "unsupported" or (residual and not focus and mode not in {"compare", "stance"} and _term_hits(slices, residual) < 3):
        mode = "unsupported"

    payload = _compose(text, mode, slices, focus, residual)
    payload["scope"] = _scope(spec, groups)
    payload["method"] = METHOD
    payload["survey_question"] = QUESTION
    payload["followups"] = [item for item in FOLLOWUPS if item.lower() != text.lower()][:3]
    return payload


def _parse(question: str) -> dict:
    normalized = normalize(question)
    found = []
    for name, aliases in COLLEGES:
        indexes = [normalized.find(alias) for alias in aliases if alias in normalized]
        if indexes:
            found.append((min(indexes), name))
    found.sort()
    colleges = [name for _, name in found]
    levels = []
    if re.search(r"\blaw students?\b|\blaw school\b", normalized):
        levels.append("law")
    if re.search(r"\bundergrads?\b|\bundergraduate\b", normalized):
        levels.append("undergraduate")
    if re.search(r"\bgraduates?\b|\bgrad students?\b", normalized) and "law" not in levels:
        levels.append("graduate")
    campus = ""
    for label, alias in CAMPUSES:
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            campus = label
            break
    year_from, year_to = _years(normalized)
    consumed = set()
    for _, aliases in COLLEGES:
        for alias in aliases:
            consumed.update(alias.split())
    for _, alias in CAMPUSES:
        consumed.update(alias.split())
    residual = [
        token
        for token in normalized.split()
        if token not in META_WORDS and token not in FUNCTION and token not in consumed and not token.isdigit() and len(token) > 2
    ]
    return {
        "normalized": normalized,
        "colleges": colleges,
        "levels": levels,
        "campus": campus,
        "year_from": year_from,
        "year_to": year_to,
        "residual": residual,
    }


def _years(normalized: str) -> tuple[int | None, int | None]:
    after = re.search(r"\bafter\s+(20(?:1[6-9]|2[0-6]))\b", normalized)
    if after:
        return int(after.group(1)) + 1, None
    since = re.search(r"\b(?:since|from)\s+(20(?:1[6-9]|2[0-6]))\b", normalized)
    if since:
        return int(since.group(1)), None
    before = re.search(r"\bbefore\s+(20(?:1[6-9]|2[0-6]))\b", normalized)
    if before:
        return None, int(before.group(1)) - 1
    until = re.search(r"\b(?:until|through)\s+(20(?:1[6-9]|2[0-6]))\b", normalized)
    if until:
        return None, int(until.group(1))
    found = [int(year) for year in re.findall(r"\b(20(?:1[6-9]|2[0-6]))\b", normalized)]
    if len(found) >= 2:
        return min(found), max(found)
    if len(found) == 1:
        return found[0], found[0]
    return None, None


def _groups(spec: dict, parsed: dict) -> list[dict]:
    """One slice, or two when the question compares groups or two time spans."""
    base = {
        "campus": spec["campus"],
        "year_from": spec["year_from"],
        "year_to": spec["year_to"],
    }
    colleges = spec["colleges"]
    levels = spec["levels"]
    if _wants_period_compare(parsed) and len(colleges) < 2 and len(levels) < 2:
        start = spec["year_from"] or 2021
        college = colleges[0] if colleges else ""
        level = levels[0] if levels else ""
        earlier = f"2016–{start - 1}"
        later = f"{start}–{spec['year_to'] or 2026}"
        return [
            {**base, "college": college, "level": level, "year_from": None, "year_to": start - 1, "label": earlier},
            {**base, "college": college, "level": level, "year_from": start, "year_to": spec["year_to"], "label": later},
        ]
    if len(colleges) >= 2:
        return [{**base, "college": colleges[0], "level": "", "label": _short(colleges[0])}, {**base, "college": colleges[1], "level": "", "label": _short(colleges[1])}]
    if len(levels) >= 2:
        college = colleges[0] if colleges else ""
        return [
            {**base, "college": college, "level": "undergraduate", "label": "Undergraduates"},
            {**base, "college": college, "level": "graduate", "label": "Graduates"},
        ]
    college = colleges[0] if colleges else ""
    level = levels[0] if levels else ""
    label = _short(college) if college else {"undergraduate": "Undergraduates", "graduate": "Graduates", "law": "Law"}.get(level, "All respondents")
    return [{**base, "college": college, "level": level, "label": label}]


def _wants_period_compare(parsed: dict) -> bool:
    text = parsed["normalized"]
    if parsed["year_from"] is None:
        return False
    return "change" in text


def _apply(records: list[Record], group: dict) -> list[Record]:
    chosen = []
    for record in records:
        if group["college"] and record.college != group["college"]:
            continue
        if not _match_level(record, group["level"]):
            continue
        if group["campus"] and group["campus"].split(",")[0].lower() not in record.campus.lower():
            continue
        if group["year_from"] is not None and record.year < group["year_from"]:
            continue
        if group["year_to"] is not None and record.year > group["year_to"]:
            continue
        chosen.append(record)
    return chosen


def _match_level(record: Record, level: str) -> bool:
    if not level:
        return True
    if level == "undergraduate":
        return _is_undergrad(record.level)
    if level == "graduate":
        return _is_grad(record.level)
    if level == "law":
        return record.level == "Law" or record.college == "School of Law"
    return record.level == level


def _is_undergrad(level: str) -> bool:
    text = level.lower()
    return "undergrad" in text


def _is_grad(level: str) -> bool:
    text = level.lower()
    return "graduate" in text and "undergrad" not in text


def _summarize(records: list[Record], label: str) -> dict:
    kept = [record for record in records if record.bucket != "exclude"]
    buckets = {name: 0 for name in ("pass", "label_only", "stance_only", "exclude")}
    stance = {name: 0 for name in ("yes", "no", "mixed", "unsure", "unlabeled")}
    for record in records:
        buckets[record.bucket] += 1
        if record.bucket == "exclude":
            continue
        stance[record.stance or "unlabeled"] += 1
    themes = []
    pass_n = buckets["pass"]
    for theme_id, theme_label, patterns in COMPILED:
        explain = 0
        short = 0
        for record in records:
            if record.bucket not in {"pass", "label_only"}:
                continue
            if any(pattern.search(record.normalized) for pattern in patterns):
                if record.bucket == "pass":
                    explain += 1
                else:
                    short += 1
        themes.append(
            {
                "id": theme_id,
                "label": theme_label,
                "explanations": explain,
                "short_labels": short,
                "share": _pct(explain, pass_n),
            }
        )
    themes.sort(key=lambda item: (item["explanations"], item["short_labels"]), reverse=True)
    return {
        "label": label,
        "n": len(records),
        "kept": len(kept),
        "buckets": buckets,
        "stance": stance,
        "themes": themes,
        "records": records,
    }


def _mode(question: str, parsed: dict, spec: dict, slices: list[dict]) -> str:
    normalized = parsed["normalized"]
    if len(slices) > 1 or any(word in normalized for word in ("compare", "comparison", "differ", "versus", "vs")):
        if len(slices) > 1:
            return "compare"
    if any(phrase in normalized for phrase in ("how many", "how often", "what percent", "what share", "yes or no", "say yes", "say no")):
        return "stance"
    return "themes"


def _focus_themes(normalized: str) -> list[tuple[str, str, list[re.Pattern[str]]]]:
    found = []
    for item in COMPILED:
        if any(pattern.search(normalized) for pattern in item[2]):
            found.append(item)
    return found


def _term_hits(slices: list[dict], terms: list[str]) -> int:
    """Documents whose explanation contains every leftover word, not just one."""
    hits = 0
    for piece in slices:
        for record in piece["records"]:
            if record.bucket != "pass":
                continue
            if all(term in record.normalized for term in terms):
                hits += 1
    return hits


def _compose(question: str, mode: str, slices: list[dict], focus, residual: list[str]) -> dict:
    if mode == "unsupported":
        return {
            "mode": mode,
            "support": "insufficient",
            "headline": "These comments don't answer that.",
            "paragraphs": [
                f"The survey item is: {QUESTION}",
                "The hard filter can count positions, short labels, and a fixed set of reason cues. "
                "It should not stretch those into a topic the wording does not carry. "
                "A later model is held to the same line: if the quotes are not there, the answer is that the evidence is insufficient.",
            ],
            "slices": [_public_slice(piece, [], None) for piece in slices],
            "review_questions": [],
        }

    for piece in slices:
        lead = _lead(piece)
        # Leftover words only steer quotations on an open theme question.
        # In a comparison they are usually the word "differently".
        quote_residual = residual if mode == "themes" else []
        piece["quotes"] = _quotes(
            piece["records"],
            focus,
            quote_residual,
            None if lead is None else lead["id"],
        )

    support = _support(slices, mode)
    paragraphs = []
    if mode == "compare":
        headline, paragraphs = _compare_copy(slices, support)
    elif mode == "stance":
        headline, paragraphs = _stance_copy(slices[0], support)
    else:
        headline, paragraphs = _theme_copy(slices[0], focus, support)

    visible_themes = []
    for piece in slices:
        for theme in piece["themes"]:
            if theme["explanations"] >= 5 or theme["short_labels"] >= 8:
                visible_themes.append(theme["id"])
    if focus and mode == "themes":
        focused = [theme_id for theme_id in visible_themes if theme_id in {item[0] for item in focus}]
        if focused:
            visible_themes = focused
    review = [REVIEW[theme_id] for theme_id in dict.fromkeys(visible_themes) if theme_id in REVIEW][:3]

    focus_ids = {item[0] for item in focus} if focus and mode == "themes" else None
    return {
        "mode": mode,
        "support": support,
        "headline": headline,
        "paragraphs": paragraphs,
        "slices": [_public_slice(piece, piece.get("quotes", []), focus_ids) for piece in slices],
        "review_questions": review,
    }


def _support(slices: list[dict], mode: str) -> str:
    smallest_pass = min(piece["buckets"]["pass"] for piece in slices)
    smallest_kept = min(piece["kept"] for piece in slices)
    if mode == "stance":
        if smallest_kept < 20:
            return "insufficient"
        if smallest_pass < 12:
            return "thin"
        return "enough"
    if smallest_pass < 8:
        return "insufficient"
    if smallest_pass < 40 or smallest_kept < 40:
        return "thin"
    return "enough"


def _stance_copy(piece: dict, support: str) -> tuple[str, list[str]]:
    stance = piece["stance"]
    labeled = stance["yes"] + stance["no"] + stance["mixed"] + stance["unsure"]
    yes_share = _pct(stance["yes"], labeled) if labeled else 0
    if support == "insufficient":
        return (
            "Too few comments in this slice to report a split.",
            [
                f"{piece['label']} has {piece['kept']} comments left after non-responses were set aside.",
                "Twenty is the floor used here for a headcount. Widen the year, college, or campus.",
            ],
        )
    headline = f"Where the opening position is clear, {yes_share}% say yes."
    paragraphs = [
        (
            f"{piece['label']}: {piece['n']:,} responses. "
            f"{piece['buckets']['exclude']:,} set aside as non-responses. "
            f"Of the rest, {stance['yes']:,} open with yes, {stance['no']:,} with no, "
            f"{stance['unsure']:,} with unsure, and {stance['mixed']:,} qualify a yes or no with but or however."
        ),
        (
            f"{stance['unlabeled']:,} comments do not start with a position the rules recognize. "
            "Many of those start with the reason itself. They stay in the explanation pile and out of the yes/no percentage."
        ),
        (
            f"{piece['buckets']['stance_only']:,} people gave a position and no reason. "
            f"{piece['buckets']['label_only']:,} named a reason in a few words. "
            f"{piece['buckets']['pass']:,} wrote an explanation. "
            "Only that last group is quoted below."
        ),
    ]
    if support == "thin":
        paragraphs.append("The yes/no count is usable. The explanations in this slice are still thin, so the reasons below are illustrations, not a stable ranking.")
    return headline, paragraphs


def _theme_copy(piece: dict, focus, support: str) -> tuple[str, list[str]]:
    if support == "insufficient":
        return (
            "There aren't enough explanations in this slice to say why.",
            [
                (
                    f"{piece['label']} has {piece['buckets']['pass']:,} explanatory comments and "
                    f"{piece['buckets']['stance_only']:,} yes/no-only comments. "
                    "The positions can be counted. The reasons cannot."
                ),
                "A later language model should refuse this slice too, rather than summarize five sentences into a theme.",
            ],
        )
    themes = [theme for theme in piece["themes"] if theme["explanations"] > 0]
    if focus:
        wanted = {item[0] for item in focus}
        themes = [theme for theme in piece["themes"] if theme["id"] in wanted] or themes
    lead = themes[0] if themes else None
    if lead is None:
        return (
            "The explanations in this slice don't use the reason cues this stage knows.",
            [
                f"{piece['buckets']['pass']:,} comments were long enough to keep, and none of them hit the keyword list.",
                "That is a limit of the keyword stage, not proof the comments are empty. The next stage, embeddings, is what reads those.",
            ],
        )
    if focus:
        headline = f"{lead['explanations']:,} explanations are about {lead['label'].lower()}."
    elif lead["share"] >= 35:
        headline = f"The reason these comments spell out is {lead['label'].lower()}."
    else:
        headline = "The explanations don't collapse to one reason."
    others = [theme for theme in themes[1:4] if theme["explanations"] >= 5]
    other_text = ", ".join(f"{theme['label'].lower()} ({theme['explanations']:,}, {theme['share']}%)" for theme in others)
    paragraphs = [
        (
            f"{piece['label']}: {piece['buckets']['pass']:,} explanations, "
            f"{piece['buckets']['label_only']:,} short reason-labels, "
            f"{piece['buckets']['stance_only']:,} positions with no reason."
        ),
        (
            f"Students name {lead['label'].lower()} in {lead['explanations']:,} explanations ({lead['share']}%). "
            f"Another {lead['short_labels']:,} people named it and stopped, so they count in the tally and not in the quotations."
        ),
    ]
    if other_text:
        paragraphs.append(f"Other cues in the explanations: {other_text}. A comment can carry more than one.")
    stance = piece["stance"]
    labeled = stance["yes"] + stance["no"] + stance["unsure"] + stance["mixed"]
    if labeled:
        paragraphs.append(
            f"Opening position, among comments where the rules can see one: "
            f"{stance['yes']:,} yes, {stance['no']:,} no, {stance['unsure']:,} unsure, {stance['mixed']:,} mixed. "
            f"{stance['unlabeled']:,} are unlabeled."
        )
    if support == "thin":
        paragraphs.append("This slice is small. Treat the ranking as a lead, and read the quotations before repeating it.")
    return headline, paragraphs


def _compare_copy(slices: list[dict], support: str) -> tuple[str, list[str]]:
    left, right = slices[0], slices[1]
    left_lead = _lead(left)
    right_lead = _lead(right)
    left_yes, left_labeled = _yes_share(left)
    right_yes, right_labeled = _yes_share(right)
    same_reason = left_lead and right_lead and left_lead["id"] == right_lead["id"]
    yes_gap = abs(left_yes - right_yes) if left_labeled >= 40 and right_labeled >= 40 else 0
    if support == "insufficient":
        headline = f"{left['label']} and {right['label']} don't both have enough explanation to compare."
    elif same_reason and yes_gap >= 12:
        lower = left if left_yes < right_yes else right
        headline = (
            f"Both lead with {left_lead['label'].lower()}. "
            f"{lower['label']} open with yes less often ({min(left_yes, right_yes)}% vs {max(left_yes, right_yes)}%)."
        )
    elif same_reason:
        headline = f"{left['label']} and {right['label']} spell out the same leading reason."
    elif left_lead and right_lead:
        headline = f"{left['label']} leads with {left_lead['label'].lower()}. {right['label']} leads with {right_lead['label'].lower()}."
    else:
        headline = f"{left['label']} and {right['label']} are hard to compare on reasons."
    paragraphs = []
    for piece, lead in ((left, left_lead), (right, right_lead)):
        stance = piece["stance"]
        labeled = sum(stance[name] for name in ("yes", "no", "unsure", "mixed"))
        reason = (
            f"The leading cue, {lead['label'].lower()}, shows up in {lead['explanations']:,} of {piece['buckets']['pass']:,} explanations ({lead['share']}%)."
            if lead
            else "No keyword cue clears the explanations in this group."
        )
        paragraphs.append(
            f"{piece['label']}: {piece['n']:,} responses, {piece['buckets']['pass']:,} explanations. "
            f"Where an opening position is clear ({labeled:,} comments), {stance['yes']:,} say yes and {stance['no']:,} say no. {reason}"
        )
    if support == "thin":
        paragraphs.append("One side of this comparison is thin. The gap may be sample size rather than a real difference in what students wrote.")
    elif support == "enough":
        paragraphs.append("Same survey item, same hard filter, same keyword list. A difference here is a difference in wording, which is what UDS can verify from the quotations.")
    return headline, paragraphs


def _yes_share(piece: dict) -> tuple[int, int]:
    stance = piece["stance"]
    labeled = stance["yes"] + stance["no"] + stance["unsure"] + stance["mixed"]
    return _pct(stance["yes"], labeled), labeled


def _lead(piece: dict) -> dict | None:
    for theme in piece["themes"]:
        if theme["explanations"] >= 5:
            return theme
    return None


def _quotes(records: list[Record], focus, residual: list[str], lead_id: str | None) -> list[Record]:
    patterns: list[re.Pattern[str]] = []
    if focus:
        for _, _, compiled in focus:
            patterns.extend(compiled)
    elif residual:
        patterns.append(re.compile("|".join(rf"\b{re.escape(term)}\b" for term in residual[:6])))
    elif lead_id:
        for theme_id, _, compiled in COMPILED:
            if theme_id == lead_id:
                patterns.extend(compiled)
    pool = [record for record in records if record.bucket == "pass" and not record.duplicate and record.words >= 8]
    if patterns:
        matched = [record for record in pool if any(pattern.search(record.normalized) for pattern in patterns)]
        if matched:
            pool = matched
    def rank(record: Record) -> tuple:
        positions = [match.start() for pattern in patterns for match in [pattern.search(record.normalized)] if match]
        earliest = min(positions) if positions else 10_000
        return (earliest, 0 if 18 <= record.words <= 70 else 1, abs(record.words - 40), -record.year, record.id)

    pool.sort(key=rank)
    picked: list[Record] = []
    seen_colleges: set[str] = set()
    for record in pool:
        if record.college in seen_colleges and len(picked) < 3:
            continue
        picked.append(record)
        seen_colleges.add(record.college)
        if len(picked) == 3:
            break
    if len(picked) < 3:
        for record in pool:
            if record not in picked:
                picked.append(record)
            if len(picked) == 3:
                break
    return picked


def _public_slice(piece: dict, quotes: list[Record], focus_ids: set[str] | None) -> dict:
    themes = [
        {
            "id": theme["id"],
            "label": theme["label"],
            "explanations": theme["explanations"],
            "short_labels": theme["short_labels"],
            "share": theme["share"],
        }
        for theme in piece["themes"]
        if theme["explanations"] or theme["short_labels"]
    ]
    if focus_ids:
        themes = [theme for theme in themes if theme["id"] in focus_ids] or themes
    themes = themes[:6]
    return {
        "label": piece["label"],
        "n": piece["n"],
        "kept": piece["kept"],
        "buckets": piece["buckets"],
        "stance": piece["stance"],
        "themes": themes,
        "quotes": [_quote_public(record) for record in quotes],
    }


def _quote_public(record: Record) -> dict:
    text = record.text
    if len(text) > 420:
        text = text[:417].rstrip() + "…"
    return {
        "id": record.id,
        "text": text,
        "year": record.year,
        "college": record.college,
        "campus": record.campus,
        "level": record.level,
        "words": record.words,
        "stance": record.stance,
    }


def _scope(spec: dict, groups: list[dict]) -> str:
    bits = []
    if len(groups) > 1:
        bits.append(f"{groups[0]['label']} vs {groups[1]['label']}")
    else:
        group = groups[0]
        if group["college"]:
            bits.append(group["college"])
        if group["level"] == "undergraduate":
            bits.append("Undergraduates")
        elif group["level"] == "graduate":
            bits.append("Graduates")
        elif group["level"] == "law" and not group["college"]:
            bits.append("Law")
    if spec["campus"]:
        bits.append(spec["campus"])
    labels_already_name_years = len(groups) > 1 and any(character.isdigit() for character in groups[0]["label"])
    start, end = (None, None) if labels_already_name_years else (spec["year_from"], spec["year_to"])
    if start and end and start == end:
        bits.append(str(start))
    elif start and end:
        bits.append(f"{start}–{end}")
    elif start:
        bits.append(f"{start}–2026")
    elif end:
        bits.append(f"2016–{end}")
    return " · ".join(bits) if bits else "All respondents · 2016–2026"


def _short(college: str) -> str:
    short = {
        "College of Engineering": "Engineering",
        "Khoury Coll of Comp Sciences": "Khoury",
        "D'Amore-McKim School Business": "D'Amore-McKim",
        "Bouve College of Hlth Sciences": "Bouvé",
        "Coll of Soc Sci & Humanities": "CSSH",
        "Coll of Arts, Media & Design": "CAMD",
        "Coll of Professional Studies": "CPS",
        "College of Science": "Science",
        "School of Law": "Law",
    }
    return short.get(college, college)


def _pct(part: int, whole: int) -> int:
    if not whole:
        return 0
    return round(100 * part / whole)
