import uuid
from datetime import datetime, timezone
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from agent_system.core.auth.middleware import get_current_user
from agent_system.core.auth.models import User
from agent_system.core.database import get_database, ConversationBusy
from agent_system.core import projects as service
from agent_system.core import workflow
from agent_system.core.settings_manager import AVAILABLE_MODELS

router=APIRouter(prefix='/api')

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

class Create(Strict):
    name:str=Field(min_length=1,max_length=100)
    goal:str=Field(default='',max_length=3000)

class Revision(Strict):
    revision:int=Field(ge=1)

class Update(Revision):
    name:Optional[str]=Field(default=None,min_length=1,max_length=100)
    goal:Optional[str]=Field(default=None,max_length=3000)
    locked:Optional[bool]=None
    auto_suggest:Optional[bool]=None
    director:Optional[service.ModelChoice]=None
    brief:Optional[workflow.Brief]=None

class Preferences(Strict):
    director:Optional[service.ModelChoice]=None

class LinkRequest(Strict):
    conversation_id:str=Field(max_length=100)

class ModuleChange(Revision):
    kind:Optional[service.KINDS]=None
    hidden:Optional[bool]=None
    direction:Optional[Literal['up','down']]=None

class ItemChange(Revision):
    item:service.ItemInput

class ProposalAction(Revision):
    proposal_id:str=Field(max_length=100)


def run(action):
    try:return action()
    except KeyError as e:raise HTTPException(404,detail=str(e))
    except (service.Conflict,ConversationBusy) as e:raise HTTPException(409,detail=str(e))
    except ValueError as e:raise HTTPException(400,detail=str(e))


def public(p):
    return {k:v for k,v in p.items() if k not in ('undo','suggestion_token')} | {'can_undo':bool(p.get('undo')), 'overview':workflow.overview(p), 'brief':p.get('brief',workflow.Brief().model_dump())}

@router.get('/preferences')
def preferences(user:User=Depends(get_current_user)):
    return {'director':get_database().get_document('preferences:'+user.id,{}).get('director'), 'effective_director':service.model_settings(user.id)['director'],'available_models':AVAILABLE_MODELS}

@router.put('/preferences')
def update_preferences(body:Preferences,user:User=Depends(get_current_user)):
    get_database().set_document('preferences:'+user.id,body.model_dump())
    return preferences(user)

@router.get('/projects')
def list_projects(user:User=Depends(get_current_user)):
    return [public(p) for p in service.list_projects(user.id)]

@router.post('/projects',status_code=201)
def create_project(body:Create,user:User=Depends(get_current_user)):
    return public(service.create_project(user.id,body.name,body.goal))

@router.get('/projects/{pid}')
def project(pid:str,user:User=Depends(get_current_user)):
    p=run(lambda:service.get_project(pid,user.id))
    return public(p) | {'conversations':[c for c in get_database().list_conversations(user.id) if c.get('project_id')==pid]}

@router.patch('/projects/{pid}')
def update_project(pid:str,body:Update,user:User=Depends(get_current_user)):
    updates=body.model_dump(exclude_unset=True,exclude={'revision'})
    if any(value is None and key!='director' for key,value in updates.items()):raise HTTPException(400,detail='قيمة غير صالحة')
    return public(run(lambda:service.mutate(pid,user.id,body.revision,lambda p:p.update(updates))))

@router.post('/projects/{pid}/conversations')
def attach(pid:str,body:LinkRequest,user:User=Depends(get_current_user)):
    run(lambda:service.attach_conversation(pid,body.conversation_id,user.id))
    return {'success':True}

@router.post('/projects/{pid}/modules')
def add_module(pid:str,body:ModuleChange,user:User=Depends(get_current_user)):
    if not body.kind:raise HTTPException(400,detail='اختر نوع القسم')
    def change(p):
        if any(m['kind']==body.kind for m in p['modules']):raise service.Conflict('القسم موجود بالفعل، يمكنك إظهاره من تخصيص اللوحة')
        service.remember(p);p['modules'].append(service.new_module(body.kind))
    return public(run(lambda:service.mutate(pid,user.id,body.revision,change)))

