from program.versions.parser.models import ParsedMediaItem


def test_movie_parse():
    # Given
    raw_title = "Jumanji (1995) RM4K (1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole"

    # When
    item = ParsedMediaItem(raw_title=raw_title)

    # Then
    assert item.raw_title == raw_title
    assert item.parsed_title == "Jumanji"
    assert item.is_4k is False
    assert item.is_multi_audio is False
    assert item.is_multi_subtitle is False
    assert item.is_complete is False
    assert item.is_unwanted_quality is False
    assert item.year == 2003
    assert item.resolution == "1080p"
    assert item.quality == "Blu-ray"
    assert item.season == []
    assert item.episodes == []
    assert item.codec == "H.265"
    assert item.audio == "AAC 5.1"
    assert item.bitdepth == 10
    assert item.hdr is False
    assert item.upscaled is False
    assert item.remastered is False
    assert item.proper is False
    assert item.repack is False
    assert item.subtitles is False
    assert item.language == []
    assert item.remux is False
    assert item.extended is False

def test_show_parse():
    # Given
    raw_title = "The Simpsons - Complete Seasons S01 to S28 (1080p, 720p, DVDRip)"

    # When
    item = ParsedMediaItem(raw_title=raw_title)

    # Then
    assert item.raw_title == raw_title
    assert item.parsed_title == "The Simpsons"
    assert item.is_4k is False
    assert item.is_multi_audio is False
    assert item.is_multi_subtitle is False
    assert item.is_complete is True
    assert item.is_unwanted_quality is False
    assert item.year == 1989
    assert item.resolution == "1080p"
    assert item.quality == "DVDRip"
    assert item.season == list(range(1, 29))
    assert item.episodes == []
    assert item.codec == []
    assert item.audio == []
    assert item.hdr is False
    assert item.upscaled is False
    assert item.remastered is False
    assert item.proper is False
    assert item.repack is False
    assert item.subtitles is False
    assert item.language == []
    assert item.remux is False
    assert item.extended is False

def test_season_parse():
    # Given
    raw_title = "The Simpsons S01 1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole"

    # When
    item = ParsedMediaItem(raw_title=raw_title)

    # Then
    assert item.raw_title == raw_title
    assert item.parsed_title == "The Simpsons"
    assert item.is_4k is False
    assert item.is_multi_audio is False
    assert item.is_multi_subtitle is False
    assert item.is_complete is False
    assert item.is_unwanted_quality is False
    assert item.year == 1989
    assert item.resolution == "1080p"
    assert item.quality == "Blu-ray"
    assert item.season == 1
    assert item.episodes == [1]
    assert item.codec == "H.265"
    assert item.audio == "AAC 5.1"
    assert item.bitdepth == 10
    assert item.hdr is False
    assert item.upscaled is False
    assert item.remastered is False
    assert item.proper is False
    assert item.repack is False
    assert item.subtitles is False
    assert item.language == []
    assert item.remux is False
    assert item.extended is False

def test_episode_parse():
    # Given
    raw_title = "Doctor Who S08E11 Dark Water 720p HDTV x264-FoV"

    # When
    item = ParsedMediaItem(raw_title=raw_title)

    # Then
    assert item.raw_title == raw_title
    assert item.parsed_title == "Doctor Who"
    assert item.is_4k is False
    assert item.is_multi_audio is False
    assert item.is_multi_subtitle is False
    assert item.is_complete is False
    assert item.is_unwanted_quality is False
    assert item.year == 2005
    assert item.resolution == "720p"
    assert item.quality == ["HDTV"]
    assert item.season == 8
    assert item.episodes == [11]
    assert item.codec == ["x264"]
    assert item.audio == []
    assert item.hdr is False
    assert item.upscaled is False
    assert item.remastered is False
    assert item.proper is False
    assert item.repack is False
    assert item.subtitles is False
    assert item.language == []
    assert item.remux is False
    assert item.extended is False