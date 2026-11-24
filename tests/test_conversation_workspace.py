"""Branch isolation, atomic interruption and durable cancellation (no model APIs)."""
import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from agent_system.core.database import Database, ConversationBusy
from agent_system.core.memory import SharedMemory
from agent_system.core.director import Director
from agent_system.core.execution_runtime import ExecutionRuntime, ExecutionCancelled
from agent_system.core.settings_manager import settings_manager
from agent_system.core.auth.manager import auth_manager
from agent_system.core.auth.models import UserRole


def turn(db, task, cid=None, **options):
    return db.start_turn(SharedMemory(task, user_id='owner').to_dict(), cid, **options)


def finish(db, data, answer):
    data = copy.deepcopy(data)
    data.update(status='complete', final_synthesis=answer)
    db.save_session(data)
    return data


def test_edit_forks_at_message_and_preserves_original_after_reopen(database, tmp_path):
    first = finish(database, turn(database, 'first'), 'one')
    cid = first['conversation_id']
    second = finish(database, turn(database, 'second', cid), 'two')
    before = database.get_conversation(cid)
    edited = turn(database, 'corrected first', cid, action='edit', message_id=first['session_id']+':user',
                  branch_id=before['branch_id'], expected_revision=before['revision'])
    assert edited['chat_history'] == []
    finish(database, edited, 'corrected answer')
    db = Database(backend='sqlite', path=database.path, legacy_dir=tmp_path/'legacy')
    current = db.get_conversation(cid)
    assert [m['content'] for m in current['messages']] == ['corrected first', 'corrected answer']
    assert len(current['branches']) == 2 and all('messages' not in b for b in current['branches'])
    old = db.switch_branch(cid, 'owner', 'main', current['revision'])
    assert [m['content'] for m in old['messages']] == ['first','one','second','two']
    assert 'branches' not in db.list_conversations('owner')[0]
    followup = turn(db, 'continue', cid)
    assert followup['chat_history'][-1]['content'] == 'two'
    assert all('corrected' not in m['content'] for m in followup['chat_history'])


def test_retry_uses_original_question_and_excludes_abandoned_future(database):
    first = finish(database, turn(database, 'first'), 'old answer')
    cid = first['conversation_id']
    finish(database, turn(database, 'future', cid), 'future answer')
    retry = turn(database, 'client text ignored', cid, action='retry', message_id=first['session_id']+':assistant')
    assert retry['task_original'] == 'first' and retry['chat_history'] == []
    assert len(database.get_conversation(cid)['branches']) == 2


def test_stop_is_durable_and_late_worker_cannot_restore_reply(database):
    saved = turn(database, 'slow')
    cid = saved['conversation_id']
    c = database.get_conversation(cid)
    cancelled = database.cancel_turn(cid, 'owner', saved['session_id'], c['revision'], c['branch_id'])
    assert cancelled['status'] == 'cancelled'
    assert database.save_session({**saved, 'status':'complete', 'final_synthesis':'late reply'}) is False
    assert database.get_session(saved['session_id'])['status'] == 'cancelled'
    assert 'late reply' not in str(database.get_conversation(cid))
    next_turn = turn(database, 'continue differently', cid)
    assert all(m['content'] != 'تم إيقاف الرد بناءً على طلبك.' for m in next_turn['chat_history'])


def test_steering_atomically_cancels_and_starts_with_new_instruction(database):
    saved = turn(database, 'old instruction')
    cid = saved['conversation_id']; c = database.get_conversation(cid)
    new = turn(database, 'make it shorter', cid, interrupt_session_id=saved['session_id'],
               expected_revision=c['revision'], branch_id=c['branch_id'])
    assert database.get_session(saved['session_id'])['status'] == 'cancelled'
    assert database.get_conversation(cid)['active_session_id'] == new['session_id']
    assert new['chat_history'] == [{'role':'user','content':'old instruction'}]
    finish(database, saved, 'stale')
    assert database.get_conversation(cid)['status'] == 'pending'


def test_invalid_steer_rolls_back_cancellation(database):
    saved = turn(database, 'original'); cid = saved['conversation_id']; c = database.get_conversation(cid)
    with pytest.raises(ValueError):
        turn(database, 'new', cid, interrupt_session_id=saved['session_id'], expected_revision=c['revision'],
             reference={'message_id':'missing', 'text':'invalid'})
    assert database.get_session(saved['session_id'])['status'] == 'pending'
    assert len(database.get_conversation(cid)['messages']) == 1


def test_cross_user_and_stale_revision_cannot_mutate(database):
    saved = finish(database, turn(database, 'first'), 'answer'); cid = saved['conversation_id']; c = database.get_conversation(cid)
    with pytest.raises(PermissionError): database.switch_branch(cid,'intruder','main',c['revision'])
    with pytest.raises(PermissionError): database.cancel_turn(cid,'intruder',saved['session_id'],c['revision'],'main')
    turn(database, 'second', cid, expected_revision=c['revision'])
    with pytest.raises(ConversationBusy): database.cancel_turn(cid,'owner',saved['session_id'],c['revision'],'main')
    assert len(database.get_conversation(cid)['messages']) == 3


