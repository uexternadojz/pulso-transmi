begin;
create or replace view competition.accuracy_cycle_station as
select sc.scenario_id, sc.participant_id, sc.station_id, c.public_id as cycle_id,
       c.closes_at, sum(sc.absolute_error) as error, sum(sc.actual_value) as actual,
       count(*) as targets, count(*) filter (where not sc.was_missing) as delivered,
       array_agg(distinct sub.model_version) as model_versions
from competition.score_components sc
join competition.forecast_cycles c on c.id=sc.cycle_id
left join competition.submissions sub on sub.id=sc.submission_id
where c.state='resolved'
group by sc.scenario_id,sc.participant_id,sc.station_id,c.public_id,c.closes_at;
grant select on competition.accuracy_cycle_station to academy_api;
insert into ops.schema_migrations (version) values ('008_accuracy_chart') on conflict do nothing;
commit;
