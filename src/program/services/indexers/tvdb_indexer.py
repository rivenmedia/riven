"""TVDB indexer module"""

from datetime import datetime
from typing import Generator, List, Optional

from kink import di
from loguru import logger

from program.media.item import MediaItem, Show, Season, Episode
from program.services.indexers.base import BaseIndexer
from program.apis.tvdb_api import TVDBApi


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
                logger.info(f"Indexed TV show {item.log_string} (IMDB: {item.imdb_id}, TVDB: {item.tvdb_id})")
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
                    show_item = self._map_show_from_tvdb_data(show_details, imdb_id)
                    if show_item:
                        self._add_seasons_to_show(show_item, show_details, tvdb_id)
                        return show_item

            # Lookup via IMDB ID
            elif imdb_id:
                search_results = self.api.search_by_imdb_id(imdb_id)
                if search_results and search_results.get("data"):
                    tvdb_id = str(search_results["data"][0]["series"]["id"])
                    show_details = self.api.get_series(tvdb_id)
                    if show_details:
                        show_item = self._map_show_from_tvdb_data(show_details, imdb_id)
                        if show_item:
                            self._add_seasons_to_show(show_item, show_details, tvdb_id)
                            return show_item

        except Exception as e:
            logger.error(f"Error creating show from TVDB ID: {e}")

        if tvdb_id:
            logger.error(f"Failed to get show details for TVDB ID: {tvdb_id}")
        elif imdb_id:
            logger.error(f"Failed to get show details for IMDB ID: {imdb_id}")
        else:
            logger.error("Failed to get show details for unknown ID")

        return None
            
    def _map_show_from_tvdb_data(self, show_data: dict = {}, imdb_id: Optional[str] = None) -> Optional[Show]:
        """Map TVDB show data to our Show object."""
        try:

            if not imdb_id:
                imdb_id: Optional[str] = next((item.get('id') for item in show_data.get('remoteIds') if item.get('sourceName') == 'IMDB'), None)

            aired_at = None
            if first_aired := show_data.get('firstAired'):
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            network = None
            if current_network := show_data.get('currentNetwork'):
                network = current_network.get('name')
            elif original_network := show_data.get('originalNetwork'):
                network = original_network.get('name')

            aliases = self.api.get_aliases(show_data) or {}
            slug = (show_data.get('slug') or '').replace('-', ' ').title()
            aliases.setdefault('eng', []).append(slug.title())

            title = None
            if show_data.get('originalLanguage') != 'eng':
                if (translation := self.api.get_translation(show_data.get('id'), "eng")):
                    aliases["eng"].extend([alias for alias in translation.get('data').get('aliases')])
                    title = translation.get('data').get('name')

            if not title:
                title = show_data.get('name')

            if aliases:
                # get rid of duplicate values
                aliases = {k: list(set(v)) for k, v in aliases.items()}

            genres_lower = [
                (g.get('name') or '').lower() for g in (show_data.get('genres') or []) if isinstance(g, dict)
            ]
            is_anime = ('anime' in genres_lower) or ('animation' in genres_lower and show_data.get('originalLanguage') != 'eng')

            show_item = {
                "title": title,
                "year": int(show_data.get('firstAired', '').split('-')[0]) if show_data.get('firstAired') else None,
                "tvdb_id": str(show_data.get('id')),
                "tmdb_id": None,
                "imdb_id": imdb_id,
                "aired_at": aired_at,
                "genres": genres_lower,
                "type": "show",
                "requested_at": datetime.now(),
                "overview": show_data.get('overview'),
                "network": network,
                "country": show_data.get('originalCountry'),
                "language": show_data.get('originalLanguage'),
                "is_anime": is_anime,
                "aliases": aliases,
            }

            return Show(show_item)
        except Exception as e:
            logger.error(f"Error mapping show from TVDB data: {str(e)}")

        return None

    def _add_seasons_to_show(self, show: Show, show_details: dict, tvdb_id: str):
        """Add seasons and episodes to the given show using TVDB API."""
        try:
            seasons = show_details.get('seasons', [])
            filtered_seasons: List[dict] = [season for season in seasons if season.get('number') != 0 and season.get('type').get('type') == 'official']
            for season_data in filtered_seasons:
                if (extended_data := self.api.get_season(season_data.get('id')).get('data')):
                    if (season_item := self._create_season_from_data(extended_data, show)):
                        if (episodes := extended_data.get('episodes', [])) and isinstance(episodes, list):
                            for episode in episodes:
                                episode_item = self._create_episode_from_data(episode, season_item)
                                if episode_item:
                                    season_item.add_episode(episode_item)
                        show.add_season(season_item)
        except Exception as e:
            logger.error(f"Error adding seasons to show: {str(e)}")
            
    def _create_season_from_data(self, season_data: dict, show: Show) -> Optional[Season]:
        """Create a Season object from TVDB season data."""
        try:
            season_number = season_data.get('number')
            if season_number is None:
                return None

            aired_at = None

            try:
                # TVDB API doesn't return firstAired for seasons so we use the first episode's aired date
                episodes = season_data.get('episodes')
                if episodes and episodes[0].get('aired'):
                    first_aired = episodes[0].get('aired')
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
            except (ValueError, TypeError):
                pass

            season_item = {
                "number": season_number,
                "tvdb_id": str(season_data.get('id')),
                "title": season_data.get('name') or f"Season {season_number}",
                "aired_at": aired_at,
                "year": int(season_data.get('year')) if season_data.get('year') else None,
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

    def _create_episode_from_data(self, episode_data: dict, season: Season) -> Optional[Episode]:
        """Create an Episode object from TVDB episode data."""
        try:
            episode_number = episode_data.get('number')
            if episode_number is None:
                return None

            aired_at = None
            if first_aired := episode_data.get('aired'):
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            episode_item = {
                "number": episode_number,
                "tvdb_id": str(episode_data.get('id')),
                "title": episode_data.get('name') or f"Episode {episode_number}",
                "aired_at": aired_at,
                "year": int(episode_data.get('year')) if episode_data.get('year') else None,
                "type": "episode",
                "is_anime": season.is_anime,
                "requested_at": datetime.now()
            }

            episode = Episode(episode_item)
            episode.parent = season
            return episode
        except Exception as e:
            logger.error(f"Error creating episode from TVDB data: {str(e)}")
            return None
