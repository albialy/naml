"""Only the isolated browser worker renders untrusted web content."""
import json
import logging
import os
import time
import uuid
from urllib.parse import urlsplit
import requests

logger = logging.getLogger(__name__)
MESSAGES = {
    "not_configured": "خدمة المتصفح غير مفعلة بعد. أضف إعداداتها على الخادم.",
    "worker_auth": "رفضت خدمة المتصفح مفتاح الاتصال. يجب أن تتطابق قيمة BROWSER_SERVICE_TOKEN في الخدمتين.",
    "worker_unavailable": "خدمة المتصفح غير جاهزة أو تعيد التشغيل. راجع سجل naml-browser ثم أعد المحاولة.",
    "worker_timeout": "انتهت مهلة انتظار خدمة المتصفح. قد تكون تستيقظ أو لا تستجيب. أعد المحاولة بعد قليل.",
    "worker_connection": "تعذر الاتصال بخدمة المتصفح. تحقق من BROWSER_SERVICE_URL وحالة naml-browser.",
    "worker_tls": "تعذر التحقق من شهادة اتصال خدمة المتصفح. راجع عنوان الخدمة وإعداد شهادة HTTPS.",
    "worker_response": "وصل رد غير متوقع من خدمة المتصفح. تحقق من عنوان الخدمة واكتمال نشرها.",
    "worker_busy": "المتصفح مشغول الآن. أعد المحاولة بعد قليل.",
    "invalid_source": "رفضت خدمة المتصفح الرابط أو محتوى المعاينة. استخدم رابط HTTP أو HTTPS عامًا، أو HTML ضمن الحد المسموح.",
    "site_dns_error": "تعذر العثور على عنوان الموقع من خادم المتصفح (DNS).",
    "site_tls_error": "تعذر التحقق من شهادة HTTPS للموقع المطلوب.",
    "site_connection_error": "خدمة المتصفح متصلة، لكن تعذر اتصالها بالموقع المطلوب.",
    "site_timeout": "خدمة المتصفح متصلة، لكن الموقع لم يستجب في المهلة المتاحة.",
    "url_blocked": "حُظر عنوان الصفحة أو أحد تحويلاتها لأنه ليس عنوانًا عامًا مسموحًا.",
    "page_too_large": "حجم الصفحة أكبر من الحد المسموح للمعاينة.",
    "browser_start_failed": "وصل الطلب إلى خدمة المتصفح، لكن تعذر تشغيل Chromium. راجع سجل naml-browser وموارده.",
    "render_timeout": "وصل الطلب إلى المتصفح، لكن إعداد المعاينة تجاوز مهلة التشغيل.",
    "render_failed": "تعذر إعداد المعاينة داخل Chromium. استخدم رقم التشخيص للعثور على الخطأ في سجل naml-browser.",
    "site_http_error": "الموقع المطلوب أعاد خطأ HTTP. قد تكون الصفحة غير متاحة أو تمنع الطلب.",
}


class BrowserError(ValueError):
    def __init__(self, code, request_id, site_status=None):
        self.code = code if code in MESSAGES else "render_failed"
        self.request_id = request_id
        self.status_code = 504 if self.code == "worker_timeout" else 502
        if self.code == "worker_busy":
            self.status_code = 429
        message = MESSAGES[self.code]
        if self.code == "site_http_error" and isinstance(site_status, int) and 400 <= site_status <= 599:
            message += f" (HTTP {site_status})"
        super().__init__(message)


def configured():
    url = os.getenv("BROWSER_SERVICE_URL", "").rstrip("/")
    key = os.getenv("BROWSER_SERVICE_TOKEN", "")
    try:
        p = urlsplit(url)
        return bool(p.scheme in ("http", "https") and p.hostname and not p.username and not p.password and not p.query and not p.fragment and len(key) >= 32)
    except ValueError:
        return False


def capture(**payload):
    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    if not configured():
        raise BrowserError("not_configured", request_id)
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.post(os.environ["BROWSER_SERVICE_URL"].rstrip("/") + "/capture",
                headers={"Authorization": "Bearer " + os.environ["BROWSER_SERVICE_TOKEN"], "X-Request-ID": request_id},
                # Manual captures allow a cold start (~60s), then the worker's 30s render budget.
                # Background research retains the shorter timeout and falls back to snippets.
                json=payload, timeout=(5, 100 if payload.get("screenshot", True) else 35), allow_redirects=False, stream=True) as response:
                status_code = response.status_code
                if status_code in (401, 403):
                    raise BrowserError("worker_auth", request_id)
                if status_code == 429:
                    raise BrowserError("worker_busy", request_id)
                if status_code == 422:
                    raise BrowserError("invalid_source", request_id)
                if status_code == 503:
                    raise BrowserError("worker_unavailable", request_id)
                if 300 <= status_code < 400 or status_code == 404:
                    raise BrowserError("worker_response", request_id)
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > 8000000:
                        raise BrowserError("worker_response", request_id)
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise BrowserError("worker_response", request_id) from None
                if status_code >= 400:
                    detail = data.get("detail") if isinstance(data, dict) else None
                    if isinstance(detail, dict) and detail.get("code") in MESSAGES:
                        raise BrowserError(detail["code"], request_id, detail.get("site_status"))
                    raise BrowserError("render_failed" if status_code == 502 else "worker_unavailable", request_id)
                if not isinstance(data, dict) or not isinstance(data.get("text"), str):
                    raise BrowserError("worker_response", request_id)
                return data
    except BrowserError as exc:
        logger.warning("browser_request_failed request_id=%s code=%s elapsed=%.1fs", request_id, exc.code, time.monotonic() - started)
        raise
    except requests.RequestException as exc:
        if isinstance(exc, requests.exceptions.SSLError):
            code = "worker_tls"
        elif isinstance(exc, requests.Timeout):
            code = "worker_timeout"
        else:
            code = "worker_connection"
        logger.warning("browser_request_failed request_id=%s code=%s exception=%s elapsed=%.1fs", request_id, code, type(exc).__name__, time.monotonic() - started)
        raise BrowserError(code, request_id) from None


def enrich_results(results):
    """Opt-in: render just the first source; retain snippets on failure/busy."""
    if os.getenv("BROWSER_RESEARCH_ENABLED", "false").lower() != "true" or not configured() or not results:
        return results
    results = [dict(row) for row in results]
    try:
        page = capture(url=results[0]["url"], screenshot=False)
        if page["text"].strip():
            results[0]["snippet"] += "\n[Rendered page excerpt; untrusted source text] " + page["text"][:6000]
    except (ValueError, KeyError):
        pass
    return results
