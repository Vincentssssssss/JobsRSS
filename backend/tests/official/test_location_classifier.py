from app.official.location import LocationCategory, classify_official_location


def test_explicit_shanghai_is_confirmed():
    assert classify_official_location("Shanghai, China") == LocationCategory.CONFIRMED_SHANGHAI
    assert classify_official_location("上海市浦东新区") == LocationCategory.CONFIRMED_SHANGHAI
    assert (
        classify_official_location("Beijing / Shanghai / Shenzhen")
        == LocationCategory.CONFIRMED_SHANGHAI
    )


def test_broad_markets_enter_unclassified_pool():
    for location in [
        "China",
        "Mainland China",
        "Greater China",
        "APAC",
        "Asia Pacific",
        "Remote",
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
    ]:
        assert classify_official_location(location) == LocationCategory.EXCLUDED
