from dataclasses import dataclass
from typing import Literal

import regex

from httpx_limiter.rate import Rate
from loguru import logger
from plexapi.media import Guid
from plexapi.video import Movie, Show
from plexapi.library import LibrarySection
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer


from program.settings.manager import settings_manager
from program.utils.request import SmartSession
from program.utils.rate_limited_client import RateLimitedClient

TMDBID_REGEX = regex.compile(r"tmdb://(\d+)")
TVDBID_REGEX = regex.compile(r"tvdb://(\d+)")


@dataclass
class WatchlistItem:
    """Dataclass for Plex watchlist item"""

    imdb_id: str | None
    tmdb_id: str | None
    tvdb_id: str | None


type ItemType = Literal["movie", "show"]


class PlexAPIError(Exception):
    """Base exception for PlexApi related errors"""


class PlexAPI:
    """Handles Plex API communication"""

    def __init__(self, token: str, base_url: str):
        self.rss_urls: list[str] | None = None
        self.token = token

        self.client = RateLimitedClient(
            base_url=base_url,
            rate_limit=Rate.create(magnitude=60, duration=1),
        )

        self.account = None
        self.plex_server = None
        self.rss_enabled = False

    def validate_account(self):
        try:
            self.account = MyPlexAccount(session=self.client, token=self.token)
        except Exception as e:
            logger.error(f"Failed to authenticate Plex account: {e}")
            return False
        return True

    def validate_server(self):
        self.plex_server = PlexServer(
            self.client.base_url, token=self.token, session=self.client, timeout=60
        )

    def set_rss_urls(self, rss_urls: list[str]):
        self.rss_urls = rss_urls

    def clear_rss_urls(self):
        self.rss_urls = None
        self.rss_enabled = False

    def validate_rss(self, url: str):
        return self.client.get(url)

    async def ratingkey_to_imdbid(self, ratingKey: str) -> str | None:
        """Convert Plex rating key to IMDb ID"""

        token = settings_manager.settings.updaters.plex.token
        filter_params = (
            "includeGuids=1&includeFields=guid,title,year&includeElements=Guid"
        )
        url = f"https://metadata.provider.plex.tv/library/metadata/{ratingKey}?X-Plex-Token={token}&{filter_params}"

        response = await self.client.get(url)

        @dataclass
        class ResponseData:
            """Dataclass for Plex rating key to IMDb ID response"""

            @dataclass
            class _MediaContainer:
                """Dataclass for Plex MediaContainer"""

                @dataclass
                class _Metadata:
                    """Dataclass for Plex Metadata"""

                    Guid: list[Guid]

                Metadata: list[_Metadata]

            MediaContainer: _MediaContainer

        response_data = ResponseData(response.json())

        if response.is_success and response_data.MediaContainer:
            metadata = response_data.MediaContainer.Metadata[0]

            return next(
                (
                    guid.id.split("//")[-1]
                    for guid in metadata.Guid
                    if "imdb://" in guid.id
                ),
                None,
            )

        logger.debug(f"Failed to fetch IMDb ID for ratingKey: {ratingKey}")

        return None

    async def get_items_from_rss(self) -> list[tuple[ItemType, str]]:
        """Fetch media from Plex RSS Feeds."""

        rss_items: list[tuple[ItemType, str]] = []

        if self.rss_urls:
            for rss_url in self.rss_urls:
                try:
                    response = await self.client.get(
                        rss_url + "?format=json",
                        timeout=60,
                    )

                    if not response.is_success or not hasattr(response.json(), "items"):
                        logger.error(f"Failed to fetch Plex RSS feed from {rss_url}")

                        continue

                    @dataclass
                    class ResponseData:
                        """Dataclass for Plex RSS feed response"""

                        @dataclass
                        class Item:
                            """Dataclass for Plex RSS feed item"""

                            title: str
                            category: ItemType
                            guids: list[str]

                        items: list[Item]

                    response_data = ResponseData(response.json())

                    for _item in response_data.items:
                        if _item.category == "movie":
                            tmdb_id = next(
                                (
                                    guid.split("//")[-1]
                                    for guid in _item.guids
                                    if guid.startswith("tmdb://")
                                ),
                                "",
                            )
                            if tmdb_id:
                                rss_items.append(("movie", tmdb_id))
                            else:
                                logger.log(
                                    "NOT_FOUND",
                                    f"Failed to extract appropriate ID from {_item.title}",
                                )

                        elif _item.category == "show":
                            tvdb_id = next(
                                (
                                    guid.split("//")[-1]
                                    for guid in _item.guids
                                    if guid.startswith("tvdb://")
                                ),
                                "",
                            )
                            if tvdb_id:
                                rss_items.append(("show", tvdb_id))
                            else:
                                logger.log(
                                    "NOT_FOUND",
                                    f"Failed to extract appropriate ID from {_item.title}",
                                )

                except Exception as e:
                    logger.error(
                        f"An unexpected error occurred while fetching Plex RSS feed from {rss_url}: {e}"
                    )

        return rss_items

    def get_items_from_watchlist(self) -> list[WatchlistItem]:
        """Fetch media from Plex watchlist"""

        assert self.account

        items: list[Movie | Show] = self.account.watchlist()
        watchlist_items: list[WatchlistItem] = []

        for item in items:
            try:
                imdb_id = None
                tmdb_id = None
                tvdb_id = None

                if item.guids:
                    imdb_id = next(
                        (
                            guid.id.split("//")[-1]
                            for guid in item.guids
                            if guid.id.startswith("imdb://")
                        ),
                        "",
                    )

                    if isinstance(item, Movie):
                        tmdb_id = next(
                            (
                                guid.id.split("//")[-1]
                                for guid in item.guids
                                if guid.id.startswith("tmdb://")
                            ),
                            "",
                        )
                    elif isinstance(item, Show):
                        tvdb_id = next(
                            (
                                guid.id.split("//")[-1]
                                for guid in item.guids
                                if guid.id.startswith("tvdb://")
                            ),
                            "",
                        )

                    if not any([imdb_id, tmdb_id, tvdb_id]):
                        logger.log(
                            "NOT_FOUND",
                            f"Unable to extract IMDb ID from {item.title} ({item.year}) with data id: {imdb_id}",
                        )

                        continue

                    watchlist_items.append(
                        WatchlistItem(
                            imdb_id=imdb_id,
                            tmdb_id=tmdb_id,
                            tvdb_id=tvdb_id,
                        )
                    )
                else:
                    logger.log(
                        "NOT_FOUND",
                        f"{item.title} ({item.year}) is missing guids attribute from Plex",
                    )
            except Exception as e:
                logger.error(
                    f"An unexpected error occurred while fetching Plex watchlist item {item.title}: {e}"
                )

        return watchlist_items

    def update_section(self, section, path: str) -> bool:
        """Update the Plex section for the given path"""
        try:
            section.update(str(path))

            return True
        except Exception as e:
            logger.error(f"Failed to update Plex section for path {path}: {e}")

            return False

    def map_sections_with_paths(self) -> dict[LibrarySection, list[str]]:
        """Map Plex sections with their paths"""

        assert self.plex_server

        # Skip sections without locations and non-movie/show sections
        sections = [
            section
            for section in self.plex_server.library.sections()
            if section.type in ["show", "movie"] and section.locations
        ]

        # Map sections with their locations with the section obj as key and the location strings as values
        return {section: section.locations for section in sections}
