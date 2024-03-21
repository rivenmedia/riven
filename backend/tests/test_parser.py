import pytest
from program.settings.manager import settings_manager as sm
from program.versions.parser import (
    ParsedMediaItem,
    Torrent,
    check_complete_series,
    check_multi_audio,
    check_multi_subtitle,
    check_unwanted_quality,
    extract_episodes,
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

    assert isinstance(torrent, Torrent)
    assert isinstance(torrent.parsed_data, ParsedMediaItem)
    assert torrent.raw_title == "The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]"
    assert torrent.infohash == "1234567890"
    assert torrent.parsed_data.parsed_title == "The Walking Dead"
    assert torrent.parsed_data.fetch is True
    assert torrent.rank == 163, f"Rank was {torrent.rank} instead of 163"


def test_check_title_match():
    """Test the check_title_match function"""
    from program.versions.parser import check_title_match

    assert check_title_match("Damsel", "Damsel") is True
    assert check_title_match("American Horror Story", "American Story Horror") is False


@pytest.mark.parametrize("raw_title, expected", test_data, ids=test_ids)
def test_parsed_media_item_properties(raw_title: str, expected: dict):
    item = ParsedMediaItem(raw_title=raw_title)
    for key, value in expected.items():
        assert (
            getattr(item, key) == value
        ), f"Attribute {key} failed for raw_title: {raw_title}"


def test_episode_parsing():
    test_cases = [
        # Regular Tests
        ("The Simpsons S01E01 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", [1]),
        ("The Simpsons S01E01E02 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", [1, 2]),
        ("The Simpsons S01E01-E02 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", [1, 2]),
        ("The Simpsons S01E01-E02-E03-E04-E05 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", [1, 2, 3, 4, 5]),
        ("The Simpsons S01E01E02E03E04E05 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", [1, 2, 3, 4, 5]),
        ("The Simpsons E1-200 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole", list(range(1, 201))), # Eps 1-200
        ("House MD All Seasons (1-8) 720p Ultra-Compressed", []),
        ("The Avengers (EMH) - S01 E15 - 459 (1080p - BluRay)", [15]),
        ("Witches Of Salem - 2Of4 - Road To Hell - Great Mysteries Of The World", [2]), # mini-series, this is correct!
        ("Lost.[Perdidos].6x05.HDTV.XviD.[www.DivxTotaL.com]", [5]),
        ("4-13 Cursed (HD)", [13]),
        # Anime Tests
        ("Dragon Ball Z Movie - 09 - Bojack Unbound - 1080p BluRay x264 DTS 5.1 -DDR", []),
        ("[F-D] Fairy Tail Season 1 - 6 + Extras [480P][Dual-Audio]", []),
        ("BoJack Horseman [06x01-08 of 16] (2019-2020) WEB-DLRip 720p", list(range(1, 9))), # Eps 1-8
        ("[HR] Boku no Hero Academia 87 (S4-24) [1080p HEVC Multi-Subs] HR-GZ", [24]),
        ("Bleach 10º Temporada - 215 ao 220 - [DB-BR]", [215, 216, 217, 218, 219, 220]),
        # Looks like it doesn't handle hypens in the episode part. It's not a big deal,
        # as it's not a common practice to use hypens in the episode part. Mostly seen in Anime.
        ("Naruto Shippuden - 107 - Strange Bedfellows", []),                             # Incorrect. [107]
        ("[224] Shingeki no Kyojin - S03 - Part 1 - 13 [BDRip.1080p.x265.FLAC]", []),    # Incorrect. [13]
        ("[Erai-raws] Shingeki no Kyojin Season 3 - 11 [1080p][Multiple Subtitle]", [])  # Incorrect. [11]
    ]
    for test_string, expected in test_cases:
        assert (
            extract_episodes(test_string) == expected
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
