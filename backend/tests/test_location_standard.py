import pytest

from app.normalization.location_standard import (
    CITIES,
    SearchTerm,
    canonical_city,
    canonical_country,
    location_label,
    parse_search,
    standardize_location,
)
from app.official.location import LocationCategory, classify_official_location


# Formats taken from a live run of every official collector (2026-11-04).
@pytest.mark.parametrize(
    ("location", "cities", "country"),
    [
        ("Shanghai, CHN", ("Shanghai",), "China"),  # Amazon
        ("Shanghai, Shanghai, CN", ("Shanghai",), "China"),  # Microsoft
        ("Shanghai, Shanghai, China's Mainland", ("Shanghai",), "China"),  # Roche
        ("China\\Shanghai-Shanghai", ("Shanghai",), "China"),  # Huawei
        ("上海市-上海市,广东省-佛山", ("Shanghai", "Foshan"), "China"),  # Midea
        ("闵行区, 上海, 上海市, 中国", ("Shanghai",), "China"),  # KPMG / Anta
        ("上海市·浦东新区", ("Shanghai",), "China"),  # WuXi AppTec
        ("北京 / 杭州", ("Hangzhou", "Beijing"), "China"),  # Alibaba: target city first
        ("北京市、上海市、深圳市", ("Shanghai", "Beijing", "Shenzhen"), "China"),  # Deloitte
        ("钱塘区, 浙江, 中国", ("Hangzhou",), "China"),  # district only
        ("滨湖区, 江苏, 中国", ("Wuxi",), "China"),
        ("义乌市, 浙江, 中国", ("Jinhua",), "China"),
        ("Hong Kong, Hong Kong SAR, HKG", ("Hong Kong",), "Hong Kong"),
        ("HKG", ("Hong Kong",), "Hong Kong"),
        ("Hong Kong Island,HK", ("Hong Kong",), "Hong Kong"),
        ("香港, 香港, 中国", ("Hong Kong",), "Hong Kong"),
        ("中国香港", ("Hong Kong",), "Hong Kong"),
        ("Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur, MYS", ("Kuala Lumpur",), "Malaysia"),
        ("Gelugor, Penang, MY", ("Penang",), "Malaysia"),
        ("Petaling Jaya, Selangor, Malaysia", ("Petaling Jaya",), "Malaysia"),
        ("SGP", ("Singapore",), "Singapore"),
        ("SG", ("Singapore",), "Singapore"),
        ("Jakarta, JABODETABEK, IDN", ("Jakarta",), "Indonesia"),
        ("Daerah Khusus Ibukota Jakarta", ("Jakarta",), "Indonesia"),
        ("กทม, Bangkok, TH", ("Bangkok",), "Thailand"),
        ("Ho Chi Minh City, VNM", ("Ho Chi Minh City",), "Vietnam"),
        ("Pasay City, National Capital Region, PHL", ("Pasay",), "Philippines"),
        ("Vietnam", (), "Vietnam"),
        ("MY", (), "Malaysia"),
        ("海外国家-越南", (), "Vietnam"),
        ("中国", (), "China"),
        ("江苏省", (), "China"),
        ("Unknown", (), None),
    ],
)
def test_source_formats_map_to_one_standard_city_and_country(location, cities, country):
    standard = standardize_location(location)
    assert standard.cities == cities
    assert standard.country == country


def test_multi_location_role_puts_the_category_city_first():
    standard = standardize_location("Singapore / Kuala Lumpur")
    assert standard.cities == ("Kuala Lumpur", "Singapore")
    assert standard.country == "Malaysia"
    assert classify_official_location("Singapore / Kuala Lumpur") == LocationCategory.CONFIRMED_MALAYSIA


def test_district_names_shared_by_two_cities_follow_the_named_city():
    assert standardize_location("Putuo District, Zhoushan, Zhejiang, China").cities == ("Zhoushan",)
    assert standardize_location("Pudong / Beijing").cities == ("Shanghai", "Beijing")


def test_chongqing_jiulongpo_is_not_kowloon():
    assert standardize_location("九龙坡区, 重庆市, 中国").cities == ("Chongqing",)
    assert classify_official_location("九龙坡区, 重庆市, 中国") != LocationCategory.CONFIRMED_HONG_KONG


