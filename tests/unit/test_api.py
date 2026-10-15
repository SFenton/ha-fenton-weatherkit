"""Developer token signing and request building."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from fenton_weatherkit.api import WeatherKitClient, WeatherKitError, iso, load_key, make_token, normalize_key


@pytest.fixture
def pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def test_token_has_exactly_apples_header_and_claims(pem) -> None:
    key = load_key(pem)
    token = make_token(key, "ABC123DEFG", "DEF123GHIJ", "com.sfenton.home.weatherkit", 1_800_000_000)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "ES256" and header["kid"] == "ABC123DEFG"
    assert header["id"] == "DEF123GHIJ.com.sfenton.home.weatherkit"
    claims = jwt.decode(token, key.public_key(), algorithms=["ES256"], options={"verify_exp": False, "verify_iat": False})
    assert claims == {"iss": "DEF123GHIJ", "iat": 1_800_000_000, "exp": 1_800_003_600,
                      "sub": "com.sfenton.home.weatherkit"}


def test_key_without_pem_lines_is_accepted(pem) -> None:
    body = "".join(line for line in pem.splitlines() if "-----" not in line)
    assert normalize_key(body).startswith("-----BEGIN PRIVATE KEY-----\n")
    load_key(body)


def test_non_key_is_rejected() -> None:
    with pytest.raises(WeatherKitError) as err:
        load_key("not a key")
    assert err.value.code == "invalid_key"


def test_iso() -> None:
    assert iso(datetime(2026, 10, 15, 18, 3, 4, 999, tzinfo=timezone.utc)) == "2026-10-15T18:03:04Z"


class FakeResponse:
    def __init__(self, status: int, body) -> None:
        self.status, self._body = status, body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def json(self, content_type=None):
        return self._body

    async def text(self) -> str:
        return str(self._body)


class FakeSession:
    def __init__(self, status: int = 200, body=None) -> None:
        self.calls: list[tuple[str, dict | None, dict]] = []
        self.status, self.body = status, body if body is not None else {}

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers or {}))
        return FakeResponse(self.status, self.body)


def test_weather_request_and_call_counting(pem) -> None:
    session, counted = FakeSession(body={"currentWeather": {}}), []
    client = WeatherKitClient(session, "ABC123DEFG", "DEF123GHIJ", "svc", pem, on_call=lambda: counted.append(1),
                              clock=lambda: 1_800_000_000)
    start = datetime(2026, 10, 15, 18, tzinfo=timezone.utc)
    result = asyncio.run(client.weather("en", 47.61, -122.33, ["currentWeather", "forecastNextHour"],
                                        "America/Los_Angeles", "US", hourly_start=start))
    assert result == {"currentWeather": {}}
    url, params, headers = session.calls[0]
    assert url == "https://weatherkit.apple.com/api/v1/weather/en/47.6100/-122.3300"
    assert params == {"dataSets": "currentWeather,forecastNextHour", "timezone": "America/Los_Angeles",
                      "countryCode": "US", "hourlyStart": "2026-10-15T18:00:00Z"}
    assert headers["Authorization"].startswith("Bearer ")
    assert counted == [1]
    # The token is reused until shortly before it expires.
    asyncio.run(client.weather("en", 1, 2, ["currentWeather"], "UTC"))
    assert session.calls[1][2] == headers


def test_attribution_is_unsigned_and_absolute(pem) -> None:
    session, counted = FakeSession(body={"logoDark@1x": "/assets/branding/dark.png", "serviceName": "Weather"}), []
    client = WeatherKitClient(session, "k", "t", "s", pem, on_call=lambda: counted.append(1))
    result = asyncio.run(client.attribution("en"))
    assert result == {"logoDark@1x": "https://weatherkit.apple.com/assets/branding/dark.png", "serviceName": "Weather"}
    assert session.calls[0][2] == {} and counted == []


@pytest.mark.parametrize(("status", "body", "code"), [
    (401, "", "invalid_auth"), (403, "", "invalid_auth"), (429, "", "over_quota"),
    (400, '{"reason": "OVER_QUOTA"}', "over_quota"), (500, "boom", "cannot_connect"), (404, "", "not_found")])
def test_errors(pem, status, body, code) -> None:
    client = WeatherKitClient(FakeSession(status, body), "k", "t", "s", pem)
    with pytest.raises(WeatherKitError) as err:
        asyncio.run(client.weather("en", 1, 2, ["currentWeather"], "UTC"))
    assert err.value.code == code and err.value.status == status
