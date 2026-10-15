"""WeatherKit REST client: signs its own developer token and calls Apple.

Home Assistant already ships PyJWT and cryptography, so this needs no extra requirements.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import time
from typing import Any

import aiohttp
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from .const import API_BASE

TOKEN_LIFETIME = 3600
TOKEN_RENEW_BEFORE = 300
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


class WeatherKitError(Exception):
    """A failed WeatherKit call; ``code`` is one of the config flow's error keys."""

    def __init__(self, code: str, status: int | None = None, detail: str = "") -> None:
        super().__init__(f"{code} ({status}): {detail}" if status else code)
        self.code = code
        self.status = status


def normalize_key(key_pem: str) -> str:
    """Accept the .p8 file's contents with or without its BEGIN/END lines."""
    text = key_pem.strip()
    if "BEGIN" not in text:
        body = "".join(text.split())
        lines = [body[i:i + 64] for i in range(0, len(body), 64)]
        text = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----"
    return text + "\n"


def load_key(key_pem: str):
    """Parse the key, raising ``WeatherKitError("invalid_key")`` when it isn't an EC private key."""
    try:
        key = load_pem_private_key(normalize_key(key_pem).encode(), password=None)
    except (ValueError, TypeError) as err:
        raise WeatherKitError("invalid_key", detail=str(err)) from err
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise WeatherKitError("invalid_key", detail="not an EC key")
    return key


def make_token(key, key_id: str, team_id: str, service_id: str, now: float) -> str:
    """The developer token Apple documents: ES256, kid and id in the header, four claims."""
    return jwt.encode(
        {"iss": team_id, "iat": int(now), "exp": int(now) + TOKEN_LIFETIME, "sub": service_id},
        key,
        algorithm="ES256",
        headers={"kid": key_id, "id": f"{team_id}.{service_id}"},
    )


def iso(value: datetime) -> str:
    """WeatherKit's timestamp form, in UTC with a Z suffix."""
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


class WeatherKitClient:
    """Calls the WeatherKit REST API for one Apple developer key."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        key_id: str,
        team_id: str,
        service_id: str,
        key_pem: str,
        on_call: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._session = session
        self._key = load_key(key_pem)
        self._key_id = key_id.strip()
        self._team_id = team_id.strip()
        self._service_id = service_id.strip()
        self._on_call = on_call
        self._clock = clock
        self._token: str | None = None
        self._token_expires = 0.0

    def _authorization(self) -> str:
        now = self._clock()
        if self._token is None or now > self._token_expires - TOKEN_RENEW_BEFORE:
            self._token = make_token(self._key, self._key_id, self._team_id, self._service_id, now)
            self._token_expires = now + TOKEN_LIFETIME
        return f"Bearer {self._token}"

    async def _get(self, path: str, params: dict[str, str] | None = None, *, signed: bool = True) -> Any:
        headers = {"Authorization": self._authorization()} if signed else {}
        if signed and self._on_call is not None:
            self._on_call()
        try:
            async with self._session.get(f"{API_BASE}{path}", params=params, headers=headers,
                                         timeout=REQUEST_TIMEOUT) as response:
                if response.status in (401, 403):
                    raise WeatherKitError("invalid_auth", response.status, await response.text())
                if response.status == 429:
                    raise WeatherKitError("over_quota", response.status, await response.text())
                if response.status == 404:
                    raise WeatherKitError("not_found", response.status)
                if response.status >= 400:
                    text = await response.text()
                    code = "over_quota" if "OVER_QUOTA" in text else "cannot_connect"
                    raise WeatherKitError(code, response.status, text[:200])
                return await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise WeatherKitError("cannot_connect", detail=str(err)) from err

    async def availability(self, latitude: float, longitude: float, country: str | None) -> list[str]:
        """The data sets Apple offers at this location."""
        params = {"country": country} if country else None
        result = await self._get(f"/api/v1/availability/{latitude:.4f}/{longitude:.4f}", params)
        return [str(item) for item in result] if isinstance(result, list) else []

    async def weather(
        self,
        language: str,
        latitude: float,
        longitude: float,
        data_sets: Iterable[str],
        timezone_name: str,
        country: str | None = None,
        hourly_start: datetime | None = None,
        hourly_end: datetime | None = None,
        daily_end: datetime | None = None,
    ) -> dict[str, Any]:
        """One call for every requested data set."""
        params = {"dataSets": ",".join(data_sets), "timezone": timezone_name}
        if country:
            params["countryCode"] = country
        if hourly_start is not None:
            params["hourlyStart"] = iso(hourly_start)
        if hourly_end is not None:
            params["hourlyEnd"] = iso(hourly_end)
        if daily_end is not None:
            params["dailyEnd"] = iso(daily_end)
        result = await self._get(f"/api/v1/weather/{language}/{latitude:.4f}/{longitude:.4f}", params)
        return result if isinstance(result, dict) else {}

    async def alert(self, language: str, alert_id: str) -> dict[str, Any]:
        """An alert's full text (one call)."""
        result = await self._get(f"/api/v1/weatherAlert/{language}/{alert_id}")
        return result if isinstance(result, dict) else {}

    async def attribution(self, language: str) -> dict[str, str]:
        """Apple's logo URLs and service name for the attribution the terms require (unsigned)."""
        result = await self._get(f"/attribution/{language}", signed=False)
        if not isinstance(result, dict):
            return {}
        return {key: (f"{API_BASE}{value}" if isinstance(value, str) and value.startswith("/") else str(value))
                for key, value in result.items()}
