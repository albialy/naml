"""Offline OAuth regression tests; no GitHub secrets or live requests are used."""
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from agent_system.core.auth import github_oauth as oauth
from agent_system.core.auth.manager import auth_manager
from agent_system.core.auth.models import UserRole
from agent_system.core.settings_manager import settings_manager

ORIGIN = "https://naml.example"


@pytest.fixture
def github(client, monkeypatch):
    client.base_url = ORIGIN
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-client")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("GITHUB_REDIRECT_URI", ORIGIN + "/api/auth/github/callback")
    monkeypatch.setattr(oauth, "fetch_identity", lambda *args: {"id": "123", "login": "example-user"})
    return client


def start(client):
    result = client.get("/api/auth/github/start", follow_redirects=False)
    assert result.status_code == 303
    return result, parse_qs(urlsplit(result.headers["location"]).query)


def callback(client, state, **extra):
    return client.get("/api/auth/github/callback", params={"state": state, "code": "test-code", **extra}, follow_redirects=False)


def link_admin(client, headers):
    result = client.post("/api/auth/github/link", json={"password": "admin123"}, headers=headers)
    assert result.status_code == 200, result.text
    state = parse_qs(urlsplit(result.json()["authorization_url"]).query)["state"][0]
    result = callback(client, state)
    assert result.headers["location"] == ORIGIN + "/settings?github=linked"
    return auth_manager.get_user_by_username("admin").id


def complete(client, origin=ORIGIN):
    return client.post("/api/auth/github/complete", headers={"Origin": origin})


def admin_handoff():
    user_id = auth_manager.get_user_by_username("admin").id
    auth_manager.database.set_document("github_identities", {"123": {"user_id": user_id, "login": "example-user"}})
    return oauth.create_handoff(user_id, "123")


def test_unconfigured_provider_is_disabled_and_never_exposes_secrets(client, monkeypatch):
    for key in ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "GITHUB_REDIRECT_URI"]:
        monkeypatch.delenv(key, raising=False)
    assert client.get("/api/auth/providers").json() == {"github": {"enabled": False}}
    result = client.get("/api/auth/github/start", follow_redirects=False)
    assert result.headers["location"] == "/login?github_error=unavailable"


@pytest.mark.parametrize("redirect", ["http://naml.example/api/auth/github/callback", "https://u:p@naml.example/api/auth/github/callback", "https://naml.example/api/auth/github/callback?next=bad", "https://naml.example/wrong"])
def test_invalid_redirect_configuration_cannot_enable_oauth(github, monkeypatch, redirect):
    monkeypatch.setenv("GITHUB_REDIRECT_URI", redirect)
    assert github.get("/api/auth/providers").json()["github"]["enabled"] is False


def test_start_uses_pkce_browser_binding_and_no_repository_scopes(github, database):
    result, params = start(github)
    assert params["code_challenge_method"] == ["S256"]
    assert "repo" not in params.get("scope", [])
    flow = next(iter(database.get_document("github_oauth_flows").values()))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(flow["verifier"].encode()).digest()).decode().rstrip("=")
    assert params["code_challenge"] == [challenge]
    cookies = ";".join(result.headers.get_list("set-cookie"))
    assert "HttpOnly" in cookies and "Secure" in cookies and "SameSite=lax" in cookies
    assert "__Host-naml_github_flow=" in cookies and "Domain=" not in cookies
    assert "test-secret" not in result.text + result.headers["location"]
    assert result.headers["cache-control"] == "no-store"


