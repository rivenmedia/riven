from typing import Generic, TypeVar
from pydantic import BaseModel


class MessageAndSuccessResponse(BaseModel):
    message: str
    success: bool

class MessageResponse(BaseModel):
    message: str

T = TypeVar('T', bound=BaseModel)

class DataAndSuccessResponse(BaseModel, Generic[T]):
    data: T
    success: bool