"""
OpenSubtitles provider for Riven.
"""

import base64
import time
import zlib
from xmlrpc.client import ServerProxy
from typing import Optional, Any

from babelfish import Language, Error as BabelfishError
from loguru import logger

from .base import SubtitleProvider


def _normalize_language_to_alpha3(language: str) -> str:
    """
    Convert language code to ISO 639-3 (3-letter code) for OpenSubtitles API.

    Uses babelfish library to handle all language code conversions, supporting:
    - ISO 639-1 (2-letter codes like 'en', 'es')
    - ISO 639-2 (3-letter codes like 'eng', 'spa')
    - ISO 639-2/B (bibliographic codes like 'fre', 'ger')
    - ISO 639-3 (terminological codes like 'fra', 'deu')

    Args:
        language: Language code in various formats

    Returns:
        ISO 639-3 language code (e.g., 'eng', 'spa', 'fra')
    """
    try:
        language_str = str(language).strip().lower()

        if not language_str:
            logger.warning("Empty language code provided, defaulting to 'eng'")
            return "eng"

        # Try different parsing strategies
        lang_obj = None

        # Strategy 1: Try as ISO 639-3 (3-letter terminological code)
        if len(language_str) == 3:
            try:
                lang_obj = Language(language_str)
            except (BabelfishError, ValueError):
                # Strategy 2: Try as ISO 639-2/B (bibliographic code)
                try:
                    lang_obj = Language.fromcode(language_str, "alpha3b")
                except (BabelfishError, ValueError, KeyError):
                    pass

        # Strategy 3: Try as ISO 639-1 (2-letter code)
        if lang_obj is None and len(language_str) == 2:
            try:
                lang_obj = Language.fromcode(language_str, "alpha2")
            except (BabelfishError, ValueError, KeyError):
                pass

        # Strategy 4: Try parsing as locale string (e.g., 'en-US', 'pt_BR')
        if lang_obj is None and ("-" in language_str or "_" in language_str):
            try:
                # Extract just the language part before the separator
                lang_part = language_str.split("-")[0].split("_")[0]
                if len(lang_part) == 2:
                    lang_obj = Language.fromcode(lang_part, "alpha2")
                elif len(lang_part) == 3:
                    lang_obj = Language(lang_part)
            except (BabelfishError, ValueError, KeyError):
                pass

        if lang_obj:
            return lang_obj.alpha3

        # Fallback to English
        logger.warning(f"Could not parse language '{language}', defaulting to 'eng'")
        return "eng"

    except Exception as e:
        logger.error(
            f"Error normalizing language '{language}': {e}, defaulting to 'eng'"
        )
        return "eng"


