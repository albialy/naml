"""
NAML Reconnaissance Layer — Station 1+4 (Discovery + Evaluation)
================================================================
Pencil principle: free search via DuckDuckGo (no key, no limit),
cheap heuristic trust-scoring in pure Python (zero tokens),
and an abstract contract so crawlers/SearXNG can plug in later.
Search costs NOTHING; only the final synthesis costs tokens.
"""
import os
import re
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from urllib.parse import urlparse


# ----------------------- Trust heuristics (pencil rules) -----------------------
HIGH_TRUST_DOMAINS = {
    "fifa.com", "un.org", "who.int", "worldbank.org",
    "bbc.com", "bbc.co.uk", "reuters.com", "apnews.com", "espn.com",
    "aljazeera.net", "aljazeera.com", "alarabiya.net", "skynewsarabia.com",
    "wikipedia.org", "britannica.com", "nature.com", "sciencedirect.com",
    "arxiv.org", "nih.gov", "cdc.gov", "spa.gov.sa", "stats.gov.sa",
    "moe.gov.sa", "my.gov.sa", "transfermarkt.com", "sofascore.com",
}
LOW_TRUST_PATTERNS = ("blogspot.", "wordpress.com", ".info", "forumarabia", "answers.")


def _domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def score_result(result: Dict[str, Any]) -> float:
    """Cheap, token-free quality score. Higher = better.
    Signals: domain trust tier, https, info density in snippet."""
    score = 0.0
    url = result.get("url", "")
    snippet = result.get("snippet", "") or ""
    dom = _domain(url)

    # Domain tier
    if any(dom == d or dom.endswith("." + d) for d in HIGH_TRUST_DOMAINS):
        score += 5.0
    if dom.endswith(".gov") or dom.endswith(".edu") or ".gov." in dom or ".edu." in dom:
        score += 4.0
    if any(p in url.lower() for p in LOW_TRUST_PATTERNS):
        score -= 4.0

    # Transport
    if url.startswith("https://"):
        score += 0.5

    # Info density: numbers, dates, proper length
    digits = len(re.findall(r"\d", snippet))
    score += min(digits * 0.15, 2.0)
    if re.search(r"\b(20\d{2}|19\d{2})\b", snippet):
        score += 1.0
    if 60 <= len(snippet) <= 400:
        score += 0.5

    return score


# ----------------------------- The contract -----------------------------------
class SearchProvider(ABC):
    """Every discovery backend fulfills this. Crawler comes later as one more class."""

    @abstractmethod
    def search(self, query: str, max_results: int = 6) -> List[Dict[str, Any]]:
        """Return list of {title, url, snippet, domain, score}, best first."""
        ...


class DuckDuckGoProvider(SearchProvider):
    """Free, keyless, unlimited-enough. The pencil."""

    def search(self, query: str, max_results: int = 6) -> List[Dict[str, Any]]:
        from ddgs import DDGS
        raw = []
        for attempt in range(2):
            try:
                raw = list(DDGS().text(query, max_results=max_results * 2))
                if raw:
                    break
            except Exception:
                if attempt == 0:
                    time.sleep(2)
        results = []
        for r in raw:
            url = r.get("href") or r.get("url") or ""
            item = {
                "title": (r.get("title") or "").strip(),
                "url": url,
                "snippet": (r.get("body") or r.get("snippet") or "").strip(),
                "domain": _domain(url),
            }
            item["score"] = score_result(item)
            results.append(item)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]


def format_evidence(results: List[Dict[str, Any]]) -> str:
    """Numbered evidence block the synthesizer cites from."""
    if not results:
        return ""
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']} — {r['snippet']} (source: {r['domain']})")
    return "\n".join(lines)


# ------------------------------ Factory ----------------------------------------
_provider = None


def get_search() -> SearchProvider:
    global _provider
    if _provider is None:
        backend = os.getenv("SEARCH_PROVIDER", "duckduckgo").lower().strip()
        if backend == "duckduckgo":
            _provider = DuckDuckGoProvider()
        else:
            raise ValueError(f"Unknown SEARCH_PROVIDER '{backend}'. Available: duckduckgo")
    return _provider
