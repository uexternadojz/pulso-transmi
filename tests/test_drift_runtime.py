import copy
from datetime import datetime,timedelta,timezone
import pytest
from app.drift_admin import validate,digest


def bundle():
    start=datetime(2030,1,1,tzinfo=timezone.utc)
    times=[start+timedelta(minutes=15*i) for i in range(1,25)]
    return dict(schema_version=1,scenario_code='example',revision=1,parent_sha256=None,
        level=1,effective_from=start.isoformat(),ends_at=(start+timedelta(hours=6)).isoformat(),
        generator_version='test-v1',reason='Integration test',
        truth=[dict(station_id=f'{s:05}',observed_at=t.isoformat(),actual_value=100,expected_mean=100.) for t in times for s in range(12)],
        context=[dict(observed_at=t.isoformat(),rain_actual=0.,rain_forecast=0.,temperature_actual=18.,temperature_forecast=18.,city_latent_factor=0.) for t in times],
        calibration=dict(status='passed',causal_four_horizons=True,frozen_accuracy=70.,fresh_lags_accuracy=75.,adaptive_accuracy=85.))


def test_continuation_grid_and_content_hash():
    b=bundle();validate(b);original=digest(b)
    b['level']=2
    assert digest(b)!=original
    b['truth'].pop()
    with pytest.raises(ValueError,match='gaps'):validate(b)


@pytest.mark.parametrize('mutation', ['duplicate','bridge','nan','context','no_recovery'])
def test_invalid_continuation_rejected(mutation):
    b=bundle()
    if mutation=='duplicate':b['truth'][-1]=copy.deepcopy(b['truth'][0])
    elif mutation=='bridge':b['truth'][0]['observed_at']=b['effective_from']
    elif mutation=='nan':b['truth'][0]['expected_mean']=float('nan')
    elif mutation=='context':b['context'].pop()
    else:b['calibration']['adaptive_accuracy']=75.
    with pytest.raises(ValueError):validate(b)