def test_concurrent_edits_create_only_one_branch(database):
    saved = finish(database, turn(database, 'first'), 'answer'); cid = saved['conversation_id']; c = database.get_conversation(cid)
    def edit(i):
        try:
            turn(database, str(i), cid, action='edit', message_id=saved['session_id']+':user', expected_revision=c['revision'])
            return True
        except ConversationBusy: return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(edit, [1,2])) == 1
    assert len(database.get_conversation(cid)['branches']) == 2


def test_selection_validated_and_preserved_on_retry(database):
    saved = finish(database, turn(database, 'first'), 'red button and blue title'); cid = saved['conversation_id']
    ref = {'message_id':saved['session_id']+':assistant','text':'red button'}
    follow = finish(database, turn(database, 'change this', cid, reference=ref), 'green button')
    retry = turn(database, 'retry', cid, action='retry', message_id=follow['session_id']+':assistant')
    assert retry['reference'] == ref
    memory = SharedMemory('change'); memory.reference = ref
    assert 'red button' in memory.conversation_context(compact=True)
    finish(database, retry, 'answer')
    with pytest.raises(ValueError): turn(database, 'bad', cid, reference={**ref,'text':'invented selection'})


def test_cancel_during_provider_call_prevents_fallback_and_later_calls(database):
    saved = turn(database, 'slow'); cid = saved['conversation_id']
    memory = SharedMemory('slow'); memory.session_id = saved['session_id']
    started = threading.Event(); release = threading.Event(); calls = []
    class Model:
        provider = 'test'; model_name = 'slow'
        def complete(self, **kwargs):
            calls.append('primary'); started.set(); assert release.wait(5)
            self.last_result = {'status_code':503}
            return 'Error: offline'
    runtime = ExecutionRuntime(memory, settings_manager.get_settings(), lambda: pytest.fail('fallback after cancellation'))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runtime.call, Model(), 'answer', 's', 'u', 0, 100)
        assert started.wait(5)
        c = database.get_conversation(cid)
        database.cancel_turn(cid,'owner',saved['session_id'],c['revision'],'main')
        release.set()
        with pytest.raises(ExecutionCancelled): future.result()
    assert calls == ['primary']
    with pytest.raises(ExecutionCancelled): runtime.check()


def test_deleted_cancelled_turn_cannot_resurrect(database):
    saved = turn(database, 'slow'); cid = saved['conversation_id']; c = database.get_conversation(cid)
    database.cancel_turn(cid,'owner',saved['session_id'],c['revision'],'main')
    assert database.delete_session(saved['session_id'])
    assert database.save_session({**saved, 'status':'complete', 'final_synthesis':'late'}) is False
    assert database.get_session(saved['session_id']) is None


def test_delete_removes_shared_turn_from_all_branches(database):
    saved = finish(database, turn(database, 'first'), 'one'); cid = saved['conversation_id']
    second = finish(database, turn(database, 'second', cid), 'two')
    edited = finish(database, turn(database,'edit second',cid,action='edit',message_id=second['session_id']+':user'), 'changed')
    database.delete_session(saved['session_id'])
    c = database.get_conversation(cid)
    assert all(m['session_id'] != saved['session_id'] for m in c['messages'])
    c = database.switch_branch(cid,'owner','main',c['revision'])
    assert [m['content'] for m in c['messages']] == ['second','two']


def test_api_edit_retry_stop_and_owner_permissions(client, headers, database, monkeypatch):
    def finish_model(self, task, memory):
        memory.status = 'complete'; memory.final_synthesis = 'reply: ' + task; memory.save_to_file()
    monkeypatch.setattr(Director,'run',finish_model)
    saved = client.post('/api/task',headers=headers,json={'task':'hello'}).json(); cid = saved['conversation_id']
    c = client.get('/api/conversations/'+cid,headers=headers).json()
    edited = client.post('/api/task',headers=headers,json={'task':'edited','conversation_id':cid,'action':'edit',
                         'message_id':saved['session_id']+':user','expected_revision':c['revision'],'branch_id':c['branch_id']})
    assert edited.status_code == 200
    c = client.get('/api/conversations/'+cid,headers=headers).json()
    assert [m['content'] for m in c['messages']] == ['edited','reply: edited']
    assert client.post('/api/task',headers=headers,json={'task':'x','conversation_id':cid,'action':'edit'}).status_code == 422
    admin = auth_manager.get_user_by_username('admin')
    auth_manager.create_user('intruder','password',UserRole.USER,admin.id)
    token = auth_manager.login('intruder','password').token
    other = {'Authorization':'Bearer '+token}
    assert client.post('/api/conversations/'+cid+'/branch',headers=other,json={'branch_id':'main','revision':c['revision']}).status_code == 403
    assert client.post('/api/conversations/'+cid+'/stop',headers=other,json={'session_id':c['active_session_id'],'revision':c['revision'],'branch_id':c['branch_id']}).status_code == 403
    assert client.post('/api/conversations/'+cid+'/branch',headers=headers,json={'branch_id':'missing','revision':c['revision']}).status_code == 404
