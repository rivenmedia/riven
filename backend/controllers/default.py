import requests
from fastapi import APIRouter, HTTPException, Request
from program.content.trakt import TraktContent
from program.settings.manager import settings_manager

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def root():
    return {
        "success": True,
        "message": "Iceburg is running!",
        "version": settings_manager.settings.version,
    }


@router.get("/health")
async def health(request: Request):
    return {
        "success": True,
        "message": request.app.program.initialized,
    }


@router.get("/user")
async def get_rd_user():
    api_key = settings_manager.settings.downloaders.real_debrid.api_key
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(
        "https://api.real-debrid.com/rest/1.0/user", headers=headers, timeout=10
    )
    return response.json()

@router.get("/torbox")
async def get_torbox_user():
    api_key = settings_manager.settings.downloaders.torbox_downloader.api_key
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(
        "https://api.torbox.app/v1/api/user/me", headers=headers, timeout=10
    )
    return response.json()

@router.get("/services")
async def get_services(request: Request):
    data = {}
    if hasattr(request.app.program, "services"):
        for service in request.app.program.services.values():
            data[service.key] = service.initialized
            if not hasattr(service, "services"):
                continue
            for sub_service in service.services.values():
                data[sub_service.key] = sub_service.initialized
    return {"success": True, "data": data}

@router.get("/trakt/oauth/initiate")
async def initiate_trakt_oauth(request: Request):
    trakt = request.app.program.services.get(TraktContent)
    if trakt is None:
        raise HTTPException(status_code=404, detail="Trakt service not found")
    auth_url = trakt.perform_oauth_flow()
    return {"auth_url": auth_url}

@router.get("/trakt/oauth/callback")
async def trakt_oauth_callback(code: str, request: Request):
    trakt = request.app.program.services.get(TraktContent)
    if trakt is None:
        raise HTTPException(status_code=404, detail="Trakt service not found")
    success = trakt.handle_oauth_callback(code)
    if success:
        return {"success": True, "message": "OAuth token obtained successfully"}
    else:
        raise HTTPException(status_code=400, detail="Failed to obtain OAuth token")
