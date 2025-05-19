from .base import BaseIndexer
from .tmdb_indexer import TMDBIndexer
from .tvdb_indexer import TVDBIndexer
from .composite import CompositeIndexer

IndexerService = CompositeIndexer