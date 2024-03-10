from typing import Any, Dict, List

import PTN
from pydantic import BaseModel, root_validator
from thefuzz import fuzz

from .patterns import (
    COMPLETE_SERIES_COMPILED,
    MULTI_AUDIO_COMPILED,
    MULTI_SUBTITLE_COMPILED,
    UNWANTED_QUALITY_COMPILED,
)


class ParsedMediaItem(BaseModel):
    """ParsedMediaItem class containing parsed data."""
    raw_title: str
    parsed_title: str = ""
    fetch: bool = False
    is_4k: bool = False
    is_multi_audio: bool = False
    is_multi_subtitle: bool = False
    is_complete: bool = False
    year: List[int] = []
    resolution: List[str] = []
    quality: List[str] = []
    season: List[int] = []
    episode: List[int] = []
    codec: List[str] = []
    audio: List[str] = []
    hdr: bool = False
    upscaled: bool = False
    remastered: bool = False
    proper: bool = False
    repack: bool = False
    subtitles: List[str] = []
    language: List[str] = []
    remux: bool = False
    bitDepth: List[int] = []
    extended: bool = False

    @root_validator(pre=True)
    def parse(cls, values):
        """Parse the raw string."""
        raw_title = values.get("raw_title")
        if not raw_title:
            return values

        parsed = PTN.parse(raw_title, coherent_types=True)
        
        # Update values with parsed data
        values.update({
            "parsed_title": parsed.get("title"),
            "fetch": cls.check_unwanted_quality(raw_title),
            "year": parsed.get("year", []),
            "resolution": parsed.get("resolution", []),
            "quality": parsed.get("quality", []),
            "season": cls.parse_seasons(parsed.get("season", [])),
            "episode": cls.parse_episodes(parsed.get("episode", [])),
            "codec": parsed.get("codec", []),
            "audio": parsed.get("audio", []),
            "language": parsed.get("language", []),
            "is_4k": cls.check_4k(parsed.get("resolution", False)),
            "hdr": parsed.get("hdr", False),
            "upscaled": parsed.get("upscaled", False),
            "remastered": parsed.get("remastered", False),
            "proper": parsed.get("proper", False),
            "repack": parsed.get("repack", False),
            "subtitles": parsed.get("subtitles", []),
            "remux": parsed.get("remux", False),
            "bitDepth": parsed.get("bitDepth", []),
            "extended": parsed.get("extended", False),
            "is_multi_audio": cls.check_multi_audio(raw_title),
            "is_multi_subtitle": cls.check_multi_subtitle(raw_title),
            "is_complete": cls.check_complete_series(raw_title),
        })

        return values

    @staticmethod
    def parse_seasons(season_data) -> List[int]:
        """Parse the seasons data."""
        if isinstance(season_data, list):
            return season_data
        elif season_data is not None:
            return [season_data]
        else:
            return []

    @staticmethod
    def parse_episodes(episode_data) -> List[int]:
        """Parse the episodes data."""
        if isinstance(episode_data, list):
            return episode_data
        elif episode_data is not None:
            return [episode_data]
        else:
            return []

    @staticmethod
    def check_4k(resolution: str) -> bool:
        """Check if the resolution indicates 4K."""
        return resolution in ["2160p", "4K", "UHD"]

    @staticmethod
    def check_unwanted_quality(string) -> bool:
        """Check if the string contains unwanted quality pattern."""
        return not any(pattern.search(string) for pattern in UNWANTED_QUALITY_COMPILED)

    @staticmethod
    def check_multi_audio(string) -> bool:
        """Check if the string contains multi-audio pattern."""
        return any(pattern.search(string) for pattern in MULTI_AUDIO_COMPILED)

    @staticmethod
    def check_multi_subtitle(string) -> bool:
        """Check if the string contains multi-subtitle pattern."""
        return any(pattern.search(string) for pattern in MULTI_SUBTITLE_COMPILED)

    @staticmethod
    def check_complete_series(string) -> bool:
        """Check if the string contains complete series pattern."""
        return any(pattern.search(string) for pattern in COMPLETE_SERIES_COMPILED)


class Torrent(BaseModel):
    """Torrent class for storing torrent data."""
    title: str = ""
    infohash: str = ""
    parsed_data: ParsedMediaItem = None
    rank: int = 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Torrent):
            return False
        return self.infohash == other.infohash

    def __hash__(self) -> int:
        return hash(self.infohash)

    @classmethod
    def create(cls, item, raw_title: str, infohash: str) -> "Torrent":
        """Create a Torrent object from the given data."""
        parsed_data: ParsedMediaItem = parser(raw_title)
        if check_title_match(item, parsed_data.parsed_title):
            parsed_data.fetch = True
            return cls(
                title=raw_title, infohash=infohash, parsed_data=parsed_data
            )


class ParsedTorrents:
    """ParsedTorrents class for storing scraped torrents."""

    def __init__(self):
        self.torrents: Dict[str, Dict[str, Any]] = {}

    def __iter__(self):
        return iter(self.torrents.values())

    def __len__(self):
        return len(self.torrents)

    def add(self, torrent: Torrent):
        """Add a Torrent object."""
        self.torrents[torrent.infohash] = {
            "title": torrent.title,
            "parsed_data": torrent.parsed_data
        }


def parser(query: str) -> ParsedMediaItem:
    """Parse the given string using the ParsedMediaItem model."""
    return ParsedMediaItem(raw_title=query)

def check_title_match(item, raw_title: str, threshold: int = 90) -> bool:
    """Check if the title matches PTN title using fuzzy matching."""
    target_title = item.title
    if item.type == "season":
        target_title = item.parent.title
    elif item.type == "episode":
        target_title = item.parent.parent.title
    return fuzz.ratio(raw_title.lower(), target_title.lower()) >= threshold

def parse_episodes(string: str, season: int = None) -> List[int]:
    """Get episode numbers from the file name."""
    parsed_data = PTN.parse(string, coherent_types=True)
    parsed_seasons = parsed_data.get("season", [])
    parsed_episodes = parsed_data.get("episode")

    # If season is specified but parsed_seasons is empty or does not contain the season, return empty list
    if season is not None and (not parsed_seasons or season not in parsed_seasons):
        return []
    
    if isinstance(parsed_episodes, list):
        episodes = parsed_episodes
    elif parsed_episodes is not None:
        episodes = [parsed_episodes]
    else:
        episodes = []
    return episodes