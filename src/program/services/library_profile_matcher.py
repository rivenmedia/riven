"""Library Profile Matcher Service

Evaluates MediaItem metadata against library profile filter rules to determine
which library profiles a media item should be placed in.
"""

from typing import List, Optional
from loguru import logger

from program.media.item import MediaItem
from program.settings.models import LibraryProfile, LibraryProfileFilterRules
from program.settings.manager import settings_manager


class LibraryProfileMatcher:
    """
    Service for matching MediaItems against library profile filter rules.

    Evaluates metadata-only filters (genres, rating, year, etc.) to determine
    which library profiles a media item belongs to.

    Note: Cannot filter on scraping results (resolution, codec, HDR) as those
    are not available from indexers - only from scrapers.
    """

    def __init__(self):
        self.key = "library_profile_matcher"

    def get_matching_profiles(self, item: MediaItem) -> List[str]:
        """
        Get list of library profile keys that match the given MediaItem.

        Evaluates all enabled library profiles and returns those whose filter
        rules match the item's metadata. Profiles are returned in the order
        they appear in settings (dict insertion order).

        Args:
            item: MediaItem to evaluate

        Returns:
            List of profile keys (e.g., ['kids', 'anime']) in settings order.
            Empty list if no profiles match.

        Example:
            >>> matcher = LibraryProfileMatcher()
            >>> profiles = matcher.get_matching_profiles(movie_item)
            >>> # ['kids', 'family']  # Movie matches both profiles
        """
        profiles = settings_manager.settings.filesystem.library_profiles or {}

        matching_profiles = []

        for profile_key, profile in profiles.items():
            # Skip disabled profiles
            if not profile.enabled:
                continue

            # Evaluate filter rules
            if self._matches_filter_rules(item, profile.filter_rules):
                matching_profiles.append(profile_key)

        return matching_profiles

    def _matches_filter_rules(
        self, item: MediaItem, rules: LibraryProfileFilterRules
    ) -> bool:
        """
        Check if a MediaItem matches the given filter rules.

        All specified rules must match (AND logic). If a rule is None/empty,
        it's considered a match (no filtering on that criterion).

        Args:
            item: MediaItem to evaluate
            rules: Filter rules to evaluate against

        Returns:
            True if all specified rules match, False otherwise
        """
        # Content type filter (movie, show, season, episode)
        # Hierarchical matching: "show" matches show/season/episode, "movie" matches movie only
        if rules.content_types:
            if not self._matches_content_type(item.type, rules.content_types):
                return False

        # Genre filters (must have at least one matching genre)
        if rules.genres:
            item_genres = self._get_normalized_genres(item)
            if not item_genres:
                return False

            # Check if any of the required genres are present
            if not any(genre in item_genres for genre in rules.genres):
                return False

        # Excluded genre filter (must not have any excluded genres)
        if rules.exclude_genres:
            item_genres = self._get_normalized_genres(item)
            if item_genres:
                # Check if any excluded genres are present
                if any(genre in item_genres for genre in rules.exclude_genres):
                    return False

        # Year filters
        if rules.min_year is not None or rules.max_year is not None:
            item_year = self._get_year(item)
            if item_year is None:
                return False

            if rules.min_year is not None and item_year < rules.min_year:
                return False

            if rules.max_year is not None and item_year > rules.max_year:
                return False

        # Anime filter
        if rules.is_anime is not None:
            if item.is_anime != rules.is_anime:
                return False

        # Network filter (for TV shows)
        if rules.networks:
            item_networks = self._get_normalized_networks(item)
            if not item_networks:
                return False

            # Check if any of the required networks are present
            if not any(network in item_networks for network in rules.networks):
                return False

        # Country filter
        if rules.countries:
            item_countries = self._get_normalized_countries(item)
            if not item_countries:
                return False

            # Check if any of the required countries are present
            if not any(country in item_countries for country in rules.countries):
                return False

        # Language filter
        if rules.languages:
            item_languages = self._get_normalized_languages(item)
            if not item_languages:
                return False

            # Check if any of the required languages are present
            if not any(lang in item_languages for lang in rules.languages):
                return False

        # Rating filters (0-10 scale)
        if rules.min_rating is not None or rules.max_rating is not None:
            if item.rating is None:
                return False

            if rules.min_rating is not None and item.rating < rules.min_rating:
                return False

            if rules.max_rating is not None and item.rating > rules.max_rating:
                return False

        # Content rating filter (US ratings: G, PG, PG-13, R, etc.)
        if rules.content_ratings:
            if not item.content_rating:
                return False

            if item.content_rating not in rules.content_ratings:
                return False

        # All rules matched
        return True

    def _matches_content_type(self, item_type: str, allowed_types: List[str]) -> bool:
        """
        Check if item type matches allowed content types with hierarchical matching.

        Hierarchical rules:
        - "movie" matches: movie only
        - "show" matches: show, season, episode (entire show hierarchy)

        Args:
            item_type: The type of the MediaItem (movie, show, season, episode)
            allowed_types: List of allowed content types from filter rules

        Returns:
            True if item type matches any allowed type (with hierarchy), False otherwise
        """
        # Direct match
        if item_type in allowed_types:
            return True

        # Hierarchical matching: if "show" is allowed, also allow season and episode
        if "show" in allowed_types and item_type in ["season", "episode"]:
            return True

        return False

    def _get_normalized_genres(self, item: MediaItem) -> List[str]:
        """Get normalized genre list (lowercase) from MediaItem."""
        if not item.genres:
            return []
        return [g.lower() for g in item.genres if g]

    def _get_normalized_networks(self, item: MediaItem) -> List[str]:
        """Get normalized network list (lowercase) from MediaItem."""
        if not item.network:
            return []
        return [n.lower() for n in item.network if n]

    def _get_normalized_countries(self, item: MediaItem) -> List[str]:
        """Get normalized country list (lowercase) from MediaItem."""
        if not item.country:
            return []
        return [c.lower() for c in item.country if c]

    def _get_normalized_languages(self, item: MediaItem) -> List[str]:
        """Get normalized language list (lowercase) from MediaItem."""
        if not item.language:
            return []
        return [lang.lower() for lang in item.language if lang]

    def _get_year(self, item: MediaItem) -> Optional[int]:
        """
        Extract year from MediaItem.

        For shows/seasons/episodes, uses the show's aired_at year.
        For movies, uses the year field directly.
        """
        if item.type in ["show", "season", "episode"]:
            # For TV content, get the show's aired_at year
            show = item.get_top_title()
            if show and hasattr(show, "aired_at") and show.aired_at:
                try:
                    return int(show.aired_at.split("-")[0])
                except (ValueError, IndexError, AttributeError):
                    return None

        # For movies or if show year not available, use year field
        if hasattr(item, "year") and item.year:
            return item.year

        return None
