begin;
create table sim.drift_revisions (
 id bigint generated always as identity primary key,
 scenario_id bigint not null references sim.scenarios(id),
 revision integer not null check(revision>0),
 parent_sha256 text,
 bundle_sha256 text not null unique check(length(bundle_sha256)=64),
 level integer not null check(level between 0 and 3),
 effective_from timestamptz not null,
 ends_at timestamptz not null,
 generator_version text not null,
 reason text not null,
 calibration jsonb not null,
 bundle jsonb not null,
 activated_at timestamptz not null default now(),
 unique(scenario_id,revision),
 check(ends_at>effective_from)
);
create function sim.protect_drift_revision() returns trigger language plpgsql as $$
begin raise exception 'Drift revisions are immutable'; end;
$$;
create trigger immutable_drift_revision before update or delete on sim.drift_revisions
for each row execute function sim.protect_drift_revision();
create table competition.drift_windows (
 scenario_id bigint primary key references sim.scenarios(id),
 starts_at_virtual timestamptz not null,
 started_at timestamptz not null default now(),
 ends_at_wall timestamptz not null,
 current_revision_id bigint not null references sim.drift_revisions(id),
 check(ends_at_wall>started_at)
);
alter table competition.forecast_cycles add column drift_revision_id bigint references sim.drift_revisions(id);
create index forecast_cycles_drift_idx on competition.forecast_cycles(drift_revision_id);
create view competition.drift_revision_status as
select id,scenario_id,revision,bundle_sha256,level,effective_from,ends_at,
 generator_version,reason,activated_at from sim.drift_revisions;
revoke all on sim.drift_revisions from public,academy_api;
grant select on sim.drift_revisions to academy_scheduler;
grant select on competition.drift_windows,competition.drift_revision_status to academy_api,academy_scheduler;
create function sim.protect_committed_truth() returns trigger language plpgsql as $$
begin
 if exists(select 1 from competition.observations where scenario_id=old.scenario_id
           and station_id=old.station_id and observed_at=old.observed_at)
    or exists(select 1 from competition.forecast_cycles where scenario_id=old.scenario_id
              and target_end_at>=old.observed_at) then
   raise exception 'Published or committed truth is immutable';
 end if;
 return old;
end;
$$;
create trigger immutable_committed_truth before update or delete on sim.generated_truth
for each row execute function sim.protect_committed_truth();
insert into ops.schema_migrations(version) values('010_controlled_drift');

create view competition.drift_health as
select h.status as scheduler_status,h.heartbeat_at,
 (select count(*) from ops.job_runs where status='failed' and started_at>now()-interval '24 hours') as errors_24h,
 (select max(completed_at) from ops.job_runs where status='succeeded') as last_success_at
from ops.scheduler_heartbeats h;
grant select on competition.drift_health to academy_api;
commit;
