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
        with pytest.raises(service.CaptureFailure, match="url_blocked"):
            await service.PublicResolver().resolve('public.example', 443)
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


@pytest.mark.parametrize("failure,code", [
    (TimeoutError(), "render_timeout"),
    (service.CaptureFailure("site_dns_error"), "site_dns_error"),
    (service.CaptureFailure("site_http_error", 403), "site_http_error"),
])
def test_worker_diagnostics_without_secrets(monkeypatch, caplog, failure, code):
    monkeypatch.setenv("BROWSER_SERVICE_TOKEN", "x" * 32)
    async def broken(spec):
        raise failure
    monkeypatch.setattr(service, "render", broken)
    r = TestClient(service.app).post("/capture", json={"url": "https://example.com"},
        headers={"Authorization": "Bearer " + "x" * 32, "X-Request-ID": "abcdef123456"})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == code
    assert r.json()["detail"]["request_id"] == "abcdef123456"
    assert "abcdef123456" in caplog.text and code in caplog.text
    assert "x" * 32 not in caplog.text
    if code == "site_http_error":
        assert r.json()["detail"]["site_status"] == 403


def fake_worker(monkeypatch, status=200, body=b'{"text":"hello"}', failure=None):
    from contextlib import nullcontext
    calls = []
    class Response:
        status_code = status
        def iter_content(self, size):
            yield body
    class Session:
        trust_env = True
        def post(self, url, **kwargs):
            calls.append(kwargs)
            assert not self.trust_env
            if failure:
                raise failure
            return nullcontext(Response())
    monkeypatch.setenv("BROWSER_SERVICE_URL", "https://worker.example")
    monkeypatch.setenv("BROWSER_SERVICE_TOKEN", "x" * 32)
    monkeypatch.setattr(browser_client.requests, "Session", lambda: nullcontext(Session()))
    return calls


@pytest.mark.parametrize("status,body,code", [
    (401, b'credentials must not be forwarded', "worker_auth"),
    (429, b'busy', "worker_busy"),
    (503, b'loading', "worker_unavailable"),
    (422, b'validation details including html', "invalid_source"),
    (200, b'<html>Starting your service</html>', "worker_response"),
    (502, b'{"detail":{"code":"site_tls_error"}}', "site_tls_error"),
    (502, b'{"detail":"legacy worker failure"}', "render_failed"),
    (502, b'{"detail":{"code":"unknown-secret"}}', "render_failed"),
])
def test_client_error_mapping(monkeypatch, status, body, code):
    fake_worker(monkeypatch, status, body)
    with pytest.raises(browser_client.BrowserError) as error:
        browser_client.capture(url="https://example.com")
    assert error.value.code == code
    assert len(error.value.request_id) == 12
    assert "unknown-secret" not in str(error.value)


def test_timeout_budgets_and_no_post_retry(monkeypatch):
    calls = fake_worker(monkeypatch)
    assert browser_client.capture(url="https://example.com")["text"] == "hello"
    browser_client.capture(url="https://example.com", screenshot=False)
    assert calls[0]["timeout"] == (5, 100)
    assert calls[1]["timeout"] == (5, 35)
    assert len(calls) == 2
    assert len(calls[0]["headers"]["X-Request-ID"]) == 12


@pytest.mark.parametrize("failure,code", [
    (browser_client.requests.ReadTimeout("sensitive"), "worker_timeout"),
    (browser_client.requests.ConnectionError("sensitive"), "worker_connection"),
    (browser_client.requests.exceptions.SSLError("sensitive"), "worker_tls"),
])
def test_client_transport_errors(monkeypatch, caplog, failure, code):
    calls = fake_worker(monkeypatch, failure=failure)
    with pytest.raises(browser_client.BrowserError) as error:
        browser_client.capture(url="https://example.com")
    assert error.value.code == code and len(calls) == 1
    assert "sensitive" not in caplog.text


def test_browser_api_diagnostic_contract(client, headers, monkeypatch):
    def broken(**kwargs):
        raise browser_client.BrowserError("worker_timeout", "abcdef123456")
    monkeypatch.setattr(browser_client, "capture", broken)
    response = client.post("/api/browser/capture", headers=headers, json={"url":"https://example.com"})
    assert response.status_code == 504
    data = response.json()
    assert data["code"] == "worker_timeout" and data["request_id"] == "abcdef123456"
    assert isinstance(data["detail"], str)
