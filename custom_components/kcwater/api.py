"""Sample API Client."""

from __future__ import annotations

import logging
import socket
from asyncio import timeout
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any

import aiohttp
from homeassistant.util import dt as dt_util

TOKEN_URL = "https://my.kcwater.us/rest/oauth/token"  # noqa: S105
CUSTOMER_INFO_URL = "https://my.kcwater.us/rest/account/customer/"
HOURLY_USAGE_URL = "https://my.kcwater.us/rest/usage/month/day"
DAILY_USAGE_URL = "https://my.kcwater.us/rest/usage/month"
_LOGGER = logging.getLogger(__name__)


@dataclass
class Account:
    """A class used to represent an Account."""

    customer_id: str
    access_token: str
    token_exp: datetime
    context: AccountContext


@dataclass
class AccountContext:
    """
    A class used to represent a Customer.

    Attributes
    ----------
    account_number : str
        The account number of the customer.
    customer_id : str
        The unique identifier for the customer.
    service_id : str
        The service identifier associated with the customer.
    saccount_port : int, optional
        The port number for the service account (default is 1).

    """

    account_number: str
    service_id: str
    saccount_port: int = 1


@dataclass
class Reading:
    """
    A class to represent a water meter reading.

    Attributes:
        readDateTime (datetime): The date and time when the reading was taken.
        uom (str): The unit of measurement for the reading.
        meterNumber (Optional[str]): The meter number, if available.
        gallonsConsumption (str): The consumption in gallons.
        rawConsumption (str): The raw consumption value.
        scaledRead (str): The scaled reading value.
        port (str): The port associated with the reading.

    """

    read_datetime: datetime
    uom: str
    meter_number: str | None
    raw_consumption: float
    port: str


class KCWaterApiClientError(Exception):
    """Exception to indicate a general API error."""


class KCWaterApiClientCommunicationError(
    KCWaterApiClientError,
):
    """Exception to indicate a communication error."""


class KCWaterApiClientAuthenticationError(
    KCWaterApiClientError,
):
    """Exception to indicate an authentication error."""


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """Verify that the response is valid."""
    if response.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN) or (
        response.url == TOKEN_URL and response.status == HTTPStatus.BAD_REQUEST
    ):
        msg = "Invalid credentials"
        raise KCWaterApiClientAuthenticationError(
            msg,
        )
    response.raise_for_status()


class KCWaterApiClient:
    """KC Water API Client."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Sample API Client."""
        self._username = username
        self._password = password
        self._session = session
        self._account: Account | None = None

    async def get_account_number(self) -> str:
        """Get the account ID."""
        await self.async_login()
        if self._account is None:
            msg = "Account not initialized after login"
            raise KCWaterApiClientError(msg)
        return self._account.context.account_number

    async def async_login(self) -> None:
        """Login to the API."""
        tz = await dt_util.async_get_time_zone("America/Chicago")
        if self._account and self._account.token_exp > datetime.now(tz=tz):
            _LOGGER.debug("Token is still valid")
            return
        _LOGGER.debug("Logging in with username: %s", self._username)
        login_payload = {
            "username": str(self._username),
            "password": str(self._password),
            "grant_type": "password",
        }
        headers = {"Authorization": "Basic d2ViQ2xpZW50SWRQYXNzd29yZDpzZWNyZXQ="}
        auth_result = await self._api_wrapper(
            method="post",
            url=TOKEN_URL,
            form_data=login_payload,
            headers=headers,
        )

        info_payload = {"customerId": str(auth_result["user"]["customerId"])}
        customer_info = await self._api_wrapper(
            method="post",
            url=CUSTOMER_INFO_URL,
            data=info_payload,
            headers={"Authorization": f"Bearer {auth_result['access_token']}"},
        )

        self._account = Account(
            customer_id=auth_result["user"]["customerId"],
            access_token=auth_result["access_token"],
            token_exp=datetime.now(tz=tz)
            + timedelta(seconds=auth_result["expires_in"]),
            context=AccountContext(
                account_number=customer_info["accountContext"]["accountNumber"],
                service_id=customer_info["accountSummaryType"]["services"][0][
                    "serviceId"
                ],
            ),
        )

    async def async_get_data(self, start: datetime, end: datetime) -> list[Reading]:
        """Get data from the API."""
        if self._account is None:
            msg = "Account not initialized. Call async_login first."
            raise KCWaterApiClientError(msg)
        _LOGGER.debug(
            "Getting data for account: %s and range %s to %s",
            self._account.context.account_number,
            start,
            end,
        )
        tz = await dt_util.async_get_time_zone("America/Chicago")
        readings: list[Reading] = []
        for day in range((end - start).days):
            await self.async_login()
            query_date = start + timedelta(days=day)
            formatted_date = query_date.strftime("%d-%b-%Y")
            _LOGGER.debug("Getting data for %s", formatted_date)
            payload = {
                "customerId": str(self._account.customer_id),
                "accountContext": {
                    "accountNumber": str(self._account.context.account_number),
                    "serviceId": str(self._account.context.service_id),
                },
                "day": formatted_date,
                "port": str(self._account.context.saccount_port),
            }

            result = await self._api_wrapper(
                method="post",
                url=HOURLY_USAGE_URL,
                data=payload,
                headers={"Authorization": f"Bearer {self._account.access_token}"},
            )
            for r in result["history"]:
                read_date = datetime.strptime(
                    f"{r['readDate']} {r['readDateTime']}", "%m-%d-%Y %I %p"
                ).replace(tzinfo=tz)
                reading = Reading(
                    read_datetime=read_date - timedelta(hours=1),
                    uom=r["uom"],
                    meter_number=r["meterNumber"],
                    raw_consumption=float(r["rawConsumption"]),
                    port=r["port"],
                )
                readings.append(reading)

        return readings

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        form_data: dict | None = None,
        data: dict | None = None,
        headers: dict | None = None,
    ) -> Any:
        """Get information from the API."""
        try:
            async with timeout(10):
                response = await self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=form_data,
                    json=data,
                )
                _verify_response_or_raise(response)
                return await response.json()

        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise KCWaterApiClientCommunicationError(
                msg,
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise KCWaterApiClientCommunicationError(
                msg,
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            msg = f"Something really wrong happened! - {exception}"
            raise KCWaterApiClientError(
                msg,
            ) from exception
