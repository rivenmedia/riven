"""TVDB indexer module"""

from datetime import datetime
from typing import Generator, Optional, Union

from kink import di
from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.indexers.base import BaseIndexer
from program.apis.tvdb_api import TVDBApi


class TVDBIndexer(BaseIndexer):
    """TVDB indexer class for TV shows, seasons and episodes"""
    key = "TVDBIndexer"

    def __init__(self):
        super().__init__()
        self.key = "tvdbindexer"
        self.ids = []
        self.api = di[TVDBApi]

    def run(self, in_item: MediaItem, log_msg: bool = True) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """Run the TVDB indexer for the given item."""
        if not in_item:
            logger.error("Item is None")
            return

        # Get available IDs
        imdb_id = in_item.imdb_id
        tvdb_id = in_item.tvdb_id
        
        if not (imdb_id or tvdb_id):
            logger.error(f"Item {in_item.log_string} does not have an imdb_id or tvdb_id, cannot index it")
            return

        if imdb_id in self.failed_ids or tvdb_id in self.failed_ids:
            logger.debug(f"Skipping previously failed IMDB ID: {imdb_id} or TVDB ID: {tvdb_id}")
            return

        # TVDB indexer will primarily handle TV shows
        if in_item.type == "movie":
            logger.debug(f"TVDB indexer skipping movie item: {in_item.log_string}")
            return

        # Get TV show details from TVDB
        item = self._create_show_from_ids(imdb_id, tvdb_id)
        
        if not item:
            logger.error(f"Failed to index TV show with ids: imdb={imdb_id}, tvdb={tvdb_id}")
            if imdb_id:
                self.failed_ids.add(imdb_id)
            return

        item = self.copy_items(in_item, item)
        item.indexed_at = datetime.now()

        if log_msg:
            logger.info(f"Indexed TV show {item.log_string} (IMDB: {item.imdb_id}, TVDB: {item.tvdb_id})")

        yield item
        
    def _create_show_from_ids(self, imdb_id: Optional[str] = None, tvdb_id: Optional[str] = None) -> Optional[Show]:
        """Create a show item from TVDB using available IDs."""
        if not imdb_id and not tvdb_id:
            logger.error("No IMDB ID or TVDB ID provided")
            return None
            
        # First try TVDB ID if available
        if tvdb_id:
            try:
                # Get show details
                show_details = self.api.get_series(tvdb_id)
                if show_details:
                    # Create show item
                    show_item = self._map_show_from_tvdb_data(show_details)
                    if show_item:
                        # Add seasons and episodes
                        self._add_seasons_to_show(show_item, show_details, tvdb_id)
                        return show_item
            except Exception as e:
                logger.error(f"Error creating show from TVDB ID: {str(e)}")
                
        # If that fails or no TVDB ID, try IMDB ID
        if imdb_id:
            try:
                # Search by IMDB ID
                search_results = self.api.search_by_imdb_id(imdb_id)
                if search_results and search_results.get('data'):
                    # Get the first result and fetch full details
                    tvdb_id = str(search_results['data'][0]['series']['id'])
                    return self._create_show_from_ids(None, tvdb_id)
            except Exception as e:
                logger.error(f"Error creating show from IMDB ID: {str(e)}")
                
        return None
            
    def _map_show_from_tvdb_data(self, show_data: dict) -> Optional[Show]:
        """Map TVDB show data to our Show object."""
        try:
            # Convert aired date to datetime
            aired_at = None
            if first_aired := show_data.get('firstAired'):
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass
                    
            # Extract genres
            genres = []
            if genre_data := show_data.get('genres'):
                genres = [genre.get('name').lower() for genre in genre_data]
                
            # Get network
            network = None

            if current_network := show_data.get('currentNetwork'):
                network = current_network.get('name')
            elif original_network := show_data.get('originalNetwork'):
                network = original_network.get('name')
            
            tmdb_id = None
            if external_ids := show_data.get('remoteIds'):
                # find item in external_ids with sourceName 'TheMovieDB.com'
                tmdb_id = next((item.get('id') for item in external_ids if item.get('sourceName') == 'TheMovieDB.com'), None)

            # Create show item
            show_item = {
                "title": show_data.get('name'),
                "year": int(show_data.get('firstAired', '').split('-')[0]) if show_data.get('firstAired') else None,
                "tvdb_id": str(show_data.get('id')),
                "tmdb_id": str(tmdb_id) if tmdb_id else None,
                "imdb_id": show_data.get('imdbId'),
                "aired_at": aired_at,
                "genres": genres,
                "type": "show",
                "requested_at": datetime.now(),
                "overview": show_data.get('overview'),
                "network": network,
                "country": show_data.get('originalCountry'),
                "language": show_data.get('originalLanguage'),
                "is_anime": 'anime' in genres or ('animation' in genres and show_data.get('originalLanguage') != 'en')
            }
            
            return Show(show_item)
        except Exception as e:
            logger.error(f"Error mapping show from TVDB data: {str(e)}")
            return None

    def _add_seasons_to_show(self, show: Show, show_details: dict, tvdb_id: str):
        """Add seasons and episodes to the given show using TVDB API."""
        try:

            seasons = show_details.get('seasons', [])
            # Filter out specials (usually season 0) and non-official seasons (for example absolute ordering)
            filtered_seasons = [season for season in seasons if season.get('number') != 0 and season.get('type').get('type') == 'official']

            for season_data in filtered_seasons:
                extended_data = self.api.get_season(season_data.get('id')).get('data')

                # Skip specials (usually season 0)
                if extended_data.get('number') == 0:
                    continue
                    
                # Create season item
                season_item = self._create_season_from_data(extended_data, show)
                if not season_item:
                    continue

                episodes = extended_data.get('episodes', [])
                if not episodes or not isinstance(episodes, list):
                    continue
                    
                for episode in episodes:
                    # Create episode item
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
                
            # Convert aired date to datetime
            aired_at = None

            # TODO: Check if this is correct, TVDB API doesn't return firstAired for seasons so we use the first episode's aired date
            if first_aired := season_data.get('episodes')[0].get('aired'):
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass
                    
            # Create season item
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
                
            # Convert aired date to datetime
            aired_at = None
            if first_aired := episode_data.get('aired'):
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass
                    
            # Create episode item
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
