"""Plex library module"""

import concurrent.futures
from threading import Lock
import os
from datetime import datetime
from typing import Optional
from plexapi.server import PlexServer
from plexapi.exceptions import BadRequest, Unauthorized
from utils.logger import logger
from program.settings.manager import settings_manager
from program.media.item import (
    Movie,
    Show,
    Season,
    Episode,
    ItemId
)

class PlexLibrary():
    """Plex library class"""

    def __init__(self):
        self.key = "plexlibrary"
        self.initialized = False
        self.library_path = os.path.abspath(
            os.path.dirname(settings_manager.settings.symlink.library_path)
        )
        self.last_fetch_times = {}
        self.settings = settings_manager.settings.plex
        try:
            self.plex = PlexServer(self.settings.url, self.settings.token, timeout=60)
        except Unauthorized:
            logger.error("Plex is not authorized!")
            return
        except BadRequest as e:
            logger.error("Plex is not configured correctly: %s", e)
            return
        except Exception as e:
            logger.error("Plex exception thrown: %s", e)
            return
        self.log_worker_count = False
        self.initialized = True if isinstance(self.plex, PlexServer) else False
        if not self.initialized:
            logger.error("Plex is not initialized!")
            return
        logger.info("Plex initialized!")
        self.lock = Lock()

    def _get_last_fetch_time(self, section):
        return self.last_fetch_times.get(section.key, datetime(1800, 1, 1))

    def run(self):
        """Run Plex library"""
        items = []
        sections = self.plex.library.sections()
        processed_sections = set()
        max_workers = os.cpu_count() / 2
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="Plex"
        ) as executor:
            for section in sections:
                is_wanted = self._is_wanted_section(section)
                if section.key in processed_sections or not is_wanted:
                    continue
                if section.refreshing:
                    processed_sections.add(section.key)
                    continue
                # Fetch only items that have been added or updated since the last fetch
                last_fetch_time = self._get_last_fetch_time(section)
                filters = {} if not self.last_fetch_times else {"addedAt>>": last_fetch_time}
                future_items = {
                    executor.submit(self._create_item, item)
                    for item in section.search(libtype=section.type, filters=filters)
                }
                for future in concurrent.futures.as_completed(future_items):
                    media_item = future.result()
                    items.append(media_item)
                with self.lock:
                    self.last_fetch_times[section.key] = datetime.now()
                processed_sections.add(section.key)

        if not processed_sections:
            logger.error(
                "Failed to process any sections.  Ensure that your library_path"
                " of {self.library_path} folders are included in the relevant sections"
                " (found in Plex Web UI Setting > Manage > Libraries > Edit Library)."
            )
            return
        yield from items

    def _create_item(self, raw_item):
        """Create a MediaItem from Plex API data."""
        item = _map_item_from_data(raw_item)
        if not item or raw_item.type != "show":
            return item
        for season in raw_item.seasons():
            if season.seasonNumber == 0:
                continue
            if not (season_item := _map_item_from_data(season)):
                continue
            episode_items = []
            for episode in season.episodes():
                episode_item = _map_item_from_data(episode)
                if episode_item:
                    episode_items.append(episode_item)
            season_item.episodes = episode_items
            item.seasons.append(season_item)
        return item

    def _is_wanted_section(self, section):
        section_located = any(
            self.library_path in location for location in section.locations
        )
        return section_located and section.type in ["movie", "show"]


def _map_item_from_data(item):
    """Map Plex API data to MediaItemContainer."""
    file = None
    guid = getattr(item, "guid", None)
    if item.type in ["movie", "episode"]:
        file = getattr(item, "locations", [None])[0].split("/")[-1]
    genres = [genre.tag for genre in getattr(item, "genres", [])]
    is_anime = "anime" in genres
    title = getattr(item, "title", None)
    key = getattr(item, "key", None)
    season_number = getattr(item, "seasonNumber", None)
    episode_number = getattr(item, "episodeNumber", None)
    art_url = getattr(item, "artUrl", None)
    imdb_id = None
    tvdb_id = None
    aired_at = None

    if item.type in ["movie", "show"]:
        guids = getattr(item, "guids", [])
        imdb_id = next(
            (guid.id.split("://")[-1] for guid in guids if "imdb" in guid.id), None
        )
        aired_at = getattr(item, "originallyAvailableAt", None)

    media_item_data = {
        "title": title,
        "imdb_id": imdb_id,
        "tvdb_id": tvdb_id,
        "aired_at": aired_at,
        "genres": genres,
        "key": key,
        "guid": guid,
        "art_url": art_url,
        "file": file,
        "is_anime": is_anime,
    }

    # Instantiate the appropriate subclass based on 'item_type'
    if item.type == "movie":
        return Movie(media_item_data)
    elif item.type == "show":
        return Show(media_item_data)
    elif item.type == "season":
        media_item_data["number"] = season_number
        return Season(media_item_data)
    elif item.type == "episode":
        media_item_data["number"] = episode_number
        media_item_data["season_number"] = season_number
        return Episode(media_item_data)
    else:
        # Specials may end up here..
        logger.error("Unknown Item: %s with type %s", item.title, item.type)
        return None
