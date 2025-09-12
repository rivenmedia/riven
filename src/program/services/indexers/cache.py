"""Indexer cache module for storing API responses"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

from loguru import logger

from program.utils import data_dir_path


class IndexerCache:
    """SQLite-based cache for indexer API responses"""
    
    def __init__(self, cache_name: str = "indexer_cache"):
        """Initialize the cache with a specific name."""
        self.cache_name = cache_name
        self.cache_dir = Path(data_dir_path) / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.db_path = self.cache_dir / f"{cache_name}.db"
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize the SQLite database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT UNIQUE NOT NULL,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ttl_seconds INTEGER,
                    expires_at TIMESTAMP
                )
            """)
            
            # Create index for faster lookups
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_key ON cache_entries(cache_key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expires_at ON cache_entries(expires_at)")
            
            conn.commit()
    
    def _generate_cache_key(self, api_name: str, endpoint: str, params: Dict[str, Any]) -> str:
        """Generate a unique cache key for the API request."""
        # Sort params for consistent key generation
        sorted_params = sorted(params.items())
        param_str = json.dumps(sorted_params, sort_keys=True)
        # Use a more stable hash method that's consistent across sessions
        import hashlib
        hash_obj = hashlib.md5(param_str.encode('utf-8'))
        hash_str = hash_obj.hexdigest()[:16]  # Use first 16 chars for shorter keys
        return f"{api_name}:{endpoint}:{hash_str}"
    
    def _is_expired(self, expires_at: Optional[str]) -> bool:
        """Check if a cache entry has expired."""
        if not expires_at:
            return False
        
        try:
            expires = datetime.fromisoformat(expires_at)
            return datetime.now() > expires
        except (ValueError, TypeError):
            return True
    
    def _calculate_ttl(self, item_type: str, year: Optional[int], status: Optional[str] = None) -> Optional[int]:
        """
        Calculate TTL (time-to-live) in seconds for a cache entry based on item type, year, and status.

        API Responsibility:
        - TMDB: Movies only (statuses: "Released", "Post Production", "In Production", "Planned", "Rumored", "Canceled")
        - TVDB: Shows/Seasons/Episodes only (statuses: "Ended", "Canceled", "Continuing", "Returning Series")

        Rules:
        - Movies (TMDB): Cache indefinitely unless in production (7 days)
        - Shows/Seasons/Episodes (TVDB): Cache indefinitely if ended/canceled or old, otherwise 5/3 days
        - Aliases: Cache indefinitely (stable metadata)
        - Default: 1 day
        """
        current_year = datetime.now().year

        # Explicit case: indefinite cache
        if item_type == "indefinite":
            return None  # Indefinite

        # Movies (TMDB only): cache indefinitely unless in production
        if item_type == "movie":
            # TMDB movie statuses: "Released", "Post Production", "In Production", "Planned", "Rumored", "Canceled"
            if status and status.lower() in ["post production", "in production", "planned", "rumored"]:
                return 7 * 24 * 60 * 60  # 7 days
            return None  # Indefinite

        # Shows/Seasons/Episodes (TVDB only): cache indefinitely if ended/canceled or old
        elif item_type in ["show", "season", "episode"]:
            # TVDB statuses: "Ended", "Canceled", "Continuing", "Returning Series"
            if status and status.lower() in ["ended", "cancelled", "canceled"]:
                return None  # Indefinite
            if year and year <= current_year - 3:
                return None  # Indefinite

            # Different TTL based on item type
            if item_type == "show":
                return 5 * 24 * 60 * 60  # 5 days for ongoing shows
            else:  # season/episode
                return 3 * 24 * 60 * 60  # 3 days for ongoing seasons/episodes

        # Default: 1 day
        return 24 * 60 * 60
    
    def get(self, api_name: str, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached data for an API request."""
        cache_key = self._generate_cache_key(api_name, endpoint, params)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT data, expires_at FROM cache_entries WHERE cache_key = ?",
                    (cache_key,)
                )
                row = cursor.fetchone()
                
                if row:
                    # Check if expired
                    if self._is_expired(row["expires_at"]):
                        # Remove expired entry
                        conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))
                        conn.commit()
                        logger.debug(f"Cache expired for {cache_key}")
                        return None
                    
                    # Return cached data, converting back to SimpleNamespace for compatibility
                    # Note: row["data"] is JSON text; pass directly to the deserializer.
                    converted_data = _from_json_for_cache(row["data"])
                    logger.debug(f"Cache hit for {cache_key}")
                    return converted_data
                
                logger.debug(f"Cache miss for {cache_key}")
                return None
                
        except Exception as e:
            logger.error(f"Error reading from cache: {e}")
            return None
    
    def set(self, api_name: str, endpoint: str, params: Dict[str, Any], 
            data: Dict[str, Any], item_type: str = "unknown", 
            year: Optional[int] = None, status: Optional[str] = None) -> bool:
        """Store data in cache with appropriate TTL."""
        cache_key = self._generate_cache_key(api_name, endpoint, params)
        ttl_seconds = self._calculate_ttl(item_type, year, status)
        
        try:
            expires_at = None
            if ttl_seconds:
                expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO cache_entries 
                    (cache_key, data, ttl_seconds, expires_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    cache_key,
                    _to_json_for_cache(data),
                    ttl_seconds,
                    expires_at.isoformat() if expires_at else None
                ))
                conn.commit()
            
            if ttl_seconds:
                logger.debug(f"Cached {cache_key} with TTL: {ttl_seconds}s")
            else:
                logger.debug(f"Cached {cache_key} indefinitely")
            return True
            
        except Exception as e:
            logger.error(f"Error writing to cache: {e}")
            return False
    
    def clear_expired(self) -> int:
        """Remove expired cache entries and return count of removed entries."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM cache_entries 
                    WHERE expires_at IS NOT NULL AND expires_at < ?
                """, (datetime.now().isoformat(),))
                
                removed_count = cursor.rowcount
                conn.commit()
                
                if removed_count > 0:
                    logger.info(f"Cleared {removed_count} expired cache entries")
                
                return removed_count
                
        except Exception as e:
            logger.error(f"Error clearing expired cache: {e}")
            return 0
    
    def clear_all(self) -> bool:
        """Clear all cache entries."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM cache_entries")
                conn.commit()
            
            logger.info("Cleared all cache entries")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing all cache: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Total entries
                total_cursor = conn.execute("SELECT COUNT(*) as count FROM cache_entries")
                total_count = total_cursor.fetchone()["count"]
                
                # Expired entries
                expired_cursor = conn.execute("""
                    SELECT COUNT(*) as count FROM cache_entries 
                    WHERE expires_at IS NOT NULL AND expires_at < ?
                """, (datetime.now().isoformat(),))
                expired_count = expired_cursor.fetchone()["count"]
                
                # Cache size
                size_cursor = conn.execute("SELECT SUM(LENGTH(data)) as size FROM cache_entries")
                cache_size = size_cursor.fetchone()["size"] or 0
                
                return {
                    "total_entries": total_count,
                    "expired_entries": expired_count,
                    "active_entries": total_count - expired_count,
                    "cache_size_bytes": cache_size,
                    "cache_size_mb": round(cache_size / (1024 * 1024), 2)
                }
                
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}


