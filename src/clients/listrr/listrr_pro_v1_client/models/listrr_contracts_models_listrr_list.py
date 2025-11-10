from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.listrr_contracts_enum_list_state_enum import (
    ListrrContractsEnumListStateEnum,
)
from ..models.listrr_contracts_enum_list_type_enum import (
    ListrrContractsEnumListTypeEnum,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="ListrrContractsModelsListrrList")


@_attrs_define
class ListrrContractsModelsListrrList:
    """
    Attributes:
        name (None | str | Unset):
        description (None | str | Unset):
        items (int | None | Unset):
        state (ListrrContractsEnumListStateEnum | Unset):
        type_ (ListrrContractsEnumListTypeEnum | Unset):
        last_processed (datetime.datetime | Unset):
        excluded_items (list[int] | None | Unset):
        include_external_lists (list[str] | None | Unset):
        exclude_external_lists (list[str] | None | Unset):
        is_static (bool | Unset):
        is_basic_filter (bool | Unset):
        is_extensive_filter (bool | Unset):
        is_private (bool | Unset):
        upvotes (int | Unset):
        created_on (datetime.datetime | Unset):
        modified_on (datetime.datetime | Unset):
        id (None | str | Unset):
    """

    name: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    items: int | None | Unset = UNSET
    state: ListrrContractsEnumListStateEnum | Unset = UNSET
    type_: ListrrContractsEnumListTypeEnum | Unset = UNSET
    last_processed: datetime.datetime | Unset = UNSET
    excluded_items: list[int] | None | Unset = UNSET
    include_external_lists: list[str] | None | Unset = UNSET
    exclude_external_lists: list[str] | None | Unset = UNSET
    is_static: bool | Unset = UNSET
    is_basic_filter: bool | Unset = UNSET
    is_extensive_filter: bool | Unset = UNSET
    is_private: bool | Unset = UNSET
    upvotes: int | Unset = UNSET
    created_on: datetime.datetime | Unset = UNSET
    modified_on: datetime.datetime | Unset = UNSET
    id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        items: int | None | Unset
        if isinstance(self.items, Unset):
            items = UNSET
        else:
            items = self.items

        state: str | Unset = UNSET
        if not isinstance(self.state, Unset):
            state = self.state.value

        type_: str | Unset = UNSET
        if not isinstance(self.type_, Unset):
            type_ = self.type_.value

        last_processed: str | Unset = UNSET
        if not isinstance(self.last_processed, Unset):
            last_processed = self.last_processed.isoformat()

        excluded_items: list[int] | None | Unset
        if isinstance(self.excluded_items, Unset):
            excluded_items = UNSET
        elif isinstance(self.excluded_items, list):
            excluded_items = self.excluded_items

        else:
            excluded_items = self.excluded_items

        include_external_lists: list[str] | None | Unset
        if isinstance(self.include_external_lists, Unset):
            include_external_lists = UNSET
        elif isinstance(self.include_external_lists, list):
            include_external_lists = self.include_external_lists

        else:
            include_external_lists = self.include_external_lists

        exclude_external_lists: list[str] | None | Unset
        if isinstance(self.exclude_external_lists, Unset):
            exclude_external_lists = UNSET
        elif isinstance(self.exclude_external_lists, list):
            exclude_external_lists = self.exclude_external_lists

        else:
            exclude_external_lists = self.exclude_external_lists

        is_static = self.is_static

        is_basic_filter = self.is_basic_filter

        is_extensive_filter = self.is_extensive_filter

        is_private = self.is_private

        upvotes = self.upvotes

        created_on: str | Unset = UNSET
        if not isinstance(self.created_on, Unset):
            created_on = self.created_on.isoformat()

        modified_on: str | Unset = UNSET
        if not isinstance(self.modified_on, Unset):
            modified_on = self.modified_on.isoformat()

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if description is not UNSET:
            field_dict["description"] = description
        if items is not UNSET:
            field_dict["items"] = items
        if state is not UNSET:
            field_dict["state"] = state
        if type_ is not UNSET:
            field_dict["type"] = type_
        if last_processed is not UNSET:
            field_dict["lastProcessed"] = last_processed
        if excluded_items is not UNSET:
            field_dict["excludedItems"] = excluded_items
        if include_external_lists is not UNSET:
            field_dict["includeExternalLists"] = include_external_lists
        if exclude_external_lists is not UNSET:
            field_dict["excludeExternalLists"] = exclude_external_lists
        if is_static is not UNSET:
            field_dict["isStatic"] = is_static
        if is_basic_filter is not UNSET:
            field_dict["isBasicFilter"] = is_basic_filter
        if is_extensive_filter is not UNSET:
            field_dict["isExtensiveFilter"] = is_extensive_filter
        if is_private is not UNSET:
            field_dict["isPrivate"] = is_private
        if upvotes is not UNSET:
            field_dict["upvotes"] = upvotes
        if created_on is not UNSET:
            field_dict["createdOn"] = created_on
        if modified_on is not UNSET:
            field_dict["modifiedOn"] = modified_on
        if id is not UNSET:
            field_dict["id"] = id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_items(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        items = _parse_items(d.pop("items", UNSET))

        _state = d.pop("state", UNSET)
        state: ListrrContractsEnumListStateEnum | Unset
        if isinstance(_state, Unset):
            state = UNSET
        else:
            state = ListrrContractsEnumListStateEnum(_state)

        _type_ = d.pop("type", UNSET)
        type_: ListrrContractsEnumListTypeEnum | Unset
        if isinstance(_type_, Unset):
            type_ = UNSET
        else:
            type_ = ListrrContractsEnumListTypeEnum(_type_)

        _last_processed = d.pop("lastProcessed", UNSET)
        last_processed: datetime.datetime | Unset
        if isinstance(_last_processed, Unset):
            last_processed = UNSET
        else:
            last_processed = isoparse(_last_processed)

        def _parse_excluded_items(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                excluded_items_type_0 = cast(list[int], data)

                return excluded_items_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        excluded_items = _parse_excluded_items(d.pop("excludedItems", UNSET))

        def _parse_include_external_lists(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                include_external_lists_type_0 = cast(list[str], data)

                return include_external_lists_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        include_external_lists = _parse_include_external_lists(
            d.pop("includeExternalLists", UNSET)
        )

        def _parse_exclude_external_lists(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                exclude_external_lists_type_0 = cast(list[str], data)

                return exclude_external_lists_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        exclude_external_lists = _parse_exclude_external_lists(
            d.pop("excludeExternalLists", UNSET)
        )

        is_static = d.pop("isStatic", UNSET)

        is_basic_filter = d.pop("isBasicFilter", UNSET)

        is_extensive_filter = d.pop("isExtensiveFilter", UNSET)

        is_private = d.pop("isPrivate", UNSET)

        upvotes = d.pop("upvotes", UNSET)

        _created_on = d.pop("createdOn", UNSET)
        created_on: datetime.datetime | Unset
        if isinstance(_created_on, Unset):
            created_on = UNSET
        else:
            created_on = isoparse(_created_on)

        _modified_on = d.pop("modifiedOn", UNSET)
        modified_on: datetime.datetime | Unset
        if isinstance(_modified_on, Unset):
            modified_on = UNSET
        else:
            modified_on = isoparse(_modified_on)

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        listrr_contracts_models_listrr_list = cls(
            name=name,
            description=description,
            items=items,
            state=state,
            type_=type_,
            last_processed=last_processed,
            excluded_items=excluded_items,
            include_external_lists=include_external_lists,
            exclude_external_lists=exclude_external_lists,
            is_static=is_static,
            is_basic_filter=is_basic_filter,
            is_extensive_filter=is_extensive_filter,
            is_private=is_private,
            upvotes=upvotes,
            created_on=created_on,
            modified_on=modified_on,
            id=id,
        )

        return listrr_contracts_models_listrr_list
