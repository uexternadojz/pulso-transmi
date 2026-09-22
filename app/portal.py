from __future__ import annotations

import hashlib
import hmac
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import HTTPException

from app.security import generate_api_key


@dataclass(frozen=True)
class PortalIdentity:
    participant_id: int
    public_id: str
    display_name: str
    cohort_code: str | None
    section_code: str | None
    preferred_name: str
    token_hash: str


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_identity(value: str, field: str) -> str:
    if field == "email":
        return value.strip().lower()
    if field == "student_code":
        return "".join(char for char in _plain(value) if char.isalnum())
    raise ValueError(f"Unsupported identity field: {field}")


def identity_hash(value: str, field: str, pepper: str) -> bytes:
    normalized = normalize_identity(value, field)
    return hmac.new(
        pepper.encode(), f"{field}:{normalized}".encode(), hashlib.sha256
    ).digest()


def normalize_preferred_name(value: str) -> str:
    """Keep a friendly name for presentation; never use it as identity proof."""
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def login(
    pool: asyncpg.Pool,
    *,
    name: str,
    email: str,
    student_code: str,
    pepper: str,
    session_hours: int,
) -> tuple[PortalIdentity, str, datetime]:
    preferred_name = normalize_preferred_name(name)
    email_digest = identity_hash(email, "email", pepper)
    code_digest = identity_hash(student_code, "student_code", pepper)
    raw_token = secrets.token_urlsafe(32)
    token_digest = session_hash(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=session_hours)

    async with pool.acquire() as connection, connection.transaction():
        row = await connection.fetchrow(
            """
            select id, public_id, display_name, cohort_code, section_code
            from competition.participants
            where kind='student'
              and login_email_hash=$1
              and login_student_code_hash=$2
            """,
            email_digest,
            code_digest,
        )
        if row is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "invalid_identity",
                    "message": "Los datos no coinciden con la matrícula activa.",
                },
            )
        await connection.execute(
            """
            insert into competition.portal_sessions
                (token_hash, participant_id, expires_at, preferred_name)
            values ($1,$2,$3,$4)
            """,
            token_digest,
            row["id"],
            expires_at,
            preferred_name,
        )
    return (
        PortalIdentity(
            participant_id=row["id"],
            public_id=row["public_id"],
            display_name=row["display_name"],
            cohort_code=row["cohort_code"],
            section_code=row["section_code"],
            preferred_name=preferred_name,
            token_hash=token_digest,
        ),
        raw_token,
        expires_at,
    )


