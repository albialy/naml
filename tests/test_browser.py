import asyncio
import socket
import pytest
from fastapi.testclient import TestClient
from browser_service import service
from agent_system.core import browser_client

@pytest.mark.parametrize('url', ['file:///etc/passwd','http://localhost','http://127.0.0.1','http://169.254.169.254/latest','http://10.1.2.3','http://[::1]','http://[::ffff:8.8.8.8]','https://u:p@example.com','http://example.com:8080','http://foo.internal','http://224.0.0.1','http://example.com\\@localhost'])
def test_reject_private_urls(url):
    with pytest.raises(ValueError): service.check_url(url)

def test_public_urls():
    assert service.check_url('https://example.com/a') == 'example.com'
    assert service.check_url('https://8.8.8.8') == '8.8.8.8'

def test_dns_rebinding_block(monkeypatch):
    async def run():
        async def fake(*args, **kwargs): return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        monkeypatch.setattr(asyncio.get_running_loop(), 'getaddrinfo', fake)
        with pytest.raises(OSError): await service.PublicResolver().resolve('public.example', 443)
    asyncio.run(run())

def test_source_validation():
    with pytest.raises(ValueError): service.Capture()
    with pytest.raises(ValueError): service.Capture(url='https://example.com',html='<h1>x</h1>')

def test_worker_auth_and_failure(monkeypatch):
    monkeypatch.setenv('BROWSER_SERVICE_TOKEN','x'*32)
    c=TestClient(service.app)
    assert c.post('/capture',json={'url':'https://example.com'}).status_code == 401
    async def broken(spec): raise RuntimeError('sensitive internal detail')
    monkeypatch.setattr(service,'render',broken)
    r=c.post('/capture',json={'url':'https://example.com'},headers={'Authorization':'Bearer '+'x'*32})
    assert r.status_code == 502 and 'sensitive' not in r.text

def test_naml_auth_and_capture(client,headers,monkeypatch):
    assert client.get('/api/browser/status').status_code in (401,403)
    monkeypatch.delenv('BROWSER_SERVICE_URL',raising=False)
    assert client.get('/api/browser/status',headers=headers).json()=={'configured':False}
    assert client.post('/api/browser/capture',headers=headers,json={}).status_code==422
    monkeypatch.setattr(browser_client,'capture',lambda **kw: {'text':'hello','screenshot':None})
    assert client.post('/api/browser/capture',headers=headers,json={'url':'https://example.com'}).json()['text']=='hello'

def test_enrichment_opt_in_and_fallback(monkeypatch):
    rows=[{'url':'https://example.com','snippet':'original'}]
    monkeypatch.delenv('BROWSER_RESEARCH_ENABLED',raising=False)
    assert browser_client.enrich_results(rows)==rows
    monkeypatch.setenv('BROWSER_RESEARCH_ENABLED','true')
    monkeypatch.setattr(browser_client,'configured',lambda:True)
    monkeypatch.setattr(browser_client,'capture',lambda **kw:{'text':'rendered'})
    assert 'rendered' in browser_client.enrich_results(rows)[0]['snippet']
    assert rows[0]['snippet']=='original'
    def fail(**kw): raise ValueError('busy')
    monkeypatch.setattr(browser_client,'capture',fail)
    assert browser_client.enrich_results(rows)==rows
