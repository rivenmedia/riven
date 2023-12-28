from fastapi import APIRouter, Request
from utils.settings import settings_manager
from program.realdebrid import get_user


router = APIRouter(
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def root(request: Request):
    return {
        "success": True,
        "message": "Iceburg is running!",
    }


@router.get("/health")
async def health(request: Request):
    return {
        "success": True,
        "message": "Iceburg is running!",
    }


@router.get("/user")
async def get_rd_user():
    return get_user()


@router.get("/services")
async def get_services():
    return {
        "success": True,
        "data": {
            "plex": settings_manager.get("plex"),
            "mdblist": settings_manager.get("mdblist"),
            "overseerr": settings_manager.get("overseerr"),
            "torrentio": settings_manager.get("torrentio"),
            "realdebrid": settings_manager.get("realdebrid"),
        },
    }
