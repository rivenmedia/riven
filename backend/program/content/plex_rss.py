"""Plex Rss Module"""
from typing import Optional
from pydantic import BaseModel
from requests import ConnectTimeout
from utils.request import get, ping
from utils.logger import logger
from utils.settings import settings_manager as settings
from program.media.container import MediaItemContainer
from program.updaters.trakt import Updater as Trakt
import json


class PlexRssConfig(BaseModel):
    enabled: bool
    rss: Optional[str]

class PlexRss:
    """Class for managing Plex rss"""

    def __init__(self, media_items: MediaItemContainer):
        self.key = "plex_rss"
        self.settings = PlexRssConfig(**settings.get(f"content.{self.key}"))
        self.media_items = media_items
        self.prev_count = 0
        self.updater = Trakt()
        self.initialized = self.validate_settings()

    def validate_settings(self):
        if not self.settings.enabled:
            logger.debug("Plex rss is set to disabled.")
            return False
        if not self.settings.rss and self.settings.enabled:
            logger.warning("Plex rss is enabled but no URL is set.")
            return False
        try:
            response = ping(
                self.settings.rss,
                timeout=10,
            )
            if response.ok:
                return True
        except ConnectTimeout:
            return False
        except Exception as e:
            logger.error(f"Plex rss configuration error: {e}")
            return False

    def run(self):
        """Fetch media from Plex rss and add them to media_items attribute
        if they are not already there"""
        items = self._get_items_from_plex_rss()
        new_items = [item for item in items if item not in self.media_items]
        container = self.updater.create_items(new_items)
        for item in container:
            item.set("requested_by", "Plex rss")
        previous_count = len(self.media_items)
        added_items = self.media_items.extend(container)
        added_items_count = len(self.media_items) - previous_count
        if (
            added_items_count != self.prev_count
        ):
            self.prev_count = added_items_count
        length = len(added_items)
        if length >= 1 and length <= 5:
            for item in added_items:
                logger.info("Added %s", item.log_string)
        elif length > 5:
            logger.info("Added %s items", length)

    def _get_items_from_plex_rss(self) -> list:
        """Fetch media from Plex rss"""
        response_obj = get(self.settings.rss, timeout=30)
        rss_data = json.loads(response_obj.response.content)
        items = rss_data.get("items", [])
        ids = []
        for item in items:
            imdb_id = next(
                (
                    guid.split("//")[-1]
                    for guid in item.get("guids")
                    if "imdb://" in guid
                ),
                None,
            )
            if imdb_id:
                ids.append(imdb_id)
            else:
                # TODO: Add support for tvdb id's
                logger.warning(
                    "Could not find IMDb ID for %s in Plex rss", item.get("title")
                )
        return ids
