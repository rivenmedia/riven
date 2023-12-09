from copy import copy
from fastapi import APIRouter, Request
from program.media import MediaItemState
from utils.settings import settings_manager
from pydantic import BaseModel


class SetSettings(BaseModel):
    key: str
    value: str


router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    responses={404: {"description": "Not found"}},
)


@router.get("/load")
async def load_settings():
    """Load settings"""
    settings_manager.load()


@router.post("/save")
async def save_settings():
    """Save settings"""
    settings_manager.save()


@router.get("/get/{key}")
async def get_settings(key: str):
    """Get settings"""
    return settings_manager.get(key)


@router.post("/set")
async def set_settings(settings: SetSettings):
    """Set settings"""
    settings_manager.set(
        settings.key,
        settings.value,
    )
