import json
from pathlib import Path
import pytest
from agent_system.core import workflow, projects
from agent_system.core.database import Database
from agent_system.core.director import Director
from agent_system.core.memory import SharedMemory
from agent_system.core.settings_manager import settings_manager
from agent_system.core.connectors.errors import failure
from agent_system.core.connectors.openrouter_connector import OpenRouterConnector

class Board:
    def __init__(self,client,headers):
        self.c,self.h=client,headers
        self.p=client.post('/api/projects',headers=headers,json={'name':'المدرسة','goal':'زيادة التسجيل'}).json()
        self.url='/api/projects/'+self.p['id']
    def call(self,path,data=None,method='post',status=200):
        r=self.c.request(method,self.url+path,headers=self.h,json={'revision':self.p['revision'],**(data or {})})
        assert r.status_code==status,r.text
        if status==200:self.p=r.json()
        return r
    def module(self,kind):
        m=next((m for m in self.p['modules'] if m['kind']==kind),None)
        if not m:
            self.call('/modules',{'kind':kind});m=next(m for m in self.p['modules'] if m['kind']==kind)
        return m['id']
    def add(self,kind,title,**kwargs):
        mid=self.module(kind);self.call('/modules/'+mid+'/items',{'item':{'title':title,**kwargs}})
        return next(m for m in self.p['modules'] if m['id']==mid)['items'][-1]
    def edit(self,kind,item,**kwargs):
        data={k:v for k,v in item.items() if k in projects.ItemInput.model_fields};data.update(kwargs)
        return '/modules/'+self.module(kind)+'/items/'+item['id'],{'item':data}


def test_school_decision_task_result_review_and_restart(client,headers,database):
    b=Board(client,headers)
    b.call('',{'brief':{'success_criteria':'40 استفسارًا','constraints':'ميزانية محدودة','stage':'decision'}},'patch')
    d=b.add('decisions','تنظيم يوم مفتوح')
    b.call('/decisions/'+d['id']+'/task',{'title':'تنظيم اللقاء'},status=400)
    b.call('/decisions/'+d['id']+'/state',{'state':'approved'})
    b.call('/decisions/'+d['id']+'/state',{'state':'approved'},status=409)
    b.call('/decisions/'+d['id']+'/task',{'title':'تنظيم اللقاء','owner':'أحمد','due_date':'2026-11-01','expected_outcome':'40 استفسارًا'})
    t=workflow.items(b.p,'tasks')[0]
    b.call(*b.edit('tasks',t,status='done'),method='put')
    assert len(b.p['overview']['missing_results'])==1
    b.add('results','استفسارات اللقاء',linked_task_id=t['id'],target=40,actual=25,unit='استفسار')
    b.call('/review')
    assert b.p['reviews'][-1]['measurements'][0]['verdict']=='not_met'
    assert b.p['brief']['stage']=='review'
    context=workflow.labeled_context(b.p)
    assert '[decisions / approved]' in context and 'owner=أحمد' in context
    reopened=Database(backend='sqlite',path=database.path,legacy_dir=Path(database.path).parent/'legacy')
    assert reopened.get_document('project:'+b.p['id'])['reviews']==b.p['reviews']


def test_dependencies_cycles_and_delete_protection(client,headers):
    b=Board(client,headers);a=b.add('tasks','الأولى');z=b.add('tasks','الثانية',blocked_by=[a['id']])
    assert len(b.p['overview']['blocked'])==1
    b.call(*b.edit('tasks',z,status='done'),method='put',status=400)
    b.call(*b.edit('tasks',a,blocked_by=[z['id']]),method='put',status=400)
    b.call('/modules/'+b.module('tasks')+'/items/'+a['id'],method='delete',status=400)
    b.call(*b.edit('tasks',a,status='done'),method='put')
    b.call(*b.edit('tasks',z,status='done'),method='put')
    assert b.p['overview']['tasks_done']==2


def test_results_require_local_task_and_zero_is_data(client,headers):
    a=Board(client,headers);b=Board(client,headers);task=a.add('tasks','عمل')
    mid=b.module('results')
    b.call('/modules/'+mid+'/items',{'item':{'title':'نتيجة','linked_task_id':task['id']}},status=400)
    b.call('/modules/'+mid+'/items',{'item':{'title':'نتيجة'}},status=400)
    t=b.add('tasks','محلي')
    b.add('results','غياب القياس',linked_task_id=t['id'],target=0,unit='خطأ',direction='decrease')
    b.add('results','صفر فعلي',linked_task_id=t['id'],actual=0,target=0,unit='خطأ',direction='decrease')
    assert [m['verdict'] for m in b.p['overview']['measurements']]==['needs_data','met']


def test_decisions_cannot_be_auto_approved_or_edited_after_approval(client,headers):
    b=Board(client,headers);mid=b.module('decisions')
    b.call('/modules/'+mid+'/items',{'item':{'title':'قرار','decision_state':'approved'}},status=400)
    d=b.add('decisions','اقتراح');b.call('/decisions/'+d['id']+'/state',{'state':'approved'})
    d=workflow.items(b.p,'decisions')[0]
    b.call(*b.edit('decisions',d,title='تغيير'),method='put',status=400)
    assert workflow.items(b.p,'decisions')[0]['title']=='اقتراح'


@pytest.mark.parametrize('route',['direct','clarify'])
def test_simple_routes_do_not_spawn_workers(database,monkeypatch,route):
    d=Director();m=SharedMemory('مرحبا')
    monkeypatch.setattr(d,'choose_strategy',lambda *a:{'route':route,'reason':'بسيط','questions':['ما الهدف؟'],'answer':'مرحبا بك'})
    monkeypatch.setattr(d,'_build_workers',lambda *a:pytest.fail('unnecessary workers'))
    d.run(m.task_original,m)
    assert m.status=='complete' and m.execution['route']==route and not m.findings


