"""TVDB API client"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from kink import inject
from loguru import logger
from pydantic import BaseModel
from requests import Session

from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseObject,
    ResponseType,
    create_service_session,
    get_cache_params,
    get_rate_limit_params,
)
from program.settings.manager import settings_manager
from program.utils import data_dir_path


class TVDBApiError(Exception):
    """Base exception for TVDB API related errors"""


class TVDBToken(BaseModel):
    """TVDB API token model"""
    token: str
    expires_at: datetime
    
    def to_dict(self) -> Dict[str, str]:
        """Convert token to dictionary for storage"""
        return {
            "token": self.token,
            "expires_at": self.expires_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "TVDBToken":
        """Create token from dictionary"""
        return cls(
            token=data["token"],
            expires_at=datetime.fromisoformat(data["expires_at"])
        )


class TVDBRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, request_logging: bool = False):
        super().__init__(session, base_url=base_url, response_type=ResponseType.DICT, custom_exception=TVDBApiError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> ResponseObject:
        return super()._request(method, endpoint, **kwargs)


@inject
class TVDBApi:
    """TVDB API client"""
    BASE_URL = "https://api4.thetvdb.com/v4"
    TOKEN_FILE = Path(data_dir_path, "tvdb_token.json")

    def __init__(self):
        self.api_key = "6be85335-5c4f-4d8d-b945-d3ed0eb8cdce"
        self.token = None
        rate_limit_params = get_rate_limit_params(max_calls=150, period=60, max_delay=60)  # TVDB allows 150 requests per minute
        tvdb_cache = get_cache_params("tvdb", 86400)
        use_cache = os.environ.get("SKIP_TVDB_CACHE", "false").lower() == "false"
        self.session = create_service_session(rate_limit_params=rate_limit_params, use_cache=use_cache, cache_params=tvdb_cache)
        self.request_handler = TVDBRequestHandler(self.session, base_url=self.BASE_URL)
        self.token = self._load_token_from_file()
        if not self.token:
            logger.error("No TVDB token found, exiting.")
            exit(0)

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
                    if not self.token:
                        exit(0)
                    self._save_token_to_file(self.token)
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
        
    def _get_auth_token(self) -> Optional[str]:
        """Get auth token, refreshing if necessary."""
        now = datetime.now()
        if self.token and self.token.expires_at > now:
            return self.token.token

        payload = {"apikey": self.api_key}
        response = self.request_handler.execute(HttpMethod.POST, "login", json=payload)
        if not response.is_ok or not response.data.get("data", {}).get("token"):
            logger.error(f"Failed to obtain TVDB token: {response.status_code}")
            return None

        if token := response.data["data"]["token"]:
            expires_at = now + timedelta(days=25)
            self.token = TVDBToken(token=token, expires_at=expires_at)
            self._save_token_to_file(self.token)
            return token
            
        return None
        
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth token."""
        token = self._get_auth_token()
        if not token:
            raise TVDBApiError("Could not obtain valid TVDB auth token")

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
    def get_series(self, series_id: str) -> Optional[Dict]:
        """Get TV series details by TVDB ID."""
        logger.debug(f"Getting series details for TVDB ID: {series_id}")

        try:
            headers = self._get_headers()
            url = f"series/{series_id}/extended"
            response = self.request_handler.execute(HttpMethod.GET, url, headers=headers)
            if not response.is_ok:
                logger.error(f"Failed to get series details: {response.status_code}")
                return None
                
            return response.data.get("data") if response.data and "data" in response.data else None
        except Exception as e:
            logger.error(f"Error getting series details: {str(e)}")
            return None

    def search_by_imdb_id(self, imdb_id: str) -> Optional[Dict]:
        """Search for a series by IMDB ID."""
        logger.debug(f"Searching for series by IMDB ID: {imdb_id}")

        try:
            headers = self._get_headers()
            url = f"search/remoteid/{imdb_id}"
            
            response = self.request_handler.execute(HttpMethod.GET, url, headers=headers)
            if not response.is_ok:
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

            response = self.request_handler.execute(HttpMethod.GET, url, headers=headers)
            if not response.is_ok:
                logger.error(f"Failed to get season details: {response.status_code}")
                return None
                
            return response.data
        except Exception as e:
            logger.error(f"Error getting season details: {str(e)}")
            return None
            
    def get_season_episodes(self, season_id: str) -> Optional[Dict]:
        """Get all episodes for a season."""
        try:
            headers = self._get_headers()
            url = f"seasons/{season_id}/extended"
            
            response = self.request_handler.execute(HttpMethod.GET, url, headers=headers)
            if not response.is_ok:
                logger.error(f"Failed to get season episodes: {response.status_code}")
                return None
                
            return response.data
        except Exception as e:
            logger.error(f"Error getting season episodes: {str(e)}")
            return None
            
    def get_episode(self, episode_id: str) -> Optional[Dict]:
        """Get episode details."""
        try:
            headers = self._get_headers()
            url = f"episodes/{episode_id}/extended"
            
            response = self.request_handler.execute(HttpMethod.GET, url, headers=headers)
            if not response.is_ok:
                logger.error(f"Failed to get episode details: {response.status_code}")
                return None
                
            return response.data.get("data") if response.data and "data" in response.data else None
        except Exception as e:
            logger.error(f"Error getting episode details: {str(e)}")
            return None
    
    def  get_translation(self, series_id: str, language: str) -> Optional[Dict]:
        """Get translation title for a series. Language must be 3 letter code."""
        try:
            headers = self._get_headers()
            url = f"series/{series_id}/extended/{language}"
            
            response = self.request_handler.execute(HttpMethod.GET, url, headers=headers)
            if not response.is_ok:
                logger.error(f"Failed to get translation title: {response.status_code}")
                return None

            return response.data # name and aliases
        except Exception as e:
            logger.error(f"Error getting translation title: {str(e)}")
            return None