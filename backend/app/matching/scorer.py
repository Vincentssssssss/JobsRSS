from typing import Iterable


POSITIVE_KEYWORDS = {
    "cloud security architect",
    "cloud security engineer",
    "security architect",
    "application security",
    "devsecops",
    "ai security",
    "security engineering manager",
    "云安全架构师",
    "云安全工程师",
    "安全架构师",
    "应用安全",
    "产品安全",
    "安全工程经理",
}
SENIORITY_KEYWORDS = {"senior", "lead", "principal", "manager", "director", "高级", "专家", "负责人", "经理", "总监"}
NEGATIVE_KEYWORDS = {"intern", "junior", "entry level", "helpdesk", "desktop support", "实习", "初级", "桌面支持", "运维支持"}


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def score_job(title: str, description: str, location: str) -> float:
    blob = f"{title} {description} {location}".lower()
    if _contains_any(blob, NEGATIVE_KEYWORDS):
        return 0

    score = 0.0
    if _contains_any(blob, POSITIVE_KEYWORDS):
        score += 55
    if _contains_any(blob, SENIORITY_KEYWORDS):
        score += 20
    if any(place in blob for place in ["hong kong", "singapore", "shanghai", "香港", "新加坡", "上海"]):
        score += 15
    if any(term in blob for term in ["apac", "greater china", "亚太", "大中华"]):
        score += 10
    return min(score, 100.0)
