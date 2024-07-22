from pydantic import BaseModel


class MigratableBaseModel(BaseModel):
    def __init__(self, **data):
        for field_name, field in self.model_fields.items():
            if field_name not in data:
                default_value = field.default if field.default is not None else None
                data[field_name] = default_value
        super().__init__(**data)

