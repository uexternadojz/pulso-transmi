"""Instructor-only publication of an explicitly reviewed private grade bundle."""
import argparse
import asyncio
import json
from pathlib import Path
from decimal import Decimal

import asyncpg
from app.settings import get_settings


async def publish(path):
    bundle = json.loads(Path(path).read_text())
    rows = bundle['students']
    assert len(rows)==32 and len({r['participant_id'] for r in rows})==32
    assert len(bundle['source_sha256'])==64
    pool = await asyncpg.create_pool(get_settings().database_url,min_size=1,max_size=1)
    try:
        async with pool.acquire() as c, c.transaction():
            assert await c.fetchval("select count(*) from competition.student_grades where version=$1",bundle['version'])==0, 'Version already published; use a new version'
            for row in rows:
                participant = await c.fetchrow("select id,kind,cohort_code from competition.participants where public_id=$1",row['participant_id'])
                assert participant and participant['kind']=='student' and participant['cohort_code']==bundle['cohort_code']
                grade = row['grade']
                assert grade is None or 0<=grade<=5
                await c.execute('''insert into competition.student_grades(participant_id,version,source_sha256,grade,feedback)
                  values($1,$2,$3,$4,$5::jsonb)''',participant['id'],bundle['version'],bundle['source_sha256'],Decimal(str(grade)) if grade is not None else None,json.dumps(row['feedback'],ensure_ascii=False))
            await c.execute("""insert into ops.audit_events(actor_type,actor_id,action,entity_type,entity_id,metadata)
              values('instructor','Julian Zuluaga','publish_private_grades','grade_version',$1,$2::jsonb)""",bundle['version'],json.dumps({'source_sha256':bundle['source_sha256'],'students':len(rows),'policy':bundle['policy']}))
        print(json.dumps({'published_version':bundle['version'],'students':len(rows),'numeric_grades':sum(r['grade'] is not None for r in rows)}))
    finally:
        await pool.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--file',required=True)
    asyncio.run(publish(parser.parse_args().file))
