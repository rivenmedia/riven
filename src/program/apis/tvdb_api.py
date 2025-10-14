"""TVDB API client"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

from kink import inject
from loguru import logger
from pydantic import BaseModel

from program.utils import data_dir_path
from program.utils.request import SmartSession


class TVDBApiError(Exception):
    """Base exception for TVDB API related errors"""


class TVDBToken(BaseModel):
    """TVDB API token model"""

    token: str
    expires_at: datetime

    def to_dict(self) -> Dict[str, str]:
        """Convert token to dictionary for storage"""
        return {"token": self.token, "expires_at": self.expires_at.isoformat()}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "TVDBToken":
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
        self.last_new_release_check: Optional[datetime] = None

        rate_limits = {
            "api4.thetvdb.com": {"rate": 25, "capacity": 1000}  # 25 requests per second
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

    def _load_token_from_file(self) -> Optional[TVDBToken]:
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

    def _get_auth_token(self) -> Optional[TVDBToken]:
        """Get auth token, refreshing if necessary."""
        now = datetime.now()
        if self.token and self.token.expires_at > now:
            return self.token

        payload = {"apikey": self.api_key}
        response = self.session.post("login", json=payload)
        if (
            not response.ok
            or not hasattr(response.data, "data")
            or not response.data.data.token
        ):
            logger.error(f"Failed to obtain TVDB token: {response.status_code}")
            return None

        if token := response.data.data.token:
            expires_at = now + timedelta(days=25)
            token_obj = TVDBToken(token=token, expires_at=expires_at)
            self._save_token_to_file(token_obj)
            return token_obj

        return None

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth token."""
        token = self._get_auth_token()
        if not token:
            raise TVDBApiError("Could not obtain valid TVDB auth token")

        return {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_series(self, series_id: str) -> Optional[Dict]:
        """Get TV series details by TVDB ID."""
        try:
            headers = self._get_headers()
            url = f"series/{series_id}/extended"
            response = self.session.get(url, headers=headers)
            if not response.ok:
                logger.error(f"Failed to get series details: {response.status_code}")
                return None

            return (
                response.data.data
                if response.data and hasattr(response.data, "data")
                else None
            )
        except Exception as e:
            logger.error(f"Error getting series details: {str(e)}")
            return None

    def search_by_imdb_id(self, imdb_id: str) -> Optional[Dict]:
        """Search for a series by IMDB ID."""
        try:
            headers = self._get_headers()
            url = f"search/remoteid/{imdb_id}"

            response = self.session.get(url, headers=headers)
            if not response.ok:
                logger.error(f"Failed to search by IMDB ID: {response.status_code}")
                return None

            return response.data
        except Exception as e:
            logger.error(f"Error searching by IMDB ID: {str(e)}")
            return None

    def get_season(self, season_id: str) -> Optional[Dict]:
        """Get details for a specific season."""
        try:
            headers = self._get_headers()
            url = f"seasons/{season_id}/extended"

            response = self.session.get(url, headers=headers)
            if not response.ok:
                logger.error(f"Failed to get season details: {response.status_code}")
                return None

            return response.data
        except Exception as e:
            logger.error(f"Error getting season details: {str(e)}")
            return None

    def get_episode(self, episode_id: str) -> Optional[Dict]:
        """Get episode details."""
        try:
            headers = self._get_headers()
            url = f"episodes/{episode_id}/extended"

            response = self.session.get(url, headers=headers)
            if not response.ok:
                logger.error(f"Failed to get episode details: {response.status_code}")
                return None

            return (
                response.data.data
                if response.data and hasattr(response.data, "data")
                else None
            )
        except Exception as e:
            logger.error(f"Error getting episode details: {str(e)}")
            return None

    def get_translation(self, series_id: str, language: str) -> Optional[Dict]:
        """Get translation title for a series. Language must be 3 letter code."""
        try:
            headers = self._get_headers()
            url = f"series/{series_id}/translations/{language}"

            response = self.session.get(url, headers=headers)
            if not response.ok:
                logger.error(f"Failed to get translation title: {response.status_code}")
                return None

            return response.data  # name and aliases
        except Exception as e:
            logger.error(f"Error getting translation title: {str(e)}")
            return None

    def get_aliases(self, series_data) -> Optional[Dict[str, list[str]]]:
        """
        Get aliases for a series, grouped by language.

        Returns:
            Dict[str, list[str]]: A dictionary where keys are language codes and values are lists of alias names.
        """
        aliases_by_lang: Dict[str, list[str]] = {}
        for alias in getattr(series_data, "aliases", []):
            lang = getattr(alias, "language", None)
            name = getattr(alias, "name", None)
            if lang and name:
                aliases_by_lang.setdefault(lang, []).append(name)
        return aliases_by_lang

    def get_updates(
        self, update_type: str = "episodes", since: int = None
    ) -> Optional[Dict]:
        """
        Get updates for a given type and since timestamp.

        Args:
            update_type: The type of updates to get. Defaults to "episodes".
            since: The since timestamp. Defaults to None.

        Returns:
            Optional[Dict]: The updates.
        """

        headers = self._get_headers()
        url = f"updates?{update_type}&since={since}&action=update"
        response = self.session.get(url, headers=headers)
        if not response.ok:
            logger.error(f"Failed to get updates: {response.status_code}")
            return None
        return response.data

    def get_new_releases(
        self, update_type: str = "episodes", hours: int = 24
    ) -> List[str]:
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
                (str(u.seriesId), str(u.recordId))
                for u in data.data
                if hasattr(u, "seriesId")
                and hasattr(u, "recordId")
                and u.seriesId
                and u.recordId
            ]

        def get_page(url: str):
            """Get a specific page using the next URL"""
            headers = self._get_headers()
            response = self.session.get(url, headers=headers)
            if response.ok and response.data:
                return response.data
            return None

        def get_epoch_hours_ago(hours: int = 24) -> int:
            """Get timestamp for hours ago"""
            import time

            return int(time.time()) - (hours * 3600)

        try:
            epoch_hours_ago = get_epoch_hours_ago(hours)
            response = self.get_updates(since=epoch_hours_ago, update_type=update_type)

            if not response or not response.data:
                logger.info(
                    f"No updates found for type {update_type} in the last {hours} hours"
                )
                return ids_to_check

            # Process first page
            page_ids = process_page(response)
            ids_to_check.extend(page_ids)

            # Process subsequent pages if they exist
            current_response = response
            while (
                hasattr(current_response, "links")
                and hasattr(current_response.links, "next")
                and current_response.links.next
            ):
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

    def get_series_release_data(self, show_data: SimpleNamespace) -> Dict:
        """Format response data from release status into dict"""
        return {
            "release_id": (
                getattr(show_data.status, "id", None)
                if hasattr(show_data, "status")
                else None
            ),
            "release_status": (
                getattr(show_data.status, "name", None)
                if hasattr(show_data, "status")
                else None
            ),
            "keep_updated": (
                getattr(show_data.status, "keepUpdated", None)
                if hasattr(show_data, "status")
                else None
            ),
            "last_updated": getattr(show_data, "lastUpdated", None),
            "first_aired": getattr(show_data, "firstAired", None),
            "last_aired": getattr(show_data, "lastAired", None),
            "next_aired": getattr(show_data, "nextAired", None),
            "airs_days": {
                "monday": (
                    getattr(show_data.airsDays, "monday", False)
                    if hasattr(show_data, "airsDays")
                    else None
                ),
                "tuesday": (
                    getattr(show_data.airsDays, "tuesday", False)
                    if hasattr(show_data, "airsDays")
                    else None
                ),
                "wednesday": (
                    getattr(show_data.airsDays, "wednesday", False)
                    if hasattr(show_data, "airsDays")
                    else None
                ),
                "thursday": (
                    getattr(show_data.airsDays, "thursday", False)
                    if hasattr(show_data, "airsDays")
                    else None
                ),
                "friday": (
                    getattr(show_data.airsDays, "friday", False)
                    if hasattr(show_data, "airsDays")
                    else None
                ),
                "saturday": (
                    getattr(show_data.airsDays, "saturday", False)
                    if hasattr(show_data, "airsDays")
                    else None
                ),
                "sunday": (
                    getattr(show_data.airsDays, "sunday", False)
                    if hasattr(show_data, "airsDays")
                    else None
                ),
            },
            "airs_time": getattr(show_data, "airsTime", None),
            "average_runtime": getattr(show_data, "averageRuntime", None),
            "last_metadata_fetch": datetime.now().isoformat(),
            "next_metadata_fetch": getattr(
                show_data, "lastAired", None
            ),  # fetch metadata again at the end of the season
        }
