import pytest
from program.settings.manager import settings_manager as sm
from program.settings.models import RankingModel
from program.versions.parser import (
    ParsedMediaItem,
    Torrent,
    check_complete_series,
    check_multi_audio,
    check_multi_subtitle,
    check_unwanted_quality,
    parse_episodes,
)
from program.versions.rank_models import DefaultRanking

test_data = [
    (
        "Jumanji (1995) RM4K (1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole",
        {
            "raw_title": "Jumanji (1995) RM4K (1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole",
            "parsed_title": "Jumanji",
            "fetch": True,
            "year": [1995],
            "resolution": ["1080p"],
            "quality": ["Blu-ray"],
            "codec": ["H.265"],
            "audio": ["AAC 5.1"],
            "bitDepth": [10],
        },
    ),
    (
        "The Simpsons - Complete Seasons S01 to S28 (1080p, 720p, DVDRip)",
        {
            "raw_title": "The Simpsons - Complete Seasons S01 to S28 (1080p, 720p, DVDRip)",
            "parsed_title": "The Simpsons",
            "fetch": True,
            "is_complete": True,
            "resolution": ["1080p"],
            "quality": ["DVD-Rip"],
            "season": list(range(1, 29)),
        },
    ),
]

test_ids = ["FullQualityCheck", "SeasonRangeCheck"]

CUSTOM_RANKS = sm.settings.ranking.custom_ranks


def test_valid_torrent_from_item():
    ranking_model = DefaultRanking()
    torrent = Torrent(
        ranking_model=ranking_model,
        raw_title="The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]",
        infohash="1234567890",
    )

    assert torrent.raw_title == "The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]"
    assert torrent.infohash == "1234567890"
    assert isinstance(torrent.parsed_data, ParsedMediaItem)
    assert torrent.parsed_data.parsed_title == "The Walking Dead"
    assert torrent.parsed_data.fetch is True
    assert torrent.rank == 83


def test_custom_ranks_is_mapped():
    # Ensure that CUSTOM_RANKS is an instance of RankingModel
    assert isinstance(sm.settings.ranking, RankingModel)
    # Access the custom ranks through the custom_ranks attribute
    custom_ranks = sm.settings.ranking.custom_ranks
    # Now you can access individual ranks
    assert custom_ranks["uhd"].fetch is False


@pytest.mark.parametrize("raw_title, expected", test_data, ids=test_ids)
def test_parsed_media_item_properties(raw_title: str, expected: dict):
    item = ParsedMediaItem(raw_title=raw_title)
    for key, value in expected.items():
        assert (
            getattr(item, key) == value
        ), f"Attribute {key} failed for raw_title: {raw_title}"


def test_episode_parsing():
    test_cases = [
        ("The Simpsons S01E01 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", [1]),
        ("The Simpsons S01E01E02 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", [1, 2]),
        ("The Simpsons S01E01-E02 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", [1, 2]),
        # Looks like it doesn't parse past the first 2 episodes
        (
            "The Simpsons S01E01-E02-E03-E04-E05 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole",
            [1, 2],
        ),
        (
            "The Simpsons S01E01E02E03E04E05 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole",
            [1, 2],
        ),
    ]
    for test_string, expected in test_cases:
        assert (
            parse_episodes(test_string) == expected
        ), f"Failed for '{test_string}' with expected {expected}"


def test_multi_audio_patterns():
    test_cases = [
        ("Lucy 2014 Dual-Audio WEBRip 1400Mb", True),
        ("Darkness Falls (2020) HDRip 720p [Hindi-Dub] Dual-Audio x264", True),
        ("The Simpsons - Season 1 Complete [DVDrip ITA ENG] TNT Village", False),
        ("Brave.2012.R5.DVDRip.XViD.LiNE-UNiQUE", False),
    ]
    for test_string, expected in test_cases:
        assert check_multi_audio(test_string) == expected


def test_multi_subtitle_patterns():
    test_cases = [
        (
            "IP Man And Four Kings 2019 HDRip 1080p x264 AAC Mandarin HC CHS-ENG SUBS Mp4Ba",
            True,
        ),
        ("The Simpsons - Season 1 Complete [DVDrip ITA ENG] TNT Village", True),
        ("The.X-Files.S01.Retail.DKsubs.720p.BluRay.x264-RAPiDCOWS", False),
        ("Hercules (2014) WEBDL DVDRip XviD-MAX", False),
    ]
    for test_string, expected in test_cases:
        assert check_multi_subtitle(test_string) == expected


def test_complete_series_patterns():
    test_cases = [
        (
            "The Sopranos - The Complete Series (Season 1, 2, 3, 4, 5 & 6) + Extras",
            True,
        ),
        ("The Inbetweeners Collection", True),
        ("The Simpsons S01 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", False),
        ("Two and a Half Men S12E01 HDTV x264 REPACK-LOL [eztv]", False),
    ]
    for test_string, expected in test_cases:
        assert check_complete_series(test_string) == expected


def test_unwanted_quality_patterns():
    # False means the pattern is unwanted, and won't be fetched.
    test_cases = [
        ("Mission.Impossible.1996.Custom.Audio.1080p.PL-Spedboy", True),
        ("Casino.1995.MULTi.REMUX.2160p.UHD.Blu-ray.HDR.HEVC.DTS-X7.1-DENDA", True),
        ("Guardians of the Galaxy (CamRip / 2014)", False),
        ("Brave.2012.R5.DVDRip.XViD.LiNE-UNiQUE", False),
    ]
    for test_string, expected in test_cases:
        assert check_unwanted_quality(test_string) == expected
