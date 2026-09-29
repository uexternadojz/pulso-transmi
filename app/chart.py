"""Read-only chart metrics, using official per-station WAPE aggregation."""
from collections import Counter, defaultdict, deque

from app.cutoff import FIRST_CUTOFF_UTC


class _Window:
    def __init__(self):
        self.stations = {}
        self.targets = 0
        self.delivered = 0
        self.delivered_cycles = 0
        self.versions = Counter()

    def change(self, samples, direction):
        self.delivered_cycles += direction * any(s['delivered'] for s in samples)
        for sample in samples:
            station = sample['station_id']
            sums = self.stations.setdefault(station, [0, 0, 0])
            sums[0] += direction * sample['error']
            sums[1] += direction * sample['actual']
            sums[2] += direction
            if not sums[2]:
                del self.stations[station]
            self.targets += direction * sample['targets']
            self.delivered += direction * sample['delivered']
            for version in sample.get('model_versions') or []:
                if version:
                    self.versions[version] += direction
                    if not self.versions[version]:
                        del self.versions[version]

    def point(self, person, cycle_id, cycle, index, window_cycles):
        accuracy = (
            100 * sum(max(0, 1 - error / max(1, actual))
                      for error, actual, _ in self.stations.values()) / len(self.stations)
            if self.stations else 0
        )
        return {
            'participant_id': person, 'accuracy': accuracy,
            'coverage': self.delivered / self.targets if self.targets else 0,
            'cycle_id': cycle_id, 'at': cycle['at'], 'index': index,
            'window_cycles': window_cycles,
            'delivered_cycles': self.delivered_cycles,
            'model_versions': sorted(self.versions),
        }


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
        cumulative = {person: _Window() for person in people}
        rolling = {person: _Window() for person in people}
        recent = {person: deque() for person in people}
        points = {'cumulative': [], 'rolling6': []}
        for index, (cycle_id, cycle) in enumerate(cycles):
            for person in people:
                samples = cycle['people'].get(person, [])
                cumulative[person].change(samples, 1)
                rolling[person].change(samples, 1)
                recent[person].append(samples)
                if len(recent[person]) > 6:
                    rolling[person].change(recent[person].popleft(), -1)
                points['cumulative'].append(
                    cumulative[person].point(person, cycle_id, cycle, index, index + 1)
                )
                points['rolling6'].append(
                    rolling[person].point(person, cycle_id, cycle, index, len(recent[person]))
                )
        result.append({'id': str(stage_id), 'label': f'Etapa {len(result)+1}',
                       'cycles': [{'id': cid, 'at': c['at']} for cid,c in cycles], **points})
    return {'stages': result}


async def accuracy_chart(pool, identity):
    async with pool.acquire() as connection:
        rows = await connection.fetch('''
            with station_scores as materialized (
                select sc.scenario_id, sc.cycle_id as internal_cycle_id,
                       sc.public_cycle_id as cycle_id, sc.closes_at,
                       p.id as internal_participant_id,
                       p.public_id as participant_id, sc.station_id,
                       sum(sc.absolute_error) as error,
                       sum(sc.actual_value) as actual,
                       count(*) as targets,
                       count(*) filter (where not sc.was_missing) as delivered
                from competition.accuracy_components_cutoff sc
                join competition.participants p on p.id=sc.participant_id
                join competition.participant_scenarios ps
                  on ps.participant_id=p.id and ps.scenario_id=sc.scenario_id
                where sc.opens_at >= $1
                  and p.cohort_code=$2 and p.kind='student' and p.eligible
                  and ps.status='active'
                group by sc.scenario_id,sc.cycle_id,sc.public_cycle_id,
                         sc.closes_at,p.id,sc.station_id
            )
            select ss.scenario_id, ss.cycle_id, ss.closes_at,
                   ss.participant_id, ss.station_id,
                   ss.error, ss.actual, ss.targets, ss.delivered,
                   case when sub.model_version is null then array[]::text[]
                        else array[sub.model_version] end as model_versions
            from station_scores ss
            left join competition.cycle_entries ce
              on ce.cycle_id=ss.internal_cycle_id
             and ce.participant_id=ss.internal_participant_id
            left join competition.submissions sub on sub.id=ce.official_submission_id
            order by ss.scenario_id, ss.closes_at
        ''', FIRST_CUTOFF_UTC, identity.cohort_code)
    chart = build_chart(rows)
    for stage in chart['stages']:
        stage['label'] = 'Corte 1'
    chart['starts_at'] = FIRST_CUTOFF_UTC
    return chart
