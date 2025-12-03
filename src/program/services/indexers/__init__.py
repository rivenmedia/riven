"""Composite indexer that uses TMDB for movies and TVDB for TV shows"""

from collections.abc import AsyncGenerator
from loguru import logger
from sqlalchemy import select

from program.db.db import db_session
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.services.indexers.base import BaseIndexer
from program.services.indexers.tmdb_indexer import TMDBIndexer
from program.services.indexers.tvdb_indexer import TVDBIndexer
from program.core.runner import RunnerResult


class IndexerService(BaseIndexer):
    """Entry point to indexing. Composite indexer that delegates to appropriate service based on media type."""

    def __init__(self):
        super().__init__()

        self.tmdb_indexer = TMDBIndexer()
        self.tvdb_indexer = TVDBIndexer()

    @classmethod
    def get_key(cls) -> str:
        return "indexer"

    async def run(
        self,
        item: MediaItem,
        log_msg: bool = True,
    ) -> AsyncGenerator[RunnerResult, None]:
        """Run the appropriate indexer based on item type."""

        if isinstance(item, Movie) or (item.tmdb_id and not item.tvdb_id):
            yield await anext(
                self.tmdb_indexer.run(
                    item=item,
                    log_msg=log_msg,
                )
            )
        elif isinstance(item, (Show, Season, Episode)) or (
            item.tvdb_id and not item.tmdb_id
        ):
            yield await anext(
                self.tvdb_indexer.run(
                    item=item,
                    log_msg=log_msg,
                )
            )
        else:
            movie_result = self.tmdb_indexer.run(
                item=item,
                log_msg=False,
            )

            indexed_item = await anext(movie_result, None)

            if not indexed_item:
                show_result = self.tvdb_indexer.run(
                    item=item,
                    log_msg=False,
                )

                indexed_item = await anext(show_result, None)

            if indexed_item:
                yield indexed_item
                return

        logger.warning(f"Unknown item type, cannot index {item.log_string}.. skipping")

        return

    async def reindex_ongoing(self) -> int:
        """
        Reindex all ongoing/unreleased movies and shows by updating them in-place.

        Returns the number of items reindexed.
        """

        try:
            with db_session() as session:
                # Gather two sets: (1) ongoing/unreleased movies & shows, (2) shows missing tvdb_status
                items_state = (
                    session.execute(
                        select(MediaItem)
                        .where(MediaItem.type.in_(["movie", "show"]))
                        .where(
                            MediaItem.last_state.in_(
                                [States.Ongoing, States.Unreleased]
                            )
                        )
                    )
                    .unique()
                    .scalars()
                    .all()
                )

                # For now to populate missing fields for existing shows, this can be removed later on.
                shows_missing_status = (
                    session.execute(select(Show).where(Show.tvdb_status.is_(None)))
                    .unique()
                    .scalars()
                    .all()
                )

                # Combine and deduplicate by id
                items_map = {i.id: i for i in items_state}

                for sh in shows_missing_status:
                    items_map.setdefault(sh.id, sh)

                items = list(items_map.values())

                if not items:
                    logger.debug("No ongoing/unreleased items to reindex")
                    return 0

                logger.debug(f"Reindexing {len(items)} ongoing/unreleased items")

                count = 0

                for item in items:
                    try:
                        updated = await anext(self.run(item, log_msg=False), None)

                        if updated:
                            with session.no_autoflush:
                                session.merge(updated)

                            count += 1
                    except Exception as e:
                        logger.error(f"Failed reindexing {item.log_string}: {e}")
                        continue

                try:
                    session.commit()
                except Exception as e:
                    logger.debug(
                        f"Commit failed during reindex (likely item was deleted): {e}"
                    )
                    session.rollback()

                return count
        except Exception as e:
            logger.error(f"Error during reindex_ongoing: {e}")
            return 0
