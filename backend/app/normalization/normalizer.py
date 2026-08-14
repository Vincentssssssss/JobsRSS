import re

from app.schemas.job import UnifiedJob


def _looks_like_mojibake(value: str) -> bool:
    if not value:
        return False
    markers = ["銆", "鍖", "鎬", "闈", "€", "�", "浜", "浣", "鏂", "绉"]
    marker_hits = sum(value.count(marker) for marker in markers)
    return marker_hits >= 2


def _try_recover_mojibake(value: str) -> str:
    if not _looks_like_mojibake(value):
        return value
    candidates = [value]
    try:
        candidates.append(value.encode("gb18030", errors="ignore").decode("utf-8", errors="ignore"))
    except Exception:
        pass
    try:
        candidates.append(value.encode("latin1", errors="ignore").decode("utf-8", errors="ignore"))
    except Exception:
        pass

    def score(text: str) -> int:
        bad_markers = ["銆", "鍖", "鎬", "闈", "€", "�"]
        bad = sum(text.count(marker) for marker in bad_markers)
        chinese = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        return chinese * 2 - bad * 3

    return max(candidates, key=score)


def normalize_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    cleaned = _try_recover_mojibake(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalize_job(job: UnifiedJob) -> UnifiedJob:
    job.title = normalize_text(job.title)
    job.company = normalize_text(job.company)
    job.location = normalize_text(job.location)
    job.description = normalize_text(job.description)
    return job
