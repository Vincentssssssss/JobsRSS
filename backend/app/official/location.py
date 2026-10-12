import re
from enum import Enum


class LocationCategory(str, Enum):
    CONFIRMED_SHANGHAI = "confirmed_shanghai"
    CONFIRMED_MALAYSIA = "confirmed_malaysia"
    UNCLASSIFIED = "unclassified"
    EXCLUDED = "excluded"


_CATEGORY_COUNTRY = {LocationCategory.CONFIRMED_MALAYSIA: "Malaysia"}


def country_for_category(category: LocationCategory, default: str = "China") -> str:
    return _CATEGORY_COUNTRY.get(category, default)



SHANGHAI_DIRECT_MARKERS = {
    "shanghai",
    "上海",
}
SHANGHAI_DISTRICT_MARKERS = {
    "pudong",
    "浦东",
    "xuhui",
    "徐汇",
    "minhang",
    "闵行",
    "jing'an",
    "静安",
    "huangpu",
    "黄浦",
    "changning",
    "长宁",
    "putuo",
    "普陀",
    "hongkou",
    "虹口",
    "yangpu",
    "杨浦",
    "baoshan",
    "宝山",
    "jinshan",
    "金山",
    "jiading",
    "嘉定",
    "songjiang",
    "松江",
    "qingpu",
    "青浦",
    "fengxian",
    "奉贤",
    "chongming",
    "崇明",
}
MALAYSIA_MARKERS = {
    "malaysia",
    "kuala lumpur",
    "selangor",
    "petaling jaya",
    "cyberjaya",
    "putrajaya",
    "penang",
    "johor",
    "sepang",
    "subang",
    "shah alam",
    "bayan lepas",
    "ipoh",
    "melaka",
    "malacca",
    "kuching",
    "kota kinabalu",
    "sarawak",
    "sabah",
    "马来西亚",
    "吉隆坡",
    "雪兰莪",
    "槟城",
    "新山",
    "柔佛",
}
# ISO codes: Amazon uses "MYS"; Microsoft ends segments with ", MY" or lists a bare "MY".
_MALAYSIA_COUNTRY_CODE = re.compile(r"\bmys\b|(?:^|[/,])\s*my\s*(?:/|$)")
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
    "yunnan",
    "云南",
    "zhoushan",
    "舟山",
    "zhejiang",
    "浙江",
    "united states",
    "usa",
    "japan",
    "日本",
}


def classify_official_location(location: str) -> LocationCategory:
    normalized = " ".join((location or "").lower().split())
    if any(marker in normalized for marker in SHANGHAI_DIRECT_MARKERS):
        return LocationCategory.CONFIRMED_SHANGHAI
    # Checked before the exclusion list so multi-country listings such as
    # "Singapore / Kuala Lumpur" stay eligible.
    if any(marker in normalized for marker in MALAYSIA_MARKERS) or _MALAYSIA_COUNTRY_CODE.search(
        normalized
    ):
        return LocationCategory.CONFIRMED_MALAYSIA
    if not normalized or normalized == "unknown":
        return LocationCategory.UNCLASSIFIED
    if any(marker in normalized for marker in EXPLICIT_NON_TARGET_MARKERS):
        return LocationCategory.EXCLUDED
    if any(marker in normalized for marker in SHANGHAI_DISTRICT_MARKERS):
        return LocationCategory.CONFIRMED_SHANGHAI
    if _is_broad_location_only(normalized):
        return LocationCategory.UNCLASSIFIED
    return LocationCategory.EXCLUDED


def _is_broad_location_only(normalized: str) -> bool:
    chinese_remainder = normalized
    for marker in ("大中华", "中国大陆", "中国", "全国", "亚太", "远程"):
        chinese_remainder = chinese_remainder.replace(marker, "")
    if normalized != chinese_remainder and not re.sub(
        r"[\s/|,，;；:：()（）-]+", "", chinese_remainder
    ):
        return True

    words = set(re.findall(r"[a-z]+", normalized))
    broad_words = {
        "china",
        "mainland",
        "greater",
        "apac",
        "asia",
        "pacific",
        "remote",
    }
    return bool(words) and words.issubset(broad_words)
