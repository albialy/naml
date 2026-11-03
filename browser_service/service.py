"""Isolated Chromium worker. No Naml database, credentials or persistent profiles."""
import asyncio
import base64
import hmac
import ipaddress
import os
import socket
from urllib.parse import urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel, Field, model_validator
from playwright.async_api import async_playwright

app = FastAPI(docs_url=None, redoc_url=None)
slot = asyncio.Semaphore(1)


def check_url(url):
    if len(url) > 4096 or any(ord(c) < 33 for c in url) or "\\" in url:
        raise ValueError("Invalid URL")
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise ValueError("Only public HTTP(S) URLs are allowed")
    if p.port not in (None, 80, 443):
        raise ValueError("Port is not allowed")
    host = p.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Private address")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if not address.is_global or address.is_multicast or (isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped):
        raise ValueError("Private address")
    return host


class PublicResolver(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        rows = await asyncio.get_running_loop().getaddrinfo(host, port, family=family, type=socket.SOCK_STREAM)
        result = []
        for af, _, proto, _, sockaddr in rows:
            ip = ipaddress.ip_address(sockaddr[0])
            if not ip.is_global or ip.is_multicast or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped):
                raise OSError("Private DNS answer blocked")
            result.append(dict(hostname=host, host=str(ip), port=port, family=af, proto=proto, flags=socket.AI_NUMERICHOST))
        return result

    async def close(self):
        pass


class Capture(BaseModel):
    url: str | None = Field(default=None, max_length=4096)
    html: str | None = Field(default=None, max_length=200000)
    mobile: bool = False
    screenshot: bool = True

    @model_validator(mode="after")
    def validate_source(self):
        if bool(self.url) == bool(self.html):
            raise ValueError("Provide exactly one of url or html")
        if self.url:
            check_url(self.url)
        return self


def authorize(authorization: str = Header(default="")):
    key = os.getenv("BROWSER_SERVICE_TOKEN", "")
    if len(key) < 32:
        raise HTTPException(503, "Browser token is not configured")
    if not hmac.compare_digest(authorization, "Bearer " + key):
        raise HTTPException(401, "Unauthorized")


@app.get("/health")
def health():
    return {"status": "ok"}


async def render(spec: Capture):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(chromium_sandbox=True, args=["--disable-dev-shm-usage", "--disable-quic", "--disable-background-networking", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"])
        try:
            context = await browser.new_context(viewport={"width": 390 if spec.mobile else 1360, "height": 844 if spec.mobile else 900},
                service_workers="block", accept_downloads=False, java_script_enabled=not bool(spec.html))
            await context.route_web_socket("**/*", lambda ws: ws.close())
            connector = aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False)
            count, total, blocked = 0, 0, 0
            async with aiohttp.ClientSession(connector=connector, trust_env=False, cookie_jar=aiohttp.DummyCookieJar(), timeout=aiohttp.ClientTimeout(total=10)) as http:
                async def route_request(route):
                    nonlocal count, total, blocked
                    count += 1
                    try:
                        req = route.request
                        if spec.html or count > 80 or total > 12000000 or req.method != "GET" or req.resource_type in ("media", "websocket"):
                            raise ValueError("Blocked")
                        check_url(req.url)
                        # Resolve and connect with the SAME validated IP; no DNS rebinding gap.
                        async with http.get(req.url, allow_redirects=False, headers={"User-Agent": "NamlBrowser/1.0"}) as response:
                            body = bytearray()
                            async for chunk in response.content.iter_chunked(65536):
                                total += len(chunk)
                                body.extend(chunk)
                                if len(body) > 2000000 or total > 12000000:
                                    raise ValueError("Page too large")
                            headers = {k: v for k, v in response.headers.items() if k.lower() in ("content-type", "location")}
                            await route.fulfill(status=response.status, headers=headers, body=bytes(body))
                    except Exception:
                        blocked += 1
                        await route.abort()
                await context.route("**/*", route_request)
                page = await context.new_page()
                if spec.url:
                    response = await page.goto(spec.url, wait_until="domcontentloaded", timeout=18000)
                    if response and response.status >= 400:
                        raise ValueError("Website returned an error")
                    await page.wait_for_timeout(800)
                else:
                    await page.set_content(spec.html, wait_until="domcontentloaded", timeout=5000)
                title = await page.title()
                content = (await page.locator("body").inner_text(timeout=5000))[:16000]
                png = await page.screenshot(type="png", full_page=False, timeout=5000) if spec.screenshot else None
                return {"title": title[:300], "url": page.url if spec.url else None, "text": content,
                    "screenshot": base64.b64encode(png).decode() if png else None,
                    "blocked_requests": blocked, "truncated": len(content) == 16000}
        finally:
            await browser.close()


@app.post("/capture", dependencies=[Depends(authorize)])
async def capture(spec: Capture):
    try:
        await asyncio.wait_for(slot.acquire(), timeout=0.1)
    except TimeoutError:
        raise HTTPException(429, "Browser busy")
    try:
        return await asyncio.wait_for(render(spec), timeout=30)
    except Exception:
        raise HTTPException(502, "Browser capture failed")
    finally:
        slot.release()
