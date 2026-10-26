"""GitHub sign-in only: state + PKCE, stable identities, no stored GitHub tokens."""
import base64
import hashlib
import hmac
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

import requests

from agent_system.core.auth.manager import auth_manager
from agent_system.core.auth.models import User, UserRole

FLOW_COOKIE = "naml_github_flow"
LOGIN_COOKIE = "naml_github_login"
COOKIE_PATH = "/"
FLOW_TTL = 600
LOGIN_TTL = 60
MAX_PENDING = 256


def cookie_name(name, secure):
    # HTTPS cookies cannot be planted by a sibling subdomain (no Domain + path /).
    return "__Host-" + name if secure else name


class OAuthError(ValueError):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True)
class Config:
    client_id: str
    secret: str
    redirect_uri: str
    origin: str
    secure: bool


def configuration():
    client_id = os.getenv("GITHUB_CLIENT_ID", "").strip()
    secret = os.getenv("GITHUB_CLIENT_SECRET", "").strip()
    redirect = os.getenv("GITHUB_REDIRECT_URI", "").strip()
    if not all((client_id, secret, redirect)):
        return None
    try:
        url = urlsplit(redirect)
        local = url.hostname in ("127.0.0.1", "localhost", "::1")
        if (not url.hostname or url.username or url.password or url.query or url.fragment
                or url.path != "/api/auth/github/callback"
                or (url.scheme != "https" and not (local and url.scheme == "http"))):
            return None
        _ = url.port
        return Config(client_id, secret, redirect, f"{url.scheme}://{url.netloc}", url.scheme == "https")
    except ValueError:
        return None


def configured():
    value = configuration()
    if value is None:
        raise OAuthError("unavailable", 503)
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _random_value(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is not None


def _put_pending(key, raw, payload, ttl, old=None):
    now = time.time()
    def add(entries):
        entries = {k: v for k, v in entries.items() if v["expires_at"] > now}
        if _random_value(old):
            entries.pop(digest(old), None)
        if len(entries) >= MAX_PENDING:
            raise OAuthError("busy", 503)
        entries[digest(raw)] = {**payload, "expires_at": now + ttl}
        return entries
    auth_manager.database.mutate_document(key, add, {})


def _consume_pending(key, raw):
    if not _random_value(raw):
        raise OAuthError("expired")
    result = None
    def consume(entries):
        nonlocal result
        result = entries.pop(digest(raw), None)
        now = time.time()
        return {k: v for k, v in entries.items() if v["expires_at"] > now}
    auth_manager.database.mutate_document(key, consume, {})
    if not result or result["expires_at"] <= time.time():
        raise OAuthError("expired")
    return result


def check_password(user, password):
    return bool(user and user.is_active and isinstance(password, str)
                and hmac.compare_digest(user.password_hash, auth_manager._hash_password(password)))


def begin(config, old=None, user=None, session_key=None):
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    payload = {"verifier": verifier, "client_id": config.client_id, "redirect_uri": config.redirect_uri,
               "intent": "link" if user else "login"}
    if user:
        payload.update(user_id=user.id, session_key=session_key, password_version=digest(user.password_hash))
        payload["link_version"] = auth_manager.database.get_document("github_link_versions", {}).get(user.id, 0)
    _put_pending("github_oauth_flows", state, payload, FLOW_TTL, old)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    url = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": config.client_id, "redirect_uri": config.redirect_uri, "scope": "",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
        "prompt": "select_account",
    })
    return state, url


def consume_flow(config, state, cookie):
    if not _random_value(state) or not _random_value(cookie) or not hmac.compare_digest(state, cookie):
        raise OAuthError("invalid_state")
    flow = _consume_pending("github_oauth_flows", state)
    if flow["client_id"] != config.client_id or flow["redirect_uri"] != config.redirect_uri:
        raise OAuthError("invalid_state")
    return flow


