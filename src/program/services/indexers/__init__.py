from .base import BaseIndexer
from .composite import CompositeIndexer
from .tmdb_indexer import TMDBIndexer
from .tvdb_indexer import TVDBIndexer

IndexerService = CompositeIndexer