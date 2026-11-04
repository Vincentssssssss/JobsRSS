"""One canonical city and country for each job, whatever language or format the
source uses ("上海-浦东新区", "Shanghai, Shanghai, China", "Shanghai, CHN" are all
Shanghai, China), so the dashboard can filter and search by place."""

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

from app.official.location import LocationCategory, classify_official_location


@dataclass(frozen=True)
class Country:
    name: str
    name_zh: str
    aliases: Tuple[str, ...] = ()
    # Matched as whole words, e.g. Amazon's "Shanghai, CHN".
    iso3: Tuple[str, ...] = ()
    # Matched only as a whole comma/slash segment, e.g. Microsoft's "Kuala Lumpur, MY".
    iso2: Tuple[str, ...] = ()
    # Place a listing that names no city ("江苏省") in the country, but searching
    # for a province should not return the whole country.
    provinces: Tuple[str, ...] = ()


@dataclass(frozen=True)
class City:
    name: str
    name_zh: str
    country: str
    aliases: Tuple[str, ...] = ()
    # Districts and suburbs place a job in the city, but searching for one
    # should not return the whole city.
    districts: Tuple[str, ...] = ()
    # Short forms accepted in the search box and as a whole segment of a location.
    codes: Tuple[str, ...] = ()


COUNTRIES: Tuple[Country, ...] = (
    Country("China", "中国", ("mainland china", "china mainland", "china's mainland", "chinese mainland",
                             "prc", "中国大陆", "中华人民共和国", "大陆"), ("chn",), ("cn",), (
        "jiangsu", "江苏", "zhejiang", "浙江", "guangdong", "广东", "sichuan", "四川", "hubei", "湖北",
        "anhui", "安徽", "shandong", "山东", "fujian", "福建", "henan", "河南", "hunan", "湖南",
        "liaoning", "辽宁", "shaanxi", "陕西", "hebei", "河北", "yunnan", "云南",
    )),
    Country("Hong Kong", "中国香港", ("hong kong sar", "hksar", "hong kong s.a.r.", "香港特别行政区",
                                  "香港"), ("hkg",), ("hk",)),
    Country("Macau", "中国澳门", ("macao", "macao sar", "澳门")),
    Country("Taiwan", "中国台湾", ("台湾",), ("twn",), ("tw",)),
    Country("Malaysia", "马来西亚", (), ("mys",), ("my",)),
    Country("Singapore", "新加坡", (), ("sgp",), ("sg",)),
    Country("Indonesia", "印度尼西亚", ("印尼",), ("idn",), ("id",)),
    Country("Thailand", "泰国", (), ("tha",), ("th",)),
    Country("Vietnam", "越南", ("viet nam",), ("vnm",), ("vn",)),
    Country("Philippines", "菲律宾", (), ("phl",), ("ph",)),
    Country("Japan", "日本", (), ("jpn",), ("jp",)),
    Country("South Korea", "韩国", ("korea", "republic of korea"), ("kor",), ("kr",)),
    Country("India", "印度", (), ("ind",)),
    Country("Australia", "澳大利亚", (), ("aus",), ("au",)),
    Country("United States", "美国", ("usa", "united states of america", "u.s.", "u.s.a."), ("usa",), ("us",)),
    Country("United Kingdom", "英国", ("uk", "england", "great britain"), ("gbr",), ("gb",)),
    Country("Germany", "德国", (), ("deu",)),
    Country("France", "法国", (), ("fra",), ("fr",)),
    Country("Ireland", "爱尔兰", (), ("irl",), ("ie",)),
    Country("Switzerland", "瑞士", (), (), ("ch",)),
    Country("Canada", "加拿大"),
)
# US state codes (CA, DE, IN, MO) collide with these countries' ISO-2 codes, so
# Canada, Germany, India and Macau are only recognised by name or ISO-3.

# A match on the country alone ("中国香港", "SGP") still places the job in the city.
_CITY_STATES = {"Hong Kong", "Singapore", "Macau"}

