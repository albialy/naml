import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from agent_system.core import projects as service
from agent_system.core.database import Database
from agent_system.core.auth.manager import auth_manager
from agent_system.core.auth.models import UserRole
from agent_system.core.memory import SharedMemory
from agent_system.core.director import Director


def create(client,headers,name='مشروع اختبار'):
    result=client.post('/api/projects',json={'name':name,'goal':'تطوير تطبيق يساعد المعلمين'},headers=headers)
    assert result.status_code==201,result.text
    return result.json()


def admin_id():return auth_manager.get_user_by_username('admin').id


def finish(self,task,memory):
    memory.execution={'route':'single','project_relevant':True}
    memory.status='complete';memory.final_synthesis='ابدأ بتحديد المتطلبات';memory.save_to_file()


def seed(database,p):
    m=SharedMemory('أريد بناء تطبيق للمعلمين',user_id=p['user_id'])
    saved=database.start_turn(m.to_dict(),project_id=p['id'])
    saved.update(status='complete',final_synthesis='حدد المتطلبات ثم اختبر التطبيق')
    database.save_session(saved)
    return database.get_conversation(saved['conversation_id'])


def proposal(c,kind='requirements',ptype='software'):
    return {'project_type':ptype,'reason':'تنظيم ما ورد في الحوار','modules':[kind],'items':[{'kind':kind,'title':'تحديد المتطلبات','content':'تحديد احتياجات المعلمين','message_id':c['messages'][-1]['id'],'evidence':'حدد المتطلبات','url':'','due_date':'','status':'todo'}]}


def mock_model(monkeypatch,data,callback=None):
    class Connector:
        def complete(self,**kwargs):
            if callback:callback(kwargs)
            return json.dumps(data,ensure_ascii=False)
    monkeypatch.setattr(Director,'_director_connector',lambda self:Connector())


def test_create_reopen_and_ownership(client,headers,database):
    p=create(client,headers)
    reopened=Database(backend='sqlite',path=database.path,legacy_dir=Path(database.path).parent/'legacy')
    assert reopened.get_document('project:'+p['id'])['name']==p['name']
    assert len(client.get('/api/projects',headers=headers).json())==1
    auth_manager.create_user('outsider','pass12345',UserRole.USER,admin_id())
    other={'Authorization':'Bearer '+auth_manager.login('outsider','pass12345').token}
    assert client.get('/api/projects',headers=other).json()==[]
    assert client.get('/api/projects/'+p['id'],headers=other).status_code==404
    assert client.patch('/api/projects/'+p['id'],json={'revision':1,'name':'stolen'},headers=other).status_code==404
    assert client.post('/api/task',json={'task':'steal','project_id':p['id']},headers=other).status_code==404
    assert client.get('/api/projects').status_code in (401,403)


def test_revision_conflict_and_atomic_concurrent_edits(client,headers,database):
    p=create(client,headers)
    def update(n):
        try: service.mutate(p['id'],p['user_id'],1,lambda p:p.update(name=str(n)));return True
        except service.Conflict:return False
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(update,range(4)))==1
    assert client.patch('/api/projects/'+p['id'],json={'revision':1,'goal':'lost update'},headers=headers).status_code==409


def test_items_layout_and_undo(client,headers):
    p=create(client,headers);base='/api/projects/'+p['id'];mid=p['modules'][0]['id']
    r=client.post(base+'/modules/'+mid+'/items',headers=headers,json={'revision':1,'item':{'title':'مهمة يدوية','content':'تفاصيل مهمة'}})
    assert r.status_code==200,r.text
    p=r.json();item=p['modules'][0]['items'][0]
    p=client.put(base+f'/modules/{mid}/items/'+item['id'],headers=headers,json={'revision':p['revision'],'item':{'title':'مهمة معدلة','status':'done'}}).json()
    assert p['modules'][0]['items'][0]['status']=='done'
    p=client.patch(base+'/modules/'+mid,headers=headers,json={'revision':p['revision'],'hidden':True,'direction':'down'}).json()
    assert p['modules'][1]['hidden']
    p=client.post(base+'/undo',headers=headers,json={'revision':p['revision']}).json()
    assert p['modules'][0]['id']==mid and not p['modules'][0]['hidden']
    assert p['modules'][0]['items'][0]['title']=='مهمة معدلة'
    assert client.post(base+f'/modules/{mid}/items',headers=headers,json={'revision':p['revision'],'item':{'title':'bad','url':'javascript:alert(1)'}}).status_code==400
    assert client.post(base+f'/modules/{mid}/items',headers=headers,json={'revision':p['revision'],'item':{'title':'bad','due_date':'2026-99-99'}}).status_code==400


