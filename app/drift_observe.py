"""Read-only operational snapshot for provisioned administrative monitoring."""
import asyncio
import json
from types import SimpleNamespace

import asyncpg
from app.settings import get_settings
from app.drift_monitor import monitor

async def main():
    pool=await asyncpg.create_pool(get_settings().database_url,min_size=1,max_size=1,command_timeout=30)
    try:
        async with pool.acquire() as c:
            teacher=await c.fetchrow("select id,cohort_code from competition.participants where kind='admin' and cohort_code is not null order by id limit 1")
        if teacher is None: raise RuntimeError('No provisioned cohort teacher')
        result=await monitor(pool,SimpleNamespace(participant_id=teacher['id'],cohort_code=teacher['cohort_code']))
        print(json.dumps(result,default=str,ensure_ascii=False))
    finally: await pool.close()

if __name__=='__main__':asyncio.run(main())
