from typing import Any
from pydantic import BaseModel
from pydantic_core import PydanticUndefined


class MigratableBaseModel(BaseModel):
    def __init__(self, **data: Any):
        for field_name, field in MigratableBaseModel.model_fields.items():
            # Handle missing fields
            if field_name not in data:
                # Check for default_factory first
                if (
                    field.default_factory is not None
                    and field.default_factory != PydanticUndefined
                ):
                    data[field_name] = field.default_factory()
                # Then check for default value
                elif field.default is not None and field.default != PydanticUndefined:
                    data[field_name] = field.default
                else:
                    data[field_name] = None
            # Handle empty dicts that should have default_factory content
            elif isinstance(data[field_name], dict) and len(data[field_name]) == 0:
                # If field has a default_factory and the dict is empty, populate with defaults
                if (
                    field.default_factory is not None
                    and field.default_factory != PydanticUndefined
                ):
                    default_value = field.default_factory()

                    # Only replace empty dict if default_factory returns non-empty dict
                    if isinstance(default_value, dict) and len(default_value) > 0:
                        data[field_name] = default_value

        super().__init__(**data)
