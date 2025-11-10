from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.listrr_contracts_enum_controllers_list_controller_show_list_sort_enum import (
    ListrrContractsEnumControllersListControllerShowListSortEnum,
)
from ...models.listrr_contracts_enum_sort_by_direction_enum import (
    ListrrContractsEnumSortByDirectionEnum,
)
from ...models.listrr_contracts_models_api_paged_response_1_listrr_contracts_models_api_show_dto import (
    ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto,
)
from ...types import Response


def _get_kwargs(
    id: str,
    sort_by: ListrrContractsEnumControllersListControllerShowListSortEnum,
    sort_by_direction: ListrrContractsEnumSortByDirectionEnum,
    page: int = 1,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/api/List/Shows/{id}/{sort_by}/{sort_by_direction}/{page}",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto | None:
    if response.status_code == 200:
        response_200 = ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto.from_dict(
            response.text
        )

        return response_200

    if response.status_code == 400:
        response_400 = cast(Any, None)
        return response_400

    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    Any | ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    sort_by: ListrrContractsEnumControllersListControllerShowListSortEnum,
    sort_by_direction: ListrrContractsEnumSortByDirectionEnum,
    page: int = 1,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    Any | ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto
]:
    """Gets a paginated list of shows the list with the given id contains

    Args:
        id (str):
        sort_by (ListrrContractsEnumControllersListControllerShowListSortEnum):
        sort_by_direction (ListrrContractsEnumSortByDirectionEnum):
        page (int):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto]
    """

    kwargs = _get_kwargs(
        id=id,
        sort_by=sort_by,
        sort_by_direction=sort_by_direction,
        page=page,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    sort_by: ListrrContractsEnumControllersListControllerShowListSortEnum,
    sort_by_direction: ListrrContractsEnumSortByDirectionEnum,
    page: int = 1,
    *,
    client: AuthenticatedClient | Client,
) -> Any | ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto | None:
    """Gets a paginated list of shows the list with the given id contains

    Args:
        id (str):
        sort_by (ListrrContractsEnumControllersListControllerShowListSortEnum):
        sort_by_direction (ListrrContractsEnumSortByDirectionEnum):
        page (int):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto
    """

    return sync_detailed(
        id=id,
        sort_by=sort_by,
        sort_by_direction=sort_by_direction,
        page=page,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: str,
    sort_by: ListrrContractsEnumControllersListControllerShowListSortEnum,
    sort_by_direction: ListrrContractsEnumSortByDirectionEnum,
    page: int = 1,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    Any | ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto
]:
    """Gets a paginated list of shows the list with the given id contains

    Args:
        id (str):
        sort_by (ListrrContractsEnumControllersListControllerShowListSortEnum):
        sort_by_direction (ListrrContractsEnumSortByDirectionEnum):
        page (int):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto]
    """

    kwargs = _get_kwargs(
        id=id,
        sort_by=sort_by,
        sort_by_direction=sort_by_direction,
        page=page,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    sort_by: ListrrContractsEnumControllersListControllerShowListSortEnum,
    sort_by_direction: ListrrContractsEnumSortByDirectionEnum,
    page: int = 1,
    *,
    client: AuthenticatedClient | Client,
) -> Any | ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto | None:
    """Gets a paginated list of shows the list with the given id contains

    Args:
        id (str):
        sort_by (ListrrContractsEnumControllersListControllerShowListSortEnum):
        sort_by_direction (ListrrContractsEnumSortByDirectionEnum):
        page (int):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto
    """

    return (
        await asyncio_detailed(
            id=id,
            sort_by=sort_by,
            sort_by_direction=sort_by_direction,
            page=page,
            client=client,
        )
    ).parsed
