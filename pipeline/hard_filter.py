"""Deterministic hard filter for the UDS advantage question.

The survey item is: "Do you feel Northeastern students have any advantages
over non-Northeastern peers? Please explain."

Most replies are a yes/no, a one-word reason ("co-op"), or a short
explanation. A generative model should not read the first two. This module
sorts every cleaned response into one bucket before any embedding or LLM
call.

Buckets
-------
exclude
    Non-response. Drop from rates, quotes, and models.
stance_only
    Yes, no, or unsure, with no reason. Use for stance rates only.
label_only
    Names a reason in closed-class words ("yes, because of co-op") and
    does not explain it. Use for keyword tallies. Do not embed. Do not
    send to a generative model.
pass
    At least one word outside that closed vocabulary. This is the only
    text later stages should read.
"""

from __future__ import annotations

import re
import unicodedata

# Full-string matches after normalization.
JUNK_EXACT = {
    "na",
    "n a",
    "none",
    "nil",
    "null",
    "test",
    "asdf",
    "blank",
    "skip",
    "pass",
    "hello",
    "hi",
    "thanks",
    "thank you",
    "nothing",
    "nothing to say",
    "no comment",
    "no comments",
    "see above",
    "same as above",
    "as above",
    "whatever",
    "idc",
    "na na",
}

# Tokens that state a position but not a reason, including hedges
# ("not much", "idk man") and Likert wording imported from other items.
STANCE = {
    "yes",
    "yeah",
    "yea",
    "yep",
    "yup",
    "yessir",
    "yesh",
    "no",
    "nope",
    "nah",
    "none",
    "maybe",
    "perhaps",
    "unsure",
    "unknown",
    "sure",
    "absolutely",
    "definitely",
    "somewhat",
    "particularly",
    "whatsoever",
    "really",
    "rlly",
    "rly",
    "not",
    "idk",
    "dunno",
    "dont",
    "cant",
    "cannot",
    "know",
    "think",
    "tell",
    "so",
    "i",
    "im",
    "do",
    "did",
    "does",
    "hard",
    "say",
    "see",
    "depends",
    "depend",
    "depending",
    "kinda",
    "kind",
    "sort",
    "guess",
    "certain",
    "extent",
    "extend",
    "degree",
    "much",
    "necessarily",
    "significantly",
    "slightly",
    "slight",
    "bit",
    "little",
    "lot",
    "lots",
    "meh",
    "man",
    "now",
    "strongly",
    "agree",
    "agreed",
    "disagree",
    "disagreed",
    "neutral",
}

# Tokens that name a reason without explaining it.
LABELS = {
    "coop",
    "coops",
    "internship",
    "internships",
    "intern",
    "work",
    "experience",
    "experiences",
    "job",
    "jobs",
    "program",
    "programs",
    "real",
    "world",
    "advantage",
    "advantages",
    "employment",
    "oriented",
    "networking",
    "network",
    "connections",
    "connection",
}

# Glue words. A reply made only of these plus stance/label tokens has no
# explanation yet.
FUNCTION = {
    "a",
    "an",
    "the",
    "of",
    "to",
    "for",
    "with",
    "due",
    "because",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "my",
    "our",
    "their",
    "your",
    "from",
    "by",
    "than",
    "over",
    "any",
    "about",
    "into",
    "per",
    "as",
    "well",
    "very",
    "more",
    "most",
    "also",
    "just",
    "too",
    "is",
    "are",
    "was",
    "were",
    "am",
    "be",
    "been",
    "being",
    "it",
    "its",
    "that",
    "this",
    "they",
    "them",
    "we",
    "you",
    "have",
    "has",
    "had",
    "can",
    "get",
    "got",
    "some",
    "only",
    "through",
    "via",
    "vs",
    "all",
    "at",
    "ever",
    "there",
    "theres",
    "thats",
    "end",
    "side",
    "course",
    "ofcourse",
    "please",
    "lol",
    "haha",
    "will",
    "gonna",
    "later",
    "soon",
}

UNSURE_PREFIXES = (
    "not really sure",
    "not sure",
    "im not sure",
    "i am not sure",
    "unsure",
    "maybe",
    "perhaps",
    "idk",
    "i dont know",
    "dont know",
    "kind of",
    "sort of",
    "we will see",
    "will see",
    "hard to say",
    "its hard to say",
    "it depends",
    "depends",
    "i cant say",
)

NO_PREFIXES = (
    "strongly disagree",
    "disagree",
    "no advantage",
    "no advantages",
    "not really",
    "not at all",
    "not whatsoever",
    "not particularly",
    "not much",
    "not very much",
    "not that much",
    "nope",
    "nah",
    "none",
    "nothing",
    "no",
    "not",
)

YES_PREFIXES = (
    "strongly agree",
    "yes",
    "yeah",
    "yea",
    "yep",
    "yup",
    "yessir",
    "yesh",
    "absolutely",
    "definitely",
    "agree",
)

BUCKET_LABELS = {
    "pass": "Explanation",
    "label_only": "Short reason",
    "stance_only": "Position only",
    "exclude": "Set aside",
}

REASON_LABELS = {
    "non_response": "Non-response",
    "low_letter_quality": "Not readable text",
    "function_words_only": "No claim",
    "position_without_reason": "Yes, no, or unsure only",
    "closed_reason_label": "Names a reason, does not explain it",
    "single_content_word": "One content word, no explanation",
    "has_explanation": "Explanation",
}

