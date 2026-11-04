import re
from enum import Enum


class LocationCategory(str, Enum):
    CONFIRMED_SHANGHAI = "confirmed_shanghai"
    CONFIRMED_YANGTZE_DELTA = "confirmed_yangtze_delta"
    CONFIRMED_HONG_KONG = "confirmed_hong_kong"
    CONFIRMED_MALAYSIA = "confirmed_malaysia"
    CONFIRMED_SOUTHEAST_ASIA = "confirmed_southeast_asia"
    UNCLASSIFIED = "unclassified"
    EXCLUDED = "excluded"


_CATEGORY_COUNTRY = {
    LocationCategory.CONFIRMED_HONG_KONG: "Hong Kong",
    LocationCategory.CONFIRMED_MALAYSIA: "Malaysia",
}


def country_for_category(
    category: LocationCategory, default: str = "China", location: str = ""
) -> str:
    if category == LocationCategory.CONFIRMED_SOUTHEAST_ASIA:
        return southeast_asia_country(location) or "Southeast Asia"
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
# Jiangsu and Zhejiang outside Shanghai.
YANGTZE_DELTA_MARKERS = {
    "jiangsu",
    "江苏",
    "suzhou",
    "苏州",
    "kunshan",
    "昆山",
    "taicang",
    "太仓",
    "nanjing",
    "南京",
    "wuxi",
    "无锡",
    "changzhou",
    "常州",
    "nantong",
    "南通",
    "zhejiang",
    "浙江",
    "hangzhou",
    "杭州",
    "ningbo",
    "宁波",
    "jiaxing",
    "嘉兴",
    "shaoxing",
    "绍兴",
    "huzhou",
    "湖州",
    "wenzhou",
    "温州",
    "zhoushan",
    "舟山",
    "xuzhou",
    "徐州",
    "yangzhou",
    "扬州",
    "zhenjiang",
    "镇江",
    "yancheng",
    "盐城",
    "huai'an",
    "huaian",
    "淮安",
    "lianyungang",
    "连云港",
    "suqian",
    "宿迁",
    "泰州",
    "jinhua",
    "金华",
    "yiwu",
    "义乌",
    "台州",
    "quzhou",
    "衢州",
    "lishui",
    "丽水",
}
HONG_KONG_MARKERS = {
    "hong kong",
    "hongkong",
    "kowloon",
    "香港",
    "九龙",
}
# Amazon lists the bare ISO-3 code "HKG".
_HONG_KONG_COUNTRY_CODE = re.compile(r"\bhkg\b")
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
# Malaysia keeps its own category; these are the other Southeast Asian markets.
SOUTHEAST_ASIA_MARKERS = {
    "Singapore": ("singapore", "新加坡"),
    "Indonesia": ("indonesia", "jakarta", "jabodetabek", "surabaya", "bandung", "batam",
                  "印度尼西亚", "印尼", "雅加达"),
    "Thailand": ("thailand", "bangkok", "泰国", "曼谷"),
    "Vietnam": ("vietnam", "viet nam", "hanoi", "ha noi", "ho chi minh", "haiphong",
                "hai phong", "da nang", "越南", "河内", "胡志明"),
    "Philippines": ("philippines", "manila", "makati", "taguig", "quezon city", "pasig",
                    "pasay", "cebu", "菲律宾", "马尼拉"),
}
# Amazon lists bare ISO-3 codes ("SGP", "VNM"); Microsoft may end a segment with ISO-2.
_SOUTHEAST_ASIA_COUNTRY_CODES = {
    "Singapore": re.compile(r"\bsgp\b|(?:^|[/,])\s*sg\s*(?:/|$)"),
    "Indonesia": re.compile(r"\bidn\b|(?:^|[/,])\s*id\s*(?:/|$)"),
    "Thailand": re.compile(r"\btha\b|(?:^|[/,])\s*th\s*(?:/|$)"),
    "Vietnam": re.compile(r"\bvnm\b|(?:^|[/,])\s*vn\s*(?:/|$)"),
    "Philippines": re.compile(r"\bphl\b|(?:^|[/,])\s*ph\s*(?:/|$)"),
}
EXPLICIT_NON_TARGET_MARKERS = {
    "beijing",
    "shenzhen",
    "guangzhou",
    "chengdu",
    "北京",
    "深圳",
    "广州",
    "成都",
    "yunnan",
    "云南",
    "united states",
    "usa",
    "japan",
    "日本",
}


def southeast_asia_country(location: str) -> str | None:
    normalized = " ".join((location or "").lower().split())
    for country, markers in SOUTHEAST_ASIA_MARKERS.items():
        if any(marker in normalized for marker in markers):
            return country
    for country, pattern in _SOUTHEAST_ASIA_COUNTRY_CODES.items():
        if pattern.search(normalized):
            return country
    return None


def classify_official_location(location: str) -> LocationCategory:
    normalized = " ".join((location or "").lower().split())
    if any(marker in normalized for marker in SHANGHAI_DIRECT_MARKERS):
        return LocationCategory.CONFIRMED_SHANGHAI
    # Targets are checked before the exclusion list so multi-city listings such
    # as "Beijing / Hangzhou" or "Singapore / Kuala Lumpur" stay eligible.
    if any(marker in normalized for marker in YANGTZE_DELTA_MARKERS):
        return LocationCategory.CONFIRMED_YANGTZE_DELTA
    # Chongqing's 九龙坡 district contains Kowloon's Chinese name.
    hong_kong_text = normalized.replace("九龙坡", "")
    if any(marker in hong_kong_text for marker in HONG_KONG_MARKERS) or _HONG_KONG_COUNTRY_CODE.search(
        hong_kong_text
    ):
        return LocationCategory.CONFIRMED_HONG_KONG
    if any(marker in normalized for marker in MALAYSIA_MARKERS) or _MALAYSIA_COUNTRY_CODE.search(
        normalized
    ):
        return LocationCategory.CONFIRMED_MALAYSIA
    if southeast_asia_country(normalized):
        return LocationCategory.CONFIRMED_SOUTHEAST_ASIA
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
