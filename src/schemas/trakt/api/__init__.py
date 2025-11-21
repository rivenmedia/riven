# flake8: noqa

if __import__("typing").TYPE_CHECKING:
    # import apis into api package
    from schemas.trakt.api.authentication_devices_api import AuthenticationDevicesApi
    from schemas.trakt.api.authentication_o_auth_api import AuthenticationOAuthApi
    from schemas.trakt.api.calendars_api import CalendarsApi
    from schemas.trakt.api.certifications_api import CertificationsApi
    from schemas.trakt.api.checkin_api import CheckinApi
    from schemas.trakt.api.comments_api import CommentsApi
    from schemas.trakt.api.countries_api import CountriesApi
    from schemas.trakt.api.episodes_api import EpisodesApi
    from schemas.trakt.api.genres_api import GenresApi
    from schemas.trakt.api.languages_api import LanguagesApi
    from schemas.trakt.api.lists_api import ListsApi
    from schemas.trakt.api.movies_api import MoviesApi
    from schemas.trakt.api.networks_api import NetworksApi
    from schemas.trakt.api.notes_api import NotesApi
    from schemas.trakt.api.people_api import PeopleApi
    from schemas.trakt.api.recommendations_api import RecommendationsApi
    from schemas.trakt.api.scrobble_api import ScrobbleApi
    from schemas.trakt.api.search_api import SearchApi
    from schemas.trakt.api.seasons_api import SeasonsApi
    from schemas.trakt.api.shows_api import ShowsApi
    from schemas.trakt.api.sync_api import SyncApi
    from schemas.trakt.api.users_api import UsersApi

else:
    from lazy_imports import LazyModule, as_package, load

    load(
        LazyModule(
            *as_package(__file__),
            """# import apis into api package
from schemas.trakt.api.authentication_devices_api import AuthenticationDevicesApi
from schemas.trakt.api.authentication_o_auth_api import AuthenticationOAuthApi
from schemas.trakt.api.calendars_api import CalendarsApi
from schemas.trakt.api.certifications_api import CertificationsApi
from schemas.trakt.api.checkin_api import CheckinApi
from schemas.trakt.api.comments_api import CommentsApi
from schemas.trakt.api.countries_api import CountriesApi
from schemas.trakt.api.episodes_api import EpisodesApi
from schemas.trakt.api.genres_api import GenresApi
from schemas.trakt.api.languages_api import LanguagesApi
from schemas.trakt.api.lists_api import ListsApi
from schemas.trakt.api.movies_api import MoviesApi
from schemas.trakt.api.networks_api import NetworksApi
from schemas.trakt.api.notes_api import NotesApi
from schemas.trakt.api.people_api import PeopleApi
from schemas.trakt.api.recommendations_api import RecommendationsApi
from schemas.trakt.api.scrobble_api import ScrobbleApi
from schemas.trakt.api.search_api import SearchApi
from schemas.trakt.api.seasons_api import SeasonsApi
from schemas.trakt.api.shows_api import ShowsApi
from schemas.trakt.api.sync_api import SyncApi
from schemas.trakt.api.users_api import UsersApi

""",
            name=__name__,
            doc=__doc__,
        )
    )
