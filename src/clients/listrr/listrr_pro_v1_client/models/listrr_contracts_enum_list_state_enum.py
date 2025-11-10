from enum import Enum


class ListrrContractsEnumListStateEnum(str, Enum):
    ERROR = "Error"
    NONE = "None"
    SCHDULEDFORDELETION = "SchduledForDeletion"
    SCHEDULED = "Scheduled"
    UPDATING = "Updating"

    def __str__(self) -> str:
        return str(self.value)