CITIES: Tuple[City, ...] = (
    # Shanghai
    City("Shanghai", "上海", "China", ("shanghai shi", "上海市"), (
        "pudong", "浦东", "xuhui", "徐汇", "minhang", "闵行", "jing'an", "jingan", "静安",
        "huangpu", "黄浦", "changning", "长宁", "putuo", "普陀", "hongkou", "虹口", "yangpu", "杨浦",
        "baoshan", "宝山", "jinshan", "金山", "jiading", "嘉定", "songjiang", "松江", "qingpu", "青浦",
        "fengxian", "奉贤", "chongming", "崇明", "lingang", "临港", "zhangjiang", "张江",
    ), ("sh",)),
    # Jiangsu and Zhejiang
    City("Hangzhou", "杭州", "China", ("杭州市",), (
        "yuhang", "余杭", "binjiang", "滨江", "xihu district", "西湖区", "xiaoshan", "萧山", "钱塘区",
        "上城区", "拱墅区", "富阳", "临平区", "临安")),
    City("Suzhou", "苏州", "China", ("苏州市", "suzhou industrial park"), (
        "苏州工业园", "wujiang", "吴江", "吴中区", "姑苏区", "相城区", "虎丘区", "常熟", "张家港")),
    City("Kunshan", "昆山", "China"),
    City("Taicang", "太仓", "China"),
    City("Nanjing", "南京", "China", ("南京市",), ("秦淮区", "江宁", "建邺区", "玄武区", "栖霞区", "浦口区",
                                             "雨花台区")),
    City("Wuxi", "无锡", "China", (), ("滨湖区", "新吴区", "梁溪区", "江阴")),
    City("Changzhou", "常州", "China", (), ("武进",)),
    City("Nantong", "南通", "China"),
    City("Xuzhou", "徐州", "China"),
    City("Yangzhou", "扬州", "China"),
    City("Zhenjiang", "镇江", "China"),
    City("Yancheng", "盐城", "China", (), ("亭湖区",)),
    City("Huai'an", "淮安", "China", ("huaian",)),
    City("Lianyungang", "连云港", "China"),
    City("Suqian", "宿迁", "China"),
    City("Taizhou (Jiangsu)", "泰州", "China"),
    City("Ningbo", "宁波", "China", (), ("鄞州区", "海曙区", "北仑区", "慈溪", "余姚")),
    City("Jiaxing", "嘉兴", "China", (), ("嘉善", "海宁", "平湖")),
    City("Shaoxing", "绍兴", "China", (), ("上虞区", "柯桥区", "越城区", "诸暨")),
    City("Huzhou", "湖州", "China", (), ("德清", "长兴")),
    City("Wenzhou", "温州", "China", (), ("瑞安", "乐清")),
    City("Jinhua", "金华", "China", (), ("义乌", "yiwu", "东阳", "永康")),
    City("Taizhou (Zhejiang)", "台州", "China"),
    City("Quzhou", "衢州", "China"),
    City("Lishui", "丽水", "China"),
    City("Zhoushan", "舟山", "China"),
    # Elsewhere in mainland China
    City("Beijing", "北京", "China", ("peking", "北京市"), ("haidian", "海淀", "chaoyang", "朝阳", "亦庄")),
    City("Shenzhen", "深圳", "China", ("深圳市",), ("nanshan", "南山")),
    City("Guangzhou", "广州", "China", ("canton",)),
    City("Chengdu", "成都", "China", (), ("武侯区", "锦江区", "青羊区", "成华区")),
    City("Chongqing", "重庆", "China", (), ("九龙坡",)),
    City("Wuhan", "武汉", "China"),
    City("Xi'an", "西安", "China", ("xian", "xi an")),
    City("Tianjin", "天津", "China"),
    City("Hefei", "合肥", "China"),
    City("Xiamen", "厦门", "China"),
    City("Fuzhou", "福州", "China"),
    City("Dalian", "大连", "China"),
    City("Shenyang", "沈阳", "China"),
    City("Qingdao", "青岛", "China"),
    City("Jinan", "济南", "China"),
    City("Zhengzhou", "郑州", "China"),
    City("Changsha", "长沙", "China"),
    City("Zhuhai", "珠海", "China"),
    City("Dongguan", "东莞", "China"),
    City("Foshan", "佛山", "China"),
    City("Kunming", "昆明", "China"),
    # Hong Kong, Macau, Taiwan
    City("Hong Kong", "香港", "Hong Kong", ("hong kong sar", "hongkong", "hong kong island", "香港特别行政区"),
         ("kowloon", "九龙城", "九龙湾", "quarry bay", "鲗鱼涌", "tsim sha tsui", "尖沙咀", "wan chai", "湾仔",
          "causeway bay", "铜锣湾", "kwun tong", "观塘", "sha tin", "沙田", "港岛"), ("hk", "hkg")),
    City("Macau", "澳门", "Macau", ("macao",)),
    City("Taipei", "台北", "Taiwan", ("臺北",)),
    City("Hsinchu", "新竹", "Taiwan"),
    # Malaysia
    City("Kuala Lumpur", "吉隆坡", "Malaysia", ("wilayah persekutuan kuala lumpur",), (), ("kl",)),
    City("Petaling Jaya", "八打灵再也", "Malaysia"),
    City("Cyberjaya", "赛城", "Malaysia"),
    City("Putrajaya", "布城", "Malaysia"),
    City("Penang", "槟城", "Malaysia", ("pulau pinang", "george town", "georgetown", "槟榔屿"),
         ("bayan lepas",)),
    City("Johor Bahru", "新山", "Malaysia", ("johor", "johor baharu", "柔佛")),
    City("Shah Alam", "莎阿南", "Malaysia"),
    City("Subang Jaya", "梳邦再也", "Malaysia", ("subang",)),
    City("Sepang", "雪邦", "Malaysia"),
    City("Ipoh", "怡保", "Malaysia"),
    City("Melaka", "马六甲", "Malaysia", ("malacca",)),
    City("Kuching", "古晋", "Malaysia"),
    City("Kota Kinabalu", "亚庇", "Malaysia"),
    # Southeast Asia
    City("Singapore", "新加坡", "Singapore", (), (), ("sg", "sgp")),
    City("Jakarta", "雅加达", "Indonesia", ("dki jakarta", "jabodetabek", "south jakarta", "jakarta selatan",
                                         "central jakarta", "jakarta pusat")),
    City("Surabaya", "泗水", "Indonesia"),
    City("Bandung", "万隆", "Indonesia"),
    City("Batam", "巴淡", "Indonesia"),
    City("Bangkok", "曼谷", "Thailand", ("krung thep",)),
    City("Hanoi", "河内", "Vietnam", ("ha noi",)),
    City("Ho Chi Minh City", "胡志明市", "Vietnam", ("ho chi minh", "hồ chí minh", "saigon", "胡志明"),
         (), ("hcmc",)),
    City("Da Nang", "岘港", "Vietnam", ("danang",)),
    City("Hai Phong", "海防", "Vietnam", ("haiphong",)),
    City("Manila", "马尼拉", "Philippines", ("metro manila",)),
    City("Makati", "马卡蒂", "Philippines"),
    City("Taguig", "达义", "Philippines", ("bonifacio global city",), (), ("bgc",)),
    City("Quezon City", "奎松城", "Philippines"),
    City("Pasig", "帕西格", "Philippines"),
    City("Pasay", "帕赛", "Philippines", ("pasay city",)),
    City("Cebu", "宿务", "Philippines", ("cebu city",)),
    # Further afield, so cross-posted roles show a real place instead of "other".
    City("Tokyo", "东京", "Japan"),
    City("Osaka", "大阪", "Japan"),
    City("Seoul", "首尔", "South Korea"),
    City("Bengaluru", "班加罗尔", "India", ("bangalore",)),
    City("Hyderabad", "海得拉巴", "India"),
    City("Mumbai", "孟买", "India"),
    City("Pune", "浦那", "India"),
    City("Sydney", "悉尼", "Australia"),
    City("Melbourne", "墨尔本", "Australia"),
    City("Seattle", "西雅图", "United States"),
    City("Redmond", "雷德蒙德", "United States"),
    City("San Francisco", "旧金山", "United States"),
    City("New York", "纽约", "United States", ("new york city", "nyc")),
    City("London", "伦敦", "United Kingdom"),
    City("Dublin", "都柏林", "Ireland"),
    City("Zurich", "苏黎世", "Switzerland", ("zürich",)),
    City("Basel", "巴塞尔", "Switzerland"),
)

