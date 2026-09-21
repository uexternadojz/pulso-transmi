from datetime import datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.competition import payload_digest, validate_target_contract
from app.contracts import SubmissionInput
from app.security import generate_api_key, split_api_key, verify_secret


def valid_payload() -> dict:
    return {
        "schema_version": "1.0",
        "cycle_id": "cyc_p1_20260916T150000Z",
        "client_run_id": "gha-123-1",
        "data_cutoff": "2026-09-16T10:00:00-05:00",
        "model": {
            "version": "xgb:3.1",
            "trained_at": "2026-09-16T09:55:00-05:00",
            "training_data_end": "2026-09-16T10:00:00-05:00",
            "git_commit": "abcdef1234567",
        },
        "predictions": [
            {
                "station_id": "02300",
                "target_at": "2026-09-16T10:15:00-05:00",
                "value": 321.5,
            }
        ],
    }


def test_api_key_is_stored_as_verifiable_hash() -> None:
    raw, prefix, encoded = generate_api_key()
    assert split_api_key(raw) is not None
    assert split_api_key(raw)[0] == prefix
    assert raw not in encoded
    assert verify_secret(raw.split(".", 1)[1], encoded)
    assert not verify_secret("wrong", encoded)


def test_submission_rejects_unknown_fields_and_bad_values() -> None:
    payload = valid_payload()
    payload["student_name"] = "identity-must-not-come-from-body"
    with pytest.raises(ValidationError):
        SubmissionInput.model_validate(payload)

    payload = valid_payload()
    payload["predictions"][0]["value"] = float("nan")
    with pytest.raises(ValidationError):
        SubmissionInput.model_validate(payload)


def test_submission_rejects_naive_timestamps() -> None:
    payload = valid_payload()
    payload["data_cutoff"] = "2026-09-16T10:00:00"
    with pytest.raises(ValidationError):
        SubmissionInput.model_validate(payload)


def test_payload_digest_is_canonical() -> None:
    first = SubmissionInput.model_validate(valid_payload())
    second = SubmissionInput.model_validate(valid_payload())
    assert payload_digest(first) == payload_digest(second)
    assert first.data_cutoff.utcoffset() is not None


def cycle_contract() -> tuple[dict, list[dict]]:
    cutoff = datetime.fromisoformat("2026-09-16T10:00:00-05:00")
    targets = [
        {
            "station_id": "02300",
            "target_at": datetime.fromisoformat("2026-09-16T10:15:00-05:00"),
            "horizon_steps": 1,
        }
    ]
    cycle = {
        "public_id": "cyc_p1_20260916T150000Z",
        "data_cutoff": cutoff,
        "target_start_at": targets[0]["target_at"],
        "target_end_at": targets[0]["target_at"],
    }
    return cycle, targets


def test_target_guardrail_returns_the_validated_period() -> None:
    payload = SubmissionInput.model_validate(valid_payload())
    cycle, targets = cycle_contract()

    contract = validate_target_contract(payload, cycle, targets)

    assert contract["cycle_id"] == payload.cycle_id
    assert contract["forecast_start_at"] == payload.predictions[0].target_at
    assert contract["forecast_end_at"] == payload.predictions[0].target_at
    assert contract["station_count"] == 1
    assert contract["horizons_minutes"] == [15]
    assert contract["expected_predictions"] == 1


def test_target_guardrail_rejects_missing_or_invented_targets() -> None:
    raw = valid_payload()
    raw["predictions"][0]["target_at"] = "2026-09-16T10:30:00-05:00"
    payload = SubmissionInput.model_validate(raw)
    cycle, targets = cycle_contract()

    with pytest.raises(HTTPException) as error:
        validate_target_contract(payload, cycle, targets)

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "invalid_target_set"
    assert error.value.detail["expected_predictions"] == 1
    assert error.value.detail["received_predictions"] == 1
    assert error.value.detail["missing"]
    assert error.value.detail["extra"]


def test_target_guardrail_fails_closed_on_broken_server_contract() -> None:
    payload = SubmissionInput.model_validate(valid_payload())
    cycle, targets = cycle_contract()
    cycle["target_end_at"] = datetime.fromisoformat("2026-09-16T10:30:00-05:00")

    with pytest.raises(HTTPException) as error:
        validate_target_contract(payload, cycle, targets)

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "cycle_contract_invalid"