def test_all_worker_failures_never_become_success(database,monkeypatch):
    d=Director();m=SharedMemory('خطة')
    monkeypatch.setattr(d,'choose_strategy',lambda *a:{'route':'team'})
    monkeypatch.setattr(d,'analyze_task',lambda *a:{'agents':[{'name':'باحث'}]})
    monkeypatch.setattr(d,'_build_workers',lambda *a:[])
    monkeypatch.setattr(d,'_execute_pattern',lambda *a:m.add_finding('باحث','الجمهور','Error: missing model',0,status='failed'))
    monkeypatch.setattr(d,'_director_connector',lambda:pytest.fail('must not synthesize errors'))
    d.run(m.task_original,m)
    assert m.status=='failed' and 'لم يتم إنتاج تحليل' in m.final_synthesis


def test_partial_evidence_excludes_error_body(database,monkeypatch):
    d=Director();m=SharedMemory('خطة');seen=[]
    m.add_finding('a','الميزانية','known evidence',80)
    m.add_finding('b','الجمهور','Error: NEVER_INCLUDE_IN_EVIDENCE',0,status='failed')
    class Model:
        def complete(self,**kwargs):seen.append(kwargs['user_message']);return 'خطة جزئية'
    monkeypatch.setattr(d,'_director_connector',lambda:Model())
    d._synthesize(m)
    assert 'known evidence' in seen[0] and 'NEVER_INCLUDE_IN_EVIDENCE' not in seen[0]
    assert 'الجمهور' in seen[0] and m.warnings


def test_researcher_and_critic_respect_provider(database):
    config={'provider':'openrouter','model':'custom/research','temperature':0.4,'max_tokens':2345}
    settings=settings_manager.get_settings();settings['director']=config;settings['workers']['fast']=config
    d=Director(settings_override=settings);m=SharedMemory('بحث')
    worker=d._build_workers({'agents':[{'name':'r','needs_web':True}]},m)[0]
    assert isinstance(worker.connector,OpenRouterConnector) and worker.connector.model_name=='custom/research'
    assert worker.runtime_config['max_tokens']==2345
    assert isinstance(d._critic_connector_live(),OpenRouterConnector)


def test_model_error_categories_are_not_inferred_from_message_text():
    assert 'غير متاح' in failure('Groq','model',404)
    assert failure('Groq','model',400)!=failure('Groq','model',404)
    assert failure('Groq','model',429)!=failure('Groq','model',401)


def test_model_repair_is_explicit_and_preserves_custom_models(client,headers):
    old={'provider':'groq','model':'llama-3.3-70b-versatile','temperature':0.3,'max_tokens':2048}
    settings_manager.update_worker('fast',old,'test')
    settings_manager.update_director({**old,'provider':'openrouter','model':'custom/model'},'test')
    preview=client.get('/api/settings/retired-models',headers=headers).json()
    assert any(c['role']=='fast' for c in preview)
    assert settings_manager.get_settings()['workers']['fast']['model']==old['model']
    assert client.post('/api/settings/repair-models',headers=headers).status_code==200
    current=settings_manager.get_settings()
    assert current['workers']['fast']['model']=='openai/gpt-oss-120b'
    assert current['director']['model']=='custom/model'


def test_model_probe_failure_and_catalog_mock(client,headers,monkeypatch):
    from agent_system.core import model_catalog
    monkeypatch.setattr(model_catalog,'catalog',lambda p:['custom/model'])
    assert client.get('/api/settings/catalog/openrouter',headers=headers).json()['models']==['custom/model']
    class Model:
        def complete(self,*args):return 'Error: نموذج غير متاح'
    monkeypatch.setattr(Director,'_connector_for',lambda *a:Model())
    r=client.post('/api/settings/test-model',headers=headers,json={'provider':'openrouter','model':'custom/model','temperature':0.2,'max_tokens':2048})
    assert r.status_code==400 and 'غير متاح' in r.text


def test_parallel_workers_share_only_initial_context_and_keep_all_findings(database):
    from threading import Barrier
    from agent_system.core.orchestrator import Orchestrator
    m=SharedMemory('parallel');barrier=Barrier(3);seen=[]
    class Worker:
        def __init__(self,name):self.name=name;self.sub_question=name
        def execute(self):
            barrier.wait(timeout=3)
            m.add_finding(self.name,self.name,'answer',80)
            seen.append(list(self.context_snapshot))
    workers=[Worker(str(i)) for i in range(3)]
    Orchestrator().run_parallel(workers,m)
    assert seen==[[],[],[]] and len(m.findings)==3
    assert len(database.get_session(m.session_id)['findings'])==3


def test_critic_revises_answer_using_only_successful_evidence(database,monkeypatch):
    d=Director();m=SharedMemory('خطة');m.final_synthesis='first answer'
    m.add_finding('a','question','actual evidence',80);m.add_finding('b','failed','Error: secret failure',0,status='failed')
    seen=[]
    class Critic:
        model_name='configured'
        def complete(self,**kwargs):return json.dumps({'severity':7,'flaws':['missing constraint'],'fabrication_detected':True})
    class Model:
        def complete(self,*args):seen.append(args[1]);return 'revised answer'
    monkeypatch.setattr(d,'_critic_connector_live',lambda:Critic());monkeypatch.setattr(d,'_director_connector',lambda:Model())
    d._critic(m)
    assert m.final_synthesis=='revised answer' and m.execution['revision_applied']
    assert 'actual evidence' in seen[0] and 'secret failure' not in seen[0]