_CITY_BY_NAME = {city.name: city for city in CITIES}
_COUNTRY_BY_NAME = {country.name: country for country in COUNTRIES}
_CJK = re.compile(r"[\u3400-\u9fff]")
_SEGMENT_SPLIT = re.compile(r"[,，/|;；·•()（）\-–]+")
# Separators between the places of a multi-location role. Commas are left out:
# most sources use them inside one place ("Kuala Lumpur, Federal Territory, MY").
_LISTING_SPLIT = re.compile(r"[/、;；|\\]+")
# The order the official location classifier gives multi-city listings, so the
# primary city agrees with the job's location category.
_CATEGORY_RANK = {
    LocationCategory.CONFIRMED_SHANGHAI: 0,
    LocationCategory.CONFIRMED_YANGTZE_DELTA: 1,
    LocationCategory.CONFIRMED_HONG_KONG: 2,
    LocationCategory.CONFIRMED_MALAYSIA: 3,
    LocationCategory.CONFIRMED_SOUTHEAST_ASIA: 4,
}


def _clean(value: str) -> str:
    return " ".join((value or "").lower().split())


def _alias_pattern(alias: str) -> re.Pattern:
    escaped = re.escape(alias.lower())
    if _CJK.search(alias):
        return re.compile(escaped)
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


