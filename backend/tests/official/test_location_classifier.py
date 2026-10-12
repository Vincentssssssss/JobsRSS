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


def test_explicit_non_shanghai_city_is_excluded():
    for location in [
        "Beijing, China",
        "Shenzhen",
        "Hangzhou, Zhejiang, China",
        "香港",
        "Singapore",
        "广州",
        "文山壮族苗族自治州",
        "昆明市",
        "Remote - United States",
        "Tokyo, APAC",
        "Wuxi, China",
        "Baoshan, Yunnan, China",
        "Putuo District, Zhoushan, Zhejiang, China",
        "Huangpu District, Guangzhou, China",
        "Yangon, Myanmar",
        "Jakarta, Indonesia",
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
