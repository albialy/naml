from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from agent_system.core.auth import github_oauth as oauth
from agent_system.core.auth.manager import auth_manager
from agent_system.core.auth.middleware import get_current_user, security
from agent_system.core.auth.models import User

router = APIRouter()


class PasswordConfirmation(BaseModel):
    password: str = Field(min_length=1, max_length=1000)


def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def cookie(response, name, value, config, ttl, same_site="lax"):
    response.set_cookie(oauth.cookie_name(name, config.secure), value, max_age=ttl, path=oauth.COOKIE_PATH,
                        secure=config.secure, httponly=True, samesite=same_site)


def clear(response, name, secure=True):
    response.delete_cookie(oauth.cookie_name(name, secure), path=oauth.COOKIE_PATH, secure=secure, httponly=True, samesite="lax")


def browser_cookie(request, name, config):
    return request.cookies.get(oauth.cookie_name(name, config.secure))


def failed(code, config=None, intent="login"):
    # Fixed paths and internal error identifiers only; never echo provider errors.
    path = "/settings" if intent == "link" else "/login"
    response = RedirectResponse((config.origin if config else "") + path + "?github_error=" + code, status_code=303)
    clear(response, oauth.FLOW_COOKIE, config.secure if config else True)
    clear(response, oauth.LOGIN_COOKIE, config.secure if config else True)
    return private_response(response)


def api_failure(error):
    raise HTTPException(error.status, detail={"code": error.code, "error": "تعذر إكمال إجراء GitHub"})


@router.get("/api/auth/providers")
def providers():
    return private_response(JSONResponse({"github": {"enabled": oauth.configuration() is not None}}))


@router.get("/api/auth/github/start")
def start(request: Request):
    config = oauth.configuration()
    try:
        if not config:
            raise oauth.OAuthError("unavailable", 503)
        state, url = oauth.begin(config, browser_cookie(request, oauth.FLOW_COOKIE, config))
        response = RedirectResponse(url, status_code=303)
        cookie(response, oauth.FLOW_COOKIE, state, config, oauth.FLOW_TTL)
        clear(response, oauth.LOGIN_COOKIE, config.secure)
        return private_response(response)
    except oauth.OAuthError as error:
        return failed(error.code, config)


@router.get("/api/auth/github/account")
def account(current_user: User = Depends(get_current_user)):
    return private_response(JSONResponse(oauth.account(current_user)))


@router.post("/api/auth/github/link")
def link(request: Request, body: PasswordConfirmation,
         current_user: User = Depends(get_current_user),
         credentials: HTTPAuthorizationCredentials = Security(security)):
    try:
        config = oauth.configured()
        if not oauth.check_password(current_user, body.password):
            raise oauth.OAuthError("password_required", 400)
        state, url = oauth.begin(config, browser_cookie(request, oauth.FLOW_COOKIE, config), current_user,
                                auth_manager._token_key(credentials.credentials))
        response = JSONResponse({"authorization_url": url})
        cookie(response, oauth.FLOW_COOKIE, state, config, oauth.FLOW_TTL)
        return private_response(response)
    except oauth.OAuthError as error:
        api_failure(error)


@router.delete("/api/auth/github/link")
def unlink(body: PasswordConfirmation, current_user: User = Depends(get_current_user)):
    try:
        oauth.unlink(current_user.id, body.password)
        return private_response(JSONResponse({"success": True}))
    except oauth.OAuthError as error:
        api_failure(error)


@router.get("/api/auth/github/callback")
def callback(request: Request, state: str = "", code: str = "", error: str = ""):
    config = oauth.configuration()
    flow = {}
    try:
        if not config:
            raise oauth.OAuthError("unavailable", 503)
        flow = oauth.consume_flow(config, state, browser_cookie(request, oauth.FLOW_COOKIE, config))
        if error:
            raise oauth.OAuthError("denied")
        if not code or len(code) > 1000:
            raise oauth.OAuthError("provider_error")
        identity = oauth.fetch_identity(config, code, flow["verifier"])
        user_id = oauth.resolve_identity(identity, flow)
        if flow["intent"] == "link":
            response = RedirectResponse(config.origin + "/settings?github=linked", status_code=303)
        else:
            handoff = oauth.create_handoff(user_id, identity["id"], browser_cookie(request, oauth.LOGIN_COOKIE, config))
            response = RedirectResponse(config.origin + "/auth/github/complete", status_code=303)
            cookie(response, oauth.LOGIN_COOKIE, handoff, config, oauth.LOGIN_TTL, "strict")
        clear(response, oauth.FLOW_COOKIE, config.secure)
        return private_response(response)
    except oauth.OAuthError as error:
        return failed(error.code, config, flow.get("intent", "login"))


@router.post("/api/auth/github/complete")
def complete(request: Request):
    try:
        config = oauth.configured()
        if request.headers.get("origin") != config.origin:
            raise oauth.OAuthError("invalid_origin", 403)
        result = oauth.complete_login(browser_cookie(request, oauth.LOGIN_COOKIE, config))
        response = JSONResponse(result)
        clear(response, oauth.LOGIN_COOKIE, config.secure)
        return private_response(response)
    except oauth.OAuthError as error:
        api_failure(error)
