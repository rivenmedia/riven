"""
Naming service for generating clean VFS paths from original filenames.

This is the single source of truth for path generation in RivenVFS.
Supports flexible naming templates configured in settings.
"""

from collections.abc import Mapping, Sequence
from string import Formatter
from typing import Any


class SafeFormatter(Formatter):
    """
    Custom string formatter that handles missing keys gracefully.

    Supports:
    - Simple variables: {title}
    - Nested access: {show[title]}
    - List indexing: {list[0]}, {list[-1]}
    - Format specs: {season:02d}
    - Missing values render as empty string (no KeyError)
    """

    def get_value(  # pyright: ignore[reportUnknownParameterType]
        self,
        key: Any,
        args: Sequence[Any],
        kwargs: Mapping[str, Any],
    ):
        if isinstance(key, str):
            # Handle nested access: show[title]
            if "[" in key and "]" in key:
                parts = key.replace("]", "").split("[")
                value = kwargs.get(parts[0], {})

                for part in parts[1:]:
                    if isinstance(value, dict):
                        value = value.get(  # pyright: ignore[reportUnknownVariableType]
                            part, ""
                        )
                    elif isinstance(value, list):
                        try:
                            # Handle negative indices like [-1]
                            value = value[  # pyright: ignore[reportUnknownVariableType]
                                int(part)
                            ]
                        except (ValueError, IndexError):
                            value = ""
                    else:
                        value = ""

                return value or ""  # pyright: ignore[reportUnknownVariableType]

            # Simple key access
            return kwargs.get(key, "")

        return super().get_value(key, args, kwargs)

    def format_field(self, value: str | None, format_spec: str):
        if value is None or value == "":
            return ""

        return super().format_field(value, format_spec)
