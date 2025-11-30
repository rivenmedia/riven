"""TVDB API client"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger
from pydantic import BaseModel

from program.utils import data_dir_path
from program.utils.request import SmartSession
from schemas.tvdb import (
    SearchByRemoteIdResult,
    SeasonExtendedRecord,
    SeriesExtendedRecord,
    Translation,
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
                "rate": 25.0,
                "capacity": 1000.0,
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

            validated_response = GetSeriesArtworks200Response.model_validate(
                response.json(),
            )

            assert validated_response.data

            return SeriesRelease.model_validate(validated_response.data.model_dump())
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

    def get_aliases(self, series_data: SeriesRelease) -> dict[str, list[str]] | None:
        """
        Get aliases for a series, grouped by language.

        Returns:
            dict[str, list[str]]: A dictionary where keys are language codes and values are lists of alias names.
        """

        if not series_data.aliases:
            return None

        aliases_by_lang = dict[str, list[str]]({})

        for alias in series_data.aliases:
            lang = alias.language
            name = alias.name

            if lang and name:
                aliases_by_lang.setdefault(lang, []).append(name)

        return aliases_by_lang

    def _load_token_from_file(self) -> TVDBToken | None:
        """Load token from file if it exists and is valid"""

        try:
            if self.TOKEN_FILE.exists():
                with open(self.TOKEN_FILE, "r") as f:
                    token_data = json.load(f)

                token = TVDBToken.from_dict(token_data)

                # Check if token is still valid
                if token.expires_at > datetime.now():


                    return token
                else:
                    logger.debug("Loaded TVDB token is expired, refreshing")

                    token = self._get_auth_token()

                    if not token:
                        logger.error("Failed to refresh expired TVDB token")
                        return None

                    logger.debug("Refreshed TVDB token")

                    self._save_token_to_file(token)

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

        data = LoginPost200ResponseData.model_validate(response.json()["data"])

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