def fetch_identity(config, code, verifier):
    """Only fixed GitHub endpoints. Never propagate upstream bodies or tokens."""
    try:
        response = requests.post("https://github.com/login/oauth/access_token", data={
            "client_id": config.client_id, "client_secret": config.secret, "code": code,
            "redirect_uri": config.redirect_uri, "code_verifier": verifier,
        }, headers={"Accept": "application/json"}, timeout=12, allow_redirects=False)
        if response.status_code != 200:
            raise OAuthError("provider_error", 502)
        data = response.json()
        token = data.get("access_token")
        if data.get("error") or not isinstance(token, str) or not token or data.get("token_type", "").lower() != "bearer":
            raise OAuthError("provider_error", 502)
        response = requests.get("https://api.github.com/user", headers={
            "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": "Naml-Sign-In",
        }, timeout=12, allow_redirects=False)
        if response.status_code != 200:
            raise OAuthError("provider_error", 502)
        identity = response.json()
        ident, login = identity.get("id"), identity.get("login")
        if (type(ident) is not int or ident <= 0 or not isinstance(login, str)
                or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", login)):
            raise OAuthError("provider_error", 502)
        # email, name and username are never used to match an existing Naml user.
        return {"id": str(ident), "login": login}
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        raise OAuthError("provider_error", 502) from None


def resolve_identity(identity, flow):
    db = auth_manager.database
    github_id, login = identity["id"], identity["login"]
    with db.connection(write=True) as conn:
        keys = ["github_identities", "users", "settings"]
        if flow["intent"] == "link":
            keys.extend([flow["session_key"], "github_link_versions"])
        for key in sorted(keys):
            db.lock(conn, key)
        identities = db._get(conn, "github_identities", {})
        users = db._get(conn, "users", {})
        existing = identities.get(github_id)
        if flow["intent"] == "link":
            user_id = flow["user_id"]
            user = users.get(user_id)
            session = db._get(conn, flow["session_key"])
            if (not user or not user["is_active"] or not session or session["user_id"] != user_id
                    or datetime.fromisoformat(session["expires_at"]) <= datetime.now(timezone.utc)
                    or digest(user["password_hash"]) != flow["password_version"]
                    or db._get(conn, "github_link_versions", {}).get(user_id, 0) != flow["link_version"]):
                raise OAuthError("session_expired", 401)
            if existing and existing["user_id"] != user_id:
                raise OAuthError("identity_in_use", 409)
            if any(k != github_id and v["user_id"] == user_id for k, v in identities.items()):
                raise OAuthError("already_linked", 409)
        elif existing:
            user_id = existing["user_id"]
            if not users.get(user_id) or not users[user_id]["is_active"]:
                raise OAuthError("account_unavailable", 403)
        else:
            settings = db._get(conn, "settings", {})
            if not settings.get("system", {}).get("allow_user_registration", False):
                raise OAuthError("registration_closed", 403)
            user_id = str(uuid.uuid4())
            username = "github_" + github_id
            if any(u["username"] == username for u in users.values()):
                username += "_" + uuid.uuid4().hex[:8]
            user = User(id=user_id, username=username, password_hash="!github-only:" + secrets.token_hex(32),
                        role=UserRole.USER, is_active=True, created_at=datetime.now(timezone.utc).isoformat(),
                        last_login="", session_limit=0)
            users[user_id] = user.to_dict()
            db._put(conn, "users", users)
        identities[github_id] = {"user_id": user_id, "login": login}
        db._put(conn, "github_identities", identities)
    return user_id


def account(user):
    identities = auth_manager.database.get_document("github_identities", {})
    linked = next((v for v in identities.values() if v["user_id"] == user.id), None)
    return {"enabled": configuration() is not None, "linked": bool(linked),
            "login": linked["login"] if linked else None,
            "password_login": bool(re.fullmatch(r"[a-f0-9]{64}", user.password_hash))}


def unlink(user_id, password):
    db = auth_manager.database
    with db.connection(write=True) as conn:
        for key in sorted(["github_identities", "github_link_versions", "github_login_handoffs", "github_oauth_flows", "users"]):
            db.lock(conn, key)
        user = auth_manager._decode(db._get(conn, "users", {}).get(user_id))
        if not check_password(user, password):
            raise OAuthError("password_required", 400)
        identities = db._get(conn, "github_identities", {})
        db._put(conn, "github_identities", {k: v for k, v in identities.items() if v["user_id"] != user_id})
        versions = db._get(conn, "github_link_versions", {})
        versions[user_id] = versions.get(user_id, 0) + 1
        db._put(conn, "github_link_versions", versions)
        for key in ["github_login_handoffs", "github_oauth_flows"]:
            entries = db._get(conn, key, {})
            db._put(conn, key, {k: v for k, v in entries.items() if v.get("user_id") != user_id})


def create_handoff(user_id, github_id, old=None):
    handoff = secrets.token_urlsafe(32)
    _put_pending("github_login_handoffs", handoff, {"user_id": user_id, "github_id": github_id}, LOGIN_TTL, old)
    return handoff


def complete_login(cookie):
    payload = _consume_pending("github_login_handoffs", cookie)
    token = auth_manager.issue_token_for_user(payload["user_id"], payload["github_id"])
    if not token:
        raise OAuthError("account_unavailable", 403)
    user = auth_manager.get_user(token.user_id)
    return {"access_token": token.token, "user": {"id": user.id, "username": user.username, "role": user.role.value}}
