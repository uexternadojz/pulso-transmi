"""Teacher observation of released drift results only."""
from fastapi import HTTPException
from statistics import median


async def monitor(pool, identity):
    async with pool.acquire() as c, c.transaction(isolation='repeatable_read',readonly=True):
        kind=await c.fetchval('select kind from competition.participants where id=$1',identity.participant_id)
        if kind!='admin': raise HTTPException(status_code=403,detail='Teacher only')
        window=await c.fetchrow('''select w.*,r.revision,r.level,r.bundle_sha256,r.generator_version,
          r.effective_from,r.reason,
          (select level from competition.drift_revision_status e where e.scenario_id=w.scenario_id
             and e.effective_from<=cl.virtual_now order by revision desc limit 1) effective_level,
          cl.state clock_state,cl.virtual_now,cl.last_tick_at,now() as as_of
          from competition.drift_windows w join competition.drift_revision_status r on r.id=w.current_revision_id
          join competition.scenario_clock cl on cl.scenario_id=w.scenario_id order by w.started_at desc limit 1''')
        if not window: return {'active':False,'message':'No drift window activated'}
        rows=await c.fetch('''with cycles as (
          select id,public_id,row_number() over(order by origin_at desc) recent
          from competition.forecast_cycles where scenario_id=$1 and state='resolved' and origin_at >=$2
        ), periods as (select c.*,w.win from cycles c cross join(values('phase'),('last6')) w(win)
                       where win='phase' or recent<=6), station as (
          select a.participant_id,p.win,a.station_id,sum(a.error) err,sum(a.actual) actual,
                 sum(a.delivered) delivered,sum(a.targets) targets
          from competition.accuracy_cycle_station a join periods p on p.public_id=a.cycle_id
          group by a.participant_id,p.win,a.station_id
        ), scores as (
          select participant_id,win,round((avg(greatest(0,1-err/greatest(1,actual)))*100)::numeric,1)::float accuracy,
          round((100*sum(delivered)::numeric/nullif(sum(targets),0)),1)::float coverage
          from station group by participant_id,win
        ), deliveries as (
          select e.participant_id,count(*) cycles,count(*) filter(where c.recent<=6) last6_cycles
          from competition.cycle_entries e join cycles c on c.id=e.cycle_id group by e.participant_id
        ) select p.public_id,p.display_name,a.accuracy,a.coverage,b.accuracy last6_accuracy,
            b.coverage last6_coverage,coalesce(d.cycles,0) delivered_cycles,coalesce(d.last6_cycles,0) last6_cycles
          from competition.participants p join competition.participant_scenarios ps on ps.participant_id=p.id
          left join scores a on a.participant_id=p.id and a.win='phase'
          left join scores b on b.participant_id=p.id and b.win='last6'
          left join deliveries d on d.participant_id=p.id
          where ps.scenario_id=$1 and ps.status='active' and p.kind='student' and p.eligible
            and p.cohort_code=$3 order by a.accuracy desc nulls last,p.display_name''',window['scenario_id'],window['effective_from'],identity.cohort_code)
        baseline=await c.fetch("""with cycles as (
          select public_id from competition.forecast_cycles where scenario_id=$1 and state='resolved'
          and origin_at<$2 order by origin_at desc limit 6
        ), station as (
          select a.participant_id,a.station_id,sum(a.error) err,sum(a.actual) actual,
          sum(a.delivered) delivered,sum(a.targets) targets from competition.accuracy_cycle_station a
          join cycles c on c.public_id=a.cycle_id group by a.participant_id,a.station_id
        ) select p.public_id,round((avg(greatest(0,1-s.err/greatest(1,s.actual)))*100)::numeric,1)::float accuracy,
          round((100*sum(s.delivered)::numeric/nullif(sum(s.targets),0)),1)::float coverage
          from station s join competition.participants p on p.id=s.participant_id group by p.public_id""",
          window['scenario_id'],window['effective_from'])
        baseline={r['public_id']:dict(r) for r in baseline}
        counts=await c.fetchrow('''select count(*) filter(where state='resolved') resolved,
          count(*) filter(where state='open') open,count(*) filter(where state='closed') awaiting_resolution,
          max(opens_at) last_opened from competition.forecast_cycles where scenario_id=$1 and origin_at>=$2''',window['scenario_id'],window['effective_from'])
        health=await c.fetchrow('select * from competition.drift_health order by heartbeat_at desc limit 1')
        revisions=await c.fetch('''select revision,level,effective_from,activated_at,reason,bundle_sha256
           from competition.drift_revision_status where scenario_id=$1 order by revision desc''',window['scenario_id'])
    students=[]
    for row in rows:
        item=dict(row);prior=baseline.get(row['public_id'],{})
        item['before_accuracy']=prior.get('accuracy');item['before_coverage']=prior.get('coverage')
        item['change_points']=round(row['last6_accuracy']-prior['accuracy'],1) if (
          counts['resolved']>=6 and (row['last6_coverage'] or 0)>=95 and
          (prior.get('coverage') or 0)>=95 and row['last6_accuracy'] is not None) else None
        students.append(item)
    alerts=[]
    if not health or (window['as_of']-health['heartbeat_at']).total_seconds()>120: alerts.append('Scheduler sin heartbeat reciente')
    if health and health['errors_24h']: alerts.append(f"{health['errors_24h']} errores de evaluación en 24 h")
    if window['clock_state']=='running' and (window['as_of']-window['last_tick_at']).total_seconds()>2400: alerts.append('Reloj sin avanzar durante más de 40 minutos')
    if counts['resolved']>=6:
        low=sum((r['last6_coverage'] or 0)<80 for r in rows)
        if low: alerts.append(f'{low} estudiantes con cobertura reciente inferior al 80 %; revisar continuidad antes de elevar dificultad')
    changes=[r['change_points'] for r in students if r['change_points'] is not None]
    if len(changes)>=8 and median(changes)<-10:
        alerts.append('Caída general superior a 10 puntos entre estudiantes con alta cobertura; mantener o revisar nivel')
    return {'active':window['clock_state']=='running','window':dict(window),'cycles':dict(counts),
            'health':dict(health) if health else None,'alerts':alerts,'students':students,
            'revisions':[dict(r) for r in revisions]}
