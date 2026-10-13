import re
from dataclasses import dataclass

_HEADER_MAP = {
    "岗位职责": "岗位职责",
    "职责": "岗位职责",
    "responsibilities": "岗位职责",
    "responsibility": "岗位职责",
    "job responsibilities": "岗位职责",
    "你将负责": "岗位职责",
    "you will": "岗位职责",
    "任职要求": "任职要求",
    "岗位要求": "任职要求",
    "职位要求": "任职要求",
    "requirements": "任职要求",
    "qualification": "任职要求",
    "qualifications": "任职要求",
    "basic qualifications": "任职要求",
    "任职资格": "任职要求",
    "加分项": "加分项",
    "优先条件": "加分项",
    "preferred qualifications": "加分项",
    "nice to have": "加分项",
}
_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•●·▪◦]|\d+[.)]|[a-zA-Z][.)])\s*")


@dataclass
class DescriptionSectionBlock:
    title: str
    lines: list[str]


def split_description_sections(description: str) -> list[DescriptionSectionBlock]:
    raw = (description or "").replace("\r\n", "\n").strip()
    if not raw:
        return []

    sections: list[DescriptionSectionBlock] = []
    current = DescriptionSectionBlock(title="岗位概览", lines=[])
    sections.append(current)

    for line in raw.split("\n"):
        text = line.strip()
        if not text:
            continue
        header = _parse_header(text)
        if header:
            current = DescriptionSectionBlock(title=header, lines=[])
            sections.append(current)
            continue
        current.lines.append(_normalize_line(text))

    normalized = [
        section for section in sections if section.lines or section.title == "岗位概览"
    ]
    if len(normalized) > 1 and normalized[0].title == "岗位概览" and not normalized[0].lines:
        normalized = normalized[1:]
    if not normalized:
        return [DescriptionSectionBlock(title="岗位概览", lines=[_normalize_line(raw)])]
    return normalized


def _parse_header(text: str) -> str | None:
    candidate = text.strip().strip(":：").strip()
    lowered = candidate.lower()
    if lowered in _HEADER_MAP:
        return _HEADER_MAP[lowered]
    if (
        text.endswith(":") or text.endswith("：")
    ) and len(candidate) <= 40 and lowered in _HEADER_MAP:
        return _HEADER_MAP[lowered]
    return None


def _normalize_line(text: str) -> str:
    return _BULLET_PREFIX.sub("", text).strip()
