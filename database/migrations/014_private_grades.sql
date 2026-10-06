begin;
create table competition.student_grades (
 participant_id bigint not null references competition.participants(id),
 version text not null,
 source_sha256 text not null check(length(source_sha256)=64),
 grade numeric(3,2) check(grade between 0 and 5),
 feedback jsonb not null,
 published_at timestamptz not null default now(),
 primary key(participant_id,version)
);
revoke all on competition.student_grades from public,academy_scheduler;
grant select on competition.student_grades to academy_api;
alter table competition.student_grades enable row level security;
create policy own_grade on competition.student_grades for select to academy_api
 using(participant_id = nullif(current_setting('app.grade_participant_id',true),'')::bigint);
insert into ops.schema_migrations(version) values('014_private_grades');
commit;
