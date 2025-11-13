# flake8: noqa

if __import__("typing").TYPE_CHECKING:
    # import apis into api package
    from schemas.mdblist.api.external_lists_api import ExternalListsApi
    from schemas.mdblist.api.scrobble_api import ScrobbleApi
    from schemas.mdblist.api.sync_api import SyncApi
    from schemas.mdblist.api.watchlist_api import WatchlistApi
    from schemas.mdblist.api.default_api import DefaultApi

else:
    from lazy_imports import LazyModule, as_package, load

    load(
        LazyModule(
            *as_package(__file__),
            """# import apis into api package
from schemas.mdblist.api.external_lists_api import ExternalListsApi
from schemas.mdblist.api.scrobble_api import ScrobbleApi
from schemas.mdblist.api.sync_api import SyncApi
from schemas.mdblist.api.watchlist_api import WatchlistApi
from schemas.mdblist.api.default_api import DefaultApi

""",
            name=__name__,
            doc=__doc__,
        )
    )
