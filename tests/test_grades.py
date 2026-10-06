import asyncio
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from app.grades import own_grade, scaled_grade
from app.main import app, portal_participant


def test_scale_endpoints_and_close_scores():
    assert scaled_grade(15.64,15.64,81.40)==Decimal('2.00')
    assert scaled_grade(81.40,15.64,81.40)==Decimal('5.00')
    assert scaled_grade(81.36,15.64,81.40)==Decimal('5.00')
    assert scaled_grade(30.90,15.64,81.40)==Decimal('2.70')


def test_personal_grade_uses_authenticated_identity_and_transaction_scoped_filter():
    class Context:
        async def __aenter__(self): return connection
        async def __aexit__(self,*args): pass
    class Connection:
        def transaction(self,**kwargs):
            assert kwargs['readonly']; return Context()
        async def execute(self,query,*args):
            assert 'set_config' in query and ',true)' in query
            assert args==('12',)
        async def fetchrow(self,query,*args):
            assert 'g.participant_id=$1' in query and 'p.cohort_code=$2' in query
            assert args==(12,'COHORT')
            return {'grade':Decimal('4.21'),'version':'v1','feedback':'{"reasons":["own feedback"]}','published_at':None}
    class Pool:
        def acquire(self): return Context()
    connection=Connection()
    identity=SimpleNamespace(participant_id=12,cohort_code='COHORT',display_name='Own student')
    result=asyncio.run(own_grade(Pool(),identity))
    assert result['grade']==4.21 and result['student_name']=='Own student'
    assert 'data' not in result


def test_grade_endpoint_requires_session():
    with TestClient(app) as client:
        response=client.get('/v1/portal/grade')
    assert response.status_code==401
