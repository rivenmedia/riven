from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.listrr_contracts_models_api_movie_dto import (
        ListrrContractsModelsAPIMovieDto,
    )


T = TypeVar(
    "T", bound="ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIMovieDto"
)


@_attrs_define
class ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIMovieDto:
    """
    Attributes:
        items (list[ListrrContractsModelsAPIMovieDto] | None | Unset):
        count (int | Unset):
        pages (int | Unset):
    """

    items: list[ListrrContractsModelsAPIMovieDto] | None | Unset = UNSET
    count: int | Unset = UNSET
    pages: int | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        items: list[dict[str, Any]] | None | Unset
        if isinstance(self.items, Unset):
            items = UNSET
        elif isinstance(self.items, list):
            items = []
            for items_type_0_item_data in self.items:
                items_type_0_item = items_type_0_item_data.to_dict()
                items.append(items_type_0_item)

        else:
            items = self.items

        count = self.count

        pages = self.pages

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if items is not UNSET:
            field_dict["items"] = items
        if count is not UNSET:
            field_dict["count"] = count
        if pages is not UNSET:
            field_dict["pages"] = pages

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.listrr_contracts_models_api_movie_dto import (
            ListrrContractsModelsAPIMovieDto,
        )

        d = dict(src_dict)

        def _parse_items(
            data: object,
        ) -> list[ListrrContractsModelsAPIMovieDto] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                items_type_0 = []
                _items_type_0 = data
                for items_type_0_item_data in _items_type_0:
                    items_type_0_item = ListrrContractsModelsAPIMovieDto.from_dict(
                        items_type_0_item_data
                    )

                    items_type_0.append(items_type_0_item)

                return items_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ListrrContractsModelsAPIMovieDto] | None | Unset, data)

        items = _parse_items(d.pop("items", UNSET))

        count = d.pop("count", UNSET)

        pages = d.pop("pages", UNSET)

        listrr_contracts_models_api_paged_response_1_listrr_contracts_models_api_movie_dto = cls(
            items=items,
            count=count,
            pages=pages,
        )

        return listrr_contracts_models_api_paged_response_1_listrr_contracts_models_api_movie_dto
