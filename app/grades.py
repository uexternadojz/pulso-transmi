"""Private immutable grading evidence; identity always comes from portal authentication."""
from decimal import Decimal, ROUND_HALF_UP


def scaled_grade(accuracy, low, high):
    a, lo, hi = map(lambda value: Decimal(str(value)), (accuracy, low, high))
    if hi <= lo:
        raise ValueError('Grading requires a nonzero performance range')
    return min(Decimal('5'), max(Decimal('2'), Decimal('2') + Decimal('3') * (a-lo)/(hi-lo))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


async def own_grade(pool, identity):
    async with pool.acquire() as connection, connection.transaction(readonly=True):
        await connection.execute("select set_config('app.grade_participant_id',$1,true)", str(identity.participant_id))
        row = await connection.fetchrow('''
          select g.grade,g.version,g.feedback,g.published_at
          from competition.student_grades g
          join competition.participants p on p.id=g.participant_id
          where g.participant_id=$1 and p.cohort_code=$2 and p.kind='student'
          order by g.published_at desc limit 1
        ''', identity.participant_id, identity.cohort_code)
    if row is None:
        return {'status':'unavailable','message':'No hay una calificación individual publicada para esta cuenta.'}
    import json
    feedback = json.loads(row['feedback']) if isinstance(row['feedback'], str) else row['feedback']
    return {'status':'pending' if row['grade'] is None else 'published',
            'grade':float(row['grade']) if row['grade'] is not None else None,
            'version':row['version'],'published_at':row['published_at'],
            'student_name':identity.display_name,'feedback':feedback}
