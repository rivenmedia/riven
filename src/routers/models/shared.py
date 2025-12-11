from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    message: str


class RootResponse(MessageResponse):
    version: str


class IdListPayload(BaseModel):
    ids: list[str] = Field(description="List of IDs", min_length=1)
