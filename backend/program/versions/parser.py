import re
from typing import Dict, List

import PTN
from program.versions.rank_models import DefaultRanking
from program.versions.ranks import (
    CUSTOM_RANKS,
    SETTINGS,
    BaseRankingModel,
    calculate_ranking,
)
from pydantic import BaseModel, Field
from thefuzz import fuzz

from .patterns import (
    COMPLETE_SERIES_COMPILED,
    HDR_DOLBY_VIDEO_COMPILED,
    MULTI_AUDIO_COMPILED,
    MULTI_SUBTITLE_COMPILED,
    UNWANTED_QUALITY_COMPILED,
)


class ParsedMediaItem(BaseModel):
    """ParsedMediaItem class containing parsed data."""

    raw_title: str
    parsed_title: str = None
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
    subtitles: List[str] = []
    language: List[str] = []
    bitDepth: List[int] = []
    hdr: str = None
    proper: bool = False
    repack: bool = False
    remux: bool = False
    upscaled: bool = False
    remastered: bool = False
    directorsCut: bool = False
    extended: bool = False
    excess: list = []

    def __init__(self, raw_title: str, **kwargs):
        super().__init__(raw_title=raw_title, **kwargs)
        parsed: dict = PTN.parse(raw_title, coherent_types=True)
        self.raw_title = raw_title
        self.parsed_title = parsed.get("title")
        self.is_multi_audio = check_multi_audio(raw_title)
        self.is_multi_subtitle = check_multi_subtitle(raw_title)
        self.is_complete = check_complete_series(raw_title)
        self.is_4k = any(
            resolution in ["2160p", "4K", "UHD"]
            for resolution in parsed.get("resolution", [])
        )
        self.year = parsed.get("year", [])
        self.resolution = parsed.get("resolution", [])
        self.quality = parsed.get("quality", [])
        self.season = parsed.get("season", [])
        self.episode = parsed.get("episode", [])
        self.codec = parsed.get("codec", [])
        self.audio = parsed.get("audio", [])
        self.subtitles = parsed.get("subtitles", [])
        self.language = parsed.get("language", [])
        self.bitDepth = parsed.get("bitDepth", [])
        self.hdr = check_hdr_dolby_video(raw_title)
        self.proper = parsed.get("proper", False)
        self.repack = parsed.get("repack", False)
        self.remux = parsed.get("remux", False)
        self.upscaled = parsed.get("upscaled", False)
        self.remastered = parsed.get("remastered", False)
        self.directorsCut = parsed.get("directorsCut", False)
        self.extended = parsed.get("extended", False)
        self.excess = parsed.get("excess", [])
        self.fetch = check_fetch(self)


class Torrent(BaseModel):
    """Torrent class for storing torrent data."""

    raw_title: str
    infohash: str
    parsed_data: ParsedMediaItem = None
    rank: int = 0

    def __init__(self, ranking_model: BaseRankingModel, raw_title: str, infohash: str):
        super().__init__(raw_title=raw_title, infohash=infohash)
        self.parsed_data = ParsedMediaItem(raw_title)
        if not ranking_model:
            ranking_model = DefaultRanking()
        self.rank = calculate_ranking(self.parsed_data, ranking_model)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Torrent):
            return False
        return self.infohash.lower() == other.infohash.lower()

    def update_rank(self, ranking_model: BaseRankingModel):
        """Update the rank based on the provided ranking model."""
        if self.parsed_data:
            self.rank = calculate_ranking(self.parsed_data, ranking_model)


class ParsedTorrents(BaseModel):
    """ParsedTorrents class for storing scraped torrents."""

    torrents: Dict[str, Torrent] = Field(default_factory=dict)

    def __iter__(self):
        return iter(self.torrents.values())

    def __len__(self):
        return len(self.torrents)

    def add(self, torrent: Torrent):
        """Add a Torrent object."""
        self.torrents[torrent.infohash] = torrent

    def sort(self):
        """Sort the torrents by rank and update the dictionary accordingly."""
        sorted_torrents = sorted(
            self.torrents.values(), key=lambda x: x.rank, reverse=True
        )
        self.torrents = {torrent.infohash: torrent for torrent in sorted_torrents}


def parser(query: str | None) -> ParsedMediaItem:
    """Parse the given string using the ParsedMediaItem model."""
    return ParsedMediaItem(raw_title=query)


def check_title_match(item, raw_title: str = str, threshold: int = 90) -> bool:
    """Check if the title matches PTN title using levenshtein algorithm."""
    # Lets make this more globally usable by allowing str or MediaItem as input
    if item is None or not raw_title:
        return False
    elif isinstance(item, str):
        return fuzz.ratio(raw_title.lower(), item.lower()) >= threshold
    else:
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
    parsed_episodes = parsed_data.get("episode", [])

    if season is not None and (not parsed_seasons or season not in parsed_seasons):
        return []

    if isinstance(parsed_episodes, list):
        episodes = parsed_episodes
    elif parsed_episodes is not None:
        episodes = [parsed_episodes]
    else:
        episodes = []
    return episodes


