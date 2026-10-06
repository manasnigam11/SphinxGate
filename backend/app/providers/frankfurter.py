"""
Frankfurter provider adapter — Phase 2.5.

Frankfurter is a free, open-source currency exchange-rate API.
https://www.frankfurter.app/docs/

No API key is required.

Supported params (forwarded from PublicAPIRequest.params):
    base    str  – Base currency code (default: "USD")
    to      str  – Comma-separated target currencies (default: all available)
    date    str  – Specific date "YYYY-MM-DD" or "latest" (default: "latest")
    amount  float– Amount to convert (default: 1.0)

Normalized response (returned in PublicAPIResponse.data):
    base:        base currency code
    date:        the date the rates apply to
    amount:      amount in base currency
    rates:       dict of currency code → exchange rate
    description: human-readable summary
"""

from typing import Any

import httpx

from app.providers.base import BasePublicAPIProvider


FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"


class FrankfurterProvider(BasePublicAPIProvider):
    """
    Provider adapter for Frankfurter (exchange rates).

    Returns current or historical exchange rates for a given base currency.
    No API key is required.
    """

    slug = "frankfurter"
    display_name = "Frankfurter"

    async def call(
        self,
        payload: dict[str, Any],
        api_key: str | None,
    ) -> dict[str, Any]:
        """
        Fetch exchange rates from Frankfurter and return a normalized dict.

        payload keys (from PublicAPIRequest.params):
            base   – base currency (default: "USD")
            to     – target currencies, comma-separated (optional)
            date   – "latest" or "YYYY-MM-DD" (default: "latest")
            amount – amount to convert (default: 1.0)
        """
        date   = payload.get("date", "latest")
        url    = f"{FRANKFURTER_BASE_URL}/{date}"

        params: dict[str, Any] = {}
        if "base" in payload:
            params["base"] = payload["base"].upper()
        if "to" in payload:
            # Accept either comma-separated string or a list
            to_val = payload["to"]
            if isinstance(to_val, list):
                to_val = ",".join(to_val)
            params["to"] = to_val.upper()
        if "amount" in payload:
            params["amount"] = payload["amount"]

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            raw = response.json()

        return _normalize(raw, payload.get("amount", 1.0))

    async def health_check(self, api_key: str | None) -> bool | None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{FRANKFURTER_BASE_URL}/latest")
            response.raise_for_status()
            return True



def _normalize(raw: dict[str, Any], amount: float) -> dict[str, Any]:
    """Convert the Frankfurter JSON into SphinxGate's normalized shape."""
    base  = raw.get("base", "USD")
    date  = raw.get("date", "")
    rates = raw.get("rates", {})

    return {
        "base":   base,
        "date":   date,
        "amount": amount,
        "rates":  rates,
        "description": (
            f"Exchange rates for {amount} {base} on {date}. "
            f"Available currencies: {', '.join(rates.keys())}."
        ),
    }