def test_link_keeps_existing_admin_and_data_then_logs_in_same_account(github, headers, database):
    admin = auth_manager.get_user_by_username("admin")
    database.set_document("project:keep", {"user_id": admin.id, "name": "keep"})
    user_id = link_admin(github, headers)
    assert len(database.get_document("users")) == 1
    _, params = start(github)
    returned = callback(github, params["state"][0])
    assert returned.headers["location"] == ORIGIN + "/auth/github/complete"
    assert "access_token" not in returned.headers["location"]
    result = complete(github)
    assert result.status_code == 200
    assert result.json()["user"]["id"] == user_id
    assert result.json()["user"]["role"] == "super_admin"
    assert database.get_document("project:keep")["user_id"] == user_id
    assert complete(github).status_code == 400  # one-time handoff
    assert auth_manager.validate_token(result.json()["access_token"]).id == user_id


def test_new_registration_closed_and_no_username_or_email_autolinking(github, database, monkeypatch):
    monkeypatch.setattr(oauth, "fetch_identity", lambda *a: {"id": "999", "login": "admin", "email": "admin@example.org"})
    before = database.get_document("users")
    _, params = start(github)
    response = callback(github, params["state"][0])
    assert response.headers["location"].endswith("github_error=registration_closed")
    assert database.get_document("users") == before
    assert complete(github).status_code == 400


def test_open_registration_creates_only_normal_user_and_cannot_unlink_only_login(github, database):
    assert settings_manager.update_system({"allow_user_registration": True}, "test")
    _, params = start(github)
    callback(github, params["state"][0])
    result = complete(github).json()
    assert result["user"]["role"] == "user"
    user = auth_manager.validate_token(result["access_token"])
    assert user.username == "github_123" and not oauth.check_password(user, "")
    headers = {"Authorization": "Bearer " + result["access_token"]}
    status = github.get("/api/auth/github/account", headers=headers).json()
    assert status["linked"] and not status["password_login"]
    assert github.request("DELETE", "/api/auth/github/link", headers=headers, json={"password": "guess"}).status_code == 400


@pytest.mark.parametrize("case", ["missing_cookie", "wrong_state", "expired", "replayed"])
def test_invalid_states_never_contact_github(github, database, monkeypatch, case):
    _, params = start(github)
    state = params["state"][0]
    monkeypatch.setattr(oauth, "fetch_identity", lambda *a: pytest.fail("invalid state reached GitHub"))
    if case == "missing_cookie":
        github.cookies.clear()
    elif case == "wrong_state":
        state = "x" * 43
    elif case == "expired":
        flows = database.get_document("github_oauth_flows")
        flows[oauth.digest(state)]["expires_at"] = time.time() - 1
        database.set_document("github_oauth_flows", flows)
    else:
        oauth.consume_flow(oauth.configured(), state, state)
    response = callback(github, state)
    assert "github_error=" in response.headers["location"]


def test_denial_clears_browser_flow_without_exchanging_code(github, monkeypatch):
    _, params = start(github)
    monkeypatch.setattr(oauth, "fetch_identity", lambda *a: pytest.fail("denied consent"))
    response = callback(github, params["state"][0], error="access_denied")
    assert response.headers["location"].endswith("github_error=denied")
    assert oauth.cookie_name(oauth.FLOW_COOKIE, True) not in github.cookies


def test_link_requires_authenticated_user_and_correct_password(github, headers, database):
    assert github.post("/api/auth/github/link", json={"password": "admin123"}).status_code in (401, 403)
    result = github.post("/api/auth/github/link", headers=headers, json={"password": "wrong"})
    assert result.status_code == 400 and result.json()["detail"]["code"] == "password_required"
    assert not database.get_document("github_oauth_flows", {})


@pytest.mark.parametrize("change", ["logout", "password", "deactivate"])
def test_link_cannot_finish_after_session_or_account_changes(github, headers, database, change):
    result = github.post("/api/auth/github/link", json={"password": "admin123"}, headers=headers)
    state = parse_qs(urlsplit(result.json()["authorization_url"]).query)["state"][0]
    if change == "logout":
        github.post("/api/auth/logout", headers=headers)
    elif change == "password":
        auth_manager.change_password(auth_manager.get_user_by_username("admin").id, "admin123", "changed")
    else:
        def disable(users):
            for user in users.values():user["is_active"] = False
            return users
        database.mutate_document("users", disable)
    response = callback(github, state)
    assert response.headers["location"].endswith("github_error=session_expired")
    assert not database.get_document("github_identities", {})


