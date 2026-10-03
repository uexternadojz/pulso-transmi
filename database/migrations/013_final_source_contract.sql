begin;
create table competition.source_contracts (
 revision_id bigint primary key references sim.drift_revisions(id),
 scenario_id bigint not null references sim.scenarios(id),
 effective_from timestamptz not null,
 schema_version smallint not null check(schema_version=2),
 missing_permyriad integer not null check(missing_permyriad between 0 and 1000),
 created_at timestamptz not null default now(),
 unique(scenario_id,effective_from)
);
create trigger immutable_source_contract before update or delete on competition.source_contracts
for each row execute function sim.protect_drift_revision();
alter table competition.observations
 add column source_schema_version smallint not null default 1 check(source_schema_version in (1,2)),
 add column source_quality text not null default 'observed' check(source_quality in ('observed','missing'));
grant select on competition.source_contracts to academy_scheduler;
grant select(revision_id,scenario_id,effective_from,schema_version) on competition.source_contracts to academy_api;
grant select(source_schema_version,source_quality) on competition.observations to academy_api;
insert into ops.schema_migrations(version) values('013_final_source_contract');
commit;
