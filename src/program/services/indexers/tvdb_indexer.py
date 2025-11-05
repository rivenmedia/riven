"""TVDB indexer module"""

from datetime import datetime
from typing import Generator, List, Optional

import regex
from kink import di
from loguru import logger

from program.apis.trakt_api import TraktAPI
from program.apis.tvdb_api import TVDBApi
from program.media.item import Episode, MediaItem, Season, Show
from program.services.indexers.base import BaseIndexer
from program.settings.manager import settings_manager


class TVDBIndexer(BaseIndexer):
    """TVDB indexer class for TV shows, seasons and episodes"""

    key = "TVDBIndexer"

    def __init__(self):
        super().__init__()
        self.key = "tvdbindexer"
        self.api = di[TVDBApi]
        self.trakt_api = di[TraktAPI]

    def run(
        self, in_item: MediaItem, log_msg: bool = True
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
            language_preference = self._get_language_preference(show)

            if tvdb_id:
                show_data = self.api.get_series(tvdb_id, language_preference)
            elif imdb_id:
                search_results = self.api.search_by_imdb_id(imdb_id)
                if search_results and search_results.data:
                    if hasattr(search_results.data[0], "series"):
                        tvdb_id = str(search_results.data[0].series.id)
                        show_data = self.api.get_series(tvdb_id, language_preference)

            if not show_data:
                logger.error(f"Could not fetch TVDB data for {show.log_string}")
                return False

            # Update Show metadata from API data
            if not imdb_id:
                imdb_id = next(
                    (
                        item.id
                        for item in show_data.remoteIds
                        if item.sourceName == "IMDB"
                    ),
                    None,
                )

            # Parse aired date
            aired_at = None
            if first_aired := show_data.firstAired:
                try:
                    aired_at = datetime.strptime(first_aired, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            # Extract network
            network = None
            if hasattr(show_data, "currentNetwork") and show_data.currentNetwork:
                network = show_data.currentNetwork.name
            elif hasattr(show_data, "originalNetwork") and show_data.originalNetwork:
                network = show_data.originalNetwork.name

            # Get aliases
            aliases = self.trakt_api.get_aliases(imdb_id, "shows") or {}
            if not aliases:
                logger.debug(
                    f"Failed to get aliases from Trakt for imdbid {imdb_id}, using TVDB aliases"
                )
                tvdb_aliases = self.api.get_aliases(show_data) or {}
                # Normalize all English variants to use "eng" as the primary key
                aliases = {}
                english_aliases = []
                for lang in ["eng", "en", "us", "gb"]:
                    if lang in tvdb_aliases:
                        english_aliases.extend(tvdb_aliases[lang])
                if english_aliases:
                    aliases["eng"] = english_aliases
                # Add any other language aliases
                for lang, lang_aliases in tvdb_aliases.items():
                    if lang not in ["eng", "en", "us", "gb"]:
                        aliases[lang] = lang_aliases
            else:
                # Normalize Trakt aliases to use "eng" for English variants
                english_aliases = []
                for lang in ["eng", "en", "us", "gb"]:
                    if lang in aliases:
                        english_aliases.extend(aliases.pop(lang))
                if english_aliases:
                    aliases["eng"] = english_aliases

            slug = (show_data.slug or "").replace("-", " ").title()
            aliases.setdefault("eng", []).append(slug.title())

            # Get title (with translation if needed)
            title = show_data.name
            poster_path = show_data.image
            if (
                hasattr(show_data, "originalLanguage")
                and show_data.originalLanguage != "eng"
            ):
                if translation := self.api.get_translation(show_data.id, "eng"):
                    if (
                        translation
                        and hasattr(translation, "data")
                        and translation.data.name
                    ):
                        title = translation.data.name
                        if (
                            hasattr(translation.data, "aliases")
                            and translation.data.aliases
                        ):
                            additional_aliases = translation.data.aliases
                            aliases.setdefault("eng", []).extend(
                                [alias for alias in additional_aliases]
                            )

            # if aliases:
            #     aliases = {k: list(set(v)) for k, v in aliases.items()}

            # Extract genres and determine if anime
            genres_lower = [
                (g.name or "").lower()
                for g in (show_data.genres or [])
                if hasattr(g, "name")
            ]
            is_anime = ("anime" in genres_lower) or (
                "animation" in genres_lower and show_data.originalLanguage != "eng"
            )

            # Clean up title
            title = regex.sub(r"\s*\(.*\)\s*$", "", title)
            release_data = self.api.get_series_release_data(show_data) or {}

            # Extract content rating
            content_rating = None
            if hasattr(show_data, "contentRatings") and show_data.contentRatings:
                for rating_obj in show_data.contentRatings:
                    if hasattr(rating_obj, "country") and rating_obj.country == "usa":
                        if hasattr(rating_obj, "name") and rating_obj.name:
                            content_rating = rating_obj.name
                            break

            # Extract TVDB status
            tvdb_status = None
            if hasattr(show_data, "status") and show_data.status:
                if hasattr(show_data.status, "name"):
                    tvdb_status = show_data.status.name

            # Update the Show object's attributes
            show.title = title
            show.poster_path = poster_path
            show.year = (
                int(show_data.firstAired.split("-")[0])
                if show_data.firstAired
                else None
            )
            show.tvdb_id = str(show_data.id)
            show.imdb_id = imdb_id
            show.aired_at = aired_at
            show.genres = genres_lower
            show.network = network
            show.country = show_data.originalCountry
            show.language = show_data.originalLanguage
            show.is_anime = is_anime
            show.aliases = aliases
            show.release_data = release_data
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
        self, imdb_id: Optional[str] = None, tvdb_id: Optional[str] = None
    ) -> Optional[Show]:
        """Create a show item from TVDB using available IDs."""
        if not imdb_id and not tvdb_id:
            logger.error("No IMDB ID or TVDB ID provided")
            return None

        try:
            # Get language preference based on global settings for initial lookup
            language_preference = self._get_global_language_preference()

            # Direct lookup by TVDB ID
            if tvdb_id:
                show_details = self.api.get_series(tvdb_id, language_preference)
                if show_details:
                    show_item = self._map_show_from_tvdb_data(show_details, imdb_id)
                    if show_item:
                        self._add_seasons_to_show(show_item, show_details)
                        return show_item

            # Lookup via IMDB ID
            elif imdb_id:
                search_results = self.api.search_by_imdb_id(imdb_id)
                if search_results and search_results.data:
                    if hasattr(search_results.data[0], "movie"):
                        logger.info(
                            f"IMDB ID {imdb_id} is a movie, not a show, skipping"
                        )
                        return None
                    elif hasattr(search_results.data[0], "series"):
                        tvdb_id = str(search_results.data[0].series.id)
                        show_details = self.api.get_series(tvdb_id, language_preference)
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
        self, show_data, imdb_id: Optional[str] = None
    ) -> Optional[Show]:
        """Map TVDB show data to our Show object."""
        try:
            if not imdb_id:
                imdb_id: Optional[str] = next(
                    (
                        item.id
                        for item in show_data.remoteIds
                        if item.sourceName == "IMDB"
                    ),
                    None,
                )

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

            aliases = self.trakt_api.get_aliases(imdb_id, "shows") or {}
            if not aliases:
                logger.debug(
                    f"Failed to get aliases from Trakt for imdbid {imdb_id}, using TVDB aliases"
                )
                tvdb_aliases = self.api.get_aliases(show_data) or {}
                # Normalize all English variants to use "eng" as the primary key
                aliases = {}
                english_aliases = []
                for lang in ["eng", "en", "us", "gb"]:
                    if lang in tvdb_aliases:
                        english_aliases.extend(tvdb_aliases[lang])
                if english_aliases:
                    aliases["eng"] = english_aliases
                # Add any other language aliases
                for lang, lang_aliases in tvdb_aliases.items():
                    if lang not in ["eng", "en", "us", "gb"]:
                        aliases[lang] = lang_aliases
            else:
                # Normalize Trakt aliases to use "eng" for English variants
                english_aliases = []
                for lang in ["eng", "en", "us", "gb"]:
                    if lang in aliases:
                        english_aliases.extend(aliases.pop(lang))
                if english_aliases:
                    aliases["eng"] = english_aliases

            slug = (show_data.slug or "").replace("-", " ").title()
            aliases.setdefault("eng", []).append(slug.title())

            title = show_data.name
            poster_path = show_data.image
            if (
                hasattr(show_data, "originalLanguage")
                and show_data.originalLanguage != "eng"
            ):
                if translation := self.api.get_translation(show_data.id, "eng"):
                    if (
                        translation
                        and hasattr(translation, "data")
                        and translation.data.name
                    ):
                        title = translation.data.name
                        if (
                            hasattr(translation.data, "aliases")
                            and translation.data.aliases
                        ):
                            additional_aliases = translation.data.aliases
                            aliases.setdefault("eng", []).extend(
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
                "animation" in genres_lower and show_data.originalLanguage != "eng"
            )

            # last minute title cleanup to remove '(year)' and '(country code)'
            title = regex.sub(r"\s*\(.*\)\s*$", "", title)
            release_data = self.api.get_series_release_data(show_data) or {}

            # Extract rating (TVDB doesn't provide ratings directly, set to None)
            rating = None

            # Extract US content rating
            content_rating = None
            if hasattr(show_data, "contentRatings") and show_data.contentRatings:
                # Look for US content rating
                for rating_obj in show_data.contentRatings:
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
                    int(show_data.firstAired.split("-")[0])
                    if show_data.firstAired
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
                "country": show_data.originalCountry,
                "language": show_data.originalLanguage,
                "is_anime": is_anime,
                "aliases": aliases,
                "release_data": release_data,
                "rating": rating,
                "content_rating": content_rating,
                "tvdb_status": tvdb_status,
            }

            return Show(show_item)
        except Exception as e:
            logger.error(f"Error mapping show from TVDB data: {str(e)}")

        return None

    def _add_seasons_to_show(self, show: Show, show_details):
        """Add or update seasons and episodes for the given show using TVDB API."""
        try:
            # Build a map of existing seasons by number for quick lookup
            existing_seasons = (
                {s.number: s for s in show.seasons} if show.seasons else {}
            )

            seasons = show_details.seasons
            filtered_seasons: List = [
                season
                for season in seasons
                if season.number != 0 and season.type.type == "official"
            ]

            for season_data in filtered_seasons:
                # Get language preference for season API call
                language_preference = self._get_global_language_preference()
                if extended_data := self.api.get_season(
                    season_data.id, language_preference
                ).data:
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
                        existing_episodes = (
                            {e.number: e for e in season_item.episodes}
                            if season_item.episodes
                            else {}
                        )

                        for episode_data in episodes:
                            episode_number = episode_data.number
                            if episode_number is None:
                                continue

                            # Fetch detailed episode data with language preference
                            language_preference = self._get_global_language_preference()
                            detailed_episode_data = None
                            if hasattr(episode_data, "id") and episode_data.id:
                                detailed_episode_data = self.api.get_episode(
                                    str(episode_data.id), language_preference
                                )

                            # Use detailed data if available, otherwise fallback to episode_data
                            final_episode_data = (
                                detailed_episode_data
                                if detailed_episode_data
                                else episode_data
                            )
                            final_episode_data.poster_path = season_item.poster_path

                            # Check if this episode already exists
                            if episode_number in existing_episodes:
                                # Update existing episode with fresh metadata
                                episode_item = existing_episodes[episode_number]
                                self._update_episode_metadata(
                                    episode_item, final_episode_data
                                )
                            else:
                                # Create new episode
                                episode_item = self._create_episode_from_data(
                                    final_episode_data, season_item
                                )
                                if episode_item:
                                    season_item.add_episode(episode_item)
        except Exception as e:
            logger.error(f"Error adding/updating seasons to show: {str(e)}")

    def _update_season_metadata(self, season: Season, season_data):
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
            year = None
            if hasattr(season_data, "year") and season_data.year:
                year = int(season_data.year)

            poster_path = None
            if hasattr(season_data, "image") and season_data.image:
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
            episode.title = self._get_episode_title_with_fallback(episode_data, episode)
            episode.poster_path = episode_data.poster_path
            episode.aired_at = aired_at
            episode.year = year
            episode.absolute_number = episode_data.absoluteNumber
            # Note: is_anime and other attributes are inherited from show via __getattribute__

        except Exception as e:
            logger.error(f"Error updating episode metadata: {str(e)}")

    def _create_episode_from_data(
        self, episode_data, season: Season
    ) -> Optional[Episode]:
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
                "title": "temp_title",  # Temporary, will be updated below
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

            # Now set the title using the fallback system with proper context
            episode.title = self._get_episode_title_with_fallback(episode_data, episode)
            episode.parent = season
            return episode
        except Exception as e:
            logger.error(f"Error creating episode from TVDB data: {str(e)}")
            return None

    def _get_language_preference(self, item: MediaItem) -> Optional[List[str]]:
        """Get language preference for TVDB API calls based on settings."""
        try:
            scraping_settings = settings_manager.settings.scraping

            # Return configured language preference if any languages are specified
            if scraping_settings.preferred_languages:
                return scraping_settings.preferred_languages

            # No language preference configured, use TVDB default
            return None

        except Exception as e:
            logger.debug(f"Error getting language preference: {e}")
            return None

    def _get_global_language_preference(self) -> Optional[List[str]]:
        """Get global language preference for TVDB API calls when item context is not available."""
        try:
            scraping_settings = settings_manager.settings.scraping

            # Return configured language preference if any languages are specified
            if scraping_settings.preferred_languages:
                return scraping_settings.preferred_languages

            # No language preference configured, use TVDB default
            return None

        except Exception as e:
            logger.debug(f"Error getting global language preference: {e}")
            return None

    def _get_episode_title_with_fallback(self, episode_data, episode_item=None) -> str:
        """Get episode title with English fallback strategies."""
        try:
            original_title = episode_data.name
            episode_number = episode_data.number

            # If we already have an English title, use it
            if original_title and self._is_likely_english(original_title):
                return original_title

            # Strategy 1: Try to get English translation from TVDB
            if hasattr(episode_data, "id") and episode_data.id:
                try:
                    translation = self.api.get_episode_translation(
                        str(episode_data.id), "eng"
                    )
                    if (
                        translation
                        and hasattr(translation, "data")
                        and translation.data
                    ):
                        if hasattr(translation.data, "name") and translation.data.name:
                            english_title = translation.data.name
                            if english_title and self._is_likely_english(english_title):
                                logger.debug(
                                    f"Found English translation for episode {episode_data.id}: {english_title}"
                                )
                                return english_title
                except Exception as e:
                    logger.debug(f"Error getting episode translation: {e}")

            # Strategy 2: Generate descriptive English title based on context
            if episode_item and hasattr(episode_item, "parent") and episode_item.parent:
                season = episode_item.parent
                if hasattr(season, "parent") and season.parent:
                    show = season.parent
                    show_title = show.title
                    season_number = getattr(season, "number", 1)

                    # For anime, create more descriptive titles
                    if getattr(show, "is_anime", False):
                        return f"{show_title} - Season {season_number} Episode {episode_number}"
                    else:
                        return f"Episode {episode_number}"

            # Strategy 3: Basic fallback with episode number
            if episode_number:
                return f"Episode {episode_number}"

            # Strategy 4: Last resort - use original title even if it's not English
            return original_title or "Unknown Episode"

        except Exception as e:
            logger.error(f"Error in episode title fallback: {e}")
            return (
                f"Episode {episode_data.number}"
                if episode_data.number
                else "Unknown Episode"
            )

    def _is_likely_english(self, text: str) -> bool:
        """Check if text is likely in English (basic heuristic)."""
        if not text:
            return False

        # Check for common English words/patterns
        english_indicators = [
            " the ",
            " and ",
            " of ",
            " to ",
            " a ",
            " in ",
            " is ",
            " it ",
            " you ",
            " that ",
            " he ",
            " was ",
            " for ",
            " on ",
            " are ",
            " as ",
            " with ",
            " his ",
            " they ",
            " at ",
            " be ",
            " this ",
            " have ",
            " from ",
            " or ",
            " one ",
            " had ",
            " by ",
            " words",
            " but ",
            " not ",
            " what ",
            " all ",
            " were ",
            " we ",
            " when ",
        ]

        text_lower = text.lower()

        # If it contains common English words, likely English
        for indicator in english_indicators:
            if indicator in text_lower:
                return True

        # Check if it's mostly ASCII characters (rough heuristic)
        try:
            ascii_chars = sum(1 for c in text if ord(c) < 128)
            total_chars = len(text)
            if total_chars > 0 and (ascii_chars / total_chars) > 0.8:
                return True
        except:
            pass

        return False