@dataclass(frozen=True)
class _Marker:
    pattern: re.Pattern
    length: int
    city: Optional[str] = None
    country: Optional[str] = None
    searchable: bool = True


def _build_markers() -> List[_Marker]:
    markers: List[_Marker] = []

    def add(alias: str, *, city=None, country=None, searchable=True):
        markers.append(_Marker(_alias_pattern(alias), len(alias), city, country, searchable))

    for city in CITIES:
        for alias in (city.name, city.name_zh, *city.aliases):
            add(alias, city=city.name)
        for alias in city.districts:
            add(alias, city=city.name, searchable=False)
    for country in COUNTRIES:
        for alias in (country.name, country.name_zh, *country.aliases):
            add(alias, country=country.name)
        for alias in (*country.iso3, *country.provinces):
            add(alias, country=country.name, searchable=False)
    # Longest first, so "hong kong sar" wins over "hong kong" and "香港特别行政区" over "香港".
    markers.sort(key=lambda marker: -marker.length)
    return markers


_MARKERS = _build_markers()
_CITY_CODES = {code: city.name for city in CITIES for code in city.codes}
_COUNTRY_ISO2 = {code: country.name for country in COUNTRIES for code in country.iso2}


def _segments(text: str) -> List[str]:
    return [segment.strip() for segment in _SEGMENT_SPLIT.split(text) if segment.strip()]


def _find_places(text: str, *, search_only: bool) -> List[Tuple[int, int, _Marker]]:
    """Non-overlapping place markers in ``text``, earliest first."""
    taken: List[Tuple[int, int]] = []
    found: List[Tuple[int, int, _Marker]] = []
    for marker in _MARKERS:
        if search_only and not marker.searchable:
            continue
        for match in marker.pattern.finditer(text):
            start, end = match.span()
            if any(start < other_end and other_start < end for other_start, other_end in taken):
                continue
            taken.append((start, end))
            found.append((start, end, marker))
    found.sort(key=lambda item: item[0])
    return found


def _city_rank(name: str) -> int:
    return _CATEGORY_RANK.get(classify_official_location(name), len(_CATEGORY_RANK))


def order_cities(names: Iterable[str]) -> List[str]:
    """Target-region cities first (in classifier precedence), then the rest, keeping
    their listed order within each rank."""
    unique = list(dict.fromkeys(name for name in names if name in _CITY_BY_NAME))
    return sorted(unique, key=lambda name: (_city_rank(name), unique.index(name)))


@dataclass(frozen=True)
class StandardLocation:
    cities: Tuple[str, ...] = ()
    country: Optional[str] = None
    countries: Tuple[str, ...] = field(default=())

    @property
    def city(self) -> Optional[str]:
        return self.cities[0] if self.cities else None


