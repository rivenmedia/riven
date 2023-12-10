"""Plex library module"""
import copy
import os
import time
from typing import List, Optional
from plexapi import exceptions
from plexapi.server import PlexServer
import requests
from requests.exceptions import ReadTimeout, ConnectionError
from pydantic import BaseModel, HttpUrl
from utils.logger import logger
from utils.settings import settings_manager as settings
from program.media import MediaItemState, MediaItem, Movie, Show, Season, Episode


class PlexSettings(BaseModel):
    user: str
    token: str
    url: HttpUrl
    user_watchlist_rss: Optional[str] = None

class Library:
    """Plex library class"""

    def __init__(self):
        # Plex class library is a necessity
        while True:
            try:
                temp_settings = settings.get("plex")
                self.plex = PlexServer(temp_settings["url"], temp_settings["token"], timeout=15)
                self.settings = PlexSettings(**temp_settings)
                break
            except exceptions.Unauthorized:
                logger.error("Wrong plex token, retrying in 2...")
            except ConnectionError:
                logger.error("Couldnt connect to plex, retrying in 2...")
            time.sleep(2)

    def update_items(self, media_items: List[MediaItem]):
        logger.info("Getting items...")
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
                logger.error(f"Timeout occurred when accessing section: {section.title}")
                continue  # Skip to the next section

            processed_sections.add(section.key)

        matched_items = self.match_items(items, media_items)
        if matched_items:
            logger.info(f"Found {len(matched_items)} new items")
        logger.info("Done!")

    def update_sections(self, media_items: List[MediaItem]):
        """Update plex library section"""
        for section in self.plex.library.sections():
            for item in media_items:
                if item.type == section.type and item.state in [MediaItemState.DOWNLOADING, MediaItemState.PARTIALLY_DOWNLOADING]:
                    if not section.refreshing:
                        section.update()
                        logger.info("Updated section %s", section.title)
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
        logger.info("Matching items...")

        items_to_be_removed = []

        for item in media_items:
            if not item:
                continue
            library_item = next(
                (
                    library_item
                    for library_item in found_items
                    if item.state != MediaItemState.LIBRARY
                    and (
                        item.type == "movie"
                        and library_item.type == "movie"
                        and item.file_name == library_item.file_name
                        or item.type == "show"
                        and library_item.type == "show"
                        and any(
                            location in item.locations
                            for location in library_item.locations
                        )
                        or item.imdb_id == library_item.imdb_id
                    )
                ),
                None,
            )

            if library_item:
                if self._fix_match(library_item, item):
                    items_to_be_removed.append(library_item)

                self._update_item(item, library_item)

                items_to_be_removed.append(library_item)

        for item in items_to_be_removed:
            found_items.remove(item)

        for item in found_items:
            if item in media_items:
                if item.state == MediaItemState.DOWNLOADING:
                    logger.debug(
                        "Could not match library item %s to any media item", item.title
                    )
                    # media_items.change_state(MediaItemState.ERROR)

        logger.info("Done!")
        return found_items

    def _update_item(self, item: MediaItem, library_item: MediaItem):
        """Internal method to use with match_items
        It does some magic to update media items according to library
        items found"""
        if item.type == "show":
            # library_season_numbers = [s.number for s in library_item.seasons]
            # item_season_numbers = [s.number for s in item.seasons]

            # # Check if any season from item is missing in library_item
            # missing_seasons = [
            #     s for s in item_season_numbers if s not in library_season_numbers
            # ]
            # if missing_seasons:
            #     state = MediaItemState.LIBRARY_ONGOING

            for season_index, season in enumerate(item.seasons):
                matching_library_season = next(
                    (s for s in library_item.seasons if s == season),
                    None,
                )

                if (
                    not matching_library_season
                ):  # if there's no matching season in the library item
                    continue

                # If the current item season has fewer or
                # same episodes as the library item season, replace it
                if len(season.episodes) <= len(matching_library_season.episodes):
                    item.seasons[season_index] = matching_library_season
                else:  # If not, we need to check each episode
                    for episode in season.episodes:
                        matching_library_episode = next(
                            (
                                e
                                for e in matching_library_season.episodes
                                if str(episode.number) in e.get_multi_episode_numbers()
                                or e == episode
                            ),
                            None,
                        )

                        # Replace the episode in item with the one from library_item
                        if matching_library_episode:
                            true_episode_number = episode.number
                            # matching_library_episode.number = episode.number
                            episode_index = season.episodes.index(episode)
                            season.episodes[episode_index] = copy.copy(
                                matching_library_episode
                            )
                            season.episodes[episode_index].number = true_episode_number
                            continue
                        # if the episode is not in library item season, change its state
                        else:
                            pass
                            # season.change_state(MediaItemState.LIBRARY_ONGOING)
                            # state = MediaItemState.LIBRARY_ONGOING

        if item.type == "movie":
            item.set("file_name", library_item.file_name)
        else:
            item.set("locations", library_item.locations)
        item.set("guid", library_item.guid)
        item.set("key", library_item.key)
        item.set("art_url", library_item.art_url)

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
    genres = [genre.tag for genre in getattr(item, "genres", [])]
    available_at = getattr(item, "originallyAvailableAt", None)
    title = getattr(item, "title", None)
    year = getattr(item, "year", None)
    guids = getattr(item, "guids", [])
    key = getattr(item, "key", None)
    locations = getattr(item, "locations", [])
    season_number = getattr(item, "seasonNumber", None)
    episode_number = getattr(item, "episodeNumber", None)
    art_url = getattr(item, "artUrl", None)

    imdb_id = next((guid.id.split("://")[-1] for guid in guids if "imdb" in guid.id), None)
    aired_at = available_at.strftime("%Y-%m-%d:%H") if available_at else None

    media_item_data = {
        "title": title,
        "imdb_id": imdb_id,
        "aired_at": aired_at,
        "genres": genres,
        "key": key,
        "guid": guid,
        "art_url": art_url,
        "file_name": os.path.basename(locations[0]) if locations else None,
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