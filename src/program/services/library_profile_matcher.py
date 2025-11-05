"""Library Profile Matcher Service

Evaluates MediaItem metadata against library profile filter rules to determine
which library profiles a media item should be placed in.
"""

from typing import List, Optional

from loguru import logger

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.settings.models import LibraryProfileFilterRules


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

        # Genre filters with exclusion support
        if rules.genres:
            if not self._matches_list_filter(
                self._get_normalized_genres(item), rules.genres, "genres"
            ):
                return False

        # Excluded genre filter (deprecated, but kept for backward compatibility)
        # The model validator auto-migrates this to genres with '!' prefix
        if rules.exclude_genres:
            item_genres = self._get_normalized_genres(item)
            if item_genres:
                # Check if any excluded genres are present
                if any(genre.lower() in item_genres for genre in rules.exclude_genres):
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

        # Network filter with exclusion support
        if rules.networks:
            if not self._matches_list_filter(
                self._get_normalized_networks(item), rules.networks, "networks"
            ):
                return False

        # Country filter with exclusion support
        if rules.countries:
            if not self._matches_list_filter(
                self._get_normalized_countries(item), rules.countries, "countries"
            ):
                return False

        # Language filter with exclusion support
        if rules.languages:
            if not self._matches_list_filter(
                self._get_normalized_languages(item), rules.languages, "languages"
            ):
                return False

        # Rating filters (0-10 scale)
        if rules.min_rating is not None or rules.max_rating is not None:
            if item.rating is None:
                return False

            if rules.min_rating is not None and item.rating < rules.min_rating:
                return False

            if rules.max_rating is not None and item.rating > rules.max_rating:
                return False

        # Content rating filter with exclusion support
        if rules.content_ratings:
            item_rating = item.content_rating
            if not self._matches_list_filter(
                [item_rating.lower()] if item_rating else [],
                rules.content_ratings,
                "content_ratings",
            ):
                return False

        # All rules matched
        return True

    def _matches_list_filter(
        self, item_values: List[str], filter_values: List[str], filter_name: str
    ) -> bool:
        """
        Check if item values match filter with inclusion/exclusion support.

        Args:
            item_values: Normalized values from the item (e.g., ['action', 'adventure'])
            filter_values: Filter values with optional '!' prefix (e.g., ['action', '!horror'])
            filter_name: Name of the filter for logging

        Returns:
            True if item matches filter rules, False otherwise

        Logic:
            1. Split filter_values into inclusions and exclusions
            2. If exclusions exist and any match item_values, return False
            3. If inclusions exist and none match item_values, return False
            4. Otherwise return True
        """
        if not item_values:
            # Item has no values for this filter
            # Only fail if there are inclusion rules (item must have at least one)
            inclusions = [v for v in filter_values if not v.startswith("!")]
            return len(inclusions) == 0

        # Normalize item values
        item_values_lower = [v.lower() for v in item_values]

        # Split into inclusions and exclusions
        inclusions = []
        exclusions = []

        for value in filter_values:
            if value.startswith("!"):
                # Exclusion rule
                exclusions.append(value[1:].lower())  # Remove '!' and normalize
            else:
                # Inclusion rule
                inclusions.append(value.lower())

        # Check exclusions first (fail fast)
        if exclusions:
            for exclusion in exclusions:
                if exclusion in item_values_lower:
                    logger.debug(
                        f"Item excluded by {filter_name} filter: "
                        f"item has '{exclusion}' which is in exclusion list"
                    )
                    return False

        # Check inclusions (must have at least one match if inclusions exist)
        if inclusions:
            has_match = any(inc in item_values_lower for inc in inclusions)
            if not has_match:
                return False

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
        """Get normalized network list (lowercase) from MediaItem.
        Accepts either a single string (e.g., "HBO Max") or a list of strings.
        """
        v = getattr(item, "network", None)
        return self._normalize_str_list(v)

    def _get_normalized_countries(self, item: MediaItem) -> List[str]:
        """Get normalized country list (lowercase) from MediaItem.
        Accepts either a single string (e.g., "USA") or a list of strings/codes.
        """
        v = getattr(item, "country", None)
        return self._normalize_str_list(v)

    def _get_normalized_languages(self, item: MediaItem) -> List[str]:
        """Get normalized language list (lowercase) from MediaItem.
        Accepts either a single string (e.g., "eng") or a list of ISO 639-3 codes.
        """
        v = getattr(item, "language", None)
        return self._normalize_str_list(v)

    def _normalize_str_list(self, value) -> List[str]:
        """Normalize a string or iterable of strings into a lowercase list.
        - None -> []
        - "HBO Max" -> ["hbo max"]
        - ["USA", "UK"] -> ["usa", "uk"]
        - Filters out empty strings and trims whitespace
        """
        if not value:
            return []
        if isinstance(value, str):
            v = value.strip()
            return [v.lower()] if v else []
        # Try to iterate (handles lists/tuples/sets)
        try:
            result = []
            for x in value:
                if x is None:
                    continue
                s = str(x).strip()
                if s:
                    result.append(s.lower())
            return result
        except TypeError:
            # Not iterable; fallback to string cast
            s = str(value).strip()
            return [s.lower()] if s else []

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