def standardize_location(location: str, fallback_country: Optional[str] = None) -> StandardLocation:
    text = _clean(location)
    cities: List[str] = []
    countries: List[str] = []
    for listing in _LISTING_SPLIT.split(text):
        named: List[str] = []
        from_districts: List[str] = []
        for _, _, marker in _find_places(listing, search_only=False):
            if marker.city:
                (named if marker.searchable else from_districts).append(marker.city)
            elif marker.country:
                countries.append(marker.country)
        segments = _segments(listing)
        named.extend(_CITY_CODES[segment] for segment in segments if segment in _CITY_CODES)
        # Only a trailing code is a country: in "Boise, ID, US" the ID is a US state.
        if segments and segments[-1] in _COUNTRY_ISO2:
            countries.append(_COUNTRY_ISO2[segments[-1]])
        # District names repeat across cities ("Putuo District, Zhoushan" is not
        # Shanghai's Putuo), so a city named in the same listing wins.
        cities.extend(named or from_districts)
    countries = list(dict.fromkeys(countries))
    cities.extend(country for country in countries if country in _CITY_STATES)
    ordered = order_cities(cities)
    if ordered:
        country = _CITY_BY_NAME[ordered[0]].country
    elif countries:
        country = countries[0]
    else:
        country = canonical_country(fallback_country)
    all_countries = list(dict.fromkeys([_CITY_BY_NAME[name].country for name in ordered] + countries))
    if country and country not in all_countries:
        all_countries.insert(0, country)
    return StandardLocation(tuple(ordered), country, tuple(all_countries))


def canonical_country(value: Optional[str]) -> Optional[str]:
    """A country name, Chinese name, alias or ISO code as the canonical name."""
    text = _clean(value or "")
    if not text:
        return None
    for country in COUNTRIES:
        names = {country.name.lower(), country.name_zh, *country.aliases, *country.iso3, *country.iso2}
        if text in names:
            return country.name
    return None


def canonical_city(value: Optional[str]) -> Optional[str]:
    """A city name in any listed spelling, or its short code, as the canonical name."""
    text = _clean(value or "")
    if not text:
        return None
    if text in _CITY_CODES:
        return _CITY_CODES[text]
    for city in CITIES:
        if text in {city.name.lower(), city.name_zh, *city.aliases, *city.districts}:
            return city.name
    return None


def city_country(name: str) -> Optional[str]:
    city = _CITY_BY_NAME.get(name)
    return city.country if city else None


def cities_in_country(name: str) -> List[str]:
    return [city.name for city in CITIES if city.country == name]


def city_label(name: str) -> str:
    city = _CITY_BY_NAME.get(name)
    return f"{city.name_zh} {city.name}" if city else name


def country_label(name: str) -> str:
    country = _COUNTRY_BY_NAME.get(name)
    return f"{country.name_zh} {country.name}" if country else name


def location_label(cities: Sequence[str], country: Optional[str]) -> str:
    """e.g. "上海 Shanghai · 中国 China"; a city-state shows its name once."""
    parts = [city_label(name) for name in cities[:3]]
    if len(cities) > 3:
        parts.append(f"+{len(cities) - 3}")
    label = " / ".join(parts)
    if country and not (len(cities) == 1 and cities[0] == country):
        label = f"{label} · {country_label(country)}" if label else country_label(country)
    return label


def encode_cities(cities: Sequence[str]) -> Optional[str]:
    """Stored as "|Shanghai|Beijing|" so one city can be matched with LIKE '%|Name|%'."""
    return f"|{'|'.join(cities)}|" if cities else None


def decode_cities(value: Optional[str]) -> List[str]:
    return [name for name in (value or "").split("|") if name]


@dataclass(frozen=True)
class SearchTerm:
    text: str
    city: Optional[str] = None
    country: Optional[str] = None
    # Short codes ("SH", "KL") would match unrelated words as plain text.
    place_only: bool = False


def parse_search(query: str) -> List[SearchTerm]:
    """Split a search into terms that must all match. A place name in any listed
    language or spelling becomes a location term, so "security 杭州" finds Hangzhou
    roles whose source writes "Hangzhou, Zhejiang, CHN"."""
    text = _clean(query)
    terms: List[SearchTerm] = []
    remainder = text
    for start, end, marker in reversed(_find_places(text, search_only=True)):
        terms.append(SearchTerm(text[start:end], city=marker.city, country=marker.country))
        remainder = remainder[:start] + " " + remainder[end:]
    terms.reverse()
    for word in re.split(r"[\s,，/|;；]+", remainder):
        if not word:
            continue
        city = _CITY_CODES.get(word)
        terms.append(SearchTerm(word, city=city, place_only=True) if city else SearchTerm(word))
    return terms
