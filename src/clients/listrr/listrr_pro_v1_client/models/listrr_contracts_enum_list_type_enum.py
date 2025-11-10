from enum import Enum


class ListrrContractsEnumListTypeEnum(str, Enum):
    MOVIE = "Movie"
    SHOW = "Show"

    def __str__(self) -> str:
        return str(self.value)
