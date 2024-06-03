from typing import Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

console = Console()


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
    rating: Optional[float] = Field(None, description="Rating of the media")
    audienceRating: Optional[float] = Field(None, description="Audience rating of the media")
    year: int
    tagline: Optional[str] = Field(None, description="Tagline of the media")
    thumb: str

class PlexPayload(BaseModel):
    event: str
    user: bool
    owner: bool
    Account: Account
    Server: Server
    Player: Player
    Metadata: Metadata


def log_plex_payload(plex_payload):
    table = Table(title="Plex Payload Details")

    table.add_column("Field", style="bold cyan")
    table.add_column("Value", style="bold magenta")

    table.add_row("Event", plex_payload.event)
    table.add_row("User", plex_payload.Account.title)
    table.add_row("User ID", str(plex_payload.Account.id))
    table.add_row("Media Title", plex_payload.Metadata.title)
    table.add_row("Media Type", plex_payload.Metadata.type)
    table.add_row("Year", str(plex_payload.Metadata.year))

    console.print(table)
