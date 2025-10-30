"""Torrent utilities for infohash extraction and manipulation."""

import base64
import re
from typing import Optional

from loguru import logger

# Pattern to match infohashes in magnet links (supports both 40-char hex and 32-char base32)
INFOHASH_PATTERN = re.compile(r"btih:([a-fA-F0-9]{40}|[a-zA-Z0-9]{32})", re.IGNORECASE)

# Pattern to match bare infohashes (40-char hex only)
INFOHASH_HEX_PATTERN = re.compile(r"\b[a-fA-F0-9]{40}\b")

# Pattern to match bare base32 infohashes (32-char)
INFOHASH_BASE32_PATTERN = re.compile(r"\b[a-zA-Z0-9]{32}\b")


def normalize_infohash(infohash: str) -> str:
    """
    Normalize an infohash to 40-character hexadecimal format.

    Converts base32-encoded infohashes (32 chars) to base16 (40 chars).

    Args:
        infohash: The infohash to normalize (32 or 40 characters)

    Returns:
        str: The normalized 40-character hexadecimal infohash (lowercase)
    """
    if len(infohash) == 32:
        # Convert base32 to base16
        try:
            infohash = base64.b16encode(base64.b32decode(infohash.upper())).decode("utf-8")
        except Exception as e:
            logger.debug(f"Failed to convert base32 infohash to base16: {e}")
            return infohash.lower()

    return infohash.lower()


def extract_infohash(text: str) -> Optional[str]:
    """
    Extract infohash from various text formats (magnet links, URLs, or bare hashes).

    Tries to find infohash in the following order:
    1. From magnet URI (btih:...)
    2. From bare hexadecimal hash (40 chars)
    3. From bare base32 hash (32 chars)

    Args:
        text: Text that may contain an infohash

    Returns:
        str | None: The normalized 40-character infohash, or None if not found
    """
    if not text:
        return None

    # First try to extract from magnet URI
    magnet_match = INFOHASH_PATTERN.search(text)
    if magnet_match:
        infohash = magnet_match.group(1)
        return normalize_infohash(infohash)

    # Try to find bare hexadecimal infohash (40 chars)
    hex_match = INFOHASH_HEX_PATTERN.search(text)
    if hex_match:
        return hex_match.group(0).lower()

    # Try to find bare base32 infohash (32 chars)
    base32_match = INFOHASH_BASE32_PATTERN.search(text)
    if base32_match:
        return normalize_infohash(base32_match.group(0))

    return None
