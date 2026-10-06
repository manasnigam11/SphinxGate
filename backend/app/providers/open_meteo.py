"""
Open-Meteo provider adapter — Phase 2.5.

Open-Meteo is a free weather API with no API key required.
https://open-meteo.com/en/docs

Supported params (forwarded from PublicAPIRequest.params):
    latitude   float  – Required. Geographic latitude (e.g. 51.5074)
    longitude  float  – Required. Geographic longitude (e.g. -0.1278)
    current    str    – Comma-separated current variables (default: "temperature_2m,wind_speed_10m")
    hourly     str    – Optional hourly variables
    daily      str    – Optional daily variables
    timezone   str    – Timezone string (default: "auto")

Normalized response (returned in PublicAPIResponse.data):
    location:
        latitude, longitude, timezone, timezone_abbreviation, elevation
    current:
        time, temperature_2m, wind_speed_10m (and any other requested variables)
    units:
        dict of variable → unit string
    raw_params:
        the params we sent upstream (for debugging)
"""

from typing import Any

import httpx

from app.providers.base import BasePublicAPIProvider


OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"

_DEFAULT_CURRENT = "temperature_2m,wind_speed_10m,weather_code,relative_humidity_2m"


class OpenMeteoProvider(BasePublicAPIProvider):
    """
    Provider adapter for Open-Meteo.

    Open-Meteo returns a weather forecast for a given latitude/longitude.
    No API key is required. The adapter normalizes the response so that
    consumers receive a consistent structure regardless of which weather
    fields they requested.
    """

    slug = "open_meteo"
    display_name = "Open-Meteo"

    async def call(
        self,
        payload: dict[str, Any],
        api_key: str | None,
    ) -> dict[str, Any]:
        """
        Fetch current weather from Open-Meteo and return a normalized dict.

        payload keys (from PublicAPIRequest.params):
            latitude, longitude — required
            current             — optional, comma-separated variables
            timezone            — optional (default: "auto")
        """
        params: dict[str, Any] = {
            "latitude":  payload.get("latitude", payload.get("lat")),
            "longitude": payload.get("longitude", payload.get("lon")),
            "current":   payload.get("current", _DEFAULT_CURRENT),
            "timezone":  payload.get("timezone", "auto"),
        }

        # Raise a clear error if lat/lon are missing.
        if params["latitude"] is None or params["longitude"] is None:
            from app.providers.base import InvalidProviderRequest
            raise InvalidProviderRequest(
                "Open-Meteo requires 'latitude' and 'longitude' parameters."
            )

        if "hourly" in payload:
            params["hourly"] = payload["hourly"]
        if "daily" in payload:
            params["daily"] = payload["daily"]

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(OPEN_METEO_BASE_URL, params=params)
            response.raise_for_status()
            raw = response.json()

        return _normalize(raw, params)

    async def health_check(self, api_key: str | None) -> bool | None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(OPEN_METEO_BASE_URL, params={"latitude": 0, "longitude": 0, "current": "temperature_2m"})
            response.raise_for_status()
            return True

def _normalize(raw: dict[str, Any], sent_params: dict[str, Any]) -> dict[str, Any]:
    """Convert the Open-Meteo JSON response into SphinxGate's normalized shape."""
    current_units = raw.get("current_units", {})
    current_data  = raw.get("current", {})

    return {
        "location": {
            "latitude":             raw.get("latitude"),
            "longitude":            raw.get("longitude"),
            "timezone":             raw.get("timezone"),
            "timezone_abbreviation": raw.get("timezone_abbreviation"),
            "elevation":            raw.get("elevation"),
        },
        "current": current_data,
        "units":   current_units,
        "daily":   raw.get("daily"),
        "raw_params": {k: v for k, v in sent_params.items() if v is not None},
    }

