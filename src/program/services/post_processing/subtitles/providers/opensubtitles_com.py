"""
OpenSubtitles.com REST API provider for Riven.

This provider uses the modern OpenSubtitles.com REST API (v1) which provides:
- JWT-based authentication with automatic token refresh
- Better rate limits for authenticated users (10 free vs 200+ VIP downloads/day)
- Superior search by IMDB ID, TMDB ID, and file hash
"""

import time
from http import HTTPStatus
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from pydantic import BaseModel, Field, ValidationError, field_validator

from program.settings.models import OpenSubtitlesComConfig
from program.utils.request import SmartSession

from .base import SubtitleItem, SubtitleProvider

# Whitelist of allowed domains for subtitle download URLs (SSRF prevention)
ALLOWED_DOWNLOAD_DOMAINS = {
    "dl.opensubtitles.com",
    "www.opensubtitles.com",
    "vip.opensubtitles.com",
}


class OpenSubtitlesLoginResponse(BaseModel):
    """Validated login response from OpenSubtitles API."""

    token: str

    @field_validator("token", mode="before")
    @classmethod
    def validate_token_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Token cannot be empty")
        return v.strip()


class OpenSubtitlesSearchResult(BaseModel):
    """Single subtitle search result from OpenSubtitles.com API."""

    id: str = Field(alias="id")
    attributes: dict[str, Any]

    model_config = {"populate_by_name": True}

    @property
    def subtitle_id(self) -> str:
        """Get the file ID for downloading."""
        files = self.attributes.get("files", [])
        if files:
            return str(files[0].get("file_id", self.id))
        return self.id

    @property
    def language(self) -> str:
        """Get the subtitle language code."""
        return self.attributes.get("language", "")

    @property
    def filename(self) -> str:
        """Get the subtitle filename."""
        files = self.attributes.get("files", [])
        if files:
            return files[0].get("file_name", "")
        return ""

    @property
    def download_count(self) -> int:
        """Get the download count."""
        return int(self.attributes.get("download_count", 0))

    @property
    def rating(self) -> float:
        """Get the subtitle rating."""
        return float(self.attributes.get("ratings", 0.0))

    @property
    def moviehash_match(self) -> bool:
        """Check if this result matched by movie hash."""
        return bool(self.attributes.get("moviehash_match", False))


