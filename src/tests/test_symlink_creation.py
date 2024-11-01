import shutil
from datetime import datetime
from pathlib import Path

import pytest
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

from program.media.item import Episode, Movie, Season, Show
from program.settings.manager import settings_manager
from program.symlink import Symlinker

logger.disable("program")  # Suppress

Base = declarative_base()
url = URL.create(
    drivername="postgresql",
    username="coderpad",
    host="/tmp/postgresql/socket",
    database="coderpad",
)
engine = create_engine(url)
Session = sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="module")
def movie():
    movie = Movie({})
    movie.title = "Riven"
    movie.aired_at = datetime(2020, 1, 1)
    movie.imdb_id = "tt18278776"
    return movie


@pytest.fixture(scope="module")
def episode():
    show = Show({})
    show.title = "Big Art"
    show.aired_at = datetime(2015, 1, 1)
    show.imdb_id = "tt4667710"

    season = Season({})
    season.title = "Season 01"
    season.parent = show
    season.number = 1

    episode = Episode({})
    episode.title = "S01E06 Riven with Fire"
    episode.parent = season
    episode.number = 6
    episode.imdb_id = "tt14496350"
    return episode


class MockSettings:
    def __init__(self, library_path, rclone_path):
        self.force_refresh = False
        self.symlink = type(
            "symlink",
            (),
            {
                "library_path": Path(library_path),
                "rclone_path": Path(rclone_path),
                "separate_anime_dirs": True,
            },
        )


@pytest.fixture
def symlinker(fs):
    library_path = "/fake/library"
    fs.create_dir(f"{library_path}")

    rclone_path = "/fake/rclone"
    fs.create_dir(f"{rclone_path}")

    settings_manager.settings = MockSettings(library_path, rclone_path)
    return Symlinker()


def test_valid_symlinker(symlinker):
    assert symlinker.initialized, "Library should be initialized successfully."
    assert symlinker.library_path_movies.exists()
    assert symlinker.library_path_shows.exists()
    assert symlinker.library_path_anime_movies.exists()
    assert symlinker.library_path_anime_shows.exists()


def test_invalid_library_structure(fs):
    valid_path = "/valid"
    invalid_path = "/invalid"
    fs.create_dir(invalid_path)

    # Invalid library path
    settings_manager.settings = MockSettings(invalid_path, valid_path)
    library = Symlinker()
    assert (
        not library.initialized
    ), "Library should fail initialization with incorrect structure."

    # invalid rclone path
    settings_manager.settings = MockSettings(valid_path, invalid_path)
    library = Symlinker()
    assert (
        not library.initialized
    ), "Library should fail initialization with incorrect structure."


def test_symlink_create_invalid_item(symlinker):
    assert symlinker.symlink(None) is False
    assert symlinker.symlink(Movie({})) is False


def test_symlink_movie(symlinker, movie, fs):
    def symlink_path(movie: Movie) -> Path:
        """
        Simplistic version of Symlinker._create_item_folders
        """
        name = symlinker._determine_file_name(movie)
        return symlinker.library_path_movies / name / (name + ".mkv")

    def symlink_check(target: Path):
        """
        Runs symlinker, confirms the movie's symlink is in the right place and points to the real path.
        """
        # Create "real" file, run symlinker
        fs.create_file(target)
        assert symlinker._symlink(movie) is True

        # Validate the symlink
        assert Path(movie.symlink_path) == symlink_path(movie)
        assert Path(movie.symlink_path).is_symlink()
        assert Path(movie.symlink_path).readlink() == target

        # cleanup
        shutil.rmtree(symlinker.rclone_path) and symlinker.rclone_path.mkdir()
        shutil.rmtree(
            symlinker.library_path_movies
        ) and symlinker.library_path_movies.mkdir()

    file = f"{movie.title}.mkv"

    movie.folder, movie.alternative_folder, movie.file = (movie.title, "other", file)
    symlink_check(symlinker.rclone_path / movie.title / file)
    symlink_check(symlinker.rclone_path / "other" / file)
    symlink_check(symlinker.rclone_path / file / file)
    symlink_check(symlinker.rclone_path / file)

    # files in the root
    movie.folder, movie.alternative_folder, movie.file = (None, None, file)
    symlink_check(symlinker.rclone_path / file)


def test_symlink_episode(symlinker, episode, fs):
    season_name = "Season %02d" % episode.parent.number

    def symlink_path(episode: Episode) -> Path:
        """
        Simplistic version of Symlinker._create_item_folders
        """
        show = episode.parent.parent
        show_name = f"{show.title} ({show.aired_at.year}) {{imdb-{show.imdb_id}}}"
        episode_name = symlinker._determine_file_name(episode)
        return (
            symlinker.library_path_shows
            / show_name
            / season_name
            / (episode_name + ".mkv")
        )

    def symlink_check(target: Path):
        """
        Runs symlinker, confirms the episode's symlink is in the right place and points to the real path.
        """
        # Create "real" file, run symlinker
        fs.create_file(target)
        assert symlinker._symlink(episode) is True

        # Validate the symlink
        assert Path(episode.symlink_path) == symlink_path(episode)
        assert Path(episode.symlink_path).is_symlink()
        assert Path(episode.symlink_path).readlink() == target

        # cleanup
        shutil.rmtree(symlinker.rclone_path) and symlinker.rclone_path.mkdir()
        shutil.rmtree(
            symlinker.library_path_shows
        ) and symlinker.library_path_shows.mkdir()

    file = f"{episode.title}.mkv"

    # Common namings
    episode.folder, episode.alternative_folder, episode.file = (
        episode.parent.parent.title,
        "other",
        file,
    )
    # symlink_check(symlinker.rclone_path / episode.parent.parent.title / season_name / file) # Not supported
    symlink_check(symlinker.rclone_path / episode.parent.parent.title / file)
    # symlink_check(symlinker.rclone_path / "other" / file)
    symlink_check(symlinker.rclone_path / file / file)
    symlink_check(symlinker.rclone_path / file)

    # Somewhat less common: Show Name - Season 01 / file
    name = str(episode.parent.parent.title + season_name)
    episode.folder, episode.alternative_folder, episode.file = (name, None, file)
    symlink_check(symlinker.rclone_path / name / file)

    # Files in the rclone root
    episode.folder, episode.alternative_folder, episode.file = (None, None, file)
    symlink_check(symlinker.rclone_path / file)
