import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pydantic import ValidationError

from .schemas import Intent

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"


@dataclass(frozen=True)
class Settings:
    router_key: str
    search_key: str
    model: str

    @classmethod
    def load(cls):
        values = {**dotenv_values(ROOT / ".env"), **os.environ}
        return cls(values.get("OPENROUTER_API_KEY") or "", values.get("SERPER_API_KEY") or "",
                   values.get("OPENROUTER_MODEL") or DEFAULT_MODEL)


class ProviderError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


async def post_json(client, provider, url, headers, body, timeout):
    for attempt in range(2):
        try:
            result = await client.post(url, headers=headers, json=body, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise ProviderError(504, f"{provider} timed out.") from exc
        except httpx.RequestError as exc:
            raise ProviderError(502, f"{provider} could not be reached.") from exc

        if result.status_code in (429, 503) and attempt == 0:
            try:
                delay = float(result.headers.get("Retry-After", "1"))
            except ValueError:
                delay = 99
            if 0 <= delay <= 2:
                await asyncio.sleep(delay)
                continue
        if result.status_code >= 400:
            status = 503 if result.status_code in (401, 402, 403, 429, 503) else 502
            raise ProviderError(status, f"{provider} returned HTTP {result.status_code}. Check credentials, quota and provider availability.")
        try:
            data = result.json()
        except ValueError as exc:
            raise ProviderError(502, f"{provider} returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise ProviderError(502, f"{provider} returned an unexpected response.")
        return data


INTENT_PROMPT = """Interpret the user's text as a prospect discovery search. Accept either an
explicit audience or a recognizable topic, product, technology, industry or interest.
For a topic alone, find people or organizations publicly discussing, building or working on it.
For example, 'new Gemini model' targets public profiles discussing Google's Gemini AI models.
Use the core subject as evidence. Words like 'new' or 'latest' need not occur in a biography.
Do not invent a release, version, location or date. Without a location use null city/state/country
and empty aliases. Use target_type 'either' when the topic doesn't specify an identity type.
Accept ordinary search requests such as 'please find ...'. Call record_intent for all usable
searches. Only call reject_query for input with no discernible subject or audience, such as a
greeting by itself or random text. An omitted role or location is valid.
Use compact natural-language phrases in the query's language. Supply null for unknown
geography. Location aliases must refer to the narrowest requested place and must not
include a broader region. Produce AND groups of equivalent expressions of public
profile evidence. E.g. agency owners require both agency/industry phrases and
owner/founder synonyms. Enthusiasts require interest and an affinity or engagement
signal (fan, supporter, player, etc). Do not use empty or generic filler concepts.
Choose individual for people and owners, business for organizations. Never supply
names, contact details, example prospects or search operators."""


async def understand(client, settings, query):
    tool = {"name": "record_intent", "description": "Record the structured audience search.",
            "parameters": Intent.model_json_schema()}
    reject = {"name": "reject_query", "description": "The input has neither a recognizable topic nor an audience.",
              "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}
    body = {"model": settings.model, "messages": [{"role": "system", "content": INTENT_PROMPT},
            {"role": "user", "content": query}], "tools": [{"type": "function", "function": t} for t in (tool, reject)],
            "tool_choice": "required",
            "provider": {"require_parameters": True}, "max_tokens": 2048}
    if settings.model == DEFAULT_MODEL:
        body["reasoning"] = {"enabled": True}
    data = await post_json(client, "OpenRouter", "https://openrouter.ai/api/v1/chat/completions",
                           {"Authorization": f"Bearer {settings.router_key}"}, body, 60)
    try:
        call = data["choices"][0]["message"]["tool_calls"][0]["function"]
        if call["name"] == "reject_query":
            raise ProviderError(422, "Enter a topic or audience, such as 'Gemini AI' or 'startup founders in London'.")
        if call["name"] != "record_intent":
            raise ValueError("Unexpected tool")
        intent = Intent.model_validate_json(call["arguments"])
        return intent
    except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
        raise ProviderError(502, "OpenRouter did not return a valid search intent.") from exc


@dataclass(frozen=True)
class Hit:
    title: str
    url: str
    snippet: str


async def search(client, settings, query):
    data = await post_json(client, "Serper", "https://google.serper.dev/search",
                           {"X-API-KEY": settings.search_key}, {"q": query, "num": 10}, 12)
    organic = data.get("organic")
    if not isinstance(organic, list):
        # Serper can omit organic on a valid search with no organic listings.
        if organic is None and isinstance(data.get("searchParameters"), dict):
            return []
        raise ProviderError(502, "Serper returned an unexpected results document.")
    return [Hit(item["title"][:350], item["link"], (item.get("snippet") or "")[:1600])
            for item in organic[:10] if isinstance(item, dict)
            and all(isinstance(item.get(key), str) for key in ("title", "link"))
            and isinstance(item.get("snippet") or "", str)]
