# flake8: noqa

if __import__("typing").TYPE_CHECKING:
    # import apis into api package
    from schemas.overseerr.api.auth_api import AuthApi
    from schemas.overseerr.api.collection_api import CollectionApi
    from schemas.overseerr.api.issue_api import IssueApi
    from schemas.overseerr.api.media_api import MediaApi
    from schemas.overseerr.api.movies_api import MoviesApi
    from schemas.overseerr.api.other_api import OtherApi
    from schemas.overseerr.api.person_api import PersonApi
    from schemas.overseerr.api.public_api import PublicApi
    from schemas.overseerr.api.request_api import RequestApi
    from schemas.overseerr.api.search_api import SearchApi
    from schemas.overseerr.api.service_api import ServiceApi
    from schemas.overseerr.api.settings_api import SettingsApi
    from schemas.overseerr.api.tmdb_api import TmdbApi
    from schemas.overseerr.api.tv_api import TvApi
    from schemas.overseerr.api.users_api import UsersApi

else:
    from lazy_imports import LazyModule, as_package, load

    load(
        LazyModule(
            *as_package(__file__),
            """# import apis into api package
from schemas.overseerr.api.auth_api import AuthApi
from schemas.overseerr.api.collection_api import CollectionApi
from schemas.overseerr.api.issue_api import IssueApi
from schemas.overseerr.api.media_api import MediaApi
from schemas.overseerr.api.movies_api import MoviesApi
from schemas.overseerr.api.other_api import OtherApi
from schemas.overseerr.api.person_api import PersonApi
from schemas.overseerr.api.public_api import PublicApi
from schemas.overseerr.api.request_api import RequestApi
from schemas.overseerr.api.search_api import SearchApi
from schemas.overseerr.api.service_api import ServiceApi
from schemas.overseerr.api.settings_api import SettingsApi
from schemas.overseerr.api.tmdb_api import TmdbApi
from schemas.overseerr.api.tv_api import TvApi
from schemas.overseerr.api.users_api import UsersApi

""",
            name=__name__,
            doc=__doc__,
        )
    )
