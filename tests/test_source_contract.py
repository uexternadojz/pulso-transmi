from datetime import datetime, timedelta, timezone
import pytest
from app.source_contract import serialize_observation
from app.drift_admin import validate_revision_transition


def test_historical_payload_is_unchanged_and_new_missing_values_are_not_exposed():
    t = datetime(2030, 1, 1, tzinfo=timezone.utc)
    row = dict(station_id='02300',observed_at=t,released_at=t,demand=347,
               source_schema_version=1,source_quality='observed')
    assert serialize_observation(row) == dict(station_id='02300',observed_at=t,released_at=t,demand=347)
    row['source_schema_version'] = 2
    assert serialize_observation(row)['measurement'] == dict(value='347.00',unit='passengers',quality='observed')
    row['source_quality'] = 'missing'
    payload = serialize_observation(row)
    assert payload['measurement']['value'] is None
    assert 'demand' not in payload
    assert '347' not in str(payload)


def transition_case():
    start = datetime(2030,1,1,tzinfo=timezone.utc)
    b = dict(revision=4,parent_sha256='parent',operation='reopen')
    old = dict(revision=3,bundle_sha256='parent',ends_at=start+timedelta(hours=12))
    clock = dict(state='completed',virtual_now=start,db_now=start)
    return b,old,clock,start,start+timedelta(hours=36),start+timedelta(hours=30),0


def test_drained_reopening_can_extend_horizon():
    validate_revision_transition(*transition_case())


@pytest.mark.parametrize('failure',['pending','running','chain','too_short','not_explicit','wrong_boundary'])
def test_unsafe_reopening_is_rejected(failure):
    b,old,clock,start,end,wall,pending = transition_case()
    if failure == 'pending': pending = 1
    if failure == 'running': clock['state'] = 'running'
    if failure == 'chain': b['parent_sha256'] = 'wrong'
    if failure == 'too_short': end = start+timedelta(hours=20)
    if failure == 'not_explicit': b.pop('operation')
    if failure == 'wrong_boundary': start += timedelta(hours=1)
    with pytest.raises(ValueError):
        validate_revision_transition(b,old,clock,start,end,wall,pending)
