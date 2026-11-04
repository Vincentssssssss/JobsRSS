from app.official.collectors.beisen import BeisenOfficialCollector

FOSUN_ROOT = "https://fosunpharma.zhiye.com"


class FosunPharmaOfficialCollector(BeisenOfficialCollector):
    # The portal moved to Beisen's JavaScript front end, so the server-rendered
    # socialxq pages the old parser read now return an empty shell.
    retired_source_url_prefixes = (f"{FOSUN_ROOT}/socialxq",)

    def __init__(self) -> None:
        super().__init__(
            source_id="fosun_pharma",
            company="Fosun Pharma / 复星医药",
            portal_root=FOSUN_ROOT,
        )
