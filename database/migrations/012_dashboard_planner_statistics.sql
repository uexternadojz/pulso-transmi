begin;

-- Small scenario/roster tables otherwise need 50 modifications before autoanalyze.
-- Stale estimates can turn the chart into hundreds of thousands of nested lookups.
alter table sim.scenarios set (
  autovacuum_analyze_threshold = 1, autovacuum_analyze_scale_factor = 0
);
alter table competition.participants set (
  autovacuum_analyze_threshold = 5, autovacuum_analyze_scale_factor = 0.05
);
alter table competition.participant_scenarios set (
  autovacuum_analyze_threshold = 5, autovacuum_analyze_scale_factor = 0.05
);
alter table competition.forecast_cycles set (
  autovacuum_analyze_threshold = 10, autovacuum_analyze_scale_factor = 0.02
);
alter table competition.score_components set (
  autovacuum_analyze_threshold = 1000, autovacuum_analyze_scale_factor = 0.02
);

analyze sim.scenarios;
analyze competition.participants;
analyze competition.participant_scenarios;
analyze competition.forecast_cycles;
analyze competition.score_components;

insert into ops.schema_migrations(version)
values ('012_dashboard_planner_statistics') on conflict do nothing;
commit;
