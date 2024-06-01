import threading
from datetime import datetime
from typing import Iterator

from cachetools import TTLCache
from utils.logger import logger


class HashCache:
    """A class for caching hashes with additional metadata and a time-to-live (TTL) mechanism."""

    def __init__(self, ttl: int = 420, maxsize: int = 2000):
        """
        Initializes the HashCache with a specified TTL and maximum size.

        Args:
            ttl (int): The time-to-live for each cache entry in seconds.
            maxsize (int): The maximum size of the cache.
        """
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.lock = threading.RLock()

    def __contains__(self, infohash: str) -> bool:
        """Check if a hash is in the cache."""
        with self.lock:
            return infohash in self.cache

    def __iter__(self) -> Iterator[str]:
        """Iterate over the cache."""
        with self.lock:
            for infohash in self.cache:
                yield infohash

    def is_blacklisted(self, infohash: str) -> bool:
        """Check if a hash is blacklisted."""
        with self.lock:
            return self._get_cache_entry(infohash).get("blacklisted", False)

    def is_downloaded(self, infohash: str) -> bool:
        """Check if a hash is marked as downloaded."""
        with self.lock:
            return self._get_cache_entry(infohash).get("downloaded", False)

    def blacklist(self, infohash: str) -> None:
        """Blacklist a hash."""
        if not infohash:
            raise ValueError("Infohash is required")

        with self.lock:
            entry = self._get_cache_entry(infohash)
            entry["blacklisted"] = True
            self.cache[infohash] = entry

    def mark_downloaded(self, infohash: str) -> None:
        """Mark a hash as downloaded."""
        if not self.is_downloaded(infohash):
            with self.lock:
                entry = self._get_cache_entry(infohash)
            entry["downloaded"] = True
            self.cache[infohash] = entry
            logger.log("CACHE", f"Marked hash {infohash} as downloaded")

    def remove(self, infohash: str) -> None:
        """Remove a hash from the blacklist."""
        if not infohash:
            raise ValueError("Infohash is required")

        with self.lock:
            if infohash in self.cache:
                del self.cache[infohash]
        logger.log("CACHE", f"Removed hash {infohash}")

    def clear_cache(self) -> None:
        """Clear the cache."""
        with self.lock:
            self.cache.clear()

    def _get_cache_entry(self, infohash: str) -> dict:
        """Helper function to get a cache entry or create a new one if it doesn't exist."""
        return self.cache.get(infohash, {"blacklisted": False, "downloaded": False, "added_at": datetime.now()})
