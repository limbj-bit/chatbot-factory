"""Lightweight language detection for customer messages.

We only need to know whether a message is Korean or foreign (and roughly
which foreign language) so the owner dashboard can show a Korean translation.
A full CLD3/LangDetect dependency is overkill; character-range heuristics are
fast, dependency-free, and accurate enough for CS-length messages.
"""

from __future__ import annotations


def _count_ranges(text: str) -> dict:
    ko = ja = zh = latin = 0
    for ch in text:
        cp = ord(ch)
        if 0xAC00 <= cp <= 0xD7AF or 0x3130 <= cp <= 0x318F or 0x1100 <= cp <= 0x11FF:
            ko += 1
        elif 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF:
            ja += 1
        elif 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
            zh += 1
        elif ("a" <= ch.lower() <= "z"):
            latin += 1
    return {"ko": ko, "ja": ja, "zh": zh, "latin": latin}


def detect_language(text: str) -> str:
    """Return a coarse language code: 'ko', 'en', 'ja', 'zh', or 'other'."""
    if not text or not text.strip():
        return "ko"
    counts = _count_ranges(text)
    total = sum(counts.values())
    if total == 0:
        return "other"
    # Korean dominates -> Korean
    if counts["ko"] / total >= 0.25:
        return "ko"
    # Japanese kana present -> Japanese (even if mixed with kanji)
    if counts["ja"] > 0:
        return "ja"
    # Chinese characters without kana -> Chinese
    if counts["zh"] > 0 and counts["zh"] >= counts["latin"]:
        return "zh"
    # Latin script -> English (covers most EU languages adequately for CS)
    if counts["latin"] / total >= 0.5:
        return "en"
    return "other"


LANGUAGE_NAMES = {
    "ko": "한국어",
    "en": "영어",
    "ja": "일본어",
    "zh": "중국어",
    "other": "기타",
}
