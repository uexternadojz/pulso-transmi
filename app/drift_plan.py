"""Validate and preview private drift plans. This module never writes to the DB."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Phase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,47}$")
    level: int = Field(strict=True, ge=0, le=3)
    duration_hours: int = Field(strict=True, ge=6, le=120)
    transition_hours: int = Field(strict=True, ge=0, le=24)

    @model_validator(mode="after")
    def check_recovery_window(self):
        if self.duration_hours - self.transition_hours < 6:
            raise ValueError("Each phase needs at least six hours after its transition")
        return self


class DriftPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    plan_id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,62}$")
    revision: int = Field(strict=True, ge=1)
    parent_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    scenario_code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,62}$")
    profile_version: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{2,62}$")
    starts_at_virtual: AwareDatetime
    phases: list[Phase] = Field(min_length=1, max_length=16)
    reason: str = Field(min_length=10, max_length=1000)

    @model_validator(mode="after")
    def check_plan(self):
        start = self.starts_at_virtual.astimezone(timezone.utc)
        if start.minute or start.second or start.microsecond:
            raise ValueError("Plan start must align to a full UTC hour")
        if (self.revision == 1) != (self.parent_sha256 is None):
            raise ValueError("Only revision 1 can omit its parent hash")
        if len({phase.phase_id for phase in self.phases}) != len(self.phases):
            raise ValueError("Phase IDs must be unique")
        if sum(phase.duration_hours for phase in self.phases) > 168:
            raise ValueError("A plan cannot exceed seven virtual days")
        return self


def plan_digest(plan: DriftPlan) -> str:
    payload = plan.model_dump(mode="json")
    payload["starts_at_virtual"] = plan.starts_at_virtual.astimezone(timezone.utc).isoformat()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_parent(plan: DriftPlan, previous: DriftPlan | None) -> None:
    if plan.revision == 1:
        if previous is not None:
            raise ValueError("Initial revision cannot replace another plan")
        return
    if previous is None:
        raise ValueError("A revised plan requires the previous revision")
    if (plan.plan_id, plan.scenario_code) != (previous.plan_id, previous.scenario_code):
        raise ValueError("Revisions must retain plan and scenario identity")
    if plan.revision != previous.revision + 1 or plan.parent_sha256 != plan_digest(previous):
        raise ValueError("Revision chain is broken")


def preview(plan: DriftPlan, protected_through: datetime, virtual_now: datetime,
            previous: DriftPlan | None = None) -> dict:
    validate_parent(plan, previous)
    for timestamp in (protected_through, virtual_now):
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Clock and protection boundary require timezones")
    boundary = max(protected_through, virtual_now)
    if plan.starts_at_virtual < boundary:
        next_start = boundary.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if next_start < boundary:
            next_start += timedelta(hours=1)
        raise ValueError(
            "Plan overlaps published data or already committed targets; "
            f"earliest available boundary: {next_start.isoformat()}"
        )
    cursor = plan.starts_at_virtual.astimezone(timezone.utc)
    phases = []
    for phase in plan.phases:
        end = cursor + timedelta(hours=phase.duration_hours)
        phases.append({
            **phase.model_dump(),
            "boundary_virtual": cursor.isoformat(),
            "first_target_virtual": (cursor + timedelta(minutes=15)).isoformat(),
            "ends_at_virtual": end.isoformat(),
        })
        cursor = end
    return {
        "status": "preview_only",
        "plan_sha256": plan_digest(plan),
        "scenario_code": plan.scenario_code,
        "revision": plan.revision,
        "protected_through": boundary.isoformat(),
        "ends_at_virtual": cursor.isoformat(),
        "phases": phases,
        "activation_requirements": [
            "private profile and generator calibration",
            "complete truth/context grid and versioned artifact",
            "transactional recheck of boundary and active revision",
            "deployment and explicit schedule activation",
        ],
    }


def read_plan(path: Path) -> DriftPlan:
    return DriftPlan.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--protected-through", type=datetime.fromisoformat, required=True)
    parser.add_argument("--virtual-now", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    try:
        result = preview(read_plan(args.plan), args.protected_through, args.virtual_now,
                         read_plan(args.previous) if args.previous else None)
    except ValueError as error:
        parser.exit(2, f"Invalid drift plan: {error}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
