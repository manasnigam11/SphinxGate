"""
Open Trivia DB (opentdb) provider adapter — Phase 2.5.

Open Trivia DB is a free trivia questions API with no API key required.
https://opentdb.com/api_config.php

Supported params (forwarded from PublicAPIRequest.params):
    amount     int  – Number of questions (default: 5, max: 50)
    category   int  – Category ID (see https://opentdb.com/api_config.php for IDs)
                       Omit for random category.
    difficulty str  – "easy", "medium", or "hard" (default: any)
    type       str  – "multiple" (multiple choice) or "boolean" (True/False)
                       (default: any)

Normalized response (returned in PublicAPIResponse.data):
    questions: list of normalized question dicts:
        question:         the question text (HTML-decoded)
        category:         category name
        difficulty:       "easy" | "medium" | "hard"
        type:             "multiple" | "boolean"
        correct_answer:   the correct answer (HTML-decoded)
        incorrect_answers: list of incorrect answers (HTML-decoded)
        all_answers:      shuffled list of all answers

API note: opentdb returns HTML-entity encoded strings; we decode them.
"""

import html
from typing import Any

import httpx

from app.providers.base import BasePublicAPIProvider


OPENTDB_BASE_URL = "https://opentdb.com/api.php"

# opentdb response codes
_OPENTDB_SUCCESS          = 0
_OPENTDB_NO_RESULTS       = 1
_OPENTDB_INVALID_PARAM    = 2
_OPENTDB_TOKEN_NOT_FOUND  = 3
_OPENTDB_TOKEN_EMPTY      = 4


class TriviaProvider(BasePublicAPIProvider):
    """
    Provider adapter for Open Trivia DB.

    Returns trivia questions for a given category/difficulty/type.
    No API key is required.
    """

    slug = "trivia"
    display_name = "Open Trivia DB"

    async def call(
        self,
        payload: dict[str, Any],
        api_key: str | None,
    ) -> dict[str, Any]:
        """
        Fetch trivia questions from Open Trivia DB and return a normalized dict.

        payload keys (from PublicAPIRequest.params):
            amount      – number of questions (1–50, default: 5)
            category    – category ID (optional, see opentdb.com)
            difficulty  – "easy" | "medium" | "hard" (optional)
            type        – "multiple" | "boolean" (optional)
        """
        amount = int(payload.get("amount", 5))
        # clamp to API-allowed range
        amount = max(1, min(amount, 50))

        params: dict[str, Any] = {"amount": amount}
        if "category" in payload:
            params["category"] = int(payload["category"])
        if "difficulty" in payload:
            params["difficulty"] = payload["difficulty"].lower()
        if "type" in payload:
            params["type"] = payload["type"].lower()

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(OPENTDB_BASE_URL, params=params)
            response.raise_for_status()
            raw = response.json()

        return _normalize(raw)

    async def health_check(self, api_key: str | None) -> bool | None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(OPENTDB_BASE_URL, params={"amount": 1})
            response.raise_for_status()
            return True



def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert the opentdb JSON into SphinxGate's normalized shape."""
    response_code = raw.get("response_code", _OPENTDB_SUCCESS)

    if response_code != _OPENTDB_SUCCESS:
        # Map API error codes to human-readable messages.
        _messages = {
            _OPENTDB_NO_RESULTS:    "Not enough questions for your query parameters.",
            _OPENTDB_INVALID_PARAM: "Invalid parameters sent to the API.",
            _OPENTDB_TOKEN_NOT_FOUND: "Session token not found.",
            _OPENTDB_TOKEN_EMPTY:   "Session token exhausted — all questions returned.",
        }
        raise ValueError(_messages.get(response_code, f"opentdb error code {response_code}"))

    raw_questions = raw.get("results", [])
    questions = []
    for q in raw_questions:
        incorrect = [html.unescape(a) for a in q.get("incorrect_answers", [])]
        correct   = html.unescape(q.get("correct_answer", ""))
        all_answers = incorrect + [correct]
        # Sort so the correct answer isn't always last (deterministic but not revealing)
        all_answers.sort()

        questions.append({
            "question":          html.unescape(q.get("question", "")),
            "category":          html.unescape(q.get("category", "")),
            "difficulty":        q.get("difficulty", ""),
            "type":              q.get("type", ""),
            "correct_answer":    correct,
            "incorrect_answers": incorrect,
            "all_answers":       all_answers,
        })

    return {
        "response_code": response_code,
        "count":         len(questions),
        "questions":     questions,
    }
