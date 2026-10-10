from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, List

from app.schemas.job import UnifiedJob


@dataclass
class CollectorMeta:
    source_name: str
    source_type: str
    collection_method: str
    polling_interval_minutes: int
    search_configuration: str = "default-profile"
    parser_name: str = "default-parser"
    normalization_logic: str = "unified-job-normalizer"


class BaseCollector(ABC):
    meta: CollectorMeta

    @abstractmethod
    def fetch_raw(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw: Dict[str, Any]) -> UnifiedJob:
        raise NotImplementedError

    def collect(self) -> List[UnifiedJob]:
        raw_items = self.fetch_raw()
        return [self.normalize(raw) for raw in raw_items]

    @staticmethod
    def build_hash(*values: str) -> str:
        return sha256("||".join(values).encode("utf-8")).hexdigest()

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