class OpenSubtitlesComProvider(SubtitleProvider):
    """
    OpenSubtitles.com REST API provider with automatic authentication.

    Uses the modern REST API at api.opensubtitles.com/api/v1 which provides:
    - JWT-based authentication with 10-minute token refresh
    - Multi-strategy search: hash > IMDB ID > filename
    - Rate limit handling with Retry-After header support
    """

    API_BASE = "https://api.opensubtitles.com/api/v1"
    TOKEN_EXPIRY_SECONDS = 540  # 9 minutes (with 1-minute safety buffer)

    def __init__(self, config: OpenSubtitlesComConfig) -> None:
        """Initialize provider with configuration."""
        self.config = config
        self.token: str | None = None
        self.token_time: float = 0.0

        # SmartSession provides: rate limiting, circuit breaker, retries
        # Rate: 2 req/sec for authenticated users (API allows higher)
        self.session = SmartSession(
            rate_limits={"api.opensubtitles.com": {"rate": 2, "capacity": 10}}
        )

        logger.debug("OpenSubtitles.com provider initialized")

    def close(self) -> None:
        """Clean up HTTP session resources."""
        if self.session:
            try:
                self.session.close()
                logger.debug("OpenSubtitles.com session closed")
            except Exception as e:
                logger.warning(f"Error closing OpenSubtitles.com session: {e}")

    @property
    def name(self) -> str:
        """Provider identifier."""
        return "opensubtitles_com"

    def _headers(self, authenticated: bool = True) -> dict[str, str]:
        """Build headers for API requests."""
        headers = {
            "Api-Key": self.config.api_key,
            "User-Agent": self.config.user_agent,
            "Content-Type": "application/json",
        }
        if authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _ensure_authenticated(self) -> bool:
        """
        Ensure valid authentication token exists.

        Note: No explicit Lock needed - Python's GIL provides sufficient
        thread safety for this pattern. Worst case: two threads both
        call _login() simultaneously, both succeed (harmless).
        """
        if self.token and (time.time() - self.token_time) < self.TOKEN_EXPIRY_SECONDS:
            logger.trace("OpenSubtitles.com token still valid")
            return True

        logger.debug("OpenSubtitles.com token expired or missing, authenticating...")
        return self._login()

    def _login(self) -> bool:
        """Authenticate with OpenSubtitles API."""
        try:
            logger.debug("Attempting OpenSubtitles.com login")

            response = self.session.post(
                f"{self.API_BASE}/login",
                json={
                    "username": self.config.username,
                    "password": self.config.password,
                },
                headers=self._headers(authenticated=False),
            )

            # Handle specific HTTP errors
            if response.status_code == HTTPStatus.UNAUTHORIZED:
                logger.warning("OpenSubtitles.com: Invalid credentials")
                return False
            elif response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
                logger.warning("OpenSubtitles.com: Rate limited on login")
                return False
            elif response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
                logger.warning(
                    f"OpenSubtitles.com server error: {response.status_code}"
                )
                return False
            elif not response.ok:
                logger.warning(
                    f"OpenSubtitles.com login failed: {response.status_code}"
                )
                return False

            # Validate response schema
            try:
                data = OpenSubtitlesLoginResponse.model_validate(response.json())
            except ValidationError as e:
                logger.error(f"OpenSubtitles.com: Invalid response schema: {e}")
                return False

            self.token = data.token
            self.token_time = time.time()

            logger.debug("OpenSubtitles.com authenticated successfully")
            return True

        except Exception as e:
            logger.warning(f"OpenSubtitles.com authentication error: {e}")
            return False

    def search_subtitles(
        self,
        imdb_id: str,
        video_hash: str | None = None,
        file_size: int | None = None,
        filename: str | None = None,
        search_tags: str | None = None,
        season: int | None = None,
        episode: int | None = None,
        language: str = "en",
    ) -> list[SubtitleItem]:
        """
        Search for subtitles using multi-strategy approach.

        Strategy priority: hash (best) > IMDB ID > filename (fallback)
        Returns empty list on failure (never raises).
        """
        if not self._ensure_authenticated():
            logger.error("OpenSubtitles.com authentication failed")
            return []

        # Build search strategies in priority order
        for strategy in self._build_search_strategies(
            video_hash, file_size, imdb_id, filename, season, episode, language
        ):
            logger.trace(f"Trying search strategy: {strategy['name']} with params={strategy['params']}")
            results = self._search(strategy["params"])
            if results:
                return self._score_results(results, strategy["name"])

        logger.debug(f"No subtitles found for language={language}")
        return []

    def _build_search_strategies(
        self,
        video_hash: str | None,
        file_size: int | None,
        imdb_id: str | None,
        filename: str | None,
        season: int | None,
        episode: int | None,
        lang_code: str,
    ) -> list[dict[str, Any]]:
        """Build list of search parameter dicts in priority order."""
        strategies: list[dict[str, Any]] = []

        # Strategy 1: Hash (most accurate)
        if video_hash:
            strategies.append(
                {
                    "name": "hash",
                    "params": {
                        "moviehash": video_hash,
                        "languages": lang_code,
                    },
                }
            )

        # Strategy 2: IMDB ID with season/episode
        if imdb_id:
            # Strip 'tt' prefix if present (use slice, not lstrip which removes all 't' chars)
            imdb_num = imdb_id[2:] if imdb_id.startswith("tt") else imdb_id
            params: dict[str, Any] = {
                "imdb_id": imdb_num,
                "languages": lang_code,
            }
            if season is not None:
                params["season_number"] = season
            if episode is not None:
                params["episode_number"] = episode
            strategies.append({"name": "imdb", "params": params})

        # Strategy 3: Filename fallback
        if filename:
            params = {"query": filename, "languages": lang_code}
            if season is not None:
                params["season_number"] = season
            if episode is not None:
                params["episode_number"] = episode
            strategies.append({"name": "filename", "params": params})

        # Add user-configured query params to all strategies
        if self.config.query_params:
            for strategy in strategies:
                strategy["params"].update(self.config.query_params)

        return strategies

    def _search(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute single search request with error handling."""
        try:
            response = self.session.get(
                f"{self.API_BASE}/subtitles",
                params=params,
                headers=self._headers(),
            )

            # Handle 401 with single retry
            if response.status_code == HTTPStatus.UNAUTHORIZED:
                logger.debug("Token expired during search, re-authenticating")
                self.token = None
                if self._ensure_authenticated():
                    response = self.session.get(
                        f"{self.API_BASE}/subtitles",
                        params=params,
                        headers=self._headers(),
                    )

            # Handle rate limiting
            if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
                retry_after = response.headers.get("Retry-After", "60")
                logger.debug(f"Rate limited, retry after {retry_after}s")
                return []

            # Handle server errors
            if response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
                logger.warning(
                    f"OpenSubtitles.com server error: {response.status_code}"
                )
                return []

            if response.status_code == HTTPStatus.OK:
                return response.json().get("data", [])

            return []

        except Exception as e:
            logger.error(f"Search request failed: {e}")
            return []

    def _score_results(
        self, results: list[dict[str, Any]], match_type: str
    ) -> list[SubtitleItem]:
        """
        Convert and score search results.

        Score weights prioritize match accuracy:
        - hash (10000): File hash match is most reliable
        - imdb (5000): IMDB ID match is good but less precise
        - filename (1000): Text search is least reliable
        Additional points from popularity (downloads/100) and rating (rating*10).
        """
        scored: list[SubtitleItem] = []

        # Score weights by match type (higher = more reliable match)
        match_scores = {"hash": 10000, "imdb": 5000, "filename": 1000}
        base_score = match_scores.get(match_type, 0)

        for item in results:
            try:
                result = OpenSubtitlesSearchResult.model_validate(item)

                # Calculate score: match_type + popularity + rating
                score = (
                    base_score + (result.download_count // 100) + int(result.rating * 10)
                )

                # Bonus for hash match
                if result.moviehash_match:
                    score += 5000

                scored.append(
                    SubtitleItem(
                        id=result.subtitle_id,
                        language=result.language,
                        filename=result.filename,
                        download_count=result.download_count,
                        rating=result.rating,
                        matched_by=match_type,
                        movie_hash=None,
                        movie_name=None,
                        provider=self.name,
                        score=score,
                    )
                )
            except ValidationError as e:
                logger.trace(f"Skipping invalid result: {e}")
                continue

        # Sort by score descending
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored

    def download_subtitle(self, subtitle_info: SubtitleItem) -> str | None:
        """
        Download subtitle content via REST API.

        Returns subtitle content as string, or None on failure.
        Never raises exceptions to caller.
        """
        if not self._ensure_authenticated():
            return None

        try:
            logger.debug(f"Downloading subtitle: {subtitle_info.filename}")

            # Step 1: Get download link
            response = self.session.post(
                f"{self.API_BASE}/download",
                json={"file_id": int(subtitle_info.id)},
                headers=self._headers(),
            )

            if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
                remaining = response.json().get("remaining", 0)
                logger.warning(f"Download limit reached. Remaining: {remaining}")
                return None

            if response.status_code != HTTPStatus.OK:
                logger.error(f"Download request failed: {response.status_code}")
                return None

            download_data = response.json()
            download_link = download_data.get("link")

            if not download_link:
                logger.error("No download link in response")
                return None

            # Validate download URL to prevent SSRF attacks
            parsed_url = urlparse(download_link)
            if not parsed_url.hostname:
                logger.error("Download link has no hostname")
                return None

            hostname_lower = parsed_url.hostname.lower()
            if hostname_lower not in ALLOWED_DOWNLOAD_DOMAINS:
                logger.error(
                    f"Download link from unauthorized domain: {parsed_url.hostname}"
                )
                return None

            if parsed_url.scheme != "https":
                logger.error(f"Download link uses non-HTTPS scheme: {parsed_url.scheme}")
                return None

            # Step 2: Fetch actual subtitle file
            file_response = self.session.get(
                download_link,
                headers=self._headers(authenticated=False),
            )

            if file_response.status_code == HTTPStatus.OK:
                content = self._decode_content(file_response.content)
                logger.debug(f"Downloaded subtitle: {len(content)} bytes")
                return content

            logger.error(f"File download failed: {file_response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

    def _decode_content(self, content: bytes) -> str:
        """Decode subtitle content as UTF-8."""
        return content.decode("utf-8")
