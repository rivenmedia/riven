import pytest

from program.apis.anilist_api import AnilistAPI


@pytest.fixture
def anilist_api():
    return AnilistAPI()

def test_anilist_validate(anilist_api):
    response = anilist_api.validate()
    assert response is not None

def test_anilist_get_media_by_id(anilist_api):
    anilist_id = 1
    response = anilist_api.get_media_by_id(anilist_id)
    assert response is not None
