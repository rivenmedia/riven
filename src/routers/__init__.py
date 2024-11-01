from fastapi import Depends, Request
from fastapi.routing import APIRouter

from auth import resolve_api_key
from program.settings.manager import settings_manager
from routers.models.shared import RootResponse
from routers.secure.default import router as default_router
from routers.secure.items import router as items_router
from routers.secure.scrape import router as scrape_router
from routers.secure.settings import router as settings_router
from routers.secure.stream import router as stream_router
from routers.secure.webhooks import router as webhooks_router

API_VERSION = "v1"

app_router = APIRouter(prefix=f"/api/{API_VERSION}")
@app_router.get("/", operation_id="root")
async def root(_: Request) -> RootResponse:
    return {
        "message": "Riven is running!",
        "version": settings_manager.settings.version,
    }

app_router.include_router(default_router, dependencies=[Depends(resolve_api_key)])
app_router.include_router(items_router, dependencies=[Depends(resolve_api_key)])
app_router.include_router(scrape_router, dependencies=[Depends(resolve_api_key)])
app_router.include_router(settings_router, dependencies=[Depends(resolve_api_key)])
app_router.include_router(webhooks_router, dependencies=[Depends(resolve_api_key)])
app_router.include_router(stream_router, dependencies=[Depends(resolve_api_key)])