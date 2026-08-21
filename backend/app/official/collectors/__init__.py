"""Official company career collectors."""

from app.official.collectors.amazon import AmazonOfficialCollector
from app.official.collectors.google import GoogleOfficialCollector
from app.official.collectors.microsoft import MicrosoftOfficialCollector

__all__ = [
    "AmazonOfficialCollector",
    "GoogleOfficialCollector",
    "MicrosoftOfficialCollector",
]
