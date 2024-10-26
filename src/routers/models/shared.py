from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str

class RootResponse(MessageResponse):
    version: str