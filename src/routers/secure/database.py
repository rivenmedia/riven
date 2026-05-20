import shutil
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from program.backup.bundle import (
    BACKUPS_DIR,
    ExportBundleOptions,
    ImportBundleOptions,
    bundle_download_path,
    clean_bundle_exports,
    export_bundle,
    import_bundle,
)
from program.utils import data_dir_path
from program.utils.cli import (
    clean_snapshots,
    snapshot_database,
)
from program.utils.cli import (
    restore_database as restore_database_from_file,
)
from program.utils.logging import logger

router = APIRouter(
    prefix="/database",
    tags=["database"],
    responses={404: {"description": "Not found"}},
)

SNAPSHOT_DIR = data_dir_path / "db_snapshot"


class BackupResponse(BaseModel):
    success: bool
    message: str
    filename: str | None = None


class RestoreResponse(BaseModel):
    success: bool
    message: str


@router.post(
    "/backup",
    operation_id="backup_database",
    response_model=BackupResponse,
)
async def backup_database() -> BackupResponse:
    """
    Create a backup of the database and return the backup filename.

    The backup is stored in ./data/db_snapshot/ directory.
    """
    try:
        filename = snapshot_database()

        if filename:
            logger.info(f"Database backup created via API: {filename}")
            return BackupResponse(
                success=True,
                message="Database backup created successfully",
                filename=filename,
            )
        else:
            raise HTTPException(
                status_code=500, detail="Failed to create database backup"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating database backup via API: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create database backup: {str(e)}"
        )


