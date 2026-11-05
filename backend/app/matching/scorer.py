from typing import Iterable

from app.official.location import (
    HONG_KONG_MARKERS,
    MALAYSIA_MARKERS,
    SOUTHEAST_ASIA_MARKERS,
    YANGTZE_DELTA_MARKERS,
)

POSITIVE_KEYWORDS = {
    "cloud security architect",
    "cloud security engineer",
    "security architect",
    "application security",
    "devsecops",
    "ai security",
    "security engineering manager",
    "cybersecurity",
    "cyber security",
    "information security",
    "security engineer",
    "security manager",
    "security consultant",
    "security specialist",
    "云安全架构师",
    "云安全工程师",
    "安全架构师",
    "应用安全",
    "产品安全",
    "安全工程经理",
    "信息安全",
    "网络安全",
    "数据安全",
    "安全专家",
    "安全经理",
    "安全顾问",
}
# Customer-facing cloud roles a security/cloud background can move into; they
# score lower than security roles but still reach the LLM for judgement.
ADJACENT_ROLE_KEYWORDS = {
    "technical account manager",
    "solutions architect",
    "solution architect",
    "cloud architect",
    "customer engineer",
    "sales engineer",
    "solutions engineer",
    "presales",
    "pre-sales",
    "技术服务经理",
    "技术服务工程师",
    "技术客户经理",
    "解决方案架构师",
    "解决方案专家",
    "售前",
    "云架构师",
}
SENIORITY_KEYWORDS = {"senior", "lead", "principal", "manager", "director", "高级", "专家", "负责人", "经理", "总监"}
NEGATIVE_KEYWORDS = {"intern", "junior", "entry level", "helpdesk", "desktop support", "实习", "初级", "桌面支持", "运维支持"}
TARGET_LOCATION_MARKERS = {
    "shanghai",
    "上海",
    *YANGTZE_DELTA_MARKERS,
    *HONG_KONG_MARKERS,
    *MALAYSIA_MARKERS,
    *(marker for markers in SOUTHEAST_ASIA_MARKERS.values() for marker in markers),
}


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
    elif _contains_any(blob, ADJACENT_ROLE_KEYWORDS):
        score += 40
    if _contains_any(blob, SENIORITY_KEYWORDS):
        score += 20
    if _contains_any(blob, TARGET_LOCATION_MARKERS):
        score += 15
    if any(term in blob for term in ["apac", "greater china", "亚太", "大中华"]):
        score += 10
    return min(score, 100.0)
