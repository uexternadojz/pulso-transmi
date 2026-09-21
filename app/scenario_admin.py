"""Private scenario bundle loader and lifecycle controls.

The public repository contains the loader, validation and state machine, but not
the official bundle nor its seed.  Run this module only with the administrative
database role through the ``scenario-admin`` Compose profile.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg

from app.scheduler import open_cycle, release_observations
from app.settings import get_settings


EXPECTED_STATIONS = 12
INTERVAL_MINUTES = 15
HORIZONS = (1, 2, 3, 4)


def parse_timestamp(raw: str) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"Timestamp must include a timezone: {raw}")
    return value


def read_bundle(path: Path) -> dict[str, Any]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        bundle = json.load(handle)
    if not isinstance(bundle, dict):
        raise ValueError("Scenario bundle must be a JSON object")
    return bundle


def validate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "scenario",
        "generator",
        "stations",
        "truth",
        "context",
        "events",
        "drifts",
        "validation",
    }
    missing = required - bundle.keys()
    if missing:
        raise ValueError(f"Bundle is missing fields: {sorted(missing)}")
    if bundle["schema_version"] != 1:
        raise ValueError("Unsupported scenario bundle schema")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", bundle["scenario"].get("code", "")):
        raise ValueError("Scenario code must use lowercase letters, numbers and hyphens")
    if not re.fullmatch(r"[a-f0-9]{64}", bundle["generator"].get("seed_digest", "")):
        raise ValueError("seed_digest must be a SHA-256 hex digest")

    scenario = bundle["scenario"]
    history_start = parse_timestamp(scenario["history_start"])
    competition_start = parse_timestamp(scenario["competition_start"])
    competition_end = parse_timestamp(scenario["competition_end"])
    if not history_start < competition_start < competition_end:
        raise ValueError("Scenario dates are not ordered")
    if competition_start.minute != 0 or competition_end.minute != 0:
        raise ValueError("Competition boundaries must be aligned to a full hour")
    if (competition_end - competition_start) != timedelta(days=7):
        raise ValueError("The official scenario must span exactly seven days")

    stations = bundle["stations"]
    station_ids = {row["station_id"] for row in stations}
    if len(stations) != EXPECTED_STATIONS or len(station_ids) != EXPECTED_STATIONS:
        raise ValueError("The official scenario must contain 12 unique stations")
    if any(not row.get("is_benchmark", True) for row in stations):
        raise ValueError("All official stations must be benchmark stations")

    expected_times = int(
        (competition_end - competition_start).total_seconds()
        // (INTERVAL_MINUTES * 60)
    ) + 1
    truth = bundle["truth"]
    expected_rows = EXPECTED_STATIONS * expected_times
    if len(truth) != expected_rows:
        raise ValueError(f"Expected {expected_rows} truth rows, received {len(truth)}")
    truth_keys: set[tuple[str, datetime]] = set()
    for row in truth:
        observed_at = parse_timestamp(row["observed_at"])
        key = (row["station_id"], observed_at)
        if row["station_id"] not in station_ids or key in truth_keys:
            raise ValueError("Truth contains an unknown station or duplicate key")
        if not competition_start <= observed_at <= competition_end:
            raise ValueError("Truth contains a timestamp outside competition")
        if observed_at.minute % INTERVAL_MINUTES != 0:
            raise ValueError("Truth is not aligned to 15-minute intervals")
        actual = row["actual_value"]
        expected_mean = row["expected_mean"]
        if isinstance(actual, bool) or not isinstance(actual, int) or actual < 0:
            raise ValueError("actual_value must be a non-negative integer")
        if not isinstance(expected_mean, (int, float)) or expected_mean < 0:
            raise ValueError("expected_mean must be non-negative")
        truth_keys.add(key)

    expected_key_set = {
        (station_id, competition_start + timedelta(minutes=INTERVAL_MINUTES * step))
        for station_id in station_ids
        for step in range(expected_times)
    }
    if truth_keys != expected_key_set:
        raise ValueError("Truth grid has gaps")

    context = bundle["context"]
    if len(context) != expected_times:
        raise ValueError(f"Expected {expected_times} context rows")
    context_times = [parse_timestamp(row["observed_at"]) for row in context]
    if set(context_times) != {
        competition_start + timedelta(minutes=INTERVAL_MINUTES * step)
        for step in range(expected_times)
    }:
        raise ValueError("Context grid has gaps")

    checks = bundle["validation"]
    if checks.get("status") != "passed":
        raise ValueError("Bundle calibration did not pass")
    required_metrics = {
        "history_matches_starter",
        "naive_day_accuracy",
        "naive_week_accuracy",
        "boosting_accuracy",
        "static_drift_drop_points",
    }
    if required_metrics - checks.keys():
        raise ValueError("Bundle does not include all calibration evidence")
    if checks["history_matches_starter"] is not True:
        raise ValueError("Generator history does not match the published starter cut")
    if not 72 <= float(checks["naive_day_accuracy"]) <= 86:
        raise ValueError("Daily naive baseline is outside the accepted band")
    if not 75 <= float(checks["naive_week_accuracy"]) <= 88:
        raise ValueError("Weekly naive baseline is outside the accepted band")
    if not 79 <= float(checks["boosting_accuracy"]) <= 93:
        raise ValueError("Boosting baseline is outside the accepted band")
    if float(checks["static_drift_drop_points"]) < 7:
        raise ValueError("Drift is not strong enough")

    return {
        "history_start": history_start,
        "competition_start": competition_start,
        "competition_end": competition_end,
        "station_count": len(stations),
        "truth_rows": len(truth),
        "context_rows": len(context),
    }


async def import_bundle(path: Path) -> None:
    bundle = read_bundle(path)
    summary = validate_bundle(bundle)
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
    bundle_hash = hashlib.sha256(canonical.encode()).hexdigest()
    scenario = bundle["scenario"]
    generator = bundle["generator"]
    settings = get_settings()

    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=1)
    try:
        async with pool.acquire() as connection, connection.transaction():
            existing = await connection.fetchrow(
                "select id,state from sim.scenarios where code=$1 for update",
                scenario["code"],
            )
            if existing is not None:
                raise SystemExit(
                    f"Scenario {scenario['code']} already exists in state {existing['state']}"
                )
            generator_id = await connection.fetchval(
                """
                insert into sim.generator_versions
                    (version,git_commit,container_digest,config_schema_version)
                values ($1,$2,$3,1)
                on conflict (version) do update set version=excluded.version
                returning id
                """,
                generator["version"],
                generator["git_commit"],
                generator.get("container_digest"),
            )
            scenario_id = await connection.fetchval(
                """
                insert into sim.scenarios
                    (code,generator_version_id,state,history_start,competition_start,
                     competition_end,seed_ciphertext,config,config_hash,generated_at)
                values ($1,$2,'generated',$3,$4,$5,decode($6,'hex'),$7::jsonb,$8,now())
                returning id
                """,
                scenario["code"],
                generator_id,
                summary["history_start"],
                summary["competition_start"],
                summary["competition_end"],
                generator["seed_digest"],
                json.dumps(scenario.get("config", {})),
                bundle_hash,
            )

            await connection.executemany(
                """
                insert into catalog.stations
                    (station_id,name,latitude,longitude,source_metadata)
                values ($1,$2,$3,$4,$5::jsonb)
                on conflict (station_id) do update set
                    name=excluded.name,latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    source_metadata=catalog.stations.source_metadata||excluded.source_metadata
                """,
                [
                    (
                        row["station_id"], row["name"], row["latitude"],
                        row["longitude"], json.dumps({"source": "starter-v1"}),
                    )
                    for row in bundle["stations"]
                ],
            )
            await connection.executemany(
                """
                insert into sim.scenario_stations
                    (scenario_id,station_id,display_order,is_benchmark,archetype,parameters)
                values ($1,$2,$3,$4,$5,$6::jsonb)
                """,
                [
                    (
                        scenario_id, row["station_id"], index,
                        row.get("is_benchmark", True), row["archetype"],
                        json.dumps(row.get("parameters", {})),
                    )
                    for index, row in enumerate(bundle["stations"], start=1)
                ],
            )
            await connection.copy_records_to_table(
                "time_context",
                schema_name="sim",
                columns=(
                    "scenario_id", "observed_at", "is_holiday", "rain_actual",
                    "rain_forecast", "temperature_actual", "temperature_forecast",
                    "city_latent_factor", "private_context", "public_context",
                ),
                records=[
                    (
                        scenario_id, parse_timestamp(row["observed_at"]),
                        row.get("is_holiday", False), row["rain_actual"],
                        row["rain_forecast"], row["temperature_actual"],
                        row["temperature_forecast"], row["city_latent_factor"],
                        json.dumps(row.get("private_context", {})),
                        json.dumps(row.get("public_context", {})),
                    )
                    for row in bundle["context"]
                ],
            )
            await connection.copy_records_to_table(
                "generated_truth",
                schema_name="sim",
                columns=(
                    "scenario_id", "station_id", "observed_at", "expected_mean",
                    "actual_value", "seasonal_component", "calendar_component",
                    "weather_component", "event_component", "spatial_component",
                    "drift_component", "latent_component",
                ),
                records=[
                    (
                        scenario_id, row["station_id"],
                        parse_timestamp(row["observed_at"]), row["expected_mean"],
                        row["actual_value"], row.get("seasonal_component", 0.0),
                        row.get("calendar_component", 0.0),
                        row.get("weather_component", 0.0),
                        row.get("event_component", 0.0),
                        row.get("spatial_component", 0.0),
                        row.get("drift_component", 0.0),
                        row.get("latent_component", 0.0),
                    )
                    for row in bundle["truth"]
                ],
            )
            for event in bundle["events"]:
                await connection.execute(
                    """
                    insert into sim.events
                        (scenario_id,event_type,latitude,longitude,starts_at,ends_at,
                         announced_at,intensity,radius_km,parameters)
                    values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
                    """,
                    scenario_id, event["event_type"], event["latitude"],
                    event["longitude"], parse_timestamp(event["starts_at"]),
                    parse_timestamp(event["ends_at"]),
                    parse_timestamp(event["announced_at"]), event["intensity"],
                    event["radius_km"], json.dumps(event.get("parameters", {})),
                )
            for drift in bundle["drifts"]:
                drift_id = await connection.fetchval(
                    """
                    insert into sim.drift_events
                        (scenario_id,drift_type,starts_at,ends_at,transition_minutes,parameters)
                    values ($1,$2,$3,$4,$5,$6::jsonb) returning id
                    """,
                    scenario_id, drift["drift_type"],
                    parse_timestamp(drift["starts_at"]),
                    parse_timestamp(drift["ends_at"]) if drift.get("ends_at") else None,
                    drift.get("transition_minutes", 0),
                    json.dumps(drift.get("parameters", {})),
                )
                await connection.executemany(
                    """
                    insert into sim.drift_targets (drift_event_id,station_id,weight)
                    values ($1,$2,$3)
                    """,
                    [
                        (drift_id, target["station_id"], target.get("weight", 1.0))
                        for target in drift["targets"]
                    ],
                )
            await connection.execute(
                """
                insert into sim.validation_runs
                    (scenario_id,completed_at,status,checks)
                values ($1,now(),'passed',$2::jsonb)
                """,
                scenario_id,
                json.dumps(bundle["validation"]),
            )
            await connection.execute(
                """
                update sim.scenarios
                set state='frozen',validated_at=now(),frozen_at=now()
                where id=$1
                """,
                scenario_id,
            )
            await connection.execute(
                """
                insert into ops.audit_events
                    (actor_type,actor_id,action,entity_type,entity_id,metadata)
                values ('admin','scenario-admin','scenario.imported','scenario',$1,$2::jsonb)
                """,
                scenario["code"],
                json.dumps({**summary, "bundle_sha256": bundle_hash}, default=str),
            )
    finally:
        await pool.close()
    print(json.dumps({"scenario": scenario["code"], "state": "frozen", **summary}, default=str))


async def activate(scenario_code: str, cohort: str) -> None:
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=1)
    try:
        async with pool.acquire() as connection, connection.transaction():
            scenario = await connection.fetchrow(
                """
                select id,code,state,competition_start,competition_end
                from sim.scenarios where code=$1 for update
                """,
                scenario_code,
            )
            if scenario is None:
                raise SystemExit(f"Scenario not found: {scenario_code}")
            if scenario["state"] != "frozen":
                raise SystemExit(f"Scenario must be frozen, found {scenario['state']}")
            valid = await connection.fetchval(
                """
                select exists(select 1 from sim.validation_runs
                where scenario_id=$1 and status='passed')
                """,
                scenario["id"],
            )
            if not valid:
                raise SystemExit("Scenario has no passing validation run")
            enrolled = await connection.fetchval(
                """
                with inserted as (
                  insert into competition.participant_scenarios
                      (participant_id,scenario_id,status)
                  select id,$1,'active' from competition.participants
                  where kind='student' and eligible and cohort_code=$2
                  on conflict (participant_id,scenario_id)
                  do update set status='active'
                  returning 1
                ) select count(*) from inserted
                """,
                scenario["id"],
                cohort,
            )
            if enrolled < 1:
                raise SystemExit(f"No eligible students found for cohort {cohort}")

            await connection.execute(
                """
                update competition.forecast_cycles
                set state='cancelled'
                where state='open' and scenario_id<>$1
                """,
                scenario["id"],
            )
            await connection.execute(
                """
                update competition.scenario_clock set state='paused'
                where state='running' and scenario_id<>$1
                """,
                scenario["id"],
            )
            await connection.execute(
                """
                insert into competition.scenario_clock
                    (scenario_id,virtual_now,tick_number,last_tick_at,state,version)
                values ($1,$2,0,now(),'running',1)
                on conflict (scenario_id) do update set
                    virtual_now=excluded.virtual_now,tick_number=0,
                    last_tick_at=excluded.last_tick_at,state='running',
                    version=competition.scenario_clock.version+1
                """,
                scenario["id"],
                scenario["competition_start"],
            )
            await release_observations(
                connection,
                scenario["id"],
                scenario["competition_start"],
                scenario["competition_start"],
                include_start=True,
            )
            cycle_id = await open_cycle(
                connection,
                scenario["id"],
                scenario["code"],
                scenario["competition_start"],
                settings.submission_window_minutes,
                scenario["competition_end"],
            )
            if cycle_id is None:
                raise SystemExit("Could not create the initial forecast cycle")
            await connection.execute(
                "update sim.scenarios set state='running' where id=$1",
                scenario["id"],
            )
            await connection.execute(
                """
                insert into ops.audit_events
                    (actor_type,actor_id,action,entity_type,entity_id,metadata)
                values ('admin','scenario-admin','scenario.activated','scenario',$1,
                        jsonb_build_object('cohort',$2::text,'participants',$3::integer,
                                           'initial_cycle',$4::text))
                """,
                scenario["code"], cohort, enrolled, cycle_id,
            )
    finally:
        await pool.close()
    print(json.dumps({"scenario": scenario_code, "state": "running", "cohort": cohort, "participants": enrolled, "initial_cycle": cycle_id}))


async def set_clock_state(scenario_code: str, requested: str) -> None:
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=1)
    try:
        async with pool.acquire() as connection, connection.transaction():
            scenario = await connection.fetchrow(
                "select id,state from sim.scenarios where code=$1 for update",
                scenario_code,
            )
            if scenario is None:
                raise SystemExit(f"Scenario not found: {scenario_code}")
            clock_state = "paused" if requested == "pause" else "running"
            result = await connection.execute(
                "update competition.scenario_clock set state=$2,version=version+1 where scenario_id=$1",
                scenario["id"], clock_state,
            )
            if result != "UPDATE 1":
                raise SystemExit("Scenario clock not found")
            if requested == "resume":
                await connection.execute(
                    "update sim.scenarios set state='running' where id=$1",
                    scenario["id"],
                )
            await connection.execute(
                """
                insert into ops.audit_events
                    (actor_type,actor_id,action,entity_type,entity_id)
                values ('admin','scenario-admin',$2,'scenario',$1)
                """,
                scenario_code, f"scenario.{requested}d",
            )
    finally:
        await pool.close()
    print(json.dumps({"scenario": scenario_code, "clock": clock_state}))


async def status(scenario_code: str) -> None:
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=1)
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                select s.code,s.state,s.history_start,s.competition_start,s.competition_end,
                       c.virtual_now,c.tick_number,c.last_tick_at,c.state as clock_state,
                       (select count(*) from sim.generated_truth t where t.scenario_id=s.id) as truth_rows,
                       (select count(*) from competition.observations o where o.scenario_id=s.id) as released_rows,
                       (select count(*) from competition.forecast_cycles f where f.scenario_id=s.id) as cycles,
                       (select count(*) from competition.participant_scenarios p where p.scenario_id=s.id and p.status='active') as participants
                from sim.scenarios s
                left join competition.scenario_clock c on c.scenario_id=s.id
                where s.code=$1
                """,
                scenario_code,
            )
            if row is None:
                raise SystemExit(f"Scenario not found: {scenario_code}")
    finally:
        await pool.close()
    print(json.dumps(dict(row), default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Pulso TransMi scenario administration")
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("import-bundle")
    load.add_argument("--bundle", required=True, type=Path)
    activate_parser = commands.add_parser("activate")
    activate_parser.add_argument("--scenario", required=True)
    activate_parser.add_argument("--cohort", required=True)
    for name in ("pause", "resume", "status"):
        child = commands.add_parser(name)
        child.add_argument("--scenario", required=True)
    args = parser.parse_args()
    if args.command == "import-bundle":
        asyncio.run(import_bundle(args.bundle))
    elif args.command == "activate":
        asyncio.run(activate(args.scenario, args.cohort))
    elif args.command in {"pause", "resume"}:
        asyncio.run(set_clock_state(args.scenario, args.command))
    else:
        asyncio.run(status(args.scenario))


if __name__ == "__main__":
    main()
