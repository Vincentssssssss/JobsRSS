"""Official company career collectors."""

from app.official.collectors.alibaba import AlibabaOfficialCollector
from app.official.collectors.amazon import AmazonOfficialCollector
from app.official.collectors.beisen import (
    ChiaTaiTianqingOfficialCollector,
    WuXiAppTecOfficialCollector,
)
from app.official.collectors.feishu_jobs import (
    ByteDanceOfficialCollector,
    XiaomiOfficialCollector,
)
from app.official.collectors.google import GoogleOfficialCollector
from app.official.collectors.fosun import FosunPharmaOfficialCollector
from app.official.collectors.hotjob import YunnanBaiyaoOfficialCollector
from app.official.collectors.huawei import HuaweiOfficialCollector
from app.official.collectors.microsoft import MicrosoftOfficialCollector
from app.official.collectors.moka import (
    GskOfficialCollector,
    WuXiBiologicsOfficialCollector,
)
from app.official.collectors.roche import RocheOfficialCollector
from app.official.collectors.tencent import TencentOfficialCollector

__all__ = [
    "AmazonOfficialCollector",
    "AlibabaOfficialCollector",
    "ByteDanceOfficialCollector",
    "ChiaTaiTianqingOfficialCollector",
    "FosunPharmaOfficialCollector",
    "GoogleOfficialCollector",
    "GskOfficialCollector",
    "HuaweiOfficialCollector",
    "MicrosoftOfficialCollector",
    "RocheOfficialCollector",
    "TencentOfficialCollector",
    "WuXiAppTecOfficialCollector",
    "WuXiBiologicsOfficialCollector",
    "XiaomiOfficialCollector",
    "YunnanBaiyaoOfficialCollector",
]