@router.patch('/projects/{pid}/modules/{mid}')
def update_module(pid:str,mid:str,body:ModuleChange,user:User=Depends(get_current_user)):
    def change(p):
        m=next((m for m in p['modules'] if m['id']==mid),None)
        if not m:raise KeyError('القسم غير موجود')
        service.remember(p)
        if body.hidden is not None:m['hidden']=body.hidden
        if body.direction:
            i=p['modules'].index(m);j=i+(-1 if body.direction=='up' else 1)
            if 0<=j<len(p['modules']):p['modules'][i],p['modules'][j]=p['modules'][j],p['modules'][i]
    return public(run(lambda:service.mutate(pid,user.id,body.revision,change)))

@router.post('/projects/{pid}/modules/{mid}/items')
def add_item(pid:str,mid:str,body:ItemChange,user:User=Depends(get_current_user)):
    def change(p):
        m=next((m for m in p['modules'] if m['id']==mid),None)
        if not m:raise KeyError('القسم غير موجود')
        if len(m['items'])>=200:raise ValueError('وصل هذا القسم إلى حد 200 عنصر')
        item=service.validate_item(body.item.model_dump())
        if item['decision_state']!='proposed':raise ValueError('اعتمد القرار من زر الاعتماد بعد حفظه')
        workflow.validate_links(p,m['kind'],item)
        service.remember(p);m['items'].append({**item,'id':str(uuid.uuid4()),'origin':'manual'})
        workflow.event(p,'item_added','إضافة: '+item['title'])
    return public(run(lambda:service.mutate(pid,user.id,body.revision,change)))

@router.put('/projects/{pid}/modules/{mid}/items/{iid}')
def update_item(pid:str,mid:str,iid:str,body:ItemChange,user:User=Depends(get_current_user)):
    def change(p):
        m=next((m for m in p['modules'] if m['id']==mid),None)
        item=next((i for i in m['items'] if i['id']==iid),None) if m else None
        if not item:raise KeyError('العنصر غير موجود')
        data=service.validate_item(body.item.model_dump())
        if data['decision_state']!=item.get('decision_state','proposed'):raise ValueError('غيّر حالة القرار من إجراء الاعتماد أو الرفض')
        if m['kind']=='decisions' and item.get('decision_state')=='approved':raise ValueError('القرار المعتمد محفوظ؛ أنشئ مقترح قرار جديد لتغييره')
        workflow.validate_links(p,m['kind'],data,iid)
        service.remember(p);item.update(data);item['origin']='manual'
        workflow.event(p,'item_updated','تحديث: '+item['title'])
    return public(run(lambda:service.mutate(pid,user.id,body.revision,change)))

@router.delete('/projects/{pid}/modules/{mid}/items/{iid}')
def delete_item(pid:str,mid:str,iid:str,body:Revision,user:User=Depends(get_current_user)):
    def change(p):
        m=next((m for m in p['modules'] if m['id']==mid),None)
        if not m or not any(i['id']==iid for i in m['items']):raise KeyError('العنصر غير موجود')
        if any(i.get('linked_decision_id')==iid or i.get('linked_task_id')==iid or iid in i.get('blocked_by',[]) for i in workflow.items(p)):
            raise ValueError('العنصر مرتبط بمهام أو نتائج؛ عالج الروابط قبل الحذف')
        service.remember(p);m['items']=[i for i in m['items'] if i['id']!=iid]
    return public(run(lambda:service.mutate(pid,user.id,body.revision,change)))

@router.post('/projects/{pid}/suggest')
def suggest(pid:str,user:User=Depends(get_current_user)):
    return public(run(lambda:service.request_proposal(pid,user.id)))

