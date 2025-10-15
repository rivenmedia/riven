import pytest
from RTN import RTN, DefaultRanking, SettingsModel, Torrent


@pytest.fixture
def settings_model():
    return SettingsModel()


@pytest.fixture
def ranking_model():
    return DefaultRanking()


# basic implementation for testing ranking
def test_manual_fetch_check_from_user(settings_model, ranking_model):
    rtn = RTN(settings_model, ranking_model)

    item: Torrent = rtn.rank(
        "Swamp People Serpent Invasion S03E05 720p WEB h264-KOGi[eztv re] mkv",
        "c08a9ee8ce3a5c2c08865e2b05406273cabc97e7",
        correct_title="Swamp People",
        remove_trash=False,
    )

    assert item.fetch is True, "Fetch should be True"
    assert item.rank > 0.0, "Rank should be greater than 0.0"
