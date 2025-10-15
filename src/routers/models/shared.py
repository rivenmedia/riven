from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str
    tmdb_ids: list[str] = []
    tvdb_ids: list[str] = []


class RootResponse(MessageResponse):
    version: str
