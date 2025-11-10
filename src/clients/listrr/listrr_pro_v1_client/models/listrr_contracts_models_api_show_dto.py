from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListrrContractsModelsAPIShowDto")


@_attrs_define
class ListrrContractsModelsAPIShowDto:
    """
    Attributes:
        id (None | str | Unset):
        name (None | str | Unset):
        first_air_date (datetime.datetime | Unset):
        im_db_id (None | str | Unset):
        tm_db_id (int | Unset):
        tv_db_id (int | Unset):
    """

    id: None | str | Unset = UNSET
    name: None | str | Unset = UNSET
    first_air_date: datetime.datetime | Unset = UNSET
    im_db_id: None | str | Unset = UNSET
    tm_db_id: int | Unset = UNSET
    tv_db_id: int | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        first_air_date: str | Unset = UNSET
        if not isinstance(self.first_air_date, Unset):
            first_air_date = self.first_air_date.isoformat()

        im_db_id: None | str | Unset
        if isinstance(self.im_db_id, Unset):
            im_db_id = UNSET
        else:
            im_db_id = self.im_db_id

        tm_db_id = self.tm_db_id

        tv_db_id = self.tv_db_id

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if first_air_date is not UNSET:
            field_dict["firstAirDate"] = first_air_date
        if im_db_id is not UNSET:
            field_dict["imDbId"] = im_db_id
        if tm_db_id is not UNSET:
            field_dict["tmDbId"] = tm_db_id
        if tv_db_id is not UNSET:
            field_dict["tvDbId"] = tv_db_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        _first_air_date = d.pop("firstAirDate", UNSET)
        first_air_date: datetime.datetime | Unset
        if isinstance(_first_air_date, Unset):
            first_air_date = UNSET
        else:
            first_air_date = isoparse(_first_air_date)

        def _parse_im_db_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        im_db_id = _parse_im_db_id(d.pop("imDbId", UNSET))

        tm_db_id = d.pop("tmDbId", UNSET)

        tv_db_id = d.pop("tvDbId", UNSET)

        listrr_contracts_models_api_show_dto = cls(
            id=id,
            name=name,
            first_air_date=first_air_date,
            im_db_id=im_db_id,
            tm_db_id=tm_db_id,
            tv_db_id=tv_db_id,
        )

        return listrr_contracts_models_api_show_dto
