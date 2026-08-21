"""Official company career collectors."""

from app.official.collectors.amazon import AmazonOfficialCollector
from app.official.collectors.feishu_jobs import (
    ByteDanceOfficialCollector,
    XiaomiOfficialCollector,
)
from app.official.collectors.google import GoogleOfficialCollector
from app.official.collectors.huawei import HuaweiOfficialCollector
from app.official.collectors.microsoft import MicrosoftOfficialCollector
from app.official.collectors.roche import RocheOfficialCollector
from app.official.collectors.tencent import TencentOfficialCollector

__all__ = [
    "AmazonOfficialCollector",
    "ByteDanceOfficialCollector",
    "GoogleOfficialCollector",
    "HuaweiOfficialCollector",
    "MicrosoftOfficialCollector",
    "RocheOfficialCollector",
    "TencentOfficialCollector",
    "XiaomiOfficialCollector",
]
