import threading
from datetime import datetime
from typing import Iterator

from cachetools import TTLCache
from utils.logger import logger


class HashCache:
    """A class for caching hashes with additional metadata and a time-to-live (TTL) mechanism."""

    def __init__(self, ttl: int = 420, maxsize: int = 2000) -> None:
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

    def blacklist(self, infohash: str) -> None:
        """Blacklist a hash."""
        if not infohash:
            raise ValueError("Infohash is required")

        with self.lock:
            if infohash in self.cache:
                if "blacklisted" not in self.cache[infohash]:
                    self.cache[infohash]["blacklisted"] = True
            else:
                self.cache[infohash] = {
                    "blacklisted": True,
                    "added_at": datetime.now()
                }

    def remove(self, infohash: str) -> None:
        """Remove a hash from the blacklist."""
        if not infohash:
            raise ValueError("Infohash is required")

        with self.lock:
            if infohash in self.cache:
                del self.cache[infohash]
        logger.log("CACHE", f"Removed hash {infohash}")

    def is_blacklisted(self, infohash: str) -> bool:
        """Check if a hash is blacklisted."""
        with self.lock:
            return infohash in self.cache and self.cache[infohash].get("status")

    def is_downloaded(self, infohash: str) -> bool:
        """Check if a hash is marked as downloaded."""
        with self.lock:
            is_downloaded = infohash in self.cache and self.cache[infohash].get("status")
        if is_downloaded:
            logger.log("CACHE", f"Infohash {infohash} is downloaded on Real-Debrid")
        return is_downloaded

    def mark_as_downloaded(self, infohash: str) -> None:
        with self.lock:
            if infohash in self.cache:
                self.cache[infohash]["downloaded"] = True
            else:
                self.cache[infohash] = {
                    "downloaded": True,
                    "added_at": datetime.now()
                }
        logger.log("CACHE", f"Marked hash {infohash} as downloaded")

    def clear_cache(self) -> None:
        """Clear the cache."""
        with self.lock:
            self.cache.clear()