class OpenSubtitlesProvider(SubtitleProvider):
    """
    OpenSubtitles XML-RPC provider implementation.

    Uses anonymous authentication and searches only by moviehash.
    This ensures reliable subtitle matching without requiring user credentials.
    """

    def __init__(self):
        self.server_url = "https://api.opensubtitles.org/xml-rpc"
        self.user_agent = "VLSub 0.11.1"
        self.token = None
        self.login_time = None
        self.server = ServerProxy(self.server_url, allow_none=True)

    @property
    def name(self) -> str:
        return "opensubtitles"

    def _check_response(self, response: dict) -> dict:
        """Check OpenSubtitles API response and handle errors."""
        if not isinstance(response, dict) or "status" not in response:
            raise Exception("Invalid response format")

        status = response["status"]
        status_code = int(status[:3])

        if status_code == 401:
            raise Exception("Unauthorized - Invalid credentials")
        elif status_code == 406:
            raise Exception("No session - Please login again")
        elif status_code == 407:
            raise Exception("Download limit reached")
        elif status_code == 503:
            raise Exception("Service unavailable")
        elif status_code != 200:
            raise Exception(f"OpenSubtitles error: {status}")

        return response

    def initialize(self):
        """Initialize the provider session with anonymous authentication."""
        logger.debug(f"Logging in anonymously with user agent: {self.user_agent}")
        # Anonymous login: empty username and password
        response = self.server.LogIn("", "", "eng", self.user_agent)
        logger.debug(f'Login response status: {response.get("status")}')
        if "status" not in response:
            raise Exception("No status in login response")
        status = response["status"]
        status_code = int(status[:3])
        if status_code != 200:
            raise Exception(f"Login failed: {status}")
        self.token = str(response["token"])
        self.login_time = time.time()
        logger.debug("Authenticated to OpenSubtitles (anonymous)")

    def _ensure_authenticated(self) -> bool:
        """Ensure we have a valid session token."""
        current_time = time.time()

        # Check if we need to login (no token or token older than 10 minutes)
        if (
            not self.token
            or not self.login_time
            or (current_time - self.login_time) > 600
        ):
            if self.login_time:
                logger.debug("Token expired (>10 minutes), re-authenticating...")
            self.initialize()

        return True

    def search_subtitles(
        self,
        imdb_id: str,
        video_hash: Optional[str] = None,
        file_size: Optional[int] = None,
        filename: Optional[str] = None,
        search_tags: Optional[str] = None,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """
        Search subtitles using multi-strategy approach.

        According to OpenSubtitles API documentation:
        - Priority: moviehash+moviebytesize > tag > imdbid > query
        - When moviehash and moviebytesize are provided, other parameters are ignored
        - When tag is provided with imdbid, it filters results by release group/format
        - Multiple search criteria can be sent in a single request

        Args:
            imdb_id: IMDB ID
            video_hash: OpenSubtitles hash of the video file
            file_size: Size of the video file in bytes
            filename: Original filename (not used - tags are preferred)
            search_tags: Comma-separated tags (release group, format) for OpenSubtitles
            season: Season number (for TV shows)
            episode: Episode number (for TV shows)
            language: Language code (ISO 639-1, ISO 639-2, or ISO 639-3)

        Returns:
            list of subtitle results, prioritized by match type
        """
        try:
            if not self._ensure_authenticated():
                return []

            # Normalize language to ISO 639-3 format for OpenSubtitles API
            opensubtitles_lang = _normalize_language_to_alpha3(language)

            # Build search criteria array (multiple strategies in one request)
            search_criteria = []

            # Strategy 1: moviehash + moviebytesize (perfect match - exact file)
            if video_hash and file_size:
                search_criteria.append(
                    {
                        "sublanguageid": opensubtitles_lang,
                        "moviehash": video_hash,
                        "moviebytesize": str(file_size),
                    }
                )
                logger.trace(
                    f"OpenSubtitles search strategy 1: moviehash={video_hash[:8]}...{video_hash[-8:]}, size={file_size:,} bytes"
                )

            # Strategy 2: imdbid + filename + tag (release-specific match)
            if imdb_id and search_tags:
                imdb_id = imdb_id.lstrip("tt")  # Remove leading 'tt' from IMDB ID
                criteria = {
                    "sublanguageid": opensubtitles_lang,
                    "imdbid": imdb_id,  # Remove leading 'tt' from IMDB ID
                    "tags": search_tags,
                }
                if season is not None:
                    criteria["season"] = str(season)
                if episode is not None:
                    criteria["episode"] = str(episode)
                search_criteria.append(criteria)
                logger.trace(
                    f"OpenSubtitles search strategy 2: imdbid={imdb_id}, tags={search_tags}, season={season}, episode={episode}"
                )

            # strategy 3: filename
            if filename:
                criteria3 = {
                    "sublanguageid": opensubtitles_lang,
                    "query": filename,
                }
                if season is not None:
                    criteria3["season"] = str(season)
                if episode is not None:
                    criteria3["episode"] = str(episode)
                search_criteria.append(criteria3)
                logger.trace(
                    f"OpenSubtitles search strategy 3: filename={filename}, season={season}, episode={episode}"
                )

            if not search_criteria:
                logger.trace("Skipping OpenSubtitles search: no valid search criteria")
                return []

            response = self.server.SearchSubtitles(self.token, search_criteria)
            response = self._check_response(response)

            data = response.get("data") or []
            if not data:
                logger.debug("No subtitles found from OpenSubtitles")
                return []

            # Process results and prioritize by match type
            # MatchedBy can be: moviehash, tag, imdbid, fulltext
            results = []
            norm_hash = str(video_hash).lower() if video_hash else None

            for item in data:
                try:
                    # Get match type from API response
                    matched_by = (item.get("MatchedBy") or "unknown").lower()
                    item_hash = str(item.get("MovieHash") or "0").lower()

                    # Validate hash matches - ensure MovieHash field matches our hash
                    if matched_by == "moviehash":
                        if not norm_hash or item_hash == "0" or item_hash != norm_hash:
                            # Invalid hash match, skip it
                            continue

                    # Determine match type for scoring
                    # Priority: moviehash > tag > imdbid > fulltext
                    is_hash_match = matched_by == "moviehash"
                    is_tag_match = matched_by == "tag"
                    is_imdb_match = matched_by == "imdbid"
                    is_fulltext_match = matched_by == "fulltext"

                    results.append(
                        {
                            "id": item["IDSubtitleFile"],
                            "language": item["SubLanguageID"],
                            "filename": item.get("SubFileName", "subtitle.srt"),
                            "download_count": int(item.get("SubDownloadsCnt", 0)),
                            "rating": float(item.get("SubRating", 0)),
                            "matched_by": matched_by,
                            "movie_hash": item.get("MovieHash"),
                            "movie_name": item.get("MovieName", ""),
                            "provider": self.name,
                            "score": self._calculate_score(
                                item,
                                is_hash_match,
                                is_tag_match,
                                is_imdb_match,
                                is_fulltext_match,
                            ),
                        }
                    )
                except Exception as e:
                    logger.warning(f"Error processing subtitle result: {e}")
                    continue

            # Sort by score (hash > tag > imdb > fulltext)
            results.sort(key=lambda x: x.get("score", 0), reverse=True)

            # Log match type distribution
            hash_count = sum(1 for r in results if r["matched_by"] == "moviehash")
            tag_count = sum(1 for r in results if r["matched_by"] == "tag")
            imdb_count = sum(1 for r in results if r["matched_by"] == "imdbid")
            fulltext_count = sum(1 for r in results if r["matched_by"] == "fulltext")
            logger.debug(
                f"Found {len(results)} subtitles from OpenSubtitles (hash:{hash_count}, tag:{tag_count}, imdb:{imdb_count}, fulltext:{fulltext_count})"
            )

            return results

        except Exception as e:
            error_msg = str(e).lower()
            if "syntax error" in error_msg or "expat" in error_msg:
                logger.warning(
                    "OpenSubtitles server issue (HTML response) - trying other providers"
                )
            else:
                logger.error(f"OpenSubtitles search error: {e}")
            return []

    def download_subtitle(self, subtitle_info: dict[str, Any]) -> Optional[str]:
        """Download subtitle content from OpenSubtitles."""
        try:
            if not self._ensure_authenticated():
                return None

            subtitle_id = subtitle_info.get("id")
            if not subtitle_id:
                return None

            logger.debug(
                f"Downloading subtitle: {subtitle_info.get('filename', 'unknown')}"
            )

            response = self.server.DownloadSubtitles(self.token, [str(subtitle_id)])
            response = self._check_response(response)

            if not response.get("data") or not response["data"]:
                return None

            # Decode subtitle content (base64 + zlib compression)
            subtitle_data = response["data"][0]["data"]
            decoded_data = base64.b64decode(subtitle_data)
            decompressed_data = zlib.decompress(decoded_data, 47)

            content = self._decode_subtitle_content(decompressed_data)

            if content and "opensubtitles vip" in content.lower():
                logger.debug("Received VIP-only content")

            logger.debug(f"Downloaded subtitle successfully")
            return content

        except Exception as e:
            logger.error(f"OpenSubtitles download error: {e}")
            return None

    def _calculate_score(
        self,
        subtitle_item: dict[str, Any],
        is_hash_match: bool,
        is_tag_match: bool = False,
        is_imdb_match: bool = False,
        is_fulltext_match: bool = False,
    ) -> int:
        """
        Score results with priority: hash > tag > imdb > fulltext.

        According to OpenSubtitles API, MatchedBy can be:
        - moviehash: Perfect file match (highest priority)
        - tag: Release-specific match (high priority)
        - imdbid: Movie-level match (medium priority)
        - fulltext: Query-based match (lowest priority)

        Args:
            subtitle_item: Subtitle result from OpenSubtitles
            is_hash_match: True if matched by moviehash
            is_tag_match: True if matched by tag
            is_imdb_match: True if matched by imdbid
            is_fulltext_match: True if matched by fulltext

        Returns:
            Score (higher is better)
        """
        score = 0

        # Priority 1: Hash matches (perfect file match)
        if is_hash_match:
            score += 10000
        # Priority 2: Tag matches (release-specific match)
        elif is_tag_match:
            score += 5000
        # Priority 3: IMDB matches (movie-level match)
        elif is_imdb_match:
            score += 2500
        # Priority 4: Fulltext matches (query-based, least accurate)
        elif is_fulltext_match:
            score += 1000

        # Tie-breakers: popularity and rating
        score += (
            int(subtitle_item.get("SubDownloadsCnt", 0)) // 100
        )  # Downloads (max ~100 points)
        score += int(
            float(subtitle_item.get("SubRating", 0)) * 10
        )  # Rating (max 100 points)

        return score

    def _decode_subtitle_content(self, content_bytes: bytes) -> Optional[str]:
        """Decode subtitle content with multiple encoding fallbacks."""
        if not content_bytes:
            return None

        encodings = ["utf-8", "utf-8-sig", "iso-8859-1", "windows-1252", "cp1252"]

        for encoding in encodings:
            try:
                decoded = content_bytes.decode(encoding)
                if len(decoded.strip()) > 0:
                    return decoded
            except (UnicodeDecodeError, UnicodeError):
                continue

        # Last resort with error replacement
        try:
            return content_bytes.decode("utf-8", errors="replace")
        except Exception:
            logger.error("Failed to decode subtitle content")
            return None
