from typing import Any, List, Literal, Optional

from pydantic import BaseModel, field_validator

MediaType = Literal["movie", "tv"]


class Media(BaseModel):
    media_type: MediaType
    status: str
    imdbId: str | None = None
    tmdbId: int
    tvdbId: int | None = None

    @field_validator("imdbId", mode="after")
    @classmethod
    def stringify_imdb_id(cls, value: Any):
        if value and isinstance(value, int):
            return f"tt{int(value):07d}"
        return None

    @field_validator("tvdbId", "tmdbId", mode="before")
    @classmethod
    def validate_ids(cls, value: Any):
        if value and isinstance(value, str) and value != "":
            return int(value)
        return None


class RequestInfo(BaseModel):
    request_id: str
    requestedBy_email: str
    requestedBy_username: str
    requestedBy_avatar: Optional[str]

class IssueInfo(BaseModel):
    issue_id: str
    issue_type: str
    issue_status: str
    reportedBy_email: str
    reportedBy_username: str
    reportedBy_avatar: Optional[str]

class CommentInfo(BaseModel):
    comment_message: str
    commentedBy_email: str
    commentedBy_username: str
    commentedBy_avatar: Optional[str]

class OverseerrWebhook(BaseModel):
    notification_type: str
    event: str
    subject: str
    message: Optional[str] = None
    image: Optional[str] = None
    media: Media
    request: Optional[RequestInfo] = None
    issue: Optional[IssueInfo] = None
    comment: Optional[CommentInfo] = None
    extra: List[dict[str, Any]] = []

    @property
    def requested_seasons(self) -> Optional[List[int]]:
        for extra in self.extra:
            if extra["name"] == "Requested Seasons":
                return [int(x) for x in extra["value"].split(",")]
        return None
