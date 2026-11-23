import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass

from .evidence import consolidate, extract, named_profile
from .platforms import PLATFORMS
from .providers import ProviderError, search, understand
from .schemas import Discovery


@dataclass(frozen=True)
class Outcome:
    response: Discovery
    unavailable: tuple[str, ...]


class DiscoveryService:
    def __init__(self, client, settings):
        self.client = client
        self.settings = settings
        self.cache = OrderedDict()
        self.search_slots = asyncio.Semaphore(4)
        self.request_slots = asyncio.Semaphore(3)

    async def platform_search(self, platform, query):
        async with self.search_slots:
            try:
                return platform, await search(self.client, self.settings, query), None
            except ProviderError as error:
                return platform, [], error

    async def discover(self, query, mode="discovery"):
        if not self.settings.search_key:
            raise ProviderError(503, "Set SERPER_API_KEY in .env and restart the service.")
        if mode == "discovery" and not self.settings.router_key:
            raise ProviderError(503, "Set OPENROUTER_API_KEY in .env and restart the service.")
        key = mode, " ".join(query.casefold().split())
        entry = self.cache.get(key)
        if entry and time.monotonic() < entry[0]:
            self.cache.move_to_end(key)
            return Outcome(entry[1].model_copy(update={"query": query}), ())
        if self.request_slots.locked():
            raise ProviderError(429, "Discovery is busy. Retry shortly.")
        async with self.request_slots:
            intent = None
            if mode == "person":
                literal = " ".join(query.replace('"', " ").split()).lstrip("@")
                base = f'"{literal}"'
            else:
                intent = await understand(self.client, self.settings, query)
                geo = intent.location
                base = " ".join(dict.fromkeys(p for p in [intent.audience, intent.interest, geo.city,
                                                           geo.state, geo.country] if p))
            jobs = [self.platform_search("Google", base)]
            for spec in PLATFORMS:
                scope = spec.search_scope
                if spec.name == "LinkedIn" and (mode == "person" or intent.target_type == "individual"):
                    scope = "site:linkedin.com/in/"
                jobs.append(self.platform_search(spec.name, f"{scope} {base}"))
            batches = await asyncio.gather(*jobs)
            unavailable = tuple(platform for platform, _, error in batches if error)
            if len(unavailable) == len(batches):
                raise batches[0][2]
            hits_seen = set()
            candidates = []
            for _, hits, _ in batches:
                for hit in hits:
                    if hit in hits_seen:
                        continue
                    hits_seen.add(hit)
                    candidate = named_profile(hit, query) if mode == "person" else extract(hit, intent)
                    if candidate:
                        candidates.append(candidate)
            prospects = consolidate(candidates)
            result = Discovery(success=True, query=query, total_prospects=len(prospects), prospects=prospects)
            if not unavailable:
                self.cache[key] = (time.monotonic() + 300, result)
                self.cache.move_to_end(key)
                if len(self.cache) > 128:
                    self.cache.popitem(last=False)
            return Outcome(result, unavailable)
