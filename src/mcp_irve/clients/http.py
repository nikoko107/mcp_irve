"""Client HTTP partagé et limiteur de débit pour les appels aux APIs externes."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx

from ..config import SETTINGS


def create_http_client() -> httpx.AsyncClient:
    """Client httpx partagé, à créer une fois par session (lifespan FastMCP) et à
    réutiliser pour tous les appels BAN/Enedis/Géoplateforme d'une même analyse."""
    return httpx.AsyncClient(
        timeout=SETTINGS.http_timeout_s,
        headers={"User-Agent": SETTINGS.http_user_agent},
    )


class RateLimiter:
    """Limiteur de débit token-bucket.

    Utilisé pour respecter la limite documentée de l'API itinéraire IGN Géoplateforme
    (5 req/s/IP) : ``selectionner_meilleur_candidat`` peut déclencher jusqu'à
    ``n_plus_proches`` appels d'itinéraire pour une seule analyse.

    ``time_func``/``sleep_func`` sont injectables pour permettre de tester le
    comportement de limitation sans dépendre d'une vraie horloge.
    """

    def __init__(
        self,
        rate_per_s: float,
        burst: int | None = None,
        *,
        time_func: Callable[[], float] = time.monotonic,
        sleep_func: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._rate = rate_per_s
        self._capacity = float(burst if burst is not None else max(1, int(rate_per_s)))
        self._tokens = self._capacity
        self._time_func = time_func
        self._sleep_func = sleep_func or asyncio.sleep
        self._last_refill = time_func()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._time_func()
                elapsed = now - self._last_refill
                self._last_refill = now
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait_s = (1 - self._tokens) / self._rate
                await self._sleep_func(wait_s)


itineraire_rate_limiter = RateLimiter(SETTINGS.geopf_itineraire_rate_limit_per_s)
