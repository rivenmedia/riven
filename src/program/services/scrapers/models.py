from pydantic import BaseModel


class RankingOverrides(BaseModel):
    resolutions: list[str] | None = None
    quality: list[str] | None = None
    rips: list[str] | None = None
    hdr: list[str] | None = None
    audio: list[str] | None = None
    extras: list[str] | None = None
    trash: list[str] | None = None
    require: list[str] | None = None
    exclude: list[str] | None = None
