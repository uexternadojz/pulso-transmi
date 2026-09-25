"""Read-only leaderboard for the first academic observation window."""

from __future__ import annotations

from datetime import datetime, timezone

import asyncpg

# 24 Sep 2026 00:00 in America/Bogota. Keep this instant fixed and documented.
FIRST_CUTOFF_UTC = datetime(2026, 9, 24, 5, 0, tzinfo=timezone.utc)
FIRST_SCENARIO_CODE = "official-20260921"


async def first_cutoff_board(
    pool: asyncpg.Pool, cohort_code: str | None
) -> dict[str, object]:
    async with pool.acquire() as connection, connection.transaction(
        isolation="repeatable_read", readonly=True
    ):
        as_of = await connection.fetchval("select transaction_timestamp()")
        scenario = await connection.fetchrow(
            """
            select s.id, s.code from competition.public_scenarios s
            where s.code=$1 and exists (
              select 1 from competition.forecast_cycles c
              where c.scenario_id=s.id and c.state='resolved' and c.opens_at >= $2
            )
            order by s.id desc limit 1
            """,
            FIRST_SCENARIO_CODE,
            FIRST_CUTOFF_UTC,
        )
        if scenario is None:
            return {"starts_at": FIRST_CUTOFF_UTC, "as_of": as_of,
                    "resolved_cycles": 0, "data": []}
        cycles = await connection.fetchval(
            """
            select count(*) from competition.forecast_cycles
            where scenario_id=$1 and state='resolved' and opens_at >= $2
            """,
            scenario["id"], FIRST_CUTOFF_UTC,
        )
        rows = await connection.fetch(
            """
            with eligible as (
              select p.id, p.public_id, p.display_name, p.section_code, p.avatar_index
              from competition.participant_scenarios ps
              join competition.participants p on p.id=ps.participant_id
              where ps.scenario_id=$1 and ps.status='active'
                and p.cohort_code=$2 and p.kind='student' and p.eligible
            ), cycles as (
              select id, public_id from competition.forecast_cycles
              where scenario_id=$1 and state='resolved' and opens_at >= $3
            ), station_scores as (
              select sc.participant_id, sc.station_id,
                     sum(sc.error) as absolute_error, sum(sc.actual) as actual_value,
                     sum(sc.targets) as expected_targets,
                     sum(sc.delivered) as delivered_targets
              from competition.accuracy_cycle_station sc
              join cycles c on c.public_id=sc.cycle_id
              group by sc.participant_id, sc.station_id
            ), scores as (
              select participant_id,
                     avg(greatest(0,1-absolute_error/greatest(1,actual_value)))*100
                       as accuracy,
                     sum(absolute_error)/greatest(1,sum(actual_value)) as raw_wape,
                     sum(delivered_targets)::float / nullif(sum(expected_targets),0)
                       as coverage
              from station_scores group by participant_id
            ), deliveries as (
              select ce.participant_id, count(*) as delivered_cycles,
                     max(ce.latest_submitted_at) as last_submission_at
              from competition.cycle_entries ce
              join cycles c on c.id=ce.cycle_id
              group by ce.participant_id
            )
            select e.public_id as participant_id, e.display_name, e.section_code,
                   e.avatar_index, coalesce(s.accuracy,0) as accuracy,
                   s.raw_wape,
                   coalesce(s.coverage,0) as coverage,
                   coalesce(d.delivered_cycles,0) as delivered_cycles,
                   d.last_submission_at,
                   dense_rank() over (
                     order by coalesce(s.accuracy,0) desc,
                              coalesce(s.coverage,0) desc
                   ) as rank
            from eligible e
            left join scores s on s.participant_id=e.id
            left join deliveries d on d.participant_id=e.id
            order by rank,e.display_name
            """,
            scenario["id"], cohort_code, FIRST_CUTOFF_UTC,
        )
    return {
        "starts_at": FIRST_CUTOFF_UTC,
        "as_of": as_of,
        "scenario": scenario["code"],
        "resolved_cycles": cycles,
        "data": [dict(row) for row in rows],
    }
