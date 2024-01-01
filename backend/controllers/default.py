from fastapi import APIRouter
import requests
from utils.settings import settings_manager


router = APIRouter(
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def root():
    return {
        "success": True,
        "message": "Iceburg is running!",
    }


@router.get("/health")
async def health():
    return {
        "success": True,
        "message": "Iceburg is running!",
    }


@router.get("/user")
async def get_rd_user():
    api_key = settings_manager.get("realdebrid.api_key")
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(
        "https://api.real-debrid.com/rest/1.0/user", headers=headers
    )
    return response.json()


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
