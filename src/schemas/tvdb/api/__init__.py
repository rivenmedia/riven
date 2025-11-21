# flake8: noqa

if __import__("typing").TYPE_CHECKING:
    # import apis into api package
    from schemas.tvdb.api.artwork_api import ArtworkApi
    from schemas.tvdb.api.artwork_statuses_api import ArtworkStatusesApi
    from schemas.tvdb.api.artwork_types_api import ArtworkTypesApi
    from schemas.tvdb.api.award_categories_api import AwardCategoriesApi
    from schemas.tvdb.api.awards_api import AwardsApi
    from schemas.tvdb.api.characters_api import CharactersApi
    from schemas.tvdb.api.companies_api import CompaniesApi
    from schemas.tvdb.api.content_ratings_api import ContentRatingsApi
    from schemas.tvdb.api.countries_api import CountriesApi
    from schemas.tvdb.api.entity_types_api import EntityTypesApi
    from schemas.tvdb.api.episodes_api import EpisodesApi
    from schemas.tvdb.api.favorites_api import FavoritesApi
    from schemas.tvdb.api.genders_api import GendersApi
    from schemas.tvdb.api.genres_api import GenresApi
    from schemas.tvdb.api.inspiration_types_api import InspirationTypesApi
    from schemas.tvdb.api.languages_api import LanguagesApi
    from schemas.tvdb.api.lists_api import ListsApi
    from schemas.tvdb.api.login_api import LoginApi
    from schemas.tvdb.api.movie_statuses_api import MovieStatusesApi
    from schemas.tvdb.api.movies_api import MoviesApi
    from schemas.tvdb.api.people_api import PeopleApi
    from schemas.tvdb.api.people_types_api import PeopleTypesApi
    from schemas.tvdb.api.search_api import SearchApi
    from schemas.tvdb.api.seasons_api import SeasonsApi
    from schemas.tvdb.api.series_api import SeriesApi
    from schemas.tvdb.api.series_statuses_api import SeriesStatusesApi
    from schemas.tvdb.api.source_types_api import SourceTypesApi
    from schemas.tvdb.api.updates_api import UpdatesApi
    from schemas.tvdb.api.user_info_api import UserInfoApi

else:
    from lazy_imports import LazyModule, as_package, load

    load(
        LazyModule(
            *as_package(__file__),
            """# import apis into api package
from schemas.tvdb.api.artwork_api import ArtworkApi
from schemas.tvdb.api.artwork_statuses_api import ArtworkStatusesApi
from schemas.tvdb.api.artwork_types_api import ArtworkTypesApi
from schemas.tvdb.api.award_categories_api import AwardCategoriesApi
from schemas.tvdb.api.awards_api import AwardsApi
from schemas.tvdb.api.characters_api import CharactersApi
from schemas.tvdb.api.companies_api import CompaniesApi
from schemas.tvdb.api.content_ratings_api import ContentRatingsApi
from schemas.tvdb.api.countries_api import CountriesApi
from schemas.tvdb.api.entity_types_api import EntityTypesApi
from schemas.tvdb.api.episodes_api import EpisodesApi
from schemas.tvdb.api.favorites_api import FavoritesApi
from schemas.tvdb.api.genders_api import GendersApi
from schemas.tvdb.api.genres_api import GenresApi
from schemas.tvdb.api.inspiration_types_api import InspirationTypesApi
from schemas.tvdb.api.languages_api import LanguagesApi
from schemas.tvdb.api.lists_api import ListsApi
from schemas.tvdb.api.login_api import LoginApi
from schemas.tvdb.api.movie_statuses_api import MovieStatusesApi
from schemas.tvdb.api.movies_api import MoviesApi
from schemas.tvdb.api.people_api import PeopleApi
from schemas.tvdb.api.people_types_api import PeopleTypesApi
from schemas.tvdb.api.search_api import SearchApi
from schemas.tvdb.api.seasons_api import SeasonsApi
from schemas.tvdb.api.series_api import SeriesApi
from schemas.tvdb.api.series_statuses_api import SeriesStatusesApi
from schemas.tvdb.api.source_types_api import SourceTypesApi
from schemas.tvdb.api.updates_api import UpdatesApi
from schemas.tvdb.api.user_info_api import UserInfoApi

""",
            name=__name__,
            doc=__doc__,
        )
    )
