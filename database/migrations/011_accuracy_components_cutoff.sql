begin;

-- The API role sees only score components from resolved official cycles in Corte 1.
-- Aggregation and model-version lookup happen after the cohort is filtered.
create view competition.accuracy_components_cutoff as
select sc.scenario_id, sc.participant_id, sc.station_id, sc.cycle_id,
       sc.absolute_error, sc.actual_value, sc.was_missing,
       c.public_id as public_cycle_id, c.opens_at, c.closes_at
from competition.score_components sc
join competition.forecast_cycles c
  on c.id=sc.cycle_id and c.scenario_id=sc.scenario_id
join competition.public_scenarios scenario on scenario.id=c.scenario_id
where scenario.code='official-20260921'
  and c.state='resolved'
  and c.opens_at >= timestamptz '2026-09-25 05:00:00+00';

grant select on competition.accuracy_components_cutoff to academy_api;

insert into ops.schema_migrations (version)
values ('011_accuracy_components_cutoff') on conflict do nothing;

commit;
