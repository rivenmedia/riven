from typing import Optional, List
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(
    prefix="/queue",
    tags=["queue"],
    responses={404: {"description": "Not found"}},
)

class QueueStatusResponse(BaseModel):
    is_paused: bool
    paused_items: List[str]
    message: str

@router.post("/pause", operation_id="pause_queue")
async def pause_queue(request: Request, item_id: Optional[str] = None) -> QueueStatusResponse:
    request.app.program.em.pause_queue(item_id)
    return {
        "is_paused": True,
        "paused_items": request.app.program.em.get_paused_items(),
        "message": f"{'Item ' + item_id if item_id else 'Queue'} paused"
    }

@router.post("/resume", operation_id="resume_queue")
async def resume_queue(request: Request, item_id: Optional[str] = None) -> QueueStatusResponse:
    request.app.program.em.resume_queue(item_id)
    return {
        "is_paused": request.app.program.em.is_paused(),
        "paused_items": request.app.program.em.get_paused_items(),
        "message": f"{'Item ' + item_id if item_id else 'Queue'} resumed"
    }

@router.get("/status", operation_id="queue_status")
async def queue_status(request: Request) -> QueueStatusResponse:
    is_globally_paused = request.app.program.em.is_paused()
    paused_items = request.app.program.em.get_paused_items()
    
    message = "Queue is globally paused" if is_globally_paused else (
        f"{len(paused_items)} items paused" if paused_items else "Queue is active"
    )
    
    return {
        "is_paused": is_globally_paused,
        "paused_items": paused_items,
        "message": message
    }