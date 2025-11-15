"""TVDB indexer module"""

from collections.abc import Generator
from datetime import datetime
from typing import cast

import regex
from kink import di
from loguru import logger

from program.apis.tvdb_api import SeriesRelease, TVDBApi
from program.apis.trakt_api import TraktAPI
from program.media.item import Episode, MediaItem, Season, Show
from program.services.indexers.base import BaseIndexer
from schemas.tvdb import SeasonExtendedRecord


class TVDBIndexer(BaseIndexer):
    """TVDB indexer class for TV shows, seasons and episodes"""

    key = "TVDBIndexer"

    def __init__(self):
        super().__init__()

        self.key = "tvdbindexer"
        self.api = di[TVDBApi]
        self.trakt_api = di[TraktAPI]

    def run(
        self,
        in_item: MediaItem,
        log_msg: bool = True,
    ) -> Generator[Show, None, None]:
        """Run the TVDB indexer for the given item."""

        if not in_item:
            logger.error("Item is None")
            return

        if in_item.type not in ["show", "mediaitem", "season", "episode"]:
            logger.debug(
                f"TVDB indexer skipping incorrect item type: {in_item.log_string}"
            )

            return

        if not (in_item.imdb_id or in_item.tvdb_id):
            logger.error(
                f"Item {in_item.log_string} does not have an imdb_id or tvdb_id, cannot index it"
            )

            return

        # Scenario 1: Fresh indexing - create new Show from API data
        if in_item.type == "mediaitem":
            if item := self._create_show_from_id(in_item.imdb_id, in_item.tvdb_id):
                item = self.copy_items(in_item, item)
                item.indexed_at = datetime.now()

                if log_msg:
                    logger.debug(
                        f"Indexed TV show {item.log_string} (IMDB: {item.imdb_id}, TVDB: {item.tvdb_id})"
                    )

                yield item

                return

        # Scenario 2: Reindexing existing Show/Season/Episode - update in-place
        elif in_item.type in ["show", "season", "episode"]:
            show: Show | None = None

            # Get the root Show object
            if in_item.type == "show":
                show = in_item
            elif in_item.type == "season":
                show = in_item.parent
            elif in_item.type == "episode":
                show = in_item.parent.parent if in_item.parent else None

            if not show:
                logger.error(f"Could not find parent Show for {in_item.log_string}")
                return

            # Fetch fresh metadata from TVDB API
            if self._update_show_metadata(show):
                show.indexed_at = datetime.now()

                if log_msg:
                    logger.debug(
                        f"Reindexed TV show {show.log_string} (IMDB: {show.imdb_id}, TVDB: {show.tvdb_id})"
                    )

                yield show

                return

        logger.error(
            f"Failed to index TV show with ids: imdb={in_item.imdb_id}, tvdb={in_item.tvdb_id}"
        )

        return

    def _update_show_metadata(self, show: Show) -> bool:
        """Update an existing Show object with fresh TVDB metadata.

        Returns True if successful, False otherwise.
        """
        try:
            # Fetch fresh data from TVDB API

            tvdb_id = show.tvdb_id
            imdb_id = show.imdb_id

            if not tvdb_id and not imdb_id:
                logger.error(f"Show {show.log_string} has no TVDB or IMDB ID")
                return False

            # Get show details from API
            show_data = None

            if tvdb_id:
                show_data = self.api.get_series(tvdb_id)
            elif imdb_id:
                search_results = self.api.search_by_imdb_id(imdb_id)

                if search_results and search_results[0].series:
                    tvdb_id = str(search_results[0].series.get("id"))
                    show_data = self.api.get_series(tvdb_id)

            if not show_data:
                logger.error(f"Could not fetch TVDB data for {show.log_string}")
                return False

            # Update Show metadata from API data
            if not imdb_id:
                imdb_id = next(
                    (
                        item.id
                        for item in show_data.remote_ids or []
                        if item.source_name == "IMDB"
                    ),
                    None,
                )

            # Parse aired date
            aired_at = None

            if first_aired := show_data.first_aired:
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            # Extract network
            network = None

            if show_data.latest_network:
                network = show_data.latest_network.name
            elif show_data.original_network:
                network = show_data.original_network.name

            # Get aliases
            aliases = self.trakt_api.get_aliases(imdb_id, "shows")

            if not aliases:
                logger.debug(
                    f"Failed to get aliases from Trakt for imdbid {imdb_id}, using TVDB aliases"
                )

                aliases = self.api.get_aliases(show_data) or {}

            slug = (show_data.slug or "").replace("-", " ").title()
            aliases.setdefault("us", []).append(slug.title())

            # Get title (with translation if needed)
            title = show_data.name
            poster_path = show_data.image

            if show_data.original_language != "eng" and show_data.id:
                if translation := self.api.get_translation(show_data.id, "eng"):
                    if translation.name:
                        title = translation.name
                        if hasattr(translation, "aliases") and translation.aliases:
                            additional_aliases = translation.aliases
                            aliases["us"].extend(
                                [alias for alias in additional_aliases]
                            )

            if aliases:
                aliases = {k: list(set(v)) for k, v in aliases.items()}

            # Extract genres and determine if anime
            genres_lower = [
                (g.name or "").lower()
                for g in (show_data.genres or [])
                if hasattr(g, "name")
            ]
            is_anime = ("anime" in genres_lower) or (
                "animation" in genres_lower and show_data.original_language != "eng"
            )

            # Clean up title
            if title:
                title = regex.sub(r"\s*\(.*\)\s*$", "", title)

            # Extract content rating
            content_rating = None

            if show_data.content_ratings:
                for rating_obj in show_data.content_ratings:
                    if rating_obj.country == "usa":
                        if rating_obj.name:
                            content_rating = rating_obj.name
                            break

            # Extract TVDB status
            tvdb_status = None

            tvdb_status = show_data.release_status

            # Update the Show object's attributes
            show.title = title
            show.poster_path = poster_path
            show.year = (
                int(show_data.first_aired.split("-")[0])
                if show_data.first_aired
                else None
            )
            show.tvdb_id = str(show_data.id)
            show.imdb_id = imdb_id
            show.aired_at = aired_at
            show.genres = genres_lower
            show.network = network
            show.country = show_data.original_country
            show.language = show_data.original_language
            show.is_anime = is_anime
            show.aliases = aliases
            show.release_data = show_data.to_dict()
            show.rating = None  # TVDB doesn't provide ratings
            show.content_rating = content_rating
            show.tvdb_status = tvdb_status

            # Update seasons and episodes (add new ones, update existing ones)
            self._add_seasons_to_show(show, show_data)

            return True

        except Exception as e:
            logger.error(f"Error updating show metadata: {str(e)}")
            return False

    def _create_show_from_id(
        self, imdb_id: str | None = None, tvdb_id: str | None = None
    ) -> Show | None:
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
                        self._add_seasons_to_show(show_item, show_details)
                        return show_item

            # Lookup via IMDB ID
            elif imdb_id:
                search_results = self.api.search_by_imdb_id(imdb_id)

                if search_results:
                    if search_results[0].movie:
                        logger.info(
                            f"IMDB ID {imdb_id} is a movie, not a show, skipping"
                        )

                        return None
                    elif search_results[0].series:
                        tvdb_id = str(search_results[0].series.get("id"))
                        show_details = self.api.get_series(tvdb_id)

                        if show_details:
                            show_item = self._map_show_from_tvdb_data(
                                show_details, imdb_id
                            )

                            if show_item:
                                self._add_seasons_to_show(show_item, show_details)
                                return show_item
                    else:
                        logger.debug(f"IMDB ID {imdb_id} is not a show, skipping")
                        return None

        except Exception as e:
            logger.error(f"Error creating show from TVDB ID: {e}")

        return None

    def _map_show_from_tvdb_data(
        self,
        show_data: SeriesRelease,
        imdb_id: str | None = None,
    ) -> Show | None:
        """Map TVDB show data to our Show object."""
        try:
            if not imdb_id:
                imdb_id = next(
                    (
                        item.id
                        for item in show_data.remote_ids or []
                        if item.source_name == "IMDB"
                    ),
                    None,
                )

            aired_at = None

            if first_aired := show_data.first_aired:
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            network = None

            if show_data.latest_network:
                network = show_data.latest_network.name
            elif show_data.original_network:
                network = show_data.original_network.name

            aliases = self.trakt_api.get_aliases(imdb_id, "shows")

            if not aliases:
                logger.debug(
                    f"Failed to get aliases from Trakt for imdbid {imdb_id}, using TVDB aliases"
                )
                aliases = self.api.get_aliases(show_data) or {}

            slug = (show_data.slug or "").replace("-", " ").title()
            aliases.setdefault("us", []).append(slug.title())

            title = show_data.name
            poster_path = show_data.image

            if show_data.original_language != "eng" and show_data.id:
                if translation := self.api.get_translation(show_data.id, "eng"):
                    if (
                        translation
                        and hasattr(translation, "data")
                        and translation.name
                    ):
                        title = translation.name
                        if hasattr(translation, "aliases") and translation.aliases:
                            additional_aliases = translation.aliases

                            aliases["us"].extend(
                                [alias for alias in additional_aliases]
                            )

            if aliases:
                # get rid of duplicate values
                aliases = {k: list(set(v)) for k, v in aliases.items()}

            genres_lower = [
                (g.name or "").lower()
                for g in (show_data.genres or [])
                if hasattr(g, "name")
            ]
            is_anime = ("anime" in genres_lower) or (
                "animation" in genres_lower and show_data.original_language != "eng"
            )

            # last minute title cleanup to remove '(year)' and '(country code)'
            if title:
                title = regex.sub(r"\s*\(.*\)\s*$", "", title)

            # Extract rating (TVDB doesn't provide ratings directly, set to None)
            rating = None

            # Extract US content rating
            content_rating = None

            if show_data.content_ratings:
                # Look for US content rating
                for rating_obj in show_data.content_ratings:
                    if hasattr(rating_obj, "country") and rating_obj.country == "usa":
                        if hasattr(rating_obj, "name") and rating_obj.name:
                            content_rating = rating_obj.name
                            break

            # Extract TVDB status (Continuing, Ended, Upcoming)
            tvdb_status = None
            if hasattr(show_data, "status") and show_data.status:
                if hasattr(show_data.status, "name"):
                    tvdb_status = show_data.status.name

            show_item = {
                "title": title,
                "poster_path": poster_path,
                "year": (
                    int(show_data.first_aired.split("-")[0])
                    if show_data.first_aired
                    else None
                ),
                "tvdb_id": str(show_data.id),
                "tmdb_id": None,
                "imdb_id": imdb_id,
                "aired_at": aired_at,
                "genres": genres_lower,
                "type": "show",
                "requested_at": datetime.now(),
                "network": network,
                "country": show_data.original_country,
                "language": show_data.original_language,
                "is_anime": is_anime,
                "aliases": aliases,
                "release_data": show_data,
                "rating": rating,
                "content_rating": content_rating,
                "tvdb_status": tvdb_status,
            }

            return Show(show_item)
        except Exception as e:
            logger.error(f"Error mapping show from TVDB data: {str(e)}")

        return None

    def _add_seasons_to_show(
        self,
        show: Show,
        show_details: SeriesRelease,
    ):
        """Add or update seasons and episodes for the given show using TVDB API."""

        try:
            # Build a map of existing seasons by number for quick lookup
            existing_seasons = {cast(int, s.number): s for s in show.seasons}

            filtered_seasons = [
                season
                for season in show_details.seasons or []
                if season.number != 0 and season.type and season.type.type == "official"
            ]

            for season_data in filtered_seasons:
                if season_data.id and (
                    extended_data := self.api.get_season(season_data.id)
                ):
                    season_number = extended_data.number

                    if season_number is None:
                        continue

                    # Check if this season already exists
                    if season_number in existing_seasons:
                        # Update existing season with fresh metadata
                        season_item = existing_seasons[season_number]

                        if season_item.poster_path is None:
                            season_item.poster_path = show.poster_path

                        self._update_season_metadata(season_item, extended_data)
                    else:
                        # Create new season
                        season_item = self._create_season_from_data(extended_data, show)

                        if not season_item:
                            continue

                        show.add_season(season_item)

                    # Handle episodes for this season
                    if (episodes := extended_data.episodes) and isinstance(
                        episodes, list
                    ):
                        # Build a map of existing episodes by number
                        existing_episodes: dict[int, Episode] = {
                            cast(int, e.number): e for e in season_item.episodes
                        }

                        for episode_data in episodes:
                            episode_number = episode_data.number

                            if episode_number is None:
                                continue

                            # Check if this episode already exists
                            if episode_number in existing_episodes:
                                # Update existing episode with fresh metadata
                                episode_item = existing_episodes[episode_number]

                                self._update_episode_metadata(
                                    episode_item, episode_data
                                )
                            else:
                                # Create new episode
                                episode_item = self._create_episode_from_data(
                                    episode_data, season_item
                                )

                                if episode_item:
                                    season_item.add_episode(episode_item)
        except Exception as e:
            logger.error(f"Error adding/updating seasons to show: {str(e)}")

    def _update_season_metadata(
        self,
        season: Season,
        season_data: SeasonExtendedRecord,
    ):
        """Update an existing Season object with fresh TVDB metadata."""
        try:
            # Parse aired date from first episode
            aired_at = None

            try:
                episodes = season_data.episodes

                if episodes and episodes[0].aired:
                    aired_at = datetime.strptime(episodes[0].aired, "%Y-%m-%d")
            except (ValueError, TypeError, IndexError):
                pass

            # Extract year
            year = int(season_data.year) if season_data.year else None

            poster_path = season_data.image

            # Update season attributes
            season.tvdb_id = str(season_data.id)
            season.title = f"Season {season_data.number}"
            season.poster_path = poster_path
            season.aired_at = aired_at
            season.year = year

            # Note: is_anime and other attributes are inherited from show via __getattribute__

        except Exception as e:
            logger.error(f"Error updating season metadata: {str(e)}")

    def _create_season_from_data(self, season_data, show: Show) -> Season | None:
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

            poster_path = None
            if hasattr(season_data, "image") and season_data.image:
                poster_path = season_data.image
            else:
                poster_path = show.poster_path

            year = None
            if hasattr(season_data, "year") and season_data.year:
                year = int(season_data.year)

            season_item = {
                "number": season_number,
                "tvdb_id": str(season_data.id),
                "title": f"Season {season_number}",
                "poster_path": poster_path,
                "aired_at": aired_at,
                "year": year,
                "type": "season",
                "is_anime": show.is_anime,
                "requested_at": datetime.now(),
            }

            season = Season(season_item)
            season.parent = show
            return season
        except Exception as e:
            logger.error(f"Error creating season from TVDB data: {str(e)}")
            return None

    def _update_episode_metadata(self, episode: Episode, episode_data):
        """Update an existing Episode object with fresh TVDB metadata."""
        try:
            # Parse aired date
            aired_at = None
            if first_aired := episode_data.aired:
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            # Extract year
            year = None
            if hasattr(episode_data, "year") and episode_data.year:
                year = int(episode_data.year)

            # Update episode attributes
            episode.tvdb_id = str(episode_data.id)
            episode.title = episode_data.name or f"Episode {episode_data.number}"
            episode.poster_path = episode_data.poster_path
            episode.aired_at = aired_at
            episode.year = year
            episode.absolute_number = episode_data.absoluteNumber
            # Note: is_anime and other attributes are inherited from show via __getattribute__

        except Exception as e:
            logger.error(f"Error updating episode metadata: {str(e)}")

    def _create_episode_from_data(self, episode_data, season: Season) -> Episode | None:
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
                "poster_path": episode_data.poster_path,
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
