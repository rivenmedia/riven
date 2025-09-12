"""Cache management API endpoints"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from loguru import logger

from program.services.indexers.cache import tmdb_cache, tvdb_cache

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/stats", summary="Get Cache Statistics")
async def get_cache_stats() -> Dict[str, Any]:
    """Get statistics for both TMDB and TVDB caches."""
    try:
        tmdb_stats = tmdb_cache.get_stats()
        tvdb_stats = tvdb_cache.get_stats()
        
        return {
            "tmdb": tmdb_stats,
            "tvdb": tvdb_stats,
            "total": {
                "active_entries": tmdb_stats.get("active_entries", 0) + tvdb_stats.get("active_entries", 0),
                "cache_size_mb": round(tmdb_stats.get("cache_size_mb", 0) + tvdb_stats.get("cache_size_mb", 0), 2)
            }
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cache stats: {str(e)}")


@router.post("/clear-expired", summary="Clear Expired Cache Entries")
async def clear_expired_cache() -> Dict[str, Any]:
    """Clear expired entries from both caches."""
    try:
        tmdb_cleaned = tmdb_cache.clear_expired()
        tvdb_cleaned = tvdb_cache.clear_expired()
        
        return {
            "message": f"Cleared {tmdb_cleaned + tvdb_cleaned} expired cache entries",
            "tmdb_cleaned": tmdb_cleaned,
            "tvdb_cleaned": tvdb_cleaned,
            "total_cleaned": tmdb_cleaned + tvdb_cleaned
        }
    except Exception as e:
        logger.error(f"Failed to clear expired cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear expired cache: {str(e)}")


@router.post("/clear-all", summary="Clear All Cache Entries")
async def clear_all_cache() -> Dict[str, Any]:
    """Clear all entries from both caches."""
    try:
        tmdb_success = tmdb_cache.clear_all()
        tvdb_success = tvdb_cache.clear_all()
        
        if tmdb_success and tvdb_success:
            return {"message": "Successfully cleared all cache entries"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear some cache entries")
            
    except Exception as e:
        logger.error(f"Failed to clear all cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear all cache: {str(e)}")
