from enum import Enum


class ListrrContractsEnumSortByDirectionEnum(str, Enum):
    ASCENDING = "Ascending"
    DESCENDING = "Descending"

    def __str__(self) -> str:
        return str(self.value)
