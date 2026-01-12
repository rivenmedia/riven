from collections.abc import Callable, Generator
import json
import os
import contextvars
from contextlib import contextmanager
from typing import Any, cast

from loguru import logger
from pydantic import ValidationError

from program.settings.models import AppModel, Observable
from program.utils import data_dir_path


class SettingsManager:
    """Class that handles settings, ensuring they are validated against a Pydantic schema."""

    def __init__(self):
        self.observers = list[Callable[[], Any]]()
        self.filename = os.environ.get("SETTINGS_FILENAME", "settings.json")
        self.settings_file = data_dir_path / self.filename
        self._overrides_ctx = contextvars.ContextVar("settings_overrides", default={})

        Observable.set_notify_observers(self.notify_observers)

        if not self.settings_file.exists():
            logger.info(f"Settings filename: {self.filename}")

            self.settings = AppModel()
            self.settings = AppModel.model_validate(
                self.check_environment(
                    self.settings.model_dump(),
                    "RIVEN",
                )
            )

            self.notify_observers()
        else:
            self.load()

    def register_observer(self, observer: Callable[[], None]):
        self.observers.append(observer)

    def notify_observers(self):
        for observer in self.observers:
            observer()

    def check_environment(
        self,
        settings: dict[str, Any],
        prefix: str = "",
        separator: str = "_",
    ):
        checked_settings = dict[str, Any]()

        for key, value in settings.items():
            if isinstance(value, dict):
                sub_checked_settings = self.check_environment(
                    settings=cast(dict[str, Any], value),
                    prefix=f"{prefix}{separator}{key}",
                )
                checked_settings[key] = sub_checked_settings
            else:
                environment_variable = f"{prefix}_{key}".upper()

                if os.getenv(environment_variable, None):
                    new_value = os.getenv(environment_variable)

                    if new_value is None:
                        checked_settings[key] = value
                    elif isinstance(value, bool):
                        checked_settings[key] = (
                            new_value.lower() == "true" or new_value == "1"
                        )
                    elif isinstance(value, int):
                        checked_settings[key] = int(new_value)
                    elif isinstance(value, float):
                        checked_settings[key] = float(new_value)
                    elif isinstance(value, list) and new_value.startswith("["):
                        checked_settings[key] = json.loads(new_value)
                    elif isinstance(value, list):
                        logger.error(
                            f"Environment variable {environment_variable} for list type must be a JSON array string. Got {new_value}."
                        )
                    else:
                        checked_settings[key] = new_value
                else:
                    checked_settings[key] = value

        return checked_settings

    def load(self, settings_dict: dict[str, Any] | None = None):
        """Load settings from file, validating against the AppModel schema."""

        try:
            if not settings_dict:
                with open(self.settings_file, "r", encoding="utf-8") as file:
                    settings_dict = json.loads(file.read())

                    if (
                        settings_dict
                        and os.environ.get("RIVEN_FORCE_ENV", "false").lower() == "true"
                    ):
                        settings_dict = self.check_environment(
                            settings_dict,
                            "RIVEN",
                        )

            self.settings = AppModel.model_validate(settings_dict)
            self.save()
        except ValidationError as e:
            formatted_error = format_validation_error(e)
            logger.error(f"Settings validation failed:\n{formatted_error}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing settings file: {e}")
            raise
        except FileNotFoundError:
            logger.warning(
                f"Error loading settings: {self.settings_file} does not exist"
            )
            raise
        self.notify_observers()

    def save(self):
        """Save settings to file, using Pydantic model for JSON serialization."""
        with open(self.settings_file, "w", encoding="utf-8") as file:
            file.write(self.settings.model_dump_json(indent=4, exclude_none=True))

    @contextmanager
    def override(self, **overrides: Any) -> Generator[None, None, None]:
        """Context manager to temporarily override settings."""
        token = self._overrides_ctx.set({**self._overrides_ctx.get(), **overrides})
        try:
            yield
        finally:
            self._overrides_ctx.reset(token)

    def get_setting(self, key: str, default: Any) -> Any:
        """Get a setting value, respecting any active overrides."""
        overrides = self._overrides_ctx.get()
        if overrides and key in overrides:
            return overrides[key]
        return default

    def get_effective_rtn_model(self):
        """Get the effective RTN settings, merging global settings with active overrides."""
        from RTN.models import SettingsModel

        # Start with global settings
        ranking_settings = self.settings.ranking.model_dump()
        
        # Apply overrides
        overrides = self._overrides_ctx.get()
        if overrides:
            valid_keys = SettingsModel.model_fields.keys()
            filtered_overrides = {k: v for k, v in overrides.items() if k in valid_keys}
            ranking_settings.update(filtered_overrides)
            
        return SettingsModel(**ranking_settings)



def format_validation_error(e: ValidationError) -> str:
    """Format validation errors in a user-friendly way"""

    messages = list[str]()

    for error in e.errors():
        field = ".".join(str(x) for x in error["loc"])
        message = error.get("msg")
        messages.append(f"• {field}: {message}")

    return "\n".join(messages)


settings_manager = SettingsManager()
