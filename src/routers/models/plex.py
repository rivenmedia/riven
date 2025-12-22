from pydantic import BaseModel, Field


class Account(BaseModel):
    id: int
    thumb: str
    title: str


class Server(BaseModel):
    title: str
    uuid: str


class Player(BaseModel):
    local: bool
    publicAddress: str
    title: str
    uuid: str


class Metadata(BaseModel):
    librarySectionType: str
    ratingKey: str
    key: str
    guid: str
    type: str
    title: str
    librarySectionTitle: str
    librarySectionID: int
    librarySectionKey: str
    contentRating: str
    summary: str
    rating: float | None = Field(None, description="Rating of the media")
    audienceRating: float | None = Field(
        None, description="Audience rating of the media"
    )
    year: int
    tagline: str | None = Field(None, description="Tagline of the media")
    thumb: str


class PlexPayload(BaseModel):
    event: str
    user: bool
    owner: bool
    Account: Account
    Server: Server
    Player: Player
    Metadata: Metadata
