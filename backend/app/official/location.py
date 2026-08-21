from enum import Enum


class LocationCategory(str, Enum):
    CONFIRMED_SHANGHAI = "confirmed_shanghai"
    UNCLASSIFIED = "unclassified"
    EXCLUDED = "excluded"


SHANGHAI_MARKERS = {"shanghai", "上海"}
BROAD_MARKERS = {
    "china",
    "mainland china",
    "greater china",
    "apac",
    "asia pacific",
    "remote",
    "中国",
    "全国",
    "亚太",
    "大中华",
}
EXPLICIT_NON_TARGET_MARKERS = {
    "beijing",
    "shenzhen",
    "hangzhou",
    "guangzhou",
    "chengdu",
    "nanjing",
    "suzhou",
    "hong kong",
    "singapore",
    "北京",
    "深圳",
    "杭州",
    "广州",
    "成都",
    "南京",
    "苏州",
    "香港",
    "新加坡",
}


def classify_official_location(location: str) -> LocationCategory:
    normalized = " ".join((location or "").lower().split())
    if any(marker in normalized for marker in SHANGHAI_MARKERS):
        return LocationCategory.CONFIRMED_SHANGHAI
    if not normalized or normalized == "unknown":
        return LocationCategory.UNCLASSIFIED
    if any(marker in normalized for marker in EXPLICIT_NON_TARGET_MARKERS):
        return LocationCategory.EXCLUDED
    if any(marker in normalized for marker in BROAD_MARKERS):
        return LocationCategory.UNCLASSIFIED
    return LocationCategory.UNCLASSIFIED
