import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from program.utils import data_dir_path
from program.utils.cli import (
    restore_database as restore_database_from_file,
    snapshot_database,
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
    from program.utils.cli import clean_snapshots

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
