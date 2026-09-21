from datetime import datetime, timedelta, timezone

import pytest

from app.scenario_admin import validate_bundle


def minimal_bundle() -> dict:
    start = datetime(2026, 9, 9, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    station_ids = [f"{index:05d}" for index in range(12)]
    timestamps = [start + timedelta(minutes=15 * step) for step in range(673)]
    return {
        "schema_version": 1,
        "scenario": {
            "code": "official-test",
            "history_start": (start - timedelta(days=45)).isoformat(),
            "competition_start": start.isoformat(),
            "competition_end": end.isoformat(),
            "config": {},
        },
        "generator": {
            "version": "test-v1",
            "git_commit": "abc1234",
            "seed_digest": "00" * 32,
        },
        "stations": [
            {
                "station_id": station_id,
                "name": station_id,
                "latitude": 4.6,
                "longitude": -74.1,
                "archetype": "interchange",
                "is_benchmark": True,
            }
            for station_id in station_ids
        ],
        "truth": [
            {
                "station_id": station_id,
                "observed_at": timestamp.isoformat(),
                "actual_value": 100,
                "expected_mean": 100.0,
            }
            for station_id in station_ids
            for timestamp in timestamps
        ],
        "context": [
            {
                "observed_at": timestamp.isoformat(),
                "rain_actual": 0.0,
                "rain_forecast": 0.0,
                "temperature_actual": 18.0,
                "temperature_forecast": 18.0,
                "city_latent_factor": 0.0,
            }
            for timestamp in timestamps
        ],
        "events": [],
        "drifts": [],
        "validation": {
            "status": "passed",
            "history_matches_starter": True,
            "naive_day_accuracy": 78.0,
            "naive_week_accuracy": 82.0,
            "boosting_accuracy": 85.0,
            "static_drift_drop_points": 10.0,
        },
    }


def test_official_bundle_requires_a_complete_seven_day_grid() -> None:
    summary = validate_bundle(minimal_bundle())

    assert summary["station_count"] == 12
    assert summary["truth_rows"] == 8_076
    assert summary["context_rows"] == 673


def test_bundle_with_a_missing_target_is_rejected() -> None:
    bundle = minimal_bundle()
    bundle["truth"].pop()

    with pytest.raises(ValueError, match="Expected 8076 truth rows"):
        validate_bundle(bundle)
