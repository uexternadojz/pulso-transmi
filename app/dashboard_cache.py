"""Short-lived, cohort-scoped cache for expensive shared score reads."""
import asyncio
from copy import deepcopy
from time import monotonic


class DashboardCache:
    def __init__(self, ttl=20):
        self.ttl = ttl
        self.entries = {}
        self.locks = {}

    async def get(self, key, load):
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            expires, value = self.entries.get(key, (0, None))
            if expires <= monotonic():
                value = await load()
                self.entries[key] = (monotonic() + self.ttl, value)
            # Callers may enrich responses; cached shared values remain untouched.
            return deepcopy(value)