def test_identity_cannot_be_linked_to_two_users(github, headers):
    link_admin(github, headers)
    admin = auth_manager.get_user_by_username("admin")
    user = auth_manager.create_user("second", "password", UserRole.USER, admin.id)
    token = auth_manager.login(user.username, "password").token
    response = github.post("/api/auth/github/link", headers={"Authorization": "Bearer " + token}, json={"password": "password"})
    state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
    assert callback(github, state).headers["location"].endswith("github_error=identity_in_use")


def test_unlink_requires_password_and_stops_future_github_login(github, headers):
    link_admin(github, headers)
    assert github.request("DELETE", "/api/auth/github/link", headers=headers, json={"password": "wrong"}).status_code == 400
    assert github.request("DELETE", "/api/auth/github/link", headers=headers, json={"password": "admin123"}).status_code == 200
    assert not github.get("/api/auth/github/account", headers=headers).json()["linked"]
    assert auth_manager.login("admin", "admin123")
    _, params = start(github)
    assert callback(github, params["state"][0]).headers["location"].endswith("github_error=registration_closed")


def test_complete_rejects_foreign_origin_before_consuming_handoff(github):
    handoff = admin_handoff()
    github.cookies.set(oauth.cookie_name(oauth.LOGIN_COOKIE, True), handoff, domain="naml.example", path=oauth.COOKIE_PATH)
    assert complete(github, "https://other.example").status_code == 403
    assert complete(github).status_code == 200


def test_pending_flow_survives_new_process(github, database):
    _, params = start(github)
    state = params["state"][0]
    code = "from agent_system.core.auth import github_oauth as o; import sys; print(o.consume_flow(o.configured(),sys.argv[1],sys.argv[1])['intent'])"
    result = subprocess.run([sys.executable, "-c", code, state], env={**os.environ, "DATABASE_PATH": database.path}, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "login"
    assert not database.get_document("github_oauth_flows")


def test_concurrent_first_signins_create_one_identity_and_one_user(github, database):
    settings_manager.update_system({"allow_user_registration": True}, "test")
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: oauth.resolve_identity({"id": "456", "login": "new-user"}, {"intent": "login"}), range(2)))
    assert ids[0] == ids[1] and len(database.get_document("users")) == 2


def test_handoff_can_be_consumed_once_even_with_concurrent_requests(github):
    value = admin_handoff()
    def run(_):
        try:return oauth.complete_login(value)
        except oauth.OAuthError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sum(value is not None for value in results) == 1


def test_real_exchange_sends_pkce_and_discards_provider_tokens(database, monkeypatch):
    cfg = oauth.Config("test-client", "test-secret", ORIGIN + "/api/auth/github/callback", ORIGIN, True)
    seen = []
    def post(url, **kwargs):
        seen.append((url, kwargs))
        return SimpleNamespace(status_code=200, json=lambda: {"access_token": "transient-access", "refresh_token": "transient-refresh", "token_type": "bearer"})
    def get(url, **kwargs):
        seen.append((url, kwargs))
        return SimpleNamespace(status_code=200, json=lambda: {"id": 123, "login": "example-user", "email": "private@example.org"})
    monkeypatch.setattr(oauth.requests, "post", post)
    monkeypatch.setattr(oauth.requests, "get", get)
    assert oauth.fetch_identity(cfg, "code", "verifier") == {"id": "123", "login": "example-user"}
    assert seen[0][1]["data"]["code_verifier"] == "verifier"
    assert seen[1][1]["headers"]["Authorization"] == "Bearer transient-access"
    assert all(not kwargs["allow_redirects"] for _, kwargs in seen)
    with database.connection() as conn:
        data = json.dumps(database.execute(conn, "SELECT data FROM naml_documents").fetchall())
    assert "transient-access" not in data and "transient-refresh" not in data and "test-secret" not in data


