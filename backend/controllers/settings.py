from copy import copy
from fastapi import APIRouter
from utils.settings import settings_manager
from pydantic import BaseModel


class SetSettings(BaseModel):
    key: str
    value: str


settings_router = APIRouter(
    tags=["settings"],
    responses={404: {"description": "Not found"}},
)

@settings_router.get("/load")
async def load_settings():
    """Load settings"""
    settings_manager.load()

@settings_router.post("/save")
async def save_settings():
    """Save settings"""
    settings_manager.save()

@settings_router.get("/get/{key}")
async def get_settings(key: str):
    """Get settings"""
    return settings_manager.get(key)

@settings_router.post("/set")
async def set_settings(settings: SetSettings):
    """Set settings"""
    settings_manager.set(
        settings.key,
        settings.value,
    )