"""Text normalization and tokenization that behave correctly for CJK.

PDF extraction routinely inserts stray whitespace inside Chinese sentences and
mixes full-width with half-width characters. Comparing raw strings would report
false negatives, so all matching happens on a normalized form.
"""
from __future__ import annotations

import re
import unicodedata

# Zero-width and BOM characters that survive NFKC but break substring matching.
_INVISIBLE = re.compile(r"[​‌‍⁠﻿]")
_WHITESPACE = re.compile(r"\s+")
_LATIN_TOKEN = re.compile(r"[a-z0-9]+")
_CJK_RUN = re.compile(r"[㐀-䶿一-鿿豈-﫿]+")


def normalize(text: str) -> str:
    """Fold text to a canonical form for substring comparison.

    NFKC unifies full-width/half-width, casefold handles Latin case, and all
    whitespace is removed - safe for CJK, where whitespace carries no meaning,
    and adequate for Latin substring checks.
    """
    folded = unicodedata.normalize("NFKC", text)
    folded = _INVISIBLE.sub("", folded)
    return _WHITESPACE.sub("", folded.casefold())


def tokenize(text: str) -> tuple[str, ...]:
    """Split text into retrieval tokens.

    Latin runs become word tokens. CJK runs become character unigrams plus
    adjacent bigrams, which approximates word segmentation well enough for
    BM25 without pulling in a segmentation dependency.
    """
    folded = unicodedata.normalize("NFKC", text)
    folded = _INVISIBLE.sub("", folded).casefold()

    tokens: list[str] = list(_LATIN_TOKEN.findall(folded))
    for run in _CJK_RUN.findall(folded):
        tokens.extend(run)
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tuple(tokens)


def coverage_ratio(needle: str, haystack: str) -> float:
    """Fraction of `needle` covered by its longest contiguous run in `haystack`.

    Both inputs must already be normalized. Returns 0.0 for an empty needle.
    Used to grade near-miss citations: a quote that is 90% present is likely a
    real citation with a transcription slip, while 20% is a fabrication.
    """
    if not needle:
        return 0.0
    # difflib is O(n*m) in the worst case; cap the haystack to keep page-sized
    # comparisons predictable.
    from difflib import SequenceMatcher

    matcher = SequenceMatcher(None, needle, haystack, autojunk=False)
    match = matcher.find_longest_match(0, len(needle), 0, len(haystack))
    return match.size / len(needle)


def collapse_for_display(text: str, limit: int = 160) -> str:
    """One-line, length-capped rendering of text for CLI output."""
    single_line = _WHITESPACE.sub(" ", text).strip()
    if len(single_line) <= limit:
        return single_line
    return single_line[: limit - 1] + "…"