def _to_json_for_cache(obj: Any) -> str:
    """
    Serialize a tree that may contain `SimpleNamespace` objects into compact JSON text.
    Designed for data that is already JSON-shaped (dict/list/str/int/float/bool/None),
    with SimpleNamespace nodes sprinkled in.

    Returns
    -------
    str
        JSON text suitable for storing in SQLite TEXT columns.
    """
    def _ns_default(o: Any) -> Any:
        if isinstance(o, SimpleNamespace):
            # `vars(o)` is faster than `o.__dict__`
            return vars(o)
        # If something non-JSON sneaks in, fail fast.
        raise TypeError(f"Unsupported type for JSON serialization: {type(o).__name__}")

    # separators produce smaller payloads; ensure_ascii=False preserves UTF-8
    return json.dumps(obj, default=_ns_default, ensure_ascii=False, separators=(",", ":"))


def _from_json_for_cache(s: str) -> Any:
    """
    Deserialize JSON text from SQLite back into a tree of `SimpleNamespace`.
    Dicts become namespaces; lists remain lists; scalars are preserved.

    Returns
    -------
    Any
        Typically a `SimpleNamespace`, list, or scalar.
    """
    def _hook(d: dict) -> Any:
        # TMDB/TVDB keys are identifier-friendly; if one isn't, let it remain a dict.
        try:
            return SimpleNamespace(**d)
        except TypeError:
            return d

    return json.loads(s, object_hook=_hook)


# Global cache instances
tmdb_cache = IndexerCache("tmdb_cache")
tvdb_cache = IndexerCache("tvdb_cache")
