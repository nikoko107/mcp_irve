from mcp_irve.clients.http import RateLimiter


class FakeClock:
    """Horloge/sleep simulés : permet de tester le token-bucket sans dépendre de vrais
    délais. ``sleep`` avance directement l'horloge simulée plutôt que d'attendre."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.now += seconds


async def test_acquire_does_not_wait_while_tokens_available():
    clock = FakeClock()
    limiter = RateLimiter(rate_per_s=4.5, time_func=clock.time, sleep_func=clock.sleep)

    for _ in range(4):  # capacité initiale = int(4.5) = 4
        await limiter.acquire()

    assert clock.sleep_calls == []


async def test_acquire_waits_when_bucket_exhausted():
    clock = FakeClock()
    limiter = RateLimiter(rate_per_s=4.5, time_func=clock.time, sleep_func=clock.sleep)

    for _ in range(4):
        await limiter.acquire()
    await limiter.acquire()  # bucket vide -> doit attendre le temps de réapprovisionner 1 jeton

    assert len(clock.sleep_calls) == 1
    assert clock.sleep_calls[0] == 1 / 4.5


async def test_acquire_refills_over_simulated_time():
    clock = FakeClock()
    limiter = RateLimiter(rate_per_s=2.0, burst=1, time_func=clock.time, sleep_func=clock.sleep)

    await limiter.acquire()  # consomme le seul jeton disponible
    clock.now += 10.0  # largement assez de temps simulé pour se réapprovisionner
    await limiter.acquire()

    assert clock.sleep_calls == []  # le jeton était déjà là, aucune attente nécessaire