def check_fetch(data: ParsedMediaItem) -> bool:
    """Check user settings and unwanted quality to determine if torrent should be fetched."""
    if not check_unwanted_quality(data.raw_title):
        return False
    if SETTINGS.require and any(
        pattern.search(data.raw_title) for pattern in SETTINGS.require if pattern
    ):
        return True
    if SETTINGS.exclude and any(
        pattern.search(data.raw_title) for pattern in SETTINGS.exclude if pattern
    ):
        return False
    fetch_conditions = (
        fetch_quality(data),
        fetch_resolution(data),
        fetch_codec(data),
        fetch_audio(data),
        fetch_other(data),
    )
    return any(fetch_condition for fetch_condition in fetch_conditions)


def fetch_quality(data: ParsedMediaItem) -> bool:
    """Check if the quality is fetchable based on user settings."""
    if not CUSTOM_RANKS["webdl"].enable and "WEB-DL" in data.quality:
        return False
    if not CUSTOM_RANKS["remux"].enable and data.remux:
        return False
    if not CUSTOM_RANKS["ddplus"].enable and "Dolby Digital Plus" in data.audio:
        return False
    if not CUSTOM_RANKS["aac"].enable and "AAC" in data.audio:
        return False
    return True


def fetch_resolution(data: ParsedMediaItem) -> bool:
    """Check if the resolution is fetchable based on user settings."""
    if not CUSTOM_RANKS["uhd"].enable and data.is_4k:
        return False
    if not CUSTOM_RANKS["fhd"].enable and "1080p" in data.resolution:
        return False
    if not CUSTOM_RANKS["hd"].enable and "720p" in data.resolution:
        return False
    if not CUSTOM_RANKS["sd"].enable and any(
        res in ["576p", "480p"] for res in data.resolution
    ):
        return False
    return True


def fetch_codec(data: ParsedMediaItem) -> bool:
    """Check if the codec is fetchable based on user settings."""
    # May add more to this later...
    if not CUSTOM_RANKS["av1"].enable and "AV1" in data.codec:
        return False
    return True


def fetch_audio(data: ParsedMediaItem) -> bool:
    """Check if the audio is fetchable based on user settings."""
    audio: str = data.audio[0] if data.audio else None
    if not audio:
        return True

    audio = re.sub(r"7.1|5.1|Dual|Mono|Original|LiNE", "", audio).strip()

    if not CUSTOM_RANKS["truehd"].enable and audio == "Dolby TrueHD":
        return False
    if not CUSTOM_RANKS["atmos"].enable and audio == "Dolby Atmos":
        return False
    if not CUSTOM_RANKS["ac3"].enable and audio == "Dolby Digital":
        return False
    if not CUSTOM_RANKS["dts_x"].enable and audio == "Dolby Digital EX":
        return False
    if not CUSTOM_RANKS["ddplus"].enable and audio == "Dolby Digital Plus":
        return False
    if not CUSTOM_RANKS["dts_hd"].enable and audio == "DTS":
        return False
    if not CUSTOM_RANKS["dts_hd_ma"].enable and audio == "DTS-HD MA":
        return False
    if not CUSTOM_RANKS["aac"].enable and audio == "AAC":
        return False
    return True


def fetch_other(data: ParsedMediaItem) -> bool:
    """Check if the other data is fetchable based on user settings."""
    if not CUSTOM_RANKS["proper"].enable and data.proper:
        return False
    if not CUSTOM_RANKS["repack"].enable and data.repack:
        return False
    if not CUSTOM_RANKS["remux"].enable and data.remux:
        return False
    return True


def check_unwanted_quality(input_string: str) -> bool:
    """Check if the string contains unwanted quality pattern."""
    return not any(
        pattern.search(input_string) for pattern in UNWANTED_QUALITY_COMPILED
    )


def check_multi_audio(input_string: str) -> bool:
    """Check if the string contains multi-audio pattern."""
    return any(pattern.search(input_string) for pattern in MULTI_AUDIO_COMPILED)


def check_multi_subtitle(input_string: str) -> bool:
    """Check if the string contains multi-subtitle pattern."""
    return any(pattern.search(input_string) for pattern in MULTI_SUBTITLE_COMPILED)


def check_complete_series(input_string: str) -> bool:
    """Check if the string contains complete series pattern."""
    return any(pattern.search(input_string) for pattern in COMPLETE_SERIES_COMPILED)


def check_hdr_dolby_video(input_string: str):
    """Check if the string contains HDR/Dolby video pattern."""
    for pattern, value in HDR_DOLBY_VIDEO_COMPILED:
        if pattern.search(input_string):
            return value
    return None
