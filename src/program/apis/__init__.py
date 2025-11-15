from kink import di

from program.settings.manager import settings_manager

from .listrr_api import ListrrAPI, ListrrAPIError
from .mdblist_api import MdblistAPI, MdblistAPIError
from .overseerr_api import OverseerrAPI, OverseerrAPIError
from .plex_api import PlexAPI, PlexAPIError
from .tmdb_api import TMDBApi, TMDBApiError
from .trakt_api import TraktAPI, TraktAPIError
from .tvdb_api import TVDBApi, TVDBApiError


def bootstrap_apis():
    __setup_plex()
    __setup_mdblist()
    __setup_overseerr()
    __setup_listrr()
    __setup_trakt()
    __setup_tmdb()
    __setup_tvdb()


def __setup_trakt():
    di[TraktAPI] = TraktAPI(settings_manager.settings.content.trakt)


def __setup_tmdb():
    di[TMDBApi] = TMDBApi()


def __setup_tvdb():
    di[TVDBApi] = TVDBApi()


def __setup_plex():
    if not settings_manager.settings.updaters.plex.enabled:
        return

    di[PlexAPI] = PlexAPI(
        settings_manager.settings.updaters.plex.token,
        settings_manager.settings.updaters.plex.url,
    )


def __setup_overseerr():
    if not settings_manager.settings.content.overseerr.enabled:
        return

    di[OverseerrAPI] = OverseerrAPI(
        settings_manager.settings.content.overseerr.api_key,
        settings_manager.settings.content.overseerr.url,
    )


def __setup_mdblist():
    if not settings_manager.settings.content.mdblist.enabled:
        return

    di[MdblistAPI] = MdblistAPI(settings_manager.settings.content.mdblist.api_key)


def __setup_listrr():
    if not settings_manager.settings.content.listrr.enabled:
        return

    di[ListrrAPI] = ListrrAPI(settings_manager.settings.content.listrr.api_key)
