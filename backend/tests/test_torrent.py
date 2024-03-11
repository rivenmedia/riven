import pytest
from program.media.item import Show
from program.versions.parser import ParsedMediaItem, ParsedTorrents, Torrent
from program.versions.ranks import DefaultRanking, calculate_ranking


@pytest.fixture
def item() -> Show:
    return Show({"title": "The Walking Dead"})

@pytest.fixture
def parsed_torrents():
    parsed_torrents = ParsedTorrents()
    test_data = {
        "1234567890": "Jumanji (1995) RM4K (1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole)",
        "0987654321": "Brave.2012.R5.DVDRip.XViD.LiNE-UNiQUE",
        "0987654322": "The Simpsons S01 4K BluRay x265 HEVC 10bit AAC 5.1 Tigole",
        "0987654323": "Attack.on.Titan.S01.S02.S03.1080p.Blu-Ray.Remux.Dual-Audio.TrueHD",
        "0987654324": "Guardians Of The Galaxy 2014 R6 720p HDCAM x264-JYK",
        "0987654325": "The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]",
    }

    for infohash, raw_title in test_data.items():
        parsed_data = ParsedMediaItem(raw_title=raw_title)
        torrent = Torrent(title=raw_title, infohash=infohash, parsed_data=parsed_data)
        ranking_model = DefaultRanking()    # Lets use the default ranking model for now
        torrent.update_rank(ranking_model)  # Update rank based on the ranking model
        parsed_torrents.add(torrent)

    assert len(parsed_torrents) == 6
    return parsed_torrents

def test_valid_torrent_from_item(item):
    torrent = Torrent.create(
        item,
        raw_title="The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]",
        infohash="1234567890",
    )

    assert torrent.title == "The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]"
    assert torrent.infohash == "1234567890"
    assert isinstance(torrent.parsed_data, ParsedMediaItem)
    assert torrent.parsed_data.parsed_title == "The Walking Dead"
    assert torrent.parsed_data.fetch is True
    assert torrent.rank == 0  # Default rank

def test_torrent_creation_from_scraper(parsed_torrents: ParsedTorrents):
    assert len(parsed_torrents) == 6
    assert len(parsed_torrents.torrents) == 6

def test_default_ranking_model():
    ranking = DefaultRanking()
    items = [
        (ParsedMediaItem(raw_title="Jumanji (1995) RM4K (1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole"), 90),
        (ParsedMediaItem(raw_title="The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]"), 80),
        (ParsedMediaItem(raw_title="The Simpsons S01 4K BluRay x265 HEVC 10bit AAC 5.1 Tigole"), -1000),
        (ParsedMediaItem(raw_title="Attack.on.Titan.S01.S02.S03.1080p.Blu-Ray.Remux.Dual-Audio.TrueHD"), -910),
    ]

    for item, expected in items:
        assert calculate_ranking(item, ranking) == expected
