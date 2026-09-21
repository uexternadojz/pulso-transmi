import asyncio
from datetime import datetime, timedelta, timezone

from app.scheduler import open_cycle, release_observations


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.cycle_inserted = True

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((query, args))
        return "INSERT 0 24"

    async def fetchrow(self, query: str, *args: object):
        self.calls.append((query, args))
        return {"id": 17} if self.cycle_inserted else None


def test_release_is_bounded_to_the_new_virtual_interval() -> None:
    connection = RecordingConnection()
    previous = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    current = previous + timedelta(minutes=30)

    released = asyncio.run(
        release_observations(connection, 9, previous, current)
    )

    assert released == 24
    assert len(connection.calls) == 3
    for query, args in connection.calls:
        assert "observed_at > $2" in query or "announced_at > $2" in query
        assert args == (9, previous, current)


def test_activation_can_release_only_the_bridge_timestamp() -> None:
    connection = RecordingConnection()
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)

    asyncio.run(
        release_observations(connection, 9, start, start, include_start=True)
    )

    for query, _ in connection.calls:
        assert "observed_at >= $2" in query or "announced_at >= $2" in query


def test_no_cycle_is_opened_when_targets_would_exceed_scenario() -> None:
    connection = RecordingConnection()
    end = datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)

    result = asyncio.run(
        open_cycle(connection, 9, "official", end, 25, end)
    )

    assert result is None
    assert connection.calls == []


def test_full_hour_cycle_has_four_horizons() -> None:
    connection = RecordingConnection()
    origin = datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc)
    end = origin + timedelta(hours=2)

    result = asyncio.run(
        open_cycle(connection, 9, "official", origin, 25, end)
    )

    assert result == "cyc_official_20260915T220000Z"
    assert len(connection.calls) == 2
    target_query = connection.calls[1][0]
    assert "generate_series(1,4)" in target_query
