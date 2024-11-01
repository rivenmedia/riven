from copy import copy
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from program.settings.manager import settings_manager
from program.settings.models import AppModel

from ..models.shared import MessageResponse


class SetSettings(BaseModel):
    key: str
    value: Any


router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    responses={404: {"description": "Not found"}},
)


@router.get("/schema", operation_id="get_settings_schema")
async def get_settings_schema() -> dict[str, Any]:
    """
    Get the JSON schema for the settings.
    """
    return settings_manager.settings.model_json_schema()

@router.get("/load", operation_id="load_settings")
async def load_settings() -> MessageResponse:
    settings_manager.load()
    return {
        "message": "Settings loaded!",
    }

@router.post("/save", operation_id="save_settings")
async def save_settings() -> MessageResponse:
    settings_manager.save()
    return {
        "message": "Settings saved!",
    }


@router.get("/get/all", operation_id="get_all_settings")
async def get_all_settings() -> AppModel:
    return copy(settings_manager.settings)


@router.get("/get/{paths}", operation_id="get_settings")
async def get_settings(paths: str) -> dict[str, Any]:
    current_settings = settings_manager.settings.model_dump()
    data = {}
    for path in paths.split(","):
        keys = path.split(".")
        current_obj = current_settings

        for k in keys:
            if k not in current_obj:
                return None
            current_obj = current_obj[k]

        data[path] = current_obj
    return data


@router.post("/set/all", operation_id="set_all_settings")
async def set_all_settings(new_settings: Dict[str, Any]) -> MessageResponse:
    current_settings = settings_manager.settings.model_dump()

    def update_settings(current_obj, new_obj):
        for key, value in new_obj.items():
            if isinstance(value, dict) and key in current_obj:
                update_settings(current_obj[key], value)
            else:
                current_obj[key] = value

    update_settings(current_settings, new_settings)

    # Validate and save the updated settings
    try:
        updated_settings = settings_manager.settings.model_validate(current_settings)
        settings_manager.load(settings_dict=updated_settings.model_dump())
        settings_manager.save()  # Ensure the changes are persisted
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "All settings updated successfully!",
    }

@router.post("/set", operation_id="set_settings")
async def set_settings(settings: List[SetSettings]) -> MessageResponse:
    current_settings = settings_manager.settings.model_dump()

    for setting in settings:
        keys = setting.key.split(".")
        current_obj = current_settings

        # Navigate to the last key's parent object, ensuring all keys exist.
        for k in keys[:-1]:
            if k not in current_obj:
                raise HTTPException(
                    status_code=400,
                    detail=f"Path '{'.'.join(keys[:-1])}' does not exist.",
                )
            current_obj = current_obj[k]

        # Ensure the final key exists before setting the value.
        if keys[-1] in current_obj:
            current_obj[keys[-1]] = setting.value
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Key '{keys[-1]}' does not exist in path '{'.'.join(keys[:-1])}'.",
            )

    # Validate and apply the updated settings to the AppModel instance
    try:
        updated_settings = settings_manager.settings.__class__(**current_settings)
        settings_manager.load(settings_dict=updated_settings.model_dump())
        settings_manager.save()  # Ensure the changes are persisted
    except ValidationError as e:
        raise HTTPException from e(
            status_code=400,
            detail=f"Failed to update settings: {str(e)}",
        )

    return {"message": "Settings updated successfully."}
