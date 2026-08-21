from fastapi import APIRouter

from app.official.registry import OFFICIAL_SOURCE_REGISTRY

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/official")
def list_official_sources():
    return {
        "total": len(OFFICIAL_SOURCE_REGISTRY),
        "first_wave": len([source for source in OFFICIAL_SOURCE_REGISTRY if source.enabled]),
        "sources": [
            {
                "source_id": source.source_id,
                "company": source.company,
                "category": source.category,
                "career_url": source.career_url,
                "enabled": source.enabled,
                "wave": source.wave,
                "collection_method": source.collection_method,
            }
            for source in OFFICIAL_SOURCE_REGISTRY
        ],
    }
