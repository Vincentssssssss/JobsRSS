import re
from typing import Iterable

EARLY_CAREER_REGEXES = [
    re.compile(r"\b(?:20\d{2}|21\d{2})\s*(?:届|graduate|graduates?)\b", re.IGNORECASE),
    re.compile(r"\bgraduation\s*dates?\b", re.IGNORECASE),
]

EARLY_CAREER_KEYWORDS = {
    "校招",
    "校园招聘",
    "应届",
    "应届生",
    "实习",
    "实习生",
    "管培生",
    "fresh graduate",
    "new grad",
    "graduate recruitment",
    "campus recruitment",
    "campus hire",
    "campus hiring",
    "campus talent",
    "entry level",
    "internship",
    "intern",
    "graduate program",
    "management trainee",
}


def detect_early_career_markers(parts: Iterable[str]) -> list[str]:
    haystack = " ".join(str(part or "") for part in parts if part)
    lowered = haystack.lower()

    markers = [keyword for keyword in sorted(EARLY_CAREER_KEYWORDS) if keyword in lowered]
    for pattern in EARLY_CAREER_REGEXES:
        if pattern.search(haystack):
            markers.append(pattern.pattern)

    if "campus-talent.alibaba.com" in lowered:
        markers.append("alibaba-campus-portal")

    deduped: list[str] = []
    for marker in markers:
        if marker not in deduped:
            deduped.append(marker)
    return deduped