@router.post('/projects/{pid}/proposal/{action}')
def proposal(pid:str,action:Literal['accept','dismiss'],body:ProposalAction,user:User=Depends(get_current_user)):
    def change(p):
        if not p.get('proposal') or p['proposal']['id']!=body.proposal_id:raise service.Conflict('الاقتراح تغير، حدّث الصفحة')
        if action=='accept':service.accept_proposal(p,body.proposal_id)
        else:p['proposal']=None
    return public(run(lambda:service.mutate(pid,user.id,body.revision,change)))

@router.post('/projects/{pid}/undo')
def undo(pid:str,body:Revision,user:User=Depends(get_current_user)):
    def change(p):
        if not p.get('undo'):raise ValueError('لا توجد تغييرات للتراجع عنها')
        p.update(p['undo'].pop())
    return public(run(lambda:service.mutate(pid,user.id,body.revision,change)))


class DecisionAction(Revision):
    state:Literal['approved','rejected']

@router.post('/projects/{pid}/decisions/{iid}/state')
def decision_state(pid:str,iid:str,body:DecisionAction,user:User=Depends(get_current_user)):
    def change(p):
        item=workflow.locate(p,iid,'decisions')
        if item.get('decision_state','proposed')!='proposed':raise service.Conflict('القرار محسوم؛ أضف مقترحًا جديدًا لتغييره')
        service.remember(p);item['decision_state']=body.state
        item['approved_by']=user.id if body.state=='approved' else None
        workflow.event(p,body.state,item['title'])
    return public(run(lambda:service.mutate(pid,user.id,body.revision,change)))

class TaskFromDecision(Revision):
    title:str=Field(min_length=1,max_length=200)
    owner:str=Field(default='',max_length=150)
    due_date:str=Field(default='',max_length=10)
    expected_outcome:str=Field(default='',max_length=1000)

@router.post('/projects/{pid}/decisions/{iid}/task')
def decision_task(pid:str,iid:str,body:TaskFromDecision,user:User=Depends(get_current_user)):
    def change(p):
        decision=workflow.locate(p,iid,'decisions')
        if decision.get('decision_state')!='approved':raise ValueError('اعتمد القرار قبل تحويله إلى مهمة')
        data=service.ItemInput(title=body.title,owner=body.owner,due_date=body.due_date,expected_outcome=body.expected_outcome,linked_decision_id=iid).model_dump()
        service.validate_item(data)
        module=next((m for m in p['modules'] if m['kind']=='tasks'),None)
        if module and len(module['items'])>=200:raise ValueError('وصل قسم المهام إلى الحد الأقصى')
        if any(i['title']==body.title and i.get('linked_decision_id')==iid for i in workflow.items(p,'tasks')):raise service.Conflict('هذه المهمة مرتبطة بالقرار بالفعل')
        service.remember(p)
        if not module:module=service.new_module('tasks');p['modules'].append(module)
        module['items'].append({**data,'id':str(uuid.uuid4()),'origin':'manual'})
        workflow.event(p,'task_created',body.title)
    return public(run(lambda:service.mutate(pid,user.id,body.revision,change)))

@router.post('/projects/{pid}/review')
def review_project(pid:str,body:Revision,user:User=Depends(get_current_user)):
    def change(p):
        report=workflow.overview(p)
        snapshot={'at':datetime.now(timezone.utc).isoformat(),'goal':p['goal'],'success_criteria':p.get('brief',{}).get('success_criteria',''),'measurements':report['measurements'],'next_step':report['next_step'],'missing_results':len(report['missing_results'])}
        p.setdefault('reviews',[]).append(snapshot);p['reviews']=p['reviews'][-20:]
        p.setdefault('brief',workflow.Brief().model_dump())['stage']='review'
        workflow.event(p,'review','تم تسجيل مراجعة النتائج مقابل الأهداف المدخلة')
    return public(run(lambda:service.mutate(pid,user.id,body.revision,change)))
