from enum import Enum


class ListrrContractsEnumControllersListControllerShowListSortEnum(str, Enum):
    NAME = "Name"
    RELEASEDATE = "ReleaseDate"

    def __str__(self) -> str:
        return str(self.value)
