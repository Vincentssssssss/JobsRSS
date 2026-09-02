from typing import Callable, Dict

from app.collectors.base import BaseCollector
from app.official.collectors.alibaba import AlibabaOfficialCollector
from app.official.collectors.amazon import AmazonOfficialCollector
from app.official.collectors.beisen import (
    ChiaTaiTianqingOfficialCollector,
    InnoventOfficialCollector,
    WuXiAppTecOfficialCollector,
)
from app.official.collectors.feishu_jobs import (
    ByteDanceOfficialCollector,
    XiaomiOfficialCollector,
)
from app.official.collectors.fosun import FosunPharmaOfficialCollector
from app.official.collectors.google import GoogleOfficialCollector
from app.official.collectors.hotjob import (
    SimcereOfficialCollector,
    YunnanBaiyaoOfficialCollector,
)
from app.official.collectors.huawei import HuaweiOfficialCollector
from app.official.collectors.midea import MideaOfficialCollector
from app.official.collectors.microsoft import MicrosoftOfficialCollector
from app.official.collectors.moka import (
    AntaOfficialCollector,
    GskOfficialCollector,
    WuXiBiologicsOfficialCollector,
)
from app.official.collectors.roche import RocheOfficialCollector
from app.official.collectors.tencent import TencentOfficialCollector

OFFICIAL_COLLECTOR_FACTORIES: Dict[str, Callable[[], BaseCollector]] = {
    "amazon_aws": AmazonOfficialCollector,
    "google": GoogleOfficialCollector,
    "microsoft": MicrosoftOfficialCollector,
    "alibaba": AlibabaOfficialCollector,
    "tencent": TencentOfficialCollector,
    "huawei": HuaweiOfficialCollector,
    "xiaomi": XiaomiOfficialCollector,
    "bytedance": ByteDanceOfficialCollector,
    "midea": MideaOfficialCollector,
    "anta": AntaOfficialCollector,
    "wuxi_apptec": WuXiAppTecOfficialCollector,
    "wuxi_biologics": WuXiBiologicsOfficialCollector,
    "fosun_pharma": FosunPharmaOfficialCollector,
    "ct_tianqing": ChiaTaiTianqingOfficialCollector,
    "yunnan_baiyao": YunnanBaiyaoOfficialCollector,
    "innovent": InnoventOfficialCollector,
    "simcere": SimcereOfficialCollector,
    "gsk": GskOfficialCollector,
    "roche": RocheOfficialCollector,
}


def create_official_collector(source_id: str) -> BaseCollector:
    try:
        factory = OFFICIAL_COLLECTOR_FACTORIES[source_id]
    except KeyError as exc:
        raise ValueError(f"No operational collector for {source_id}") from exc
    return factory()
