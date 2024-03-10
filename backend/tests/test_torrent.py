from program.media.item import Show
from program.versions.parser import Torrent


def test_valid_torrent():
    item = Show({"title": "The Walking Dead"})

    torrent = Torrent.create(
        item,
        raw_title="The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]",
        infohash="1234567890",
    )

    assert torrent.title == "The Walking Dead S05E03 720p HDTV x264-ASAP[ettv]"
    assert torrent.infohash == "1234567890"
    assert torrent.parsed_data is not None
    assert torrent.parsed_data.parsed_title == "The Walking Dead"
    assert torrent.parsed_data.fetch is True
    assert torrent.rank == 0   # ranking is not implemented yet - default value is 0
