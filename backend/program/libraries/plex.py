"""Plex library module"""
import threading
import time
from typing import List, Optional
from plexapi import exceptions
from plexapi.server import PlexServer
import requests
from requests.exceptions import ReadTimeout, ConnectionError
from pydantic import BaseModel, HttpUrl
from utils.logger import logger
from utils.settings import settings_manager as settings
from program.media import (
    MediaItemContainer,
    MediaItemState,
    MediaItem,
    Movie,
    Show,
    Season,
    Episode,
)


class PlexSettings(BaseModel):
    user: str
    token: str
    url: HttpUrl
    user_watchlist_rss: Optional[str] = None


class Library(threading.Thread):
    """Plex library class"""

    def __init__(self, media_items: MediaItemContainer):
        super().__init__(name="Plex")
        # Plex class library is a necessity
        while True:
            try:
                temp_settings = settings.get("plex")
                self.plex = PlexServer(
                    temp_settings["url"], temp_settings["token"], timeout=15
                )
                self.settings = PlexSettings(**temp_settings)
                self.running = False
                self.media_items = media_items
                self._update_items()
                break
            except exceptions.Unauthorized:
                logger.error("Wrong plex token, retrying in 2...")
            except ConnectionError:
                logger.error("Couldnt connect to plex, retrying in 2...")
            time.sleep(2)

    def run(self):
        while self.running:
            self._update_sections()
            self._update_items()

    def start(self):
        self.running = True
        super().start()

    def stop(self):
        self.running = False
        super().join()

    def _update_items(self):
        items = []
        sections = self.plex.library.sections()
        processed_sections = set()

        for section in sections:
            if section.key in processed_sections:
                continue

            try:
                if not section.refreshing:
                    for item in section.all():
                        media_item = self._create_item(item)
                        if media_item:
                            items.append(media_item)
            except requests.exceptions.ReadTimeout:
                logger.error(
                    f"Timeout occurred when accessing section: {section.title}"
                )
                continue

            processed_sections.add(section.key)

        self.media_items.extend(items)

        matched_items = self.match_items(items, self.media_items)
        if matched_items > 0:
            logger.info(f"Found {matched_items} new items")

    def _update_sections(self):
        """Update plex library section"""
        for section in self.plex.library.sections():
            movie_items = [
                item
                for item in self.media_items
                if item.type == "movie"
                and item.state is MediaItemState.SYMLINK
                and item.update_folder != "updated"
            ]
            episodes = [
                episode
                for item in self.media_items
                if item.type == "show"
                for season in item.seasons
                for episode in season.episodes
                if episode.state is MediaItemState.SYMLINK
                and episode.update_folder != "updated"
            ]
            items = movie_items + episodes

            for item in items:
                if (
                    item.type == section.type
                    or item.type in ["season", "episode"]
                    and section.type == "show"
                ):
                    section.update(item.update_folder)
                    item.set("update_folder", "updated")
                    log_string = item.title
                    if item.type == "episode":
                        log_string = f"{item.parent.parent.title} season {item.parent.number} episode {item.number}"
                    logger.debug("Updated section %s for %s", section.title, log_string)
                    break

    def _create_item(self, item):
        new_item = _map_item_from_data(item, item.type)
        if new_item and item.type == "show":
            for season in item.seasons():
                if season.seasonNumber != 0:
                    new_season = _map_item_from_data(season, "season")
                    if new_season:
                        new_season_episodes = []
                        for episode in season.episodes():
                            new_episode = _map_item_from_data(episode, "episode")
                            if new_episode:
                                new_season_episodes.append(new_episode)
                        new_season.episodes = new_season_episodes
                        new_item.seasons.append(new_season)
        return new_item

    def match_items(self, found_items: List[MediaItem], media_items: List[MediaItem]):
        """Matches items in given mediacontainer that are not in library
        to items that are in library"""
        items_to_update = 0

        for item in media_items:
            if item.state != MediaItemState.LIBRARY:
                if item.type == "movie":
                    for found_item in found_items:
                        if (
                            found_item.type == "movie"
                            and found_item.imdb_id == item.imdb_id
                        ):
                            self._update_item(item, found_item)
                            items_to_update += 1
                            break
                if item.type == "show":
                    for found_item in found_items:
                        if found_item.type == "show":
                            for found_season in found_item.seasons:
                                for found_episode in found_season.episodes:
                                    for season in item.seasons:
                                        for episode in season.episodes:
                                            if (
                                                episode.state
                                                is not MediaItemState.LIBRARY
                                            ):
                                                if (
                                                    episode.imdb_id
                                                    == found_episode.imdb_id
                                                ):
                                                    self._update_item(
                                                        episode, found_episode
                                                    )
                                                    items_to_update += 1
                                                    break

        return items_to_update

    def _update_item(self, item: MediaItem, library_item: MediaItem):
        """Internal method to use with match_items
        It does some magic to update media items according to library
        items found"""
        item.set("guid", library_item.guid)
        item.set("key", library_item.key)

    def _fix_match(self, library_item: MediaItem, item: MediaItem):
        """Internal method to use in match_items method.
        It gets plex guid and checks if it matches with plex metadata
        for given imdb_id. If it does, it will update the metadata of the plex item."""
        section = next(
            section
            for section in self.plex.library.sections()
            if section.type == item.type
        )
        dummy = section.search(maxresults=1)[0]

        if dummy and not section.refreshing:
            if item.imdb_id:
                try:
                    match = dummy.matches(agent=section.agent, title=item.imdb_id)[0]
                except ReadTimeout:
                    return False
                except IndexError:
                    return False
                if library_item.guid != match.guid:
                    item_to_update = self.plex.fetchItem(library_item.key)
                    item_to_update.fixMatch(match)
                    return True
        return False


def _map_item_from_data(item, item_type):
    """Map Plex API data to MediaItemContainer."""
    guid = getattr(item, "guid", None)
    file = None
    if item_type in ["movie", "episode"]:
        file = getattr(item, "locations", [None])[0].split("/")[-1]
    genres = [genre.tag for genre in getattr(item, "genres", [])]
    available_at = getattr(item, "originallyAvailableAt", None)
    title = getattr(item, "title", None)
    guids = getattr(item, "guids", [])
    key = getattr(item, "key", None)
    season_number = getattr(item, "seasonNumber", None)
    episode_number = getattr(item, "episodeNumber", None)
    art_url = getattr(item, "artUrl", None)

    imdb_id = next(
        (guid.id.split("://")[-1] for guid in guids if "imdb" in guid.id), None
    )
    aired_at = available_at or None

    media_item_data = {
        "title": title,
        "imdb_id": imdb_id,
        "aired_at": aired_at,
        "genres": genres,
        "key": key,
        "guid": guid,
        "art_url": art_url,
        "file": file,
    }

    # Instantiate the appropriate subclass based on 'item_type'
    if item_type == "movie":
        return Movie(media_item_data)
    elif item_type == "show":
        return Show(media_item_data)
    elif item_type == "season":
        media_item_data["number"] = season_number
        return Season(media_item_data)
    elif item_type == "episode":
        media_item_data["number"] = episode_number
        media_item_data["season_number"] = season_number
        return Episode(media_item_data)
    else:
        return None
