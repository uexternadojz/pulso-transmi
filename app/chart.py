"""Read-only chart metrics, using official per-station WAPE aggregation."""
from collections import defaultdict

from app.cutoff import FIRST_CUTOFF_UTC, FIRST_SCENARIO_CODE


def build_chart(rows):
    stages = {}
    for row in rows:
        stage = stages.setdefault(row['scenario_id'], {})
        cycle = stage.setdefault(row['cycle_id'], {'at': row['closes_at'], 'people': defaultdict(list)})
        cycle['people'][row['participant_id']].append(dict(row))
    result = []
    for stage_id, by_cycle in stages.items():
        cycles = sorted(by_cycle.items(), key=lambda item: item[1]['at'])
        people = {p for _, c in cycles for p in c['people']}
        points = {'cumulative': [], 'rolling6': []}
        for index, (cycle_id, cycle) in enumerate(cycles):
            for mode, start in [('cumulative', 0), ('rolling6', max(0, index-5))]:
                window = cycles[start:index+1]
                for person in people:
                    samples = [s for _, c in window for s in c['people'].get(person, [])]
                    delivered = sum(s['delivered'] for s in samples)
                    stations = defaultdict(lambda: [0, 0])
                    for sample in samples:
                        stations[sample['station_id']][0] += sample['error']
                        stations[sample['station_id']][1] += sample['actual']
                    accuracy = (
                        100 * sum(max(0, 1-e/max(1,a)) for e,a in stations.values()) / len(stations)
                        if stations else 0
                    )
                    points[mode].append({
                        'participant_id': person, 'accuracy': accuracy,
                        'coverage': delivered / sum(s['targets'] for s in samples) if samples else 0,
                        'cycle_id': cycle_id, 'at': cycle['at'], 'index': index,
                        'window_cycles': len(window),
                        'delivered_cycles': sum(any(s['delivered'] for s in c['people'].get(person, [])) for _,c in window),
                        'model_versions': sorted({v for s in samples for v in (s.get('model_versions') or []) if v}),
                    })
        result.append({'id': str(stage_id), 'label': f'Etapa {len(result)+1}',
                       'cycles': [{'id': cid, 'at': c['at']} for cid,c in cycles], **points})
    return {'stages': result}


async def accuracy_chart(pool, identity):
    async with pool.acquire() as connection:
        rows = await connection.fetch('''
            select sc.scenario_id, c.public_id as cycle_id, c.closes_at,
                   p.public_id as participant_id, sc.station_id,
                   sum(sc.absolute_error) as error,
                   sum(sc.actual_value) as actual,
                   count(*) as targets,
                   count(*) filter (where not sc.was_missing) as delivered,
                   array_agg(distinct sub.model_version) as model_versions
            from competition.forecast_cycles c
            join competition.public_scenarios scenario
              on scenario.id=c.scenario_id
            join competition.score_components sc
              on sc.cycle_id=c.id and sc.scenario_id=c.scenario_id
            join competition.participants p on p.id=sc.participant_id
            join competition.participant_scenarios ps
              on ps.participant_id=p.id and ps.scenario_id=sc.scenario_id
            left join competition.submissions sub on sub.id=sc.submission_id
            where p.cohort_code=$1 and p.kind='student' and p.eligible
              and ps.status='active' and scenario.code=$2
              and c.state='resolved' and c.opens_at >= $3
            group by sc.scenario_id,c.id,p.public_id,sc.station_id
            order by sc.scenario_id,c.closes_at
        ''', identity.cohort_code, FIRST_SCENARIO_CODE, FIRST_CUTOFF_UTC)
    chart = build_chart(rows)
    for stage in chart['stages']:
        stage['label'] = 'Corte 1'
    chart['starts_at'] = FIRST_CUTOFF_UTC
    return chart
