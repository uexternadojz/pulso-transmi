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


def compact_chart(chart):
    """Deduplicate tooltip metadata on the wire; preserve every cycle and score."""
    packed = {**chart, 'format': 'compact-v1', 'stages': []}
    for stage in chart['stages']:
        participants = sorted({p['participant_id'] for p in stage['cumulative']})
        participant_index = {p: i for i, p in enumerate(participants)}
        versions = []
        version_index = {}
        output = {**stage, 'participants': participants, 'version_sets': versions}
        for mode in ('cumulative', 'rolling6'):
            output[mode] = []
            for point in stage[mode]:
                key = tuple(point['model_versions'])
                if key not in version_index:
                    version_index[key] = len(versions)
                    versions.append(list(key))
                output[mode].append([
                    participant_index[point['participant_id']], point['index'],
                    point['accuracy'], point['coverage'], point['delivered_cycles'],
                    point['window_cycles'], version_index[key],
                ])
        packed['stages'].append(output)
    return packed


async def accuracy_chart(pool, identity, compact=False):
    async with pool.acquire() as connection, connection.transaction(readonly=True):
        # Bound query memory and avoid parallel sort/merge overhead on the small VPS.
        await connection.execute("set local work_mem = '32MB'")
        await connection.execute("set local max_parallel_workers_per_gather = 0")
        # The materialized aggregate's join estimate is ~63 rows vs 74k actual.
        # Hash joins avoid 3 index lookups per station row (over 200k probes).
        # Scope the planner choice to this read-only chart transaction.
        await connection.execute("set local enable_nestloop = off")
        rows = await connection.fetch('''
            with eligible as materialized (
                select p.id, p.public_id, ps.scenario_id
                from competition.participants p
                join competition.participant_scenarios ps on ps.participant_id=p.id
                where p.cohort_code=$2 and p.kind='student' and p.eligible
                  and ps.status='active'
            ), station_scores as materialized (
                select sc.scenario_id, sc.cycle_id as internal_cycle_id,
                       sc.participant_id as internal_participant_id, sc.station_id,
                       sum(sc.absolute_error) as error,
                       sum(sc.actual_value) as actual,
                       count(*) as targets,
                       count(*) filter (where not sc.was_missing) as delivered
                from competition.accuracy_components_cutoff sc
                join eligible e on e.id=sc.participant_id and e.scenario_id=sc.scenario_id
                where sc.opens_at >= $1
                group by sc.scenario_id,sc.cycle_id,sc.participant_id,sc.station_id
            )
            select ss.scenario_id, c.public_id as cycle_id, c.closes_at,
                   e.public_id as participant_id, ss.station_id,
                   ss.error, ss.actual, ss.targets, ss.delivered,
                   case when sub.model_version is null then array[]::text[]
                        else array[sub.model_version] end as model_versions
            from station_scores ss
            join competition.forecast_cycles c on c.id=ss.internal_cycle_id
            join eligible e on e.id=ss.internal_participant_id and e.scenario_id=ss.scenario_id
            left join competition.cycle_entries ce
              on ce.cycle_id=ss.internal_cycle_id
             and ce.participant_id=ss.internal_participant_id
            left join competition.submissions sub on sub.id=ce.official_submission_id
            order by ss.scenario_id, c.closes_at
        ''', FIRST_CUTOFF_UTC, identity.cohort_code)
    chart = build_chart(rows)
    for stage in chart['stages']:
        stage['label'] = 'Corte 1'
    chart['starts_at'] = FIRST_CUTOFF_UTC
    return compact_chart(chart) if compact else chart
