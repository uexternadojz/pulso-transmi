"""Administrative continuation importer. Private artifacts are never served by the API."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg

from app.settings import get_settings


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Timestamps require timezone')
    return result.astimezone(timezone.utc)


def digest(bundle):
    return hashlib.sha256(json.dumps(bundle,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate(bundle):
    required={'schema_version','scenario_code','revision','parent_sha256','level','effective_from','ends_at',
              'generator_version','reason','truth','context','calibration'}
    if required-bundle.keys() or bundle['schema_version'] != 1:
        raise ValueError('Invalid continuation contract')
    if type(bundle['level']) is not int or not 0<=bundle['level']<=3:
        raise ValueError('Invalid level')
    if type(bundle['revision']) is not int or bundle['revision']<1:
        raise ValueError('Invalid revision')
    start,end=timestamp(bundle['effective_from']),timestamp(bundle['ends_at'])
    if any(t.minute or t.second or t.microsecond for t in (start,end)):
        raise ValueError('Boundaries must align to a UTC hour')
    if not timedelta(hours=6)<=end-start<=timedelta(days=7):
        raise ValueError('Continuation must span 6–168 hours')
    stations={r['station_id'] for r in bundle['truth']}
    if len(stations)!=12:
        raise ValueError('Expected twelve stations')
    times=[start+timedelta(minutes=15*i) for i in range(1,int((end-start).total_seconds()/900)+1)]
    expected={(s,t) for s in stations for t in times}
    actual=[]
    for r in bundle['truth']:
        actual.append((r['station_id'],timestamp(r['observed_at'])))
        if type(r['actual_value']) is not int or not 0<=r['actual_value']<=100000:
            raise ValueError('Invalid truth value')
        if not isinstance(r['expected_mean'],(int,float)) or not math.isfinite(r['expected_mean']) or not 0<=r['expected_mean']<=100000:
            raise ValueError('Invalid mean')
    if len(actual)!=len(expected) or set(actual)!=expected:
        raise ValueError('Truth has gaps, duplicates or out-of-range targets')
    context_times=[timestamp(r['observed_at']) for r in bundle['context']]
    if len(context_times)!=len(times) or set(context_times)!=set(times):
        raise ValueError('Context grid mismatch')
    for r in bundle['context']:
        for field in ('rain_actual','rain_forecast','temperature_actual','temperature_forecast','city_latent_factor'):
            if not isinstance(r.get(field),(int,float)) or not math.isfinite(r[field]):
                raise ValueError('Invalid context values')
        if r['rain_actual']<0 or r['rain_forecast']<0:
            raise ValueError('Negative rain')
    calibration=bundle['calibration']
    if calibration.get('status')!='passed' or calibration.get('causal_four_horizons') is not True:
        raise ValueError('Missing causal calibration evidence')
    for metric in ('frozen_accuracy','fresh_lags_accuracy','adaptive_accuracy'):
        if not isinstance(calibration.get(metric),(int,float)) or not 0<=calibration[metric]<=100:
            raise ValueError('Invalid calibration metrics')
    if bundle['level']>0 and calibration['adaptive_accuracy']-calibration['fresh_lags_accuracy']<3:
        raise ValueError('Adaptation must outperform the fresh-lag fixed reference by 3 points')
    if calibration['adaptive_accuracy']<70:
        raise ValueError('Adaptive reference below learnability floor')
    return start,end,stations


async def apply(connection,bundle,wall_end,expected_clock):
    start,end,stations=validate(bundle)
    bundle_hash=digest(bundle)
    async with connection.transaction():
        scenario=await connection.fetchrow('select id from sim.scenarios where code=$1',bundle['scenario_code'])
        if scenario is None: raise ValueError('Unknown scenario')
        sid=scenario['id']
        await connection.execute('select pg_advisory_xact_lock(71001,$1::integer)',sid)
        clock=await connection.fetchrow('select *,now() as db_now from competition.scenario_clock where scenario_id=$1 for update',sid)
        existing=await connection.fetchval('select id from sim.drift_revisions where bundle_sha256=$1',bundle_hash)
        if existing: return {'status':'already_applied','revision_id':existing,'sha256':bundle_hash}
        if clock['virtual_now']!=expected_clock:
            raise ValueError('Clock changed; regenerate preview against current boundary')
        if wall_end<=clock['db_now']+timedelta(hours=2):
            raise ValueError('Deadline must leave time to evaluate cycles')
        frontier=await connection.fetchval('''select greatest($2::timestamptz,
          (select max(target_end_at) from competition.forecast_cycles where scenario_id=$1),
          (select max(observed_at) from competition.observations where scenario_id=$1))''',sid,clock['virtual_now'])
        if start<frontier: raise ValueError('Continuation overlaps committed targets')
        # No gaps: adjustments start at the next committed boundary; initial continuation at the exhausted clock.
        if start!=frontier: raise ValueError('Continuation must start exactly at the protected boundary')
        old=await connection.fetchrow('select * from sim.drift_revisions where scenario_id=$1 order by revision desc limit 1',sid)
        if old:
            if bundle['revision']!=old['revision']+1 or bundle['parent_sha256']!=old['bundle_sha256']:
                raise ValueError('Revision chain mismatch')
            if end!=old['ends_at']: raise ValueError('A level adjustment must preserve the virtual end')
        elif bundle['revision']!=1 or bundle['parent_sha256'] is not None or clock['state']!='completed':
            raise ValueError('Initial continuation requires a completed clock and revision 1')
        known=await connection.fetch('select station_id from sim.scenario_stations where scenario_id=$1 and is_benchmark',sid)
        if {r['station_id'] for r in known}!=stations: raise ValueError('Station set mismatch')
        # Existing future is preserved in the immutable revision artifact before any replacement.
        revision_id=await connection.fetchval('''insert into sim.drift_revisions
         (scenario_id,revision,parent_sha256,bundle_sha256,level,effective_from,ends_at,generator_version,reason,calibration,bundle)
         values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb) returning id''',sid,bundle['revision'],bundle['parent_sha256'],bundle_hash,bundle['level'],start,end,bundle['generator_version'],bundle['reason'],json.dumps(bundle['calibration']),json.dumps(bundle))
        if old:
            await connection.execute('delete from sim.generated_truth where scenario_id=$1 and observed_at>$2',sid,start)
            await connection.execute('delete from sim.time_context where scenario_id=$1 and observed_at>$2',sid,start)
        await connection.copy_records_to_table('generated_truth',schema_name='sim',columns=(
          'scenario_id','station_id','observed_at','expected_mean','actual_value','seasonal_component','calendar_component','weather_component','event_component','spatial_component','drift_component','latent_component'),records=[
          (sid,r['station_id'],timestamp(r['observed_at']),r['expected_mean'],r['actual_value'],0.,0.,0.,0.,0.,0.,0.) for r in bundle['truth']])
        await connection.copy_records_to_table('time_context',schema_name='sim',columns=(
          'scenario_id','observed_at','rain_actual','rain_forecast','temperature_actual','temperature_forecast','is_holiday','city_latent_factor','public_context'),records=[
          (sid,timestamp(r['observed_at']),r['rain_actual'],r['rain_forecast'],r['temperature_actual'],r['temperature_forecast'],False,r['city_latent_factor'],'{}') for r in bundle['context']])
        await connection.execute('update sim.scenarios set competition_end=$2,state=\'running\' where id=$1',sid,end)
        await connection.execute('''insert into competition.drift_windows(scenario_id,starts_at_virtual,ends_at_wall,current_revision_id)
          values($1,$2,$3,$4) on conflict(scenario_id) do update set current_revision_id=excluded.current_revision_id,
          ends_at_wall=excluded.ends_at_wall''',sid,start,wall_end,revision_id)
        if not old:
            await connection.execute("update competition.scenario_clock set state='running',last_tick_at=now(),version=version+1 where scenario_id=$1",sid)
            from app.scheduler import open_cycle
            cycle=await open_cycle(connection,sid,bundle['scenario_code'],clock['virtual_now'],25,end)
            if cycle is None: raise ValueError('Initial drift cycle could not open')
        await connection.execute('''insert into ops.audit_events(actor_type,actor_id,action,entity_type,entity_id,metadata)
          values('admin','drift-admin','drift.activated','scenario',$1,$2::jsonb)''',bundle['scenario_code'],json.dumps({'revision_id':revision_id,'level':bundle['level'],'sha256':bundle_hash,'reason':bundle['reason']}))
    return {'status':'active','revision_id':revision_id,'level':bundle['level'],'sha256':bundle_hash,'ends_at_wall':wall_end.isoformat()}


async def main_async(args):
    bundle=json.loads(args.bundle.read_text())
    start,end,stations=validate(bundle)
    if args.command=='validate':
        print(json.dumps({'status':'valid','sha256':digest(bundle),'targets':len(bundle['truth']),'calibration':bundle['calibration']}));return
    connection=await asyncpg.connect(get_settings().database_url)
    try: result=await apply(connection,bundle,timestamp(args.wall_end),timestamp(args.expected_clock))
    finally: await connection.close()
    print(json.dumps(result))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('validate','apply'))
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--wall-end')
    parser.add_argument('--expected-clock')
    args=parser.parse_args()
    if args.command=='apply' and (not args.wall_end or not args.expected_clock): parser.error('apply requires wall-end and expected-clock')
    asyncio.run(main_async(args))

if __name__=='__main__': main()
