from app.official.location import (
    LocationCategory,
    classify_official_location,
    country_for_category,
)


def test_explicit_shanghai_is_confirmed():
    assert classify_official_location("Shanghai, China") == LocationCategory.CONFIRMED_SHANGHAI
    assert classify_official_location("上海市浦东新区") == LocationCategory.CONFIRMED_SHANGHAI
    assert (
        classify_official_location("Beijing / Shanghai / Shenzhen")
        == LocationCategory.CONFIRMED_SHANGHAI
    )
    assert classify_official_location("浦东新区") == LocationCategory.CONFIRMED_SHANGHAI
    assert (
        classify_official_location("Pudong New Area")
        == LocationCategory.CONFIRMED_SHANGHAI
    )
    assert classify_official_location("金山区") == LocationCategory.CONFIRMED_SHANGHAI


def test_broad_markets_enter_unclassified_pool():
    for location in [
        "China",
        "Mainland China",
        "Greater China",
        "APAC",
        "Asia Pacific",
        "Remote",
        "Remote / APAC",
        "China / APAC",
        "中国",
        "全国",
        "",
        "Unknown",
    ]:
        assert classify_official_location(location) == LocationCategory.UNCLASSIFIED


def test_explicit_non_target_city_is_excluded():
    for location in [
        "Beijing, China",
        "Shenzhen",
        "广州",
        "文山壮族苗族自治州",
        "昆明市",
        "Remote - United States",
        "Tokyo, APAC",
        "Baoshan, Yunnan, China",
        "Huangpu District, Guangzhou, China",
        "Yangon, Myanmar",
        "Sydney, AUS",
    ]:
        assert classify_official_location(location) == LocationCategory.EXCLUDED


def test_malaysia_locations_from_each_source_format_are_confirmed():
    for location in [
        "Kuala Lumpur, Malaysia",
        "Petaling Jaya, Selangor, Malaysia",
        "Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur, MYS",
        "Johor Bahru, Johor, MY",
        "Sepang, Selangor, MY",
        "MY",
        "MY / Sepang, Selangor, MY",
        "SG / Kuala Lumpur, Federal Territory of Kuala Lumpur, MY / ID / TH / PH",
        "Jakarta, Indonesia / Kuala Lumpur, Malaysia / Bangkok, Thailand",
        "Johor Bahru",
        "吉隆坡",
    ]:
        assert (
            classify_official_location(location) == LocationCategory.CONFIRMED_MALAYSIA
        ), location


def test_shanghai_wins_over_malaysia_for_multi_country_roles():
    assert (
        classify_official_location("Shanghai, China / Kuala Lumpur, Malaysia")
        == LocationCategory.CONFIRMED_SHANGHAI
    )


def test_country_follows_location_category():
    assert country_for_category(LocationCategory.CONFIRMED_MALAYSIA) == "Malaysia"
    assert country_for_category(LocationCategory.CONFIRMED_SHANGHAI) == "China"
    assert country_for_category(LocationCategory.UNCLASSIFIED) == "China"


def test_southeast_asia_is_confirmed_by_country():
    for location, country in [
        ("Singapore", "Singapore"),
        ("SGP", "Singapore"),
        ("Jakarta, JABODETABEK, IDN", "Indonesia"),
        ("Indonesia, Jakarta, Jakarta", "Indonesia"),
        ("Jakarta, Indonesia", "Indonesia"),
        ("Bangkok, THA", "Thailand"),
        ("Hanoi, VNM", "Vietnam"),
        ("Vietnam, Multiple Locations, Multiple Locations", "Vietnam"),
        ("Taguig City, National Capital Region, PHL", "Philippines"),
        ("Makati City, Metro Manila, PH", "Philippines"),
        ("新加坡", "Singapore"),
    ]:
        category = classify_official_location(location)
        assert category == LocationCategory.CONFIRMED_SOUTHEAST_ASIA, location
        assert country_for_category(category, location=location) == country, location


def test_yangtze_delta_cities_are_confirmed():
    for location in [
        "Hangzhou, Zhejiang, China",
        "杭州市余杭区",
        "China, Jiangsu, Suzhou",
        "Wuxi, China",
        "南京",
        "Ningbo",
        "Putuo District, Zhoushan, Zhejiang, China",
        "Beijing / Hangzhou",
    ]:
        category = classify_official_location(location)
        assert category == LocationCategory.CONFIRMED_YANGTZE_DELTA, location
        assert country_for_category(category) == "China"


def test_hong_kong_is_confirmed():
    for location in [
        "Hong Kong",
        "香港",
        "Hong Kong SAR, Hong Kong Island, Hong Kong",
        "Kowloon, HKG",
        "HKG",
    ]:
        category = classify_official_location(location)
        assert category == LocationCategory.CONFIRMED_HONG_KONG, location
        assert country_for_category(category) == "Hong Kong"


def test_target_precedence_for_multi_city_roles():
    assert (
        classify_official_location("Singapore / Kuala Lumpur, Malaysia")
        == LocationCategory.CONFIRMED_MALAYSIA
    )
    assert (
        classify_official_location("Shanghai, China / Singapore")
        == LocationCategory.CONFIRMED_SHANGHAI
    )
    assert (
        classify_official_location("Shanghai / Hangzhou")
        == LocationCategory.CONFIRMED_SHANGHAI
    )
    assert (
        classify_official_location("Hong Kong / Singapore")
        == LocationCategory.CONFIRMED_HONG_KONG
    )
