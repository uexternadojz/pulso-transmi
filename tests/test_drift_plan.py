from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.drift_plan import DriftPlan, plan_digest, preview, read_plan


@pytest.fixture
def plan():
    return read_plan(Path(__file__).resolve().parents[1] / "config/drift-plan.example.json")


def test_commit_boundary_excludes_existing_target_and_has_no_gap(plan):
    result = preview(plan, plan.starts_at_virtual, plan.starts_at_virtual)
    assert result["status"] == "preview_only"
    assert result["phases"][0]["first_target_virtual"] == "2030-01-01T00:15:00+00:00"
    assert result["phases"][0]["ends_at_virtual"] == result["phases"][1]["boundary_virtual"]
    with pytest.raises(ValueError, match="committed"):
        preview(plan, plan.starts_at_virtual + timedelta(minutes=15), plan.starts_at_virtual)


def test_revision_cannot_change_parent_or_skip_revision(plan):
    data = plan.model_dump()
    data.update(revision=2, parent_sha256=plan_digest(plan))
    revised = DriftPlan.model_validate(data)
    preview(revised, plan.starts_at_virtual, plan.starts_at_virtual, plan)
    data["parent_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="chain"):
        preview(DriftPlan.model_validate(data), plan.starts_at_virtual, plan.starts_at_virtual, plan)
    with pytest.raises(ValueError, match="previous"):
        preview(revised, plan.starts_at_virtual, plan.starts_at_virtual)


def test_timezone_equivalent_plan_has_same_hash(plan):
    data = plan.model_dump()
    data["starts_at_virtual"] = plan.starts_at_virtual.astimezone(timezone(timedelta(hours=-5)))
    assert plan_digest(DriftPlan.model_validate(data)) == plan_digest(plan)


@pytest.mark.parametrize("level", [-1, 4, True, 1.5])
def test_invalid_level_is_rejected(plan, level):
    data = plan.model_dump()
    data["phases"][0]["level"] = level
    with pytest.raises(ValidationError):
        DriftPlan.model_validate(data)


def test_recovery_window_and_unknown_fields_are_rejected(plan):
    data = plan.model_dump()
    data["phases"][0].update(duration_hours=6, transition_hours=6)
    with pytest.raises(ValidationError, match="six hours"):
        DriftPlan.model_validate(data)
    data = plan.model_dump()
    data["seed"] = "must-not-be-in-public-contract"
    with pytest.raises(ValidationError):
        DriftPlan.model_validate(data)


def test_naive_boundary_is_rejected(plan):
    with pytest.raises(ValueError, match="timezones"):
        preview(plan, datetime(2030, 1, 1), plan.starts_at_virtual)