async def authenticate_session(
    pool: asyncpg.Pool, raw_token: str | None
) -> PortalIdentity:
    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail={"code": "portal_session_required", "message": "Inicia sesión."},
        )
    token_digest = session_hash(raw_token)
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            select p.id, p.public_id, p.display_name, p.cohort_code, p.section_code,
                   coalesce(s.preferred_name, p.display_name) as preferred_name
            from competition.portal_sessions s
            join competition.participants p on p.id=s.participant_id
            where s.token_hash=$1 and s.revoked_at is null and s.expires_at > now()
            """,
            token_digest,
        )
        if row is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "portal_session_expired",
                    "message": "La sesión venció. Ingresa de nuevo.",
                },
            )
        await connection.execute(
            "update competition.portal_sessions set last_seen_at=now() where token_hash=$1",
            token_digest,
        )
    return PortalIdentity(
        participant_id=row["id"],
        public_id=row["public_id"],
        display_name=row["display_name"],
        cohort_code=row["cohort_code"],
        section_code=row["section_code"],
        preferred_name=row["preferred_name"],
        token_hash=token_digest,
    )


async def logout(pool: asyncpg.Pool, identity: PortalIdentity) -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            "update competition.portal_sessions set revoked_at=now() where token_hash=$1",
            identity.token_hash,
        )


async def issue_api_key(
    pool: asyncpg.Pool, identity: PortalIdentity
) -> dict[str, object]:
    raw_key, prefix, secret_hash = generate_api_key()
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute(
            "select pg_advisory_xact_lock(9042026, $1::integer)",
            identity.participant_id,
        )
        active = await connection.fetchrow(
            """
            select key_prefix, created_at, last_used_at
            from competition.api_keys
            where participant_id=$1 and revoked_at is null
            order by created_at desc limit 1
            """,
            identity.participant_id,
        )
        if active is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "api_key_already_issued",
                    "message": "La API key ya fue generada. Si la perdiste, rótala desde el portal.",
                    "key_prefix": active["key_prefix"],
                },
            )
        created_at = await connection.fetchval(
            """
            insert into competition.api_keys (participant_id,key_prefix,secret_hash)
            values ($1,$2,$3) returning created_at
            """,
            identity.participant_id,
            prefix,
            secret_hash,
        )
        await connection.execute(
            "update competition.participants set credential_claimed_at=now() where id=$1",
            identity.participant_id,
        )
        await connection.execute(
            """
            insert into ops.audit_events
                (actor_type, actor_id, action, entity_type, entity_id, metadata)
            values ('participant',$1,'api_key.issued','api_key',$2,'{}'::jsonb)
            """,
            identity.public_id,
            prefix,
        )
    return {
        "api_key": raw_key,
        "key_prefix": prefix,
        "created_at": created_at,
        "shown_once": True,
    }


async def rotate_api_key(
    pool: asyncpg.Pool,
    identity: PortalIdentity,
    issuance_limit_per_hour: int,
) -> dict[str, object]:
    """Replace the active credential without ever recovering its secret."""
    raw_key, prefix, secret_hash = generate_api_key()
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute(
            "select pg_advisory_xact_lock(9042026, $1::integer)",
            identity.participant_id,
        )
        active = await connection.fetchrow(
            """
            select id, key_prefix
            from competition.api_keys
            where participant_id=$1 and revoked_at is null
            order by created_at desc limit 1
            """,
            identity.participant_id,
        )
        if active is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "api_key_missing",
                    "message": "No hay una API key activa para rotar. Genera la primera credencial.",
                },
            )
        issued_recently = await connection.fetchval(
            """
            select count(*) from competition.api_keys
            where participant_id=$1 and created_at > now() - interval '1 hour'
            """,
            identity.participant_id,
        )
        if int(issued_recently) >= issuance_limit_per_hour:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "api_key_rotation_rate_limited",
                    "message": "Alcanzaste el límite de cambios de API key. Intenta de nuevo en una hora.",
                },
            )

        await connection.execute(
            """
            update competition.api_keys set revoked_at=now()
            where participant_id=$1 and revoked_at is null
            """,
            identity.participant_id,
        )
        created_at = await connection.fetchval(
            """
            insert into competition.api_keys (participant_id,key_prefix,secret_hash)
            values ($1,$2,$3) returning created_at
            """,
            identity.participant_id,
            prefix,
            secret_hash,
        )
        await connection.execute(
            "update competition.participants set credential_claimed_at=now() where id=$1",
            identity.participant_id,
        )
        await connection.execute(
            """
            insert into ops.audit_events
                (actor_type, actor_id, action, entity_type, entity_id, metadata)
            values (
                'participant',$1,'api_key.rotated','api_key',$2,
                jsonb_build_object('revoked_key_prefix',$3::text)
            )
            """,
            identity.public_id,
            prefix,
            active["key_prefix"],
        )
    return {
        "api_key": raw_key,
        "key_prefix": prefix,
        "created_at": created_at,
        "revoked_key_prefix": active["key_prefix"],
        "shown_once": True,
    }


async def dashboard(pool: asyncpg.Pool, identity: PortalIdentity) -> dict[str, object]:
    async with pool.acquire() as connection:
        key = await connection.fetchrow(
            """
            select key_prefix, created_at, last_used_at
            from competition.api_keys
            where participant_id=$1 and revoked_at is null
            order by created_at desc limit 1
            """,
            identity.participant_id,
        )
        cycle = await connection.fetchrow(
            """
            select id, public_id, data_cutoff, opens_at, closes_at,
                   target_start_at, target_end_at, state,
                   (select count(*) from competition.cycle_targets t where t.cycle_id=c.id) as expected_predictions
            from competition.forecast_cycles c
            where state='open' and now() < closes_at
            order by opens_at desc limit 1
            """
        )
        submissions = await connection.fetch(
            """
            select s.public_id as submission_id, c.public_id as cycle_id, s.status,
                   s.attempt_number, s.received_at, s.model_version,
                   (select count(*) from competition.predictions p where p.submission_id=s.id) as prediction_count,
                   (e.official_submission_id=s.id) as is_official
            from competition.submissions s
            join competition.forecast_cycles c on c.id=s.cycle_id
            left join competition.cycle_entries e
              on e.cycle_id=s.cycle_id and e.participant_id=s.participant_id
            where s.participant_id=$1
            order by s.received_at desc limit 10
            """,
            identity.participant_id,
        )
    return {
        "participant": {
            "participant_id": identity.public_id,
            "display_name": identity.display_name,
            "preferred_name": identity.preferred_name,
            "cohort": identity.cohort_code,
            "section": identity.section_code,
        },
        "api_key": dict(key) if key else None,
        "cycle": dict(cycle) if cycle else None,
        "submissions": [dict(row) for row in submissions],
    }


async def cohort_board(
    pool: asyncpg.Pool, identity: PortalIdentity
) -> dict[str, object]:
    async with pool.acquire() as connection:
        cycle = await connection.fetchrow(
            """
            select id, public_id, scenario_id, state, opens_at, closes_at,
                   (select count(*) from competition.cycle_targets t where t.cycle_id=c.id) as expected_predictions
            from competition.forecast_cycles c
            order by (state='open' and now() < closes_at) desc, opens_at desc
            limit 1
            """
        )
        if cycle is None:
            return {
                "mode": "integration",
                "cycle": None,
                "data": [],
                "timeline": [],
                "count": 0,
            }
        rows = await connection.fetch(
            """
            select p.id as participant_db_id,
                   p.public_id as participant_id, p.display_name, p.section_code,
                   coalesce(
                     p.avatar_index,
                     ((row_number() over (order by p.public_id) - 1) % 36)::smallint
                   ) as avatar_index,
                   exists(
                     select 1 from competition.api_keys k
                     where k.participant_id=p.id and k.revoked_at is null
                   ) as api_key_active,
                   latest.status as submission_status,
                   latest.attempt_number,
                   latest.received_at as last_submission_at,
                   latest.model_version,
                   coalesce((
                     select count(*) from competition.predictions pr
                     where pr.submission_id=latest.id
                   ), 0) as prediction_count,
                   lb.rank, lb.accuracy, lb.coverage, lb.calculated_at
            from competition.participant_scenarios ps
            join competition.participants p on p.id=ps.participant_id
            left join lateral (
                select s.id, s.status, s.attempt_number, s.received_at,
                       s.model_version
                from competition.cycle_entries ce
                join competition.submissions s on s.id=ce.official_submission_id
                join competition.forecast_cycles fc on fc.id=ce.cycle_id
                where ce.participant_id=p.id and fc.scenario_id=$1
                order by s.received_at desc
                limit 1
            ) latest on true
            left join competition.leaderboard_latest lb
              on lb.participant_id=p.id
             and lb.scenario_id=$1
             and lb.window_type='cumulative'
            where ps.scenario_id=$1 and ps.status='active' and p.kind='student'
              and p.eligible is true
              and p.cohort_code=$2
            order by (latest.status='accepted') desc,
                     api_key_active desc, p.display_name
            """,
            cycle["scenario_id"],
            identity.cohort_code,
        )
        recent_cycles = await connection.fetch(
            """
            select id as cycle_db_id, public_id as cycle_id, opens_at, closes_at
            from competition.forecast_cycles
            where scenario_id=$1 and closes_at <= now()
            order by opens_at desc
            limit 6
            """,
            cycle["scenario_id"],
        )
        official_submissions = await connection.fetch(
            """
            select p.id as participant_db_id,
                   c.id as cycle_db_id, c.public_id as cycle_id,
                   c.opens_at, c.closes_at,
                   s.received_at, s.model_version, s.status,
                   (select count(*) from competition.predictions pr
                    where pr.submission_id=s.id) as prediction_count
            from competition.cycle_entries ce
            join competition.submissions s on s.id=ce.official_submission_id
            join competition.forecast_cycles c on c.id=ce.cycle_id
            join competition.participants p on p.id=ce.participant_id
            join competition.participant_scenarios ps
              on ps.participant_id=p.id and ps.scenario_id=c.scenario_id
            where c.scenario_id=$1 and ps.status='active'
              and p.kind='student' and p.eligible is true and p.cohort_code=$2
            order by c.opens_at, p.display_name
            """,
            cycle["scenario_id"],
            identity.cohort_code,
        )
        timeline = await connection.fetch(
            """
            select participant_id, display_name, calculated_at, accuracy,
                   coverage, rank
            from (
                select p.public_id as participant_id, p.display_name,
                       ss.calculated_at, ss.accuracy, ss.coverage, ss.rank,
                       row_number() over (
                           partition by ss.participant_id
                           order by ss.calculated_at desc
                       ) as point_number
                from competition.score_snapshots ss
                join competition.participants p on p.id=ss.participant_id
                join competition.participant_scenarios ps
                  on ps.participant_id=p.id and ps.scenario_id=ss.scenario_id
                where ss.scenario_id=$1
                  and ss.window_type='cumulative'
                  and ps.status='active'
                  and p.kind='student'
                  and p.eligible is true
                  and p.cohort_code=$2
            ) history
            where point_number <= 96
            order by calculated_at, participant_id
            """,
            cycle["scenario_id"],
            identity.cohort_code,
        )
    recent_cycle_rows = [dict(item) for item in reversed(recent_cycles)]
    submissions_by_participant: dict[int, list[dict[str, object]]] = {}
    for submission in official_submissions:
        item = dict(submission)
        submissions_by_participant.setdefault(item["participant_db_id"], []).append(item)

    board_rows: list[dict[str, object]] = []
    for source in rows:
        row = dict(source)
        participant_db_id = row.pop("participant_db_id")
        history = submissions_by_participant.get(participant_db_id, [])
        history_by_cycle = {item["cycle_db_id"]: item for item in history}
        recent_history = [
            history_by_cycle.get(recent_cycle["cycle_db_id"])
            for recent_cycle in recent_cycle_rows
        ]
        accepted_window = sum(item is not None for item in recent_history)
        streak = 0
        for item in reversed(recent_history):
            if item is None:
                break
            streak += 1
        total_cycles = len({item["cycle_db_id"] for item in history})
        row["accepted_cycles_window"] = accepted_window
        row["accepted_cycles_total"] = total_cycles
        row["current_streak"] = streak
        row["has_started"] = total_cycles > 0
        row["window_coverage"] = (
            accepted_window / len(recent_cycle_rows) if recent_cycle_rows else 0.0
        )
        row["recent_cycles"] = [
            {
                "cycle_id": recent_cycle["cycle_id"],
                "opens_at": recent_cycle["opens_at"],
                "closes_at": recent_cycle["closes_at"],
                "submitted": submission is not None,
                "received_at": submission["received_at"] if submission else None,
                "model_version": submission["model_version"] if submission else None,
            }
            for recent_cycle, submission in zip(recent_cycle_rows, recent_history)
        ]
        board_rows.append(row)

    board_rows.sort(
        key=lambda row: (
            not row["has_started"],
            -row["accepted_cycles_window"],
            -row["current_streak"],
            -row["accepted_cycles_total"],
            -(row["last_submission_at"].timestamp() if row["last_submission_at"] else 0),
            row["display_name"],
        )
    )
    operations_rank = 0
    for row in board_rows:
        if row["has_started"]:
            operations_rank += 1
            row["operations_rank"] = operations_rank
        else:
            row["operations_rank"] = None

    active_count = sum(bool(row["has_started"]) for row in board_rows)
    api_key_count = sum(bool(row["api_key_active"]) for row in board_rows)
    submissions_total = sum(int(row["accepted_cycles_total"]) for row in board_rows)
    steady_count = sum(
        int(row["accepted_cycles_window"]) >= max(1, len(recent_cycle_rows) - 1)
        for row in board_rows
    )
    return {
        "mode": "operations",
        "cycle": {
            "cycle_id": cycle["public_id"],
            "state": cycle["state"],
            "opens_at": cycle["opens_at"],
            "closes_at": cycle["closes_at"],
            "expected_predictions": cycle["expected_predictions"],
        },
        "operations": {
            "window_size": len(recent_cycle_rows),
            "cycles": [
                {
                    "cycle_id": item["cycle_id"],
                    "opens_at": item["opens_at"],
                    "closes_at": item["closes_at"],
                }
                for item in recent_cycle_rows
            ],
            "active_participants": active_count,
            "api_key_count": api_key_count,
            "submissions_total": submissions_total,
            "steady_participants": steady_count,
        },
        "data": board_rows,
        "timeline": [dict(point) for point in timeline],
        "count": len(board_rows),
    }
