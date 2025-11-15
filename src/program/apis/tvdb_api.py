"""TVDB API client"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from kink import inject
from loguru import logger
from pydantic import BaseModel

from program.utils import data_dir_path
from program.utils.request import SmartSession
from schemas.tvdb import (
    EpisodeExtendedRecord,
    SearchByRemoteIdResult,
    SeasonExtendedRecord,
    SeriesExtendedRecord,
    Translation,
    Updates200Response,
)


class SeriesRelease(SeriesExtendedRecord):
    """TVDB Series Release Status Model"""

    @property
    def release_id(self) -> int:
        """Get release status ID"""

        assert self.status and self.status.id is not None

        return self.status.id

    @property
    def release_status(self) -> str:
        """Get release status name"""

        assert self.status and self.status.name

        return self.status.name

    @property
    def keep_updated(self) -> bool:
        """Get keep updated flag"""

        assert self.status and self.status.keep_updated is not None

        return self.status.keep_updated

    @property
    def last_metadata_fetch(self) -> str:
        """Get last metadata fetch time"""

        from datetime import datetime

        return datetime.now().isoformat()

    @property
    def next_metadata_fetch(self) -> str | None:
        """Get next metadata fetch time"""

        return self.last_aired


class TVDBApiError(Exception):
    """Base exception for TVDB API related errors"""


class TVDBToken(BaseModel):
    """TVDB API token model"""

    token: str
    expires_at: datetime

    def to_dict(self) -> dict[str, str]:
        """Convert token to dictionary for storage"""

        return {
            "token": self.token,
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "TVDBToken":
        """Create token from dictionary"""

        return cls(
            token=data["token"], expires_at=datetime.fromisoformat(data["expires_at"])
        )


@inject
class TVDBApi:
    """TVDB API client"""

    BASE_URL = "https://api4.thetvdb.com/v4"
    TOKEN_FILE = Path(data_dir_path, "tvdb_token.json")

    def __init__(self):
        self.api_key = "6be85335-5c4f-4d8d-b945-d3ed0eb8cdce"
        self.token = None
        self.last_new_release_check: datetime | None = None

        rate_limits = {
            # 25 requests per second
            "api4.thetvdb.com": {
                "rate": 25,
                "capacity": 1000,
            }
        }

        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits=rate_limits,
            retries=2,
            backoff_factor=0.3,
        )

        self.token = self._load_token_from_file()

        if not self.token:
            logger.info("No TVDB token found, attempting to get new token...")

            self.token = self._get_auth_token()

            if not self.token:
                logger.error("Failed to obtain TVDB token, exiting.")

                exit(0)

            logger.info("Successfully obtained new TVDB token")

    def get_series(self, series_id: str) -> SeriesRelease | None:
        """Get TV series details by TVDB ID."""

        try:
            response = self.session.get(
                f"series/{series_id}/extended",
                headers=self._get_headers(),
            )

            if not response.ok:
                logger.error(f"Failed to get series details: {response.status_code}")
                return None

            from schemas.tvdb import GetSeriesArtworks200Response

            validated_response = GetSeriesArtworks200Response.from_dict(response.json())

            assert validated_response

            return SeriesRelease.model_validate(validated_response.data)
        except Exception as e:
            logger.error(f"Error getting series details: {str(e)}")

            return None

    def search_by_imdb_id(self, imdb_id: str) -> list[SearchByRemoteIdResult] | None:
        """Search for a series by IMDB ID."""

        try:
            response = self.session.get(
                f"search/remoteid/{imdb_id}",
                headers=self._get_headers(),
            )

            if not response.ok:
                logger.error(f"Failed to search by IMDB ID: {response.status_code}")
                return None

            from schemas.tvdb import GetSearchResultsByRemoteId200Response

            validated_response = GetSearchResultsByRemoteId200Response.from_dict(
                response.json()
            )

            assert validated_response

            return validated_response.data
        except Exception as e:
            logger.error(f"Error searching by IMDB ID: {str(e)}")
            return None

    def get_season(self, season_id: int) -> SeasonExtendedRecord | None:
        """Get details for a specific season."""

        try:
            response = self.session.get(
                f"seasons/{season_id}/extended",
                headers=self._get_headers(),
            )

            if not response.ok:
                logger.error(f"Failed to get season details: {response.status_code}")
                return None

            from schemas.tvdb import GetSeasonExtended200Response

            validated_data = GetSeasonExtended200Response.from_dict(response.json())

            assert validated_data

            return validated_data.data
        except Exception as e:
            logger.error(f"Error getting season details: {str(e)}")
            return None

    def get_episode(self, episode_id: str) -> EpisodeExtendedRecord | None:
        """Get episode details."""

        try:
            response = self.session.get(
                f"episodes/{episode_id}/extended",
                headers=self._get_headers(),
            )

            if not response.ok:
                logger.error(f"Failed to get episode details: {response.status_code}")
                return None

            from schemas.tvdb import GetEpisodeExtended200Response

            validated_response = GetEpisodeExtended200Response.from_dict(
                response.json()
            )

            assert validated_response

            return validated_response.data
        except Exception as e:
            logger.error(f"Error getting episode details: {str(e)}")
            return None

    def get_translation(self, series_id: int, language: str) -> Translation | None:
        """Get translation title for a series. Language must be 3 letter code."""

        try:
            response = self.session.get(
                f"series/{series_id}/translations/{language}",
                headers=self._get_headers(),
            )

            if not response.ok:
                logger.error(f"Failed to get translation title: {response.status_code}")
                return None

            from schemas.tvdb import GetEpisodeTranslation200Response

            validated_response = GetEpisodeTranslation200Response.from_dict(
                response.json()
            )

            assert validated_response

            return validated_response.data
        except Exception as e:
            logger.error(f"Error getting translation title: {str(e)}")
            return None

    def get_aliases(self, series_data) -> dict[str, list[str]] | None:
        """
        Get aliases for a series, grouped by language.

        Returns:
            dict[str, list[str]]: A dictionary where keys are language codes and values are lists of alias names.
        """

        aliases_by_lang: dict[str, list[str]] = {}

        for alias in getattr(series_data, "aliases", []):
            lang = getattr(alias, "language", None)
            name = getattr(alias, "name", None)

            if lang and name:
                aliases_by_lang.setdefault(lang, []).append(name)

        return aliases_by_lang

    def get_updates(
        self,
        update_type: str = "episodes",
        since: int | None = None,
    ) -> Updates200Response | None:
        """
        Get updates for a given type and since timestamp.

        Args:
            update_type: The type of updates to get. Defaults to "episodes".
            since: The since timestamp. Defaults to None.

        Returns:
            Optional[dict]: The updates.
        """

        response = self.session.get(
            url=f"updates?{update_type}&since={since}&action=update",
            headers=self._get_headers(),
        )

        if not response.ok:
            logger.error(f"Failed to get updates: {response.status_code}")
            return None

        return Updates200Response.from_dict(response.json())

    def get_new_releases(
        self,
        update_type: str = "episodes",
        hours: int = 24,
    ) -> list[str]:
        """
        Get new releases for a given type and since timestamp.

        Args:
            update_type: Type of updates to get (episodes, series, etc.)
            hours: Number of hours to look back for updates

        Returns:
            List of record IDs from TVDB updates
        """

        pages_checked = 0
        ids_to_check = []

        def process_page(data):
            """Process a single page of updates and extract record IDs"""

            nonlocal pages_checked

            if not data or not hasattr(data, "data"):
                return []

            pages_checked += 1

            return [
                (str(object=u.seriesId), str(u.recordId))
                for u in data.data
                if hasattr(u, "seriesId")
                and hasattr(u, "recordId")
                and u.seriesId
                and u.recordId
            ]

        def get_page(url: str):
            """Get a specific page using the next URL"""

            response = self.session.get(
                url,
                headers=self._get_headers(),
            )

            if not response.ok:
                logger.error(f"Failed to get updates page: {response.status_code}")
                return None

            return Updates200Response.from_dict(response.json())

        def get_epoch_hours_ago(hours: int = 24) -> int:
            """Get timestamp for hours ago"""

            import time

            return int(time.time()) - (hours * 3600)

        try:
            epoch_hours_ago = get_epoch_hours_ago(hours)
            updates = self.get_updates(since=epoch_hours_ago, update_type=update_type)

            if not updates:
                logger.info(
                    f"No updates found for type {update_type} in the last {hours} hours"
                )

                return ids_to_check

            # Process first page
            page_ids = process_page(updates)
            ids_to_check.extend(page_ids)

            # Process subsequent pages if they exist
            current_response = updates

            while current_response.links and current_response.links.next:
                next_page_data = get_page(current_response.links.next)

                if next_page_data:
                    page_ids = process_page(next_page_data)
                    ids_to_check.extend(page_ids)
                    current_response = next_page_data
                else:
                    break

            logger.info(
                f"Found {len(ids_to_check)} {update_type} updates in the last {hours} hours from {pages_checked} pages"
            )

            self.last_new_release_check = datetime.now()

            return ids_to_check
        except Exception as e:
            logger.error(f"Error getting new releases: {str(e)}")
            return ids_to_check

    def _load_token_from_file(self) -> TVDBToken | None:
        """Load token from file if it exists and is valid"""

        try:
            if self.TOKEN_FILE.exists():
                with open(self.TOKEN_FILE, "r") as f:
                    token_data = json.load(f)

                token = TVDBToken.from_dict(token_data)

                # Check if token is still valid
                if token.expires_at > datetime.now():
                    logger.debug("Loaded valid TVDB token from file")

                    return token
                else:
                    logger.debug("Loaded TVDB token is expired, refreshing")

                    token = self._get_auth_token()

                    if not token:
                        logger.error("Failed to refresh expired TVDB token")
                        return None

                    logger.debug("Refreshed TVDB token")

                    return token

            return None
        except Exception as e:
            logger.error(f"Error loading TVDB token from file: {str(e)}")
            return None

    def _save_token_to_file(self, token: TVDBToken) -> None:
        """Save token to file for persistence"""

        try:
            # Create directory if it doesn't exist
            self.TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

            with open(self.TOKEN_FILE, "w") as f:
                json.dump(token.to_dict(), f)

            logger.debug("Saved TVDB token to file")
        except Exception as e:
            logger.error(f"Error saving TVDB token to file: {str(e)}")

    def _get_auth_token(self) -> TVDBToken | None:
        """Get auth token, refreshing if necessary."""

        now = datetime.now()

        if self.token and self.token.expires_at > now:
            return self.token

        payload = {"apikey": self.api_key}
        response = self.session.post("login", json=payload)

        if not response.ok:
            logger.error(f"Failed to obtain TVDB token: {response.status_code}")
            return None

        from schemas.tvdb import LoginPost200ResponseData

        data = LoginPost200ResponseData.from_dict(response.json())

        assert data

        if not data.token:
            logger.error(f"Failed to obtain TVDB token: No token in response")
            return None

        expires_at = now + timedelta(days=25)
        token_obj = TVDBToken(token=data.token, expires_at=expires_at)

        self._save_token_to_file(token_obj)

        return token_obj

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with auth token."""

        token = self._get_auth_token()

        if not token:
            raise TVDBApiError("Could not obtain valid TVDB auth token")

        return {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