@router.get(
    "/backup/download/{filename}",
    operation_id="download_backup",
    response_class=FileResponse,
)
async def download_backup(filename: str) -> FileResponse:
    """
    Download a database backup file by filename.

    Use the filename returned from the /backup endpoint.
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not filename.endswith(".sql"):
        raise HTTPException(status_code=400, detail="Invalid file type")

    backup_path = SNAPSHOT_DIR / filename

    if not backup_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Backup file not found: {filename}"
        )

    return FileResponse(
        path=backup_path, filename=filename, media_type="application/sql"
    )


@router.post(
    "/restore",
    operation_id="restore_database",
    response_model=RestoreResponse,
)
async def restore_database(
    filename: Annotated[
        str | None,
        Form(description="Name of backup file in db_snapshot folder to restore from"),
    ] = None,
    file: Annotated[
        UploadFile | None,
        File(description="SQL backup file to upload and restore from"),
    ] = None,
) -> RestoreResponse:
    """
    Restore the database from a backup.

    Provide either:
    - filename: Name of an existing backup file in the db_snapshot folder
    - file: Upload a SQL backup file to restore from

    If neither is provided, restores from 'latest.sql'.
    """
    temp_file_path: Path | None = None
    try:
        snapshot_path: Path | None = None

        if file and filename:
            raise HTTPException(
                status_code=400, detail="Provide either 'filename' or 'file', not both"
            )

        if file:
            if not file.filename or not file.filename.endswith(".sql"):
                raise HTTPException(
                    status_code=400, detail="Uploaded file must be a .sql file"
                )

            if "/" in file.filename or "\\" in file.filename or ".." in file.filename:
                raise HTTPException(status_code=400, detail="Invalid filename")

            SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            temp_file_path = SNAPSHOT_DIR / f"_uploaded_{file.filename}"

            with open(temp_file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            snapshot_path = temp_file_path
            logger.info(f"Uploaded backup file saved to: {temp_file_path}")

        elif filename:
            if "/" in filename or "\\" in filename or ".." in filename:
                raise HTTPException(status_code=400, detail="Invalid filename")

            if not filename.endswith(".sql"):
                raise HTTPException(
                    status_code=400, detail="Invalid file type, must be .sql"
                )

            snapshot_path = SNAPSHOT_DIR / filename

            if not snapshot_path.exists():
                raise HTTPException(
                    status_code=404, detail=f"Backup file not found: {filename}"
                )

        # If no file or filename provided, restore_database will use latest.sql
        success = restore_database_from_file(snapshot_path)

        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()

        if success:
            source = filename or (file.filename if file else "latest.sql")
            logger.info(f"Database restored via API from: {source}")
            return RestoreResponse(
                success=True, message=f"Database restored successfully from {source}"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to restore database")

    except HTTPException:
        raise
    except Exception as e:
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()
        logger.error(f"Error restoring database via API: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to restore database: {str(e)}"
        )


class CleanSnapshotsResponse(BaseModel):
    success: bool
    message: str
    deleted_files: list[str]


@router.delete(
    "/backup/clean",
    operation_id="clean_snapshots",
    response_model=CleanSnapshotsResponse,
)
async def clean_snapshots_endpoint(
    filename: str | None = None,
) -> CleanSnapshotsResponse:
    """
    Clean database snapshot files.

    If filename is provided, deletes only that specific snapshot.
    If no filename is provided, deletes all snapshots.
    """
    try:
        # Validate filename if provided
        if filename:
            if "/" in filename or "\\" in filename or ".." in filename:
                raise HTTPException(status_code=400, detail="Invalid filename")

        success, deleted_files = clean_snapshots(filename)

        if success:
            if filename:
                message = f"Deleted snapshot: {filename}"
            else:
                message = f"Deleted {len(deleted_files)} snapshot(s)"

            logger.info(f"Snapshots cleaned via API: {deleted_files}")
            return CleanSnapshotsResponse(
                success=True,
                message=message,
                deleted_files=deleted_files,
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to clean snapshots")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning snapshots via API: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to clean snapshots: {str(e)}"
        )


class ExportBundleResponse(BaseModel):
    success: bool
    message: str
    filename: str | None = None
    manifest: dict[str, Any] | None = None


class ImportBundleResponse(BaseModel):
    success: bool
    message: str
    added_movies: int = 0
    added_shows: int = 0
    skipped_titles: int = 0
    pins_restored: int = 0
    pins_failed: int = 0
    errors: list[str] = []


class CleanBundlesResponse(BaseModel):
    success: bool
    message: str
    deleted_files: list[str]


@router.post(
    "/export/bundle",
    operation_id="export_backup_bundle",
    response_model=ExportBundleResponse,
)
async def export_backup_bundle(
    include_settings: Annotated[bool, Query()] = True,
    redact_secrets: Annotated[bool, Query()] = False,
) -> ExportBundleResponse:
    """Create a CSV library backup ZIP on disk and return the download filename."""
    logger.info(
        "[backup] API export requested (include_settings={}, redact_secrets={})",
        include_settings,
        redact_secrets,
    )
    try:
        result = export_bundle(
            ExportBundleOptions(
                include_settings=include_settings,
                redact_secrets=redact_secrets,
            )
        )
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
        logger.info(f"Backup bundle created via API: {result.filename}")
        return ExportBundleResponse(
            success=True,
            message=result.message,
            filename=result.filename,
            manifest=result.manifest,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating backup bundle via API: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create backup bundle: {str(e)}"
        )


@router.get(
    "/export/download/{filename}",
    operation_id="download_backup_bundle",
    response_class=FileResponse,
)
async def download_backup_bundle(filename: str) -> FileResponse:
    """Download a backup bundle ZIP by filename."""
    try:
        backup_path = bundle_download_path(filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not backup_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Backup file not found: {filename}"
        )

    size_mb = backup_path.stat().st_size / (1024 * 1024)
    logger.info("[backup] API download: {} ({:.2f} MB)", filename, size_mb)

    return FileResponse(
        path=backup_path,
        filename=filename,
        media_type="application/zip",
    )


@router.post(
    "/import/bundle",
    operation_id="import_backup_bundle",
    response_model=ImportBundleResponse,
)
async def import_backup_bundle(
    file: Annotated[
        UploadFile,
        File(description="Backup bundle ZIP to import"),
    ],
    restore_settings: Annotated[bool, Form()] = False,
    skip_existing_titles: Annotated[bool, Form()] = True,
    restore_pins: Annotated[bool, Form()] = True,
) -> ImportBundleResponse:
    """Import library titles and pinned streams from a backup bundle ZIP."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    if "/" in file.filename or "\\" in file.filename or ".." in file.filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    upload_path = BACKUPS_DIR / f"_uploaded_{file.filename}"

    logger.info(
        "[backup] API import requested: {} (restore_settings={}, "
        "skip_existing={}, restore_pins={})",
        file.filename,
        restore_settings,
        skip_existing_titles,
        restore_pins,
    )

    try:
        with open(upload_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        result = import_bundle(
            upload_path,
            ImportBundleOptions(
                restore_settings=restore_settings,
                skip_existing_titles=skip_existing_titles,
                restore_pins=restore_pins,
            ),
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)

        logger.info(f"Backup bundle imported via API: {result.message}")
        return ImportBundleResponse(
            success=True,
            message=result.message,
            added_movies=result.added_movies,
            added_shows=result.added_shows,
            skipped_titles=result.skipped_titles,
            pins_restored=result.pins_restored,
            pins_failed=result.pins_failed,
            errors=result.errors[:50],
        )
    except HTTPException:
        raise
    except Exception as e:
        if upload_path.exists():
            upload_path.unlink()
        logger.error(f"Error importing backup bundle via API: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to import backup bundle: {str(e)}"
        )


@router.delete(
    "/export/clean",
    operation_id="clean_backup_bundles",
    response_model=CleanBundlesResponse,
)
async def clean_backup_bundles_endpoint(
    filename: str | None = None,
) -> CleanBundlesResponse:
    """Delete backup bundle ZIP file(s) from data/backups/."""
    try:
        if filename:
            if "/" in filename or "\\" in filename or ".." in filename:
                raise HTTPException(status_code=400, detail="Invalid filename")

        success, deleted_files = clean_bundle_exports(filename)

        if success:
            if filename:
                message = f"Deleted backup bundle: {filename}"
            else:
                message = f"Deleted {len(deleted_files)} backup bundle(s)"
            logger.info("[backup] {}", message)
            return CleanBundlesResponse(
                success=True,
                message=message,
                deleted_files=deleted_files,
            )
        raise HTTPException(status_code=500, detail="Failed to clean backup bundles")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning backup bundles via API: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to clean backup bundles: {str(e)}"
        )
