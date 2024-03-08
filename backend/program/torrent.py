from typing import Any, Dict, List, Set

from program.media.item import MediaItem
from program.versions.parser.parser import ParsedMediaItem, parser
from program.versions.sorter.sorter import RankingConfig, rank_items
from pydantic import BaseModel, Field


class Torrent(BaseModel):
    """Torrent class for storing torrent data."""
    title: str = Field(default="")
    infohash: str = Field(default="")
    parsed_data: ParsedMediaItem = Field(default=None)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Torrent):
            return False
        return self.infohash == other.infohash

    def __hash__(self) -> int:
        return hash(self.infohash)

    @classmethod
    def create(cls, item: MediaItem, raw_title: str, infohash: str) -> "Torrent":
        """Create a Torrent object from the given data."""
        parsed_data: ParsedMediaItem = parser.parse(raw_title)
        if parser.check_title_match(item, parsed_data.parsed_title):
            return cls(
                title=raw_title, infohash=infohash, parsed_data=parsed_data
            )


class ScrapedTorrents:
    """ScrapedTorrents class for storing scraped torrents."""

    def __init__(self):
        self.torrents: Set[Torrent] = set()

    def __iter__(self):
        return iter(self.torrents)

    def __len__(self):
        return len(self.torrents)

    def add(self, torrent: Torrent):
        self.torrents.add(torrent)

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Convert the set of Torrent objects into a list of dictionaries."""
        return [torrent.model_dump() for torrent in self.torrents]

    def sort_by_ranking(self, ranking_config: RankingConfig) -> List[Torrent]:
        """Sort `Torrents` using the provided ranking configuration."""
        torrents_dicts = self.to_dict_list()
        ranked_torrent_dicts = rank_items(torrents_dicts, ranking_config)
        # Convert dictionaries back into Torrent objects
        return [Torrent(**torrent_dict) for torrent_dict in ranked_torrent_dicts]
