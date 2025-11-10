from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.listrr_contracts_models_api_paged_response_1_listrr_contracts_models_listrr_list import (
    ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList,
)
from ...types import Response


def _get_kwargs(
    page: int = 1,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/api/List/My/{page}",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList | None:
    if response.status_code == 200:
        response_200 = ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList.from_dict(
            response.text
        )

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    page: int = 1,
    *,
    client: AuthenticatedClient | Client,
) -> Response[ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList]:
    """Gets a paginated list of lists a user has created

    Args:
        page (int):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList]
    """

    kwargs = _get_kwargs(
        page=page,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    page: int = 1,
    *,
    client: AuthenticatedClient | Client,
) -> ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList | None:
    """Gets a paginated list of lists a user has created

    Args:
        page (int):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList
    """

    return sync_detailed(
        page=page,
        client=client,
    ).parsed


async def asyncio_detailed(
    page: int = 1,
    *,
    client: AuthenticatedClient | Client,
) -> Response[ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList]:
    """Gets a paginated list of lists a user has created

    Args:
        page (int):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList]
    """

    kwargs = _get_kwargs(
        page=page,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    page: int = 1,
    *,
    client: AuthenticatedClient | Client,
) -> ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList | None:
    """Gets a paginated list of lists a user has created

    Args:
        page (int):  Default: 1.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsListrrList
    """

    return (
        await asyncio_detailed(
            page=page,
            client=client,
        )
    ).parsed
