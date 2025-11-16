"""Plex Watchlist Module"""

from collections.abc import Generator
from kink import di
from loguru import logger
from requests import HTTPError

from program.apis.plex_api import PlexAPI
from program.db.db_functions import item_exists_by_any_id
from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.core.content_service import ContentService
from program.settings.models import PlexWatchlistModel
from program.core.runner import MediaItemGenerator, RunnerResult


class PlexWatchlist(ContentService[PlexWatchlistModel]):
    """Class for managing Plex Watchlists"""

    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.content.plex_watchlist

        if not self.enabled:
            return

        self.api = di[PlexAPI]
        self.initialized = self.validate()

        if not self.initialized:
            return

        logger.success("Plex Watchlist initialized!")

    @classmethod
    def get_key(cls) -> str:
        return "plex_watchlist"

    def validate(self):
        if not self.enabled:
            return False

        if not settings_manager.settings.updaters.plex.token:
            logger.error("Plex token is not set!")
            return False

        try:
            self.api.validate_account()
        except Exception as e:
            logger.error(f"Unable to authenticate Plex account: {e}")
            return False

        if self.settings.rss:
            self.api.set_rss_urls(self.settings.rss)

            for rss_url in self.settings.rss:
                try:
                    response = self.api.validate_rss(rss_url)

                    response.raise_for_status()

                    self.api.rss_enabled = True
                except HTTPError as e:
                    if e.response.status_code == 404:
                        logger.warning(
                            f"Plex RSS URL {rss_url} is Not Found. Please check your RSS URL in settings."
                        )

                        return False
                    else:
                        logger.warning(
                            f"Plex RSS URL {rss_url} is not reachable (HTTP status code: {e.response.status_code})."
                        )

                        return False
                except Exception as e:
                    logger.error(
                        f"Failed to validate Plex RSS URL {rss_url}: {e}", exc_info=True
                    )

                    return False

        return True

    def run(self) -> MediaItemGenerator:
        """Fetch new media from `Plex Watchlist` and RSS feed if enabled."""

        try:
            watchlist_items: list[dict[str, str]] = self.api.get_items_from_watchlist()
            rss_items: list[tuple[str, str]] = (
                self.api.get_items_from_rss() if self.api.rss_enabled else []
            )
        except Exception as e:
            logger.warning(f"Error fetching items: {e}")
            return

        items_to_yield: list[MediaItem] = []

        if watchlist_items:
            for d in watchlist_items:
                if d["tvdb_id"] and not d["tmdb_id"]:  # show
                    items_to_yield.append(
                        MediaItem({"tvdb_id": d["tvdb_id"], "requested_by": self.key})
                    )
                elif d["tmdb_id"] and not d["tvdb_id"]:  # movie
                    items_to_yield.append(
                        MediaItem({"tmdb_id": d["tmdb_id"], "requested_by": self.key})
                    )

        if rss_items:
            for r in rss_items:
                _type, _id = r
                if _type == "show":
                    items_to_yield.append(
                        MediaItem({"tvdb_id": _id, "requested_by": self.key})
                    )
                elif _type == "movie":
                    items_to_yield.append(
                        MediaItem({"tmdb_id": _id, "requested_by": self.key})
                    )

        if items_to_yield:
            items_to_yield = [
                item
                for item in items_to_yield
                if not item_exists_by_any_id(
                    imdb_id=item.imdb_id, tvdb_id=item.tvdb_id, tmdb_id=item.tmdb_id
                )
            ]

        logger.info(f"Fetched {len(items_to_yield)} new items from plex watchlist")

        yield RunnerResult(media_items=items_to_yield)
