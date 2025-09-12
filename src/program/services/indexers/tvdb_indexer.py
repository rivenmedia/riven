"""TVDB indexer module"""

from datetime import datetime
from types import SimpleNamespace
from typing import Generator, List, Optional

import regex
from kink import di
from loguru import logger

from program.apis.tvdb_api import TVDBApi
from program.media.item import Episode, MediaItem, Season, Show
from program.services.indexers.base import BaseIndexer


class TVDBIndexer(BaseIndexer):
    """TVDB indexer class for TV shows, seasons and episodes"""
    key = "TVDBIndexer"

    def __init__(self):
        super().__init__()
        self.key = "tvdbindexer"
        self.api = di[TVDBApi]

    def run(self, in_item: MediaItem, log_msg: bool = True) -> Generator[Show, None, None]:
        """Run the TVDB indexer for the given item."""
        if not in_item:
            logger.error("Item is None")
            return

        if in_item.type not in ["show", "mediaitem"]:
            logger.debug(f"TVDB indexer skipping incorrect item type: {in_item.log_string}")
            return

        if not (in_item.imdb_id or in_item.tvdb_id):
            logger.error(f"Item {in_item.log_string} does not have an imdb_id or tvdb_id, cannot index it")
            return

        if (item := self._create_show_from_id(in_item.imdb_id, in_item.tvdb_id)):
            item = self.copy_items(in_item, item)
            item.indexed_at = datetime.now()
            if log_msg:
                logger.log("NEW", f"Indexed TV show {item.log_string} (IMDB: {item.imdb_id}, TVDB: {item.tvdb_id})")
            yield item

        logger.error(f"Failed to index TV show with ids: imdb={in_item.imdb_id}, tvdb={in_item.tvdb_id}")
        return
        
    def _create_show_from_id(self, imdb_id: Optional[str] = None, tvdb_id: Optional[str] = None) -> Optional[Show]:
        """Create a show item from TVDB using available IDs."""
        if not imdb_id and not tvdb_id:
            logger.error("No IMDB ID or TVDB ID provided")
            return None

        try:
            # Direct lookup by TVDB ID
            if tvdb_id:
                show_details = self.api.get_series(tvdb_id)
                
                if show_details:
                    # Extract status for season processing
                    show_status = getattr(show_details, "status", None)
                    if hasattr(show_status, "name"):
                        show_status = show_status.name

                    show_item = self._map_show_from_tvdb_data(show_details, imdb_id)
                    if show_item:
                        self._add_seasons_to_show(show_item, show_details, tvdb_id, show_status)
                        return show_item

            # Lookup via IMDB ID
            elif imdb_id:
                search_results = self.api.search_by_imdb_id(imdb_id)
                search_results_data = search_results.data if search_results and search_results.data else None
                
                if search_results_data:
                    if hasattr(search_results_data[0], "movie"):
                        logger.info(f"IMDB ID {imdb_id} is a movie, not a show, skipping")
                        return None
                    elif hasattr(search_results_data[0], "series"):
                        tvdb_id = str(search_results_data[0].series.id)

                        # Get series details
                        show_details = self.api.get_series(tvdb_id)

                        if show_details:
                            # Extract status for season processing
                            show_status = getattr(show_details, "status", None)
                            if hasattr(show_status, "name"):
                                show_status = show_status.name

                            show_item = self._map_show_from_tvdb_data(show_details, imdb_id)
                            if show_item:
                                self._add_seasons_to_show(show_item, show_details, tvdb_id, show_status)
                                return show_item
                    else:
                        logger.log("NOT_FOUND", f"IMDB ID {imdb_id} is not a show, skipping")
                        return None

        except Exception as e:
            logger.error(f"Error creating show from TVDB ID: {e}")

        return None
            
    def _map_show_from_tvdb_data(self, show_data, imdb_id: Optional[str] = None) -> Optional[Show]:
        """Map TVDB show data to our Show object."""
        try:
            if not imdb_id:
                imdb_id: Optional[str] = next((item.id for item in show_data.remoteIds if item.sourceName == "IMDB"), None)

            aired_at = None
            if first_aired := show_data.firstAired:
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            network = None
            if hasattr(show_data, "currentNetwork") and show_data.currentNetwork:
                network = show_data.currentNetwork.name
            elif hasattr(show_data, "originalNetwork") and show_data.originalNetwork:
                network = show_data.originalNetwork.name

            if show_data.aliases:
                aliases = self.api.get_aliases(show_data)
            else:
                aliases = SimpleNamespace()
            slug = (show_data.slug or "").replace("-", " ").title()

            # Handle aliases as SimpleNamespace
            if not hasattr(aliases, "eng"):
                aliases.eng = []
            aliases.eng.append(slug.title())

            title = show_data.name
            if hasattr(show_data, "originalLanguage") and show_data.originalLanguage != "eng":
                translation_result = self.api.get_translation(show_data.id, "eng")
                translation_data = translation_result.data if translation_result else None
                
                if translation_data and hasattr(translation_data, "name") and translation_data.name:
                    title = translation_data.name
                    if hasattr(translation_data, "aliases") and translation_data.aliases:
                        additional_aliases = translation_data.aliases
                        if hasattr(aliases, "eng") and hasattr(additional_aliases, "eng"):
                            aliases.eng.extend([alias for alias in additional_aliases.eng])

            if aliases:
                # get rid of duplicate values - convert to dict, dedupe, convert back
                aliases_dict = {}
                for attr in dir(aliases):
                    if not attr.startswith('_') and hasattr(aliases, attr):
                        value = getattr(aliases, attr)
                        if isinstance(value, list):
                            aliases_dict[attr] = list(set(value))
                aliases = SimpleNamespace(**aliases_dict)

            genres_lower = []
            for g in (show_data.genres or []):
                if hasattr(g, "name"):
                    genre_name = getattr(g, "name", "")
                    if genre_name:
                        genre_str = str(genre_name) if not isinstance(genre_name, str) else genre_name
                        genres_lower.append(genre_str.lower())
            is_anime = ("anime" in genres_lower) or ("animation" in genres_lower and show_data.originalLanguage != "eng")

            # last minute title cleanup to remove '(year)' and '(country code)'
            title = regex.sub(r"\s*\(.*\)\s*$", "", title)

            # Convert aliases SimpleNamespace back to dict for database serialization
            aliases_dict = {}
            if aliases:
                for attr in dir(aliases):
                    if not attr.startswith('_') and hasattr(aliases, attr):
                        aliases_dict[attr] = getattr(aliases, attr)

            show_item = {
                "title": title,
                "year": int(show_data.firstAired.split("-")[0]) if show_data.firstAired else None,
                "tvdb_id": str(show_data.id),
                "tmdb_id": None,
                "imdb_id": imdb_id,
                "aired_at": aired_at,
                "genres": genres_lower,
                "type": "show",
                "requested_at": datetime.now(),
                "overview": show_data.overview,
                "network": network,
                "country": show_data.originalCountry,
                "language": show_data.originalLanguage,
                "is_anime": is_anime,
                "aliases": aliases_dict,
            }

            return Show(show_item)
        except Exception as e:
            logger.error(f"Error mapping show from TVDB data: {str(e)}")

        return None

    def _add_seasons_to_show(self, show: Show, show_details, _tvdb_id: str, show_status: Optional[str] = None):
        """Add seasons and episodes to the given show using TVDB API."""
        try:
            seasons = show_details.seasons
            filtered_seasons: List = [season for season in seasons if season.number != 0 and season.type.type == "official"]
            for season_data in filtered_seasons:
                season_result = self.api.get_season(season_data.id)
                extended_data = season_result.data if season_result else None
                
                if extended_data:
                    if (season_item := self._create_season_from_data(extended_data, show)):
                        if (episodes := extended_data.episodes) and isinstance(episodes, list):
                            for episode in episodes:
                                episode_item = self._create_episode_from_data(episode, season_item)
                                if episode_item:
                                    season_item.add_episode(episode_item)
                        show.add_season(season_item)
        except Exception as e:
            logger.error(f"Error adding seasons to show: {str(e)}")
            
    def _create_season_from_data(self, season_data, show: Show) -> Optional[Season]:
        """Create a Season object from TVDB season data."""
        try:
            season_number = season_data.number
            if season_number is None:
                return None

            aired_at = None

            try:
                # TVDB API doesn't return firstAired for seasons so we use the first episode's aired date
                episodes = season_data.episodes
                if episodes and episodes[0].aired:
                    first_aired = episodes[0].aired
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
            except (ValueError, TypeError):
                pass

            year = None
            if hasattr(season_data, "year") and season_data.year:
                year = int(season_data.year)

            season_item = {
                "number": season_number,
                "tvdb_id": str(season_data.id),
                "title": f"Season {season_number}",
                "aired_at": aired_at,
                "year": year,
                "type": "season",
                "is_anime": show.is_anime,
                "requested_at": datetime.now()
            }
            
            season = Season(season_item)
            season.parent = show
            return season
        except Exception as e:
            logger.error(f"Error creating season from TVDB data: {str(e)}")
            return None

    def _create_episode_from_data(self, episode_data, season: Season) -> Optional[Episode]:
        """Create an Episode object from TVDB episode data."""
        try:
            episode_number = episode_data.number
            if episode_number is None:
                return None

            aired_at = None
            if first_aired := episode_data.aired:
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            year = None
            if hasattr(episode_data, "year") and episode_data.year:
                year = int(episode_data.year)

            episode_item = {
                "number": episode_number,
                "tvdb_id": str(episode_data.id),
                "title": episode_data.name or f"Episode {episode_number}",
                "aired_at": aired_at,
                "year": year,
                "type": "episode",
                "is_anime": season.is_anime,
                "requested_at": datetime.now(),
                "absolute_number": episode_data.absoluteNumber,
            }

            episode = Episode(episode_item)
            episode.parent = season
            return episode
        except Exception as e:
            logger.error(f"Error creating episode from TVDB data: {str(e)}")
            return None
