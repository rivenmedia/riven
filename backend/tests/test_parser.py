import pytest
from utils.parser import Parser


@pytest.fixture
def parser():
    return Parser()


# Test parser
def test_fetch_with_movie(parser):
    # Use mocked movie item in parser test
    parsed_data = parser.parse(item=None, string="Inception 2010 1080p BluRay x264")
    assert parsed_data["fetch"] is True
    # Add more assertions as needed


def test_fetch_with_episode(parser):
    # Use mocked episode item in parser test
    parsed_data = parser.parse(item=None, string="Breaking Bad S01E01 720p BluRay x264")
    assert parsed_data["fetch"] is True
    # Add more assertions as needed


def test_parse_resolution_4k(parser):
    parsed_data = parser.parse(
        item=None, string="Movie.Name.2018.2160p.UHD.BluRay.x265"
    )
    assert parsed_data["is_4k"] is True
    assert parsed_data["resolution"] == "2160p"


def test_parse_resolution_1080p(parser):
    parsed_data = parser.parse(item=None, string="Another.Movie.2019.1080p.WEB-DL.x264")
    assert parsed_data["is_4k"] is False
    assert parsed_data["resolution"] == "1080p"


def test_parse_dual_audio_present(parser):
    parsed_data = parser.parse(
        item=None, string="Series S01E01 720p BluRay x264 Dual-Audio"
    )
    assert parsed_data["is_dual_audio"] is True


def test_parse_dual_audio_absent(parser):
    parsed_data = parser.parse(item=None, string="Series S01E02 720p BluRay x264")
    assert parsed_data["is_dual_audio"] is False


def test_parse_complete_series_detected(parser):
    parsed_data = parser.parse(item=None, string="The Complete Series Box Set 1080p")
    assert parsed_data["is_complete"] is True


def test_parse_complete_series_not_detected(parser):
    parsed_data = parser.parse(item=None, string="Single.Movie.2020.1080p.BluRay")
    assert parsed_data["is_complete"] is False


def test_parse_unwanted_quality_detected(parser):
    parsed_data = parser.parse(item=None, string="Low.Quality.Movie.CAM.2020")
    assert parsed_data["is_unwanted_quality"] is True


def test_parse_unwanted_quality_not_detected(parser):
    parsed_data = parser.parse(item=None, string="High.Quality.Movie.1080p.2020")
    assert parsed_data["is_unwanted_quality"] is False
