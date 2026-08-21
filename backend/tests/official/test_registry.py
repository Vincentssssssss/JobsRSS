from app.official.collectors.catalog import OFFICIAL_COLLECTOR_FACTORIES
from app.official.registry import FIRST_WAVE_SOURCE_IDS, OFFICIAL_SOURCE_REGISTRY


def test_registry_contains_38_unique_company_sources():
    source_ids = [source.source_id for source in OFFICIAL_SOURCE_REGISTRY]

    assert len(source_ids) == 38
    assert len(set(source_ids)) == 38


def test_first_wave_contains_approved_16_sources():
    assert FIRST_WAVE_SOURCE_IDS == {
        "amazon_aws",
        "google",
        "microsoft",
        "alibaba",
        "tencent",
        "huawei",
        "xiaomi",
        "bytedance",
        "wuxi_apptec",
        "wuxi_biologics",
        "hengrui",
        "fosun_pharma",
        "ct_tianqing",
        "yunnan_baiyao",
        "gsk",
        "roche",
    }

    enabled = {source.source_id for source in OFFICIAL_SOURCE_REGISTRY if source.enabled}
    assert enabled == FIRST_WAVE_SOURCE_IDS


def test_every_source_has_official_identity_and_category():
    for source in OFFICIAL_SOURCE_REGISTRY:
        assert source.company
        assert source.category in {"technology", "pharma", "biotech", "cro_cdmo"}
        assert source.career_url.startswith("https://")


def test_hengrui_is_monitored_but_not_operational_without_job_inventory():
    hengrui = next(
        source for source in OFFICIAL_SOURCE_REGISTRY
        if source.source_id == "hengrui"
    )

    assert hengrui.enabled
    assert not hengrui.operational
    assert hengrui.collection_method == "monitor_only_no_inventory"


def test_every_operational_first_wave_source_has_collector_factory():
    operational = {
        source.source_id
        for source in OFFICIAL_SOURCE_REGISTRY
        if source.enabled and source.operational
    }

    assert set(OFFICIAL_COLLECTOR_FACTORIES) == operational
    assert len(operational) == 15
