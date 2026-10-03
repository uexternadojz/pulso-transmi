"""Explicit integration probe against a disposable restored database only.

Run as an administrator inside the ops image; --database MUST end in _test.
Requires migration 013 and a completed/drained scenario matching the bundle.
Never accepts the configured production database as a target.
"""
import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from app.settings import get_settings
from app.drift_admin import apply, timestamp
from app.scheduler import tick_scenario
from app.source_contract import serialize_observation


async def main(args):
    parts = urlsplit(get_settings().database_url)
    assert args.database.endswith('_test') and args.database != parts.path.lstrip('/')
    dsn = urlunsplit(parts._replace(path='/'+args.database))
    c = await asyncpg.connect(dsn, command_timeout=90)
    try:
        assert await c.fetchval('select current_database()') == args.database
        b = json.loads(Path(args.bundle).read_text())
        start = timestamp(b['effective_from'])
        sid = await c.fetchval('select id from sim.scenarios where code=$1',b['scenario_code'])
        async def fingerprints():
            return tuple([await c.fetchval(query,sid,start) for query in (
                "select md5(string_agg(row(station_id,observed_at,value,released_at,source_schema_version,source_quality)::text,',' order by station_id,observed_at)) from competition.observations where scenario_id=$1 and observed_at<=$2",
                "select md5(string_agg(row(station_id,observed_at,actual_value,expected_mean)::text,',' order by station_id,observed_at)) from sim.generated_truth where scenario_id=$1 and observed_at<=$2",
                "select md5(string_agg(row(participant_id,cycle_id,station_id,target_at,actual_value,predicted_value,absolute_error)::text,',' order by participant_id,cycle_id,station_id,target_at)) from competition.score_components where scenario_id=$1 and target_at<=$2",
            )])
        before = await fingerprints()
        wall = datetime.now(timezone.utc)+timedelta(hours=28)
        result = await apply(c,b,wall,start)
        assert result['status']=='active'
        assert (await apply(c,b,wall,start))['status']=='already_applied'
        assert await fingerprints()==before
        assert await c.fetchval("select count(*) from competition.forecast_cycles where scenario_id=$1 and origin_at=$2 and state='open'",sid,start)==1
        # Exercise actual ticks and scheduler role, without advancing real production time.
        scenario = dict(await c.fetchrow('select id scenario_id,code,competition_start,competition_end from sim.scenarios where id=$1',sid))
        for _ in range(2):
            await c.execute("update competition.scenario_clock set last_tick_at=now()-interval '31 minutes' where scenario_id=$1",sid)
            await c.execute("update competition.forecast_cycles set closes_at=now()-interval '1 second' where scenario_id=$1 and state='open'",sid)
            async with c.transaction():
                await c.execute('set local role academy_scheduler')
                tick = await tick_scenario(c,scenario,30,25)
                assert tick is not None
        assert await fingerprints()==before
        assert await c.fetchval("select state from competition.forecast_cycles where scenario_id=$1 and origin_at=$2",sid,start)=='resolved'
        rows=await c.fetch('select station_id,observed_at,value demand,released_at,source_schema_version,source_quality from competition.observations where scenario_id=$1 and observed_at>$2',sid,start)
        assert len(rows)==48 and all(r['source_schema_version']==2 for r in rows)
        assert all('demand' not in serialize_observation(r) for r in rows)
        assert all(serialize_observation(r)['measurement']['value'] is None for r in rows if r['source_quality']=='missing')
        assert await c.fetchval('''select count(*) from competition.score_components s join sim.generated_truth t
          on t.scenario_id=s.scenario_id and t.station_id=s.station_id and t.observed_at=s.target_at
          where s.scenario_id=$1 and s.target_at>$2 and s.actual_value<>t.actual_value''',sid,start)==0
        await c.execute('set role academy_api')
        await c.fetch('select source_schema_version,source_quality from competition.observations limit 1')
        await c.fetch('select schema_version from competition.source_contracts where scenario_id=$1 order by effective_from desc limit 1',sid)
        await c.execute('reset role')
        # Deadline drains the admitted second cycle, then no further cycles appear.
        await c.execute("update competition.drift_windows set ends_at_wall=now()-interval '1 second' where scenario_id=$1",sid)
        for _ in range(3):
            await c.execute("update competition.scenario_clock set last_tick_at=now()-interval '31 minutes' where scenario_id=$1",sid)
            await c.execute("update competition.forecast_cycles set closes_at=now()-interval '1 second' where scenario_id=$1 and state='open'",sid)
            async with c.transaction():
                await c.execute('set local role academy_scheduler')
                await tick_scenario(c,scenario,30,25)
        assert await c.fetchval('select state from competition.scenario_clock where scenario_id=$1',sid)=='completed'
        assert await c.fetchval("select count(*) from competition.forecast_cycles where scenario_id=$1 and state in ('open','closed')",sid)==0
        assert await c.fetchval('select count(*) from competition.forecast_cycles where scenario_id=$1 and origin_at>=$2',sid,start)==2
        print(json.dumps({'status':'passed','checks':['history hashes unchanged','reopen atomic/idempotent','two scheduler ticks','v2 source projection','full truth scoring','API permissions','deadline drain without extra cycles'],'new_observations':len(rows)}))
    finally:
        await c.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--bundle',required=True)
    asyncio.run(main(p.parse_args()))