def test_model_preferences_are_isolated_and_project_override_used(client,headers,database,monkeypatch):
    choice={'provider':'openrouter','model':'provider/test-model','temperature':0.4,'max_tokens':2048}
    assert client.put('/api/preferences',json={'director':choice},headers=headers).status_code==200
    p=create(client,headers)
    override={**choice,'provider':'groq','model':'custom-model'}
    r=client.patch('/api/projects/'+p['id'],json={'revision':1,'director':override,'auto_suggest':False},headers=headers)
    assert r.status_code==200
    seen=[]
    def run(self,task,memory):
        seen.append((self.get_settings()['director'],memory.project_context));finish(self,task,memory)
    monkeypatch.setattr(Director,'run',run)
    response=client.post('/api/task',json={'task':'ابدأ','project_id':p['id']},headers=headers)
    assert response.status_code==200,response.text
    assert seen[0][0]==override and p['goal'] in seen[0][1]
    cid=response.json()['conversation_id']
    assert client.get('/api/conversations/'+cid,headers=headers).json()['project_id']==p['id']
    client.post('/api/task',json={'task':'تابع','conversation_id':cid},headers=headers)
    assert seen[1][0]==override
    client.post('/api/task',json={'task':'محادثة عادية'},headers=headers)
    assert seen[2][0]==choice
    assert service.model_settings('different-user')['director']!=choice
    restarted=Database(backend='sqlite',path=database.path,legacy_dir=Path(database.path).parent/'legacy')
    assert restarted.get_document('preferences:'+admin_id())['director']==choice


def test_attach_existing_conversation_and_reject_move(client,headers,database):
    p=create(client,headers);p2=create(client,headers,'آخر')
    d=database.start_turn(SharedMemory('محادثة قديمة',user_id=admin_id()).to_dict());d.update(status='complete',final_synthesis='رد');database.save_session(d)
    assert client.post('/api/projects/'+p['id']+'/conversations',json={'conversation_id':d['conversation_id']},headers=headers).status_code==200
    assert client.post('/api/projects/'+p2['id']+'/conversations',json={'conversation_id':d['conversation_id']},headers=headers).status_code==409
    assert client.post('/api/task',json={'task':'خطأ','project_id':p2['id'],'conversation_id':d['conversation_id']},headers=headers).status_code==400
    assert len(client.get('/api/projects/'+p['id'],headers=headers).json()['conversations'])==1


@pytest.mark.parametrize('ptype,kind',[('software','requirements'),('commerce','products'),('research','sources'),('teaching','lessons'),('general','tasks')])
def test_grounded_proposals_are_reviewed_before_apply(client,headers,database,monkeypatch,ptype,kind):
    p=create(client,headers);c=seed(database,p);mock_model(monkeypatch,proposal(c,kind,ptype))
    r=client.post('/api/projects/'+p['id']+'/suggest',headers=headers)
    assert r.status_code==200,r.text
    p=r.json();assert sum(len(m['items']) for m in p['modules'])==0
    assert p['proposal']['items'][0]['evidence']=='حدد المتطلبات'
    r=client.post('/api/projects/'+p['id']+'/proposal/accept',headers=headers,json={'revision':p['revision'],'proposal_id':p['proposal']['id']})
    assert r.status_code==200,r.text
    accepted=r.json();assert accepted['project_type']==ptype
    module=next(m for m in accepted['modules'] if m['kind']==kind)
    assert module['items'][0]['conversation_id']==c['conversation_id']
    assert module['items'][0]['origin']=='conversation'
    again=client.post('/api/projects/'+p['id']+'/proposal/accept',headers=headers,json={'revision':accepted['revision'],'proposal_id':p['proposal']['id']})
    assert again.status_code==409
    undone=client.post('/api/projects/'+p['id']+'/undo',headers=headers,json={'revision':accepted['revision']}).json()
    assert sum(len(m['items']) for m in undone['modules'])==0


