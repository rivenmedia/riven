import pytest
from program.versions.parser import ParsedMediaItem, ParsedTorrents, Torrent
from program.versions.rank_models import DefaultRanking, RankModels
from program.versions.ranks import calculate_ranking


@pytest.fixture
def parsed_torrents():
    parsed_torrents = ParsedTorrents()
    test_data = {
        "0987654320": "Jumanji (1995) RM4K (1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole)",
        "0987654321": "Brave.2012.R5.DVDRip.XViD.LiNE-UNiQUE",
        "0987654322": "The Simpsons S01 4K BluRay x265 HEVC 10bit AAC 5.1 Tigole",
        "0987654323": "Attack.on.Titan.S01.S02.S03.1080p.Blu-Ray.Remux.Dual-Audio.TrueHD",
        "0987654324": "Guardians Of The Galaxy 2014 R6 720p HDCAM x264-JYK",
        "0987654325": "The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]",
        "0987654326": "Transformers.The.Last.Knight.2017.1080p.BluRay.x264.DTS-HD.MA.7.1-FGT",
        "0987654327": "Inception (2010) 1080p BluRay x264 DTS [Hindi DD5.1 + English DD5.1]",
        "0987654328": "The Simpsons - Complete Seasons S01 to S28 (1080p, 720p, DVDRip)",
        "0987654329": "Casino (1995) (1080p BluRay x265 HEVC 10bit HDR AAC 7.1 afm72) [QxR]",
        "0987654330": "X-men The Last Stand (2006) (720p BluRay x265 HEVC 10bit AAC 6.1 Vyndros)",
        "0987654331": "The Simpsons S01E01 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole",
        "0987654332": "Are You Being Served (1972) Season 1-10 S01-S10 + Extras (576p AMZN WEB-DL x265 HEVC 10bit EAC3 2.0 MONOLITH) [QxR]",
        "0987654333": "Escape.Room.Tournament.of.Champions.2021.PL.EXTENDED.1080p.BRRip.HE-AACv2.AV1",
    }

    for infohash, raw_title in test_data.items():
        ranking_model = DefaultRanking()
        torrent = Torrent(
            ranking_model=ranking_model, raw_title=raw_title, infohash=infohash
        )
        parsed_torrents.add(torrent)
    assert len(parsed_torrents) == 14
    return parsed_torrents


def test_default_ranking_model():
    """Test default ranking model"""
    ranking = DefaultRanking()
    items: list[ParsedMediaItem] = [
        (
            ParsedMediaItem(
                raw_title="Jumanji (1995) RM4K (1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole)"
            ),
            260,
        ),
        (
            ParsedMediaItem(
                raw_title="Inception (2010) 1080p BluRay x264 DTS [Hindi DD5.1 + English DD5.1]"
            ),
            233,
        ),
        (
            ParsedMediaItem(
                raw_title="[Yameii] Solo Leveling - S01E08 [English Dub] [CR WEB-DL 1080p] [DABC4BF4] (Ore dake Level Up na Ken)"
            ),
            320,
        ),
        (
            ParsedMediaItem(
                raw_title="Transformers.The.Last.Knight.2017.1080p.BluRay.x264.DTS-HD.MA.7.1-FGT"
            ),
            193,
        ),
        (
            ParsedMediaItem(
                raw_title="The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]"
            ),
            163,
        ),
        (
            ParsedMediaItem(
                raw_title="Attack.on.Titan.S01.S02.S03.1080p.Blu-Ray.Remux.Dual-Audio.TrueHD"
            ),
            -498,
        ),
        (
            ParsedMediaItem(
                raw_title="Escape.Room.Tournament.of.Champions.2021.PL.EXTENDED.1080p.BRRip.HE-AACv2.AV1"
            ),
            180,
        ),
        (
            ParsedMediaItem(
                raw_title="The Simpsons S01 4K BluRay x265 HEVC 10bit AAC 5.1 Tigole"
            ),
            -740,
        ),
        (ParsedMediaItem(raw_title="Brave.2012.R5.DVDRip.XViD.LiNE-UNiQUE"), -1000),
    ]

    for item, expected in items:
        assert (
            calculate_ranking(item, ranking) == expected
        ), f"Failed for item: {item.raw_title}"


def test_sorted_torrents(parsed_torrents: ParsedTorrents):
    """Test sorted parsed_torrents"""
    parsed_torrents.sort()
    sorted_title_order = [
        "The Simpsons - Complete Seasons S01 to S28 (1080p, 720p, DVDRip)",
        "Are You Being Served (1972) Season 1-10 S01-S10 + Extras (576p AMZN WEB-DL x265 HEVC 10bit EAC3 2.0 MONOLITH) [QxR]",
        "The Simpsons S01E01 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole",
        "Jumanji (1995) RM4K (1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole)",
        "Casino (1995) (1080p BluRay x265 HEVC 10bit HDR AAC 7.1 afm72) [QxR]",
        "Inception (2010) 1080p BluRay x264 DTS [Hindi DD5.1 + English DD5.1]",
        "The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]",
        "X-men The Last Stand (2006) (720p BluRay x265 HEVC 10bit AAC 6.1 Vyndros)",
        "Brave.2012.R5.DVDRip.XViD.LiNE-UNiQUE",
        "The Simpsons S01 4K BluRay x265 HEVC 10bit AAC 5.1 Tigole",
        "Attack.on.Titan.S01.S02.S03.1080p.Blu-Ray.Remux.Dual-Audio.TrueHD",
        "Guardians Of The Galaxy 2014 R6 720p HDCAM x264-JYK",
        "Transformers.The.Last.Knight.2017.1080p.BluRay.x264.DTS-HD.MA.7.1-FGT",
        "Escape.Room.Tournament.of.Champions.2021.PL.EXTENDED.1080p.BRRip.HE-AACv2.AV1",
    ]
    # On the default rank model we shove 4K and Remux to the bottom, and sort the rest by rank.
    for index, torrent in enumerate(parsed_torrents):
        assert (
            torrent.raw_title == sorted_title_order[index]
        ), f"Failed for index: {index}"


def test_get_ranking_model():
    """Test getting a ranking model"""
    models = RankModels()
    assert RankModels.get("default") == models.default
    assert RankModels.get("remux") == models.remux
    assert RankModels.get("web") == models.web
    assert RankModels.get("resolution") == models.resolution
    assert RankModels.get("overall") == models.overall
    assert RankModels.get("anime") == models.anime
    assert RankModels.get("all") == models.all
    # Test non-existent model. Should default to default model.
    assert RankModels.get("invalid") == models.default