def test_us_state_codes_are_not_read_as_countries():
    assert standardize_location("San Francisco, CA").country == "United States"
    assert standardize_location("Boise, ID, US").country == "United States"


def test_fallback_country_is_canonicalized():
    assert standardize_location("Remote", "CN").country == "China"
    assert standardize_location("Remote", "APAC").country is None
    assert standardize_location("Remote", "Unknown").country is None


@pytest.mark.parametrize(
    ("country", "category"),
    [
        ("Hong Kong", LocationCategory.CONFIRMED_HONG_KONG),
        ("Malaysia", LocationCategory.CONFIRMED_MALAYSIA),
        ("Singapore", LocationCategory.CONFIRMED_SOUTHEAST_ASIA),
        ("Indonesia", LocationCategory.CONFIRMED_SOUTHEAST_ASIA),
        ("Thailand", LocationCategory.CONFIRMED_SOUTHEAST_ASIA),
        ("Vietnam", LocationCategory.CONFIRMED_SOUTHEAST_ASIA),
        ("Philippines", LocationCategory.CONFIRMED_SOUTHEAST_ASIA),
    ],
)
def test_every_target_city_is_accepted_by_the_location_classifier(country, category):
    for city in (city for city in CITIES if city.country == country):
        assert classify_official_location(city.name) == category, city.name


JIANGSU_ZHEJIANG = {
    "Hangzhou", "Suzhou", "Kunshan", "Taicang", "Nanjing", "Wuxi", "Changzhou", "Nantong",
    "Xuzhou", "Yangzhou", "Zhenjiang", "Yancheng", "Huai'an", "Lianyungang", "Suqian",
    "Taizhou (Jiangsu)", "Ningbo", "Jiaxing", "Shaoxing", "Huzhou", "Wenzhou", "Jinhua",
    "Taizhou (Zhejiang)", "Quzhou", "Lishui", "Zhoushan",
}


def test_jiangsu_and_zhejiang_cities_are_accepted_by_the_location_classifier():
    for city in CITIES:
        if city.name in JIANGSU_ZHEJIANG:
            assert classify_official_location(city.name_zh) == LocationCategory.CONFIRMED_YANGTZE_DELTA, city.name
    assert classify_official_location("上海") == LocationCategory.CONFIRMED_SHANGHAI


def test_aliases_resolve_to_canonical_names():
    assert canonical_city("上海") == "Shanghai"
    assert canonical_city("SH") == "Shanghai"
    assert canonical_city("hcmc") == "Ho Chi Minh City"
    assert canonical_city("bangalore") == "Bengaluru"
    assert canonical_city("Atlantis") is None
    assert canonical_country("中国大陆") == "China"
    assert canonical_country("HKG") == "Hong Kong"
    assert canonical_country("马来西亚") == "Malaysia"


def test_location_label_shows_chinese_and_english_names():
    assert location_label(["Shanghai"], "China") == "上海 Shanghai · 中国 China"
    assert location_label(["Singapore"], "Singapore") == "新加坡 Singapore"
    assert location_label([], "Vietnam") == "越南 Vietnam"
    assert location_label(["Shanghai", "Beijing", "Shenzhen", "Guangzhou"], "China") == (
        "上海 Shanghai / 北京 Beijing / 深圳 Shenzhen / +1 · 中国 China"
    )
    assert location_label([], None) == ""


def test_search_splits_place_names_from_keywords():
    assert parse_search("security 杭州") == [
        SearchTerm("杭州", city="Hangzhou"),
        SearchTerm("security"),
    ]
    assert parse_search("上海安全") == [SearchTerm("上海", city="Shanghai"), SearchTerm("安全")]
    assert parse_search("Hong Kong architect") == [
        SearchTerm("hong kong", city="Hong Kong"),
        SearchTerm("architect"),
    ]
    assert parse_search("KL") == [SearchTerm("kl", city="Kuala Lumpur", place_only=True)]
    assert parse_search("马来西亚") == [SearchTerm("马来西亚", country="Malaysia")]
    assert parse_search("cloud security") == [SearchTerm("cloud"), SearchTerm("security")]


def test_search_does_not_widen_a_district_or_province():
    assert parse_search("浦东") == [SearchTerm("浦东")]
    assert parse_search("浙江") == [SearchTerm("浙江")]