_CURLY = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": " ",
        "\u2014": " ",
    }
)


def normalize(text: str) -> str:
    """Lowercase, unify co-op spellings, and strip punctuation."""
    value = unicodedata.normalize("NFKC", text or "").translate(_CURLY)
    value = value.lower().replace("'", "")
    value = re.sub(r"co[\s-]*ops?\b", "coop", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    # "yesssss" and "nooo" are the same answer as yes and no.
    return " ".join(re.sub(r"(.)\1{2,}", r"\1", token) for token in value.split())


def _looks_like_mash(token: str) -> bool:
    letters = [ch for ch in token if ch.isalpha()]
    if len(letters) < 5:
        return False
    return not any(ch in "aeiou" for ch in letters)


def classify(text: str) -> dict:
    """Return bucket, normalized text, stance, and a short reason code."""
    norm = normalize(text)
    tokens = norm.split() if norm else []

    if not tokens or norm in JUNK_EXACT or sum(ch.isalpha() for ch in norm) < 2:
        return _row(norm, "exclude", "non_response", None)

    mash = [token for token in tokens if _looks_like_mash(token)]
    if mash and len(mash) * 2 >= len(tokens):
        return _row(norm, "exclude", "low_letter_quality", None)

    outside = [token for token in tokens if token not in STANCE and token not in LABELS and token not in FUNCTION]
    has_label = any(token in LABELS for token in tokens)
    has_stance = any(token in STANCE for token in tokens)

    # One unfamiliar word is still a label or a hedge, not an explanation.
    # Two unfamiliar words, or one inside a longer reply, is enough to keep.
    if len(outside) >= 2 or (len(outside) >= 1 and len(tokens) >= 8) or len(tokens) >= 15:
        bucket, reason = "pass", "has_explanation"
    elif has_label or outside:
        bucket, reason = "label_only", "closed_reason_label" if not outside else "single_content_word"
    elif has_stance:
        bucket, reason = "stance_only", "position_without_reason"
    else:
        bucket, reason = "exclude", "function_words_only"

    return _row(norm, bucket, reason, _stance(norm, bucket))


def _stance(norm: str, bucket: str) -> str | None:
    if bucket == "exclude":
        return None
    # A contrast usually reverses or qualifies the opening yes/no.
    if bucket == "pass" and re.search(r"\b(but|however|although|though)\b", norm):
        return "mixed"
    for prefix in UNSURE_PREFIXES:
        if norm == prefix or norm.startswith(prefix + " "):
            return "unsure"
    for prefix in NO_PREFIXES:
        if norm == prefix or norm.startswith(prefix + " "):
            return "no"
    for prefix in YES_PREFIXES:
        if norm == prefix or norm.startswith(prefix + " "):
            return "yes"
    if "not sure" in norm or "dont know" in norm:
        return "unsure"
    return None


def _row(norm: str, bucket: str, reason: str, stance: str | None) -> dict:
    return {
        "normalized": norm,
        "bucket": bucket,
        "reason": reason,
        "stance": stance,
    }


# Hand-checked cases from the cleaned file. Keep these aligned with samples.
FIXTURES = [
    ("Yes", "stance_only", "yes"),
    ("No", "stance_only", "no"),
    ("I don't know", "stance_only", "unsure"),
    ("Not whatsoever.", "stance_only", "no"),
    ("it's hard to say", "stance_only", "unsure"),
    ("maybe to certain extend", "stance_only", "unsure"),
    ("No comments", "exclude", None),
    ("n/a", "exclude", None),
    ("Co-op", "label_only", None),
    ("yes because of co-op", "label_only", "yes"),
    ("Yes, work experience", "label_only", "yes"),
    ("With co-op", "label_only", None),
    ("No advantage", "label_only", "no"),
    ("yes, Co op program is great.", "label_only", "yes"),
    ("Yes, coop builds experience", "label_only", "yes"),
    ("Co-op of course!", "label_only", None),
    ("Not much", "stance_only", "no"),
    ("Not necessarily", "stance_only", "no"),
    ("Idk man", "stance_only", "unsure"),
    ("YESSSSSSSSSSSSSSS", "stance_only", "yes"),
    ("It depends on your major.", "label_only", "unsure"),
    ("should be equivalent to others", "pass", None),
    ("Yes more connections thanks to coop", "label_only", "yes"),
    ("Great course work, amazing co-op", "pass", None),
    ("No clear advantages.", "label_only", "no"),
    ("we will see", "stance_only", "unsure"),
    ("kind of", "stance_only", "unsure"),
    ("The name opens doors.", "pass", None),
    ("Not whatsoever.", "stance_only", "no"),
]


def _self_check() -> None:
    failed = 0
    for text, bucket, stance in FIXTURES:
        got = classify(text)
        if got["bucket"] != bucket or got["stance"] != stance:
            failed += 1
            print(f"FAIL {text!r}: got {got['bucket']} {got['stance']} expected {bucket} {stance}")
    if failed:
        raise SystemExit(f"{failed} fixture(s) failed")
    print(f"{len(FIXTURES)} fixtures passed")


if __name__ == "__main__":
    _self_check()
