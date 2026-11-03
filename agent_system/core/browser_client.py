"""Only the isolated browser worker renders untrusted web content."""
import os
from urllib.parse import urlsplit
import requests


def configured():
    url = os.getenv("BROWSER_SERVICE_URL", "").rstrip("/")
    key = os.getenv("BROWSER_SERVICE_TOKEN", "")
    p = urlsplit(url)
    return bool(p.scheme in ("http", "https") and p.hostname and not p.username and not p.password and not p.query and not p.fragment and len(key) >= 32)


def capture(**payload):
    if not configured():
        raise ValueError("خدمة المتصفح غير مفعلة بعد. أضف إعداداتها على الخادم.")
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.post(os.environ["BROWSER_SERVICE_URL"].rstrip("/") + "/capture",
                headers={"Authorization": "Bearer " + os.environ["BROWSER_SERVICE_TOKEN"]},
                json=payload, timeout=(5, 35), allow_redirects=False, stream=True) as response:
                if response.status_code == 429:
                    raise ValueError("المتصفح مشغول الآن. أعد المحاولة بعد قليل.")
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > 8000000:
                        raise ValueError("نتيجة المتصفح أكبر من الحد المسموح.")
                import json
                data = json.loads(raw)
                if not isinstance(data, dict) or not isinstance(data.get("text"), str):
                    raise ValueError("استجابة غير صالحة من خدمة المتصفح.")
                return data
    except requests.RequestException:
        raise ValueError("تعذر فتح الصفحة. تحقق من الرابط وحالة خدمة المتصفح.") from None


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