def test_provider_failure_does_not_expose_raw_error_or_secret(github, monkeypatch):
    _, params = start(github)
    def fail(*args):raise oauth.OAuthError("provider_error", 502)
    monkeypatch.setattr(oauth, "fetch_identity", fail)
    response = callback(github, params["state"][0])
    assert response.headers["location"].endswith("github_error=provider_error")
    assert "test-secret" not in response.text + response.headers["location"]


@pytest.mark.parametrize("failure", ["http", "token_error", "bad_identity", "json", "network"])
def test_exchange_rejects_untrusted_upstream_responses(monkeypatch, failure):
    cfg = oauth.Config("client", "secret", ORIGIN + "/api/auth/github/callback", ORIGIN, True)
    def post(*args, **kwargs):
        if failure == "network":raise oauth.requests.RequestException("secret upstream detail")
        def body():
            if failure == "json":raise ValueError("secret upstream detail")
            return {"error": "bad_verification_code"} if failure == "token_error" else {"access_token": "temporary", "token_type": "bearer"}
        return SimpleNamespace(status_code=401 if failure == "http" else 200, json=body)
    monkeypatch.setattr(oauth.requests, "post", post)
    monkeypatch.setattr(oauth.requests, "get", lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {"id": True, "login": "example"}))
    with pytest.raises(oauth.OAuthError, match="^provider_error$"):
        oauth.fetch_identity(cfg, "code", "verifier")


def test_disabling_user_after_callback_prevents_session_issuance(github, headers, database):
    link_admin(github, headers)
    _, params = start(github)
    callback(github, params["state"][0])
    def disable(users):
        for user in users.values():user["is_active"] = False
        return users
    database.mutate_document("users", disable)
    assert complete(github).status_code == 403


def test_expired_handoff_does_not_issue_a_session(github, database):
    value = admin_handoff()
    entries = database.get_document("github_login_handoffs")
    entries[oauth.digest(value)]["expires_at"] = time.time() - 1
    database.set_document("github_login_handoffs", entries)
    with pytest.raises(oauth.OAuthError, match="expired"):
        oauth.complete_login(value)


def test_configuration_change_invalidates_in_progress_flow(github, monkeypatch):
    _, params = start(github)
    monkeypatch.setenv("GITHUB_CLIENT_ID", "different-client")
    monkeypatch.setattr(oauth, "fetch_identity", lambda *a: pytest.fail("config changed"))
    assert callback(github, params["state"][0]).headers["location"].endswith("github_error=invalid_state")


def test_unlink_cancels_pending_link_and_login_handoffs(github, headers, database):
    user_id = link_admin(github, headers)
    handoff = oauth.create_handoff(user_id, "123")
    pending = github.post("/api/auth/github/link", headers=headers, json={"password": "admin123"})
    state = parse_qs(urlsplit(pending.json()["authorization_url"]).query)["state"][0]
    oauth.unlink(user_id, "admin123")
    assert callback(github, state).headers["location"].endswith("github_error=expired")
    with pytest.raises(oauth.OAuthError, match="expired"):
        oauth.complete_login(handoff)


def test_identity_is_rechecked_atomically_before_session_issuance(github, database):
    user_id = auth_manager.get_user_by_username("admin").id
    assert auth_manager.issue_token_for_user(user_id, "missing") is None


def test_unlink_also_invalidates_link_already_waiting_for_github(github, headers):
    user_id = link_admin(github, headers)
    response = github.post("/api/auth/github/link", headers=headers, json={"password": "admin123"})
    state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
    in_flight = oauth.consume_flow(oauth.configured(), state, state)
    oauth.unlink(user_id, "admin123")
    with pytest.raises(oauth.OAuthError, match="session_expired"):
        oauth.resolve_identity({"id": "123", "login": "example-user"}, in_flight)
