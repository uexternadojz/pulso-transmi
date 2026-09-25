begin;

create view competition.accuracy_cycle_station_cutoff as
select sc.scenario_id, sc.participant_id, sc.station_id,
       c.public_id as cycle_id, c.opens_at, c.closes_at,
       sum(sc.absolute_error) as error, sum(sc.actual_value) as actual,
       count(*) as targets,
       count(*) filter (where not sc.was_missing) as delivered,
       array_agg(distinct sub.model_version) as model_versions
from competition.forecast_cycles c
join sim.scenarios scenario on scenario.id=c.scenario_id
join competition.score_components sc
  on sc.cycle_id=c.id and sc.scenario_id=c.scenario_id
left join competition.submissions sub on sub.id=sc.submission_id
where c.state='resolved'
  and c.opens_at >= timestamptz '2026-09-25 05:00:00+00'
  and scenario.code='official-20260921'
group by sc.scenario_id,sc.participant_id,sc.station_id,c.id;

grant select on competition.accuracy_cycle_station_cutoff to academy_api;
insert into ops.schema_migrations (version)
values ('009_accuracy_chart_cutoff_view') on conflict do nothing;

commit;
