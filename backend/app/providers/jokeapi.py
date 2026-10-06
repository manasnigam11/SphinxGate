"""
JokeAPI provider adapter — Phase 2.5.

JokeAPI is a free joke API with no API key required.
https://jokeapi.dev/

Supported params (forwarded from PublicAPIRequest.params):
    category   str  – Joke category: "Any", "Programming", "Misc", "Dark",
                       "Pun", "Spooky", "Christmas" (default: "Any")
    type       str  – "single" or "twopart" (default: "Any")
    lang       str  – Language code (default: "en")
    safe_mode  bool – If True, filters out NSFW/explicit jokes (default: True)

Normalized response (returned in PublicAPIResponse.data):
    joke:
        category, type, delivery, setup/joke text
    flags:
        content flags returned by the API
    safe:
        bool — whether safe-mode was active
"""

from typing import Any

import httpx

from app.providers.base import BasePublicAPIProvider


JOKEAPI_BASE_URL = "https://v2.jokeapi.dev/joke"


class JokeAPIProvider(BasePublicAPIProvider):
    """
    Provider adapter for JokeAPI.

    Returns a single joke (single-delivery or setup/delivery format).
    No API key is required.
    """

    slug = "jokeapi"
    display_name = "JokeAPI"

    async def call(
        self,
        payload: dict[str, Any],
        api_key: str | None,
    ) -> dict[str, Any]:
        """
        Fetch a joke from JokeAPI and return a normalized dict.

        payload keys (from PublicAPIRequest.params):
            category   – default "Any"
            type       – default (any type)
            lang       – default "en"
            safe_mode  – default True
        """
        category = payload.get("category", "Any")
        url = f"{JOKEAPI_BASE_URL}/{category}"

        params: dict[str, Any] = {}
        if "type" in payload:
            params["type"] = payload["type"]
        if "lang" in payload:
            params["lang"] = payload["lang"]

        # Safe-mode: enabled by default unless caller explicitly passes False.
        if payload.get("safe_mode", True):
            params["safe-mode"] = ""  # query flag with no value

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            raw = response.json()

        return _normalize(raw)

    async def health_check(self, api_key: str | None) -> bool | None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("https://v2.jokeapi.dev/ping")
            response.raise_for_status()
            return True



def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert the JokeAPI JSON into SphinxGate's normalized shape."""
    if raw.get("type") == "twopart":
        joke_text = raw.get("setup", "")
        delivery  = raw.get("delivery", "")
    else:
        joke_text = raw.get("joke", "")
        delivery  = None

    return {
        "joke": {
            "category": raw.get("category"),
            "type":     raw.get("type"),
            "text":     joke_text,
            "delivery": delivery,
            "id":       raw.get("id"),
            "safe":     raw.get("safe"),
            "lang":     raw.get("lang"),
        },
        "flags": raw.get("flags", {}),
        "error": raw.get("error", False),
    }
