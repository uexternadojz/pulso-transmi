"""Read-only final score reports for the instructor's private archive."""
import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import asyncpg

from app.cutoff import first_cutoff_board
from app.drift_monitor import monitor
from app.settings import get_settings


async def main():
    pool = await asyncpg.create_pool(get_settings().database_url, min_size=1, max_size=1, command_timeout=120)
    try:
        async with pool.acquire() as connection:
            teacher = await connection.fetchrow("select id,cohort_code from competition.participants where kind='admin' and cohort_code is not null order by id limit 1")
        if teacher is None:
            raise RuntimeError("No provisioned cohort teacher")
        phase = await monitor(pool, SimpleNamespace(participant_id=teacher['id'], cohort_code=teacher['cohort_code']))
        cutoff = await first_cutoff_board(pool, teacher['cohort_code'])
        print(json.dumps({"final_phase": phase, "academic_cutoff": cutoff}, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value), ensure_ascii=False))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
