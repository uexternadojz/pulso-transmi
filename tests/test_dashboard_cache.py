import asyncio
from app.dashboard_cache import DashboardCache


def test_shared_reads_coalesce_and_keep_cohorts_and_mutations_separate():
    async def run():
        cache=DashboardCache();calls=[]
        async def load():
            calls.append(1)
            await asyncio.sleep(0)
            return {'data': [1]}
        a,b=await asyncio.gather(cache.get(('chart','a'),load),cache.get(('chart','a'),load))
        assert len(calls)==1
        a['data'].append(2)
        assert b['data']==[1]
        await cache.get(('chart','b'),load)
        assert len(calls)==2
        cache.ttl=0
        cache.entries.clear()
        await cache.get(('chart','a'),load)
        await cache.get(('chart','a'),load)
        assert len(calls)==4
    asyncio.run(run())