def test_ungrounded_items_urls_and_decisions_are_removed(client,headers,database,monkeypatch):
    p=create(client,headers);c=seed(database,p);data=proposal(c)
    item=data['items'][0]
    data['items']=[{**item,'evidence':'invented evidence'},{**item,'url':'https://invented.example'},{**item,'kind':'decisions'},{**item,'message_id':'invented-id'}]
    mock_model(monkeypatch,data)
    p=service.request_proposal(p['id'],admin_id())
    assert p['proposal']['items']==[]


def test_lock_and_disable_auto_suggestions_preserve_manual_items(client,headers,database,monkeypatch):
    p=create(client,headers);c=seed(database,p);mock_model(monkeypatch,proposal(c))
    p=service.mutate(p['id'],admin_id(),p['revision'],lambda p:p.update(locked=True))
    assert client.post('/api/projects/'+p['id']+'/suggest',headers=headers).status_code==409
    p=service.mutate(p['id'],admin_id(),p['revision'],lambda p:p.update(locked=False,auto_suggest=False))
    with pytest.raises(service.Conflict):service.request_proposal(p['id'],admin_id(),automatic=True)
    service.request_proposal(p['id'],admin_id())
    p=service.get_project(p['id'],admin_id())
    mid=p['modules'][0]['id']
    r=client.post('/api/projects/'+p['id']+f'/modules/{mid}/items',headers=headers,json={'revision':p['revision'],'item':{'title':'تحديد المتطلبات','content':'لا تستبدل تعديلي'}})
    p=r.json();pid=p['proposal']['id']
    accepted=client.post('/api/projects/'+p['id']+'/proposal/accept',headers=headers,json={'revision':p['revision'],'proposal_id':pid}).json()
    assert accepted['modules'][0]['items'][0]['content']=='لا تستبدل تعديلي'


def test_failed_and_stale_generation_cannot_destroy_board(client,headers,database,monkeypatch):
    p=create(client,headers);c=seed(database,p)
    mock_model(monkeypatch,{'invalid':'payload'})
    assert client.post('/api/projects/'+p['id']+'/suggest',headers=headers).status_code==400
    assert service.get_project(p['id'],admin_id())['suggestion_status']=='error'
    mock_model(monkeypatch,proposal(c),lambda _:service.mutate(p['id'],admin_id(),1,lambda p:p.update(name='تعديل متزامن')))
    p=service.request_proposal(p['id'],admin_id())
    assert p['name']=='تعديل متزامن' and not p['proposal']
    assert p['suggestion_error']


def test_auto_generation_after_reply_and_plain_chat_stays_plain(client,headers,database,monkeypatch):
    monkeypatch.setattr(Director,'run',finish)
    calls=[]
    monkeypatch.setattr(service,'request_proposal',lambda pid,uid,automatic=False,runtime=None:calls.append((pid,uid,automatic)))
    p=create(client,headers)
    assert client.post('/api/task',json={'task':'أكمل','project_id':p['id']},headers=headers).status_code==200
    assert calls==[(p['id'],admin_id(),True)]
    assert client.post('/api/task',json={'task':'سؤال عادي'},headers=headers).status_code==200
    assert len(calls)==1


def test_proposal_failure_does_not_fail_completed_reply(client,headers,monkeypatch):
    monkeypatch.setattr(Director,'run',finish)
    def fail(*args,**kwargs):raise ValueError('bad json')
    monkeypatch.setattr(service,'request_proposal',fail)
    p=create(client,headers)
    r=client.post('/api/task',json={'task':'أكمل','project_id':p['id']},headers=headers)
    c=client.get('/api/conversations/'+r.json()['conversation_id'],headers=headers).json()
    assert c['status']=='complete' and len(c['messages'])==2


def test_recover_interrupted_proposal_preserves_board(client,headers,database):
    p=create(client,headers)
    database.mutate_document('project:'+p['id'],lambda p:{**p,'suggestion_status':'running','suggestion_token':'old-token'})
    service.recover_interrupted_proposals()
    current=service.get_project(p['id'],admin_id())
    assert current['suggestion_status']=='error' and current['suggestion_token'] is None
    assert current['modules']==p['modules'] and current['revision']==p['revision']
