"""Official company career-source registry and collection utilities."""

from app.official.location import LocationCategory, classify_official_location
from app.official.registry import OFFICIAL_SOURCE_REGISTRY, OfficialSourceSpec

__all__ = [
    "LocationCategory",
    "OFFICIAL_SOURCE_REGISTRY",
    "OfficialSourceSpec",
    "classify_official_location",
]
