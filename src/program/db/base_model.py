from sqlalchemy import MetaData, orm


class Base(orm.DeclarativeBase):
    """Base class for all database models"""

    pass


def get_base_metadata() -> MetaData:
    """Get the Base metadata for Alembic migrations"""

    # Import models to register them with Base.metadata

    from program.media import (
        MediaItem,  # pyright: ignore[reportUnusedImport]
        FilesystemEntry,  # pyright: ignore[reportUnusedImport]
        StreamRelation,  # pyright: ignore[reportUnusedImport]
        StreamBlacklistRelation,  # pyright: ignore[reportUnusedImport]
        Stream,  # pyright: ignore[reportUnusedImport]
    )
    from program.scheduling import (
        ScheduledTask,  # pyright: ignore[reportUnusedImport]
    )

    return Base.metadata
