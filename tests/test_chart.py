from datetime import datetime, timedelta, timezone
from app.chart import build_chart
from app.cutoff import FIRST_CUTOFF_UTC


def test_academic_cut_starts_at_25_september_midnight_bogota():
    assert FIRST_CUTOFF_UTC == datetime(2026, 9, 25, 5, tzinfo=timezone.utc)


def test_windows_recompute_station_wape_and_missing_coverage():
    rows=[]
    for i in range(7):
        for person in ['sent','absent']:
            rows.append(dict(scenario_id=1,cycle_id=f'c{i}',closes_at=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i),participant_id=person,station_id='a',error=100 if i==0 or person=='absent' else 0,actual=100,targets=4,delivered=0 if person=='absent' or i==0 else 4))
    stage=build_chart(rows)['stages'][0]
    sent = [point for point in stage['cumulative'] if point['participant_id']=='sent']
    absent = [point for point in stage['cumulative'] if point['participant_id']=='absent']
    rolling_sent = [point for point in stage['rolling6'] if point['participant_id']=='sent']
    assert len(sent)==len(absent)==7
    assert abs(sent[-1]['accuracy']-600/7)<1e-8
    assert rolling_sent[-1]['accuracy']==100
    assert rolling_sent[-1]['coverage']==1
    assert sent[-1]['coverage']==6/7
    assert all(point['accuracy']==0 and point['coverage']==0 for point in absent)


def test_stations_are_macro_averaged_and_stages_isolated():
    rows=[dict(scenario_id=1,cycle_id='c',closes_at=datetime(2026,1,1),participant_id='p',station_id=s,error=e,actual=a,targets=4,delivered=4) for s,e,a in [('a',0,1000),('b',10,10)]]
    rows.append(dict(rows[0],scenario_id=2,cycle_id='d'))
    stages=build_chart(rows)['stages']
    assert stages[0]['cumulative'][0]['accuracy']==50
    assert stages[1]['cumulative'][0]['accuracy']==100


def test_later_participant_has_zero_score_before_first_record():
    first = datetime(2026, 9, 25, tzinfo=timezone.utc)
    rows = [
        dict(scenario_id=1, cycle_id='c1', closes_at=first,
             participant_id='early', station_id='a', error=0, actual=10,
             targets=1, delivered=1),
        dict(scenario_id=1, cycle_id='c2', closes_at=first+timedelta(hours=1),
             participant_id='late', station_id='a', error=0, actual=10,
             targets=1, delivered=1),
    ]
    stage = build_chart(rows)['stages'][0]
    before_first_record = next(point for point in stage['cumulative']
                               if point['participant_id']=='late' and point['cycle_id']=='c1')
    assert before_first_record['accuracy'] == 0
    assert before_first_record['coverage'] == 0
