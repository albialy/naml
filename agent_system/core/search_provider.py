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


HIGH_TRUST_DOMAINS = {
    "fifa.com", "un.org", "who.int", "worldbank.org",
    "bbc.com", "bbc.co.uk", "reuters.com", "apnews.com", "espn.com",
    "aljazeera.net", "aljazeera.com", "alarabiya.net", "skynewsarabia.com",
    "wikipedia.org", "britannica.com", "nature.com", "sciencedirect.com",
    "arxiv.org", "nih.gov", "cdc.gov", "spa.gov.sa", "stats.gov.sa",
    "moe.gov.sa", "my.gov.sa", "transfermarkt.com", "sofascore.com",
}
LOW_TRUST_PATTERNS = ("blogspot.", "wordpress.com", ".info", "forumarabia", "answers.")

TOPIC_TRUST_BOOST = {
    ("earthquake", "زلزال", "seismic", "زلازل"): {
        "earthquake.usgs.gov": 10.0, "usgs.gov": 9.0, "emsc.eu": 9.0,
        "emsc-csem.org": 9.0, "nriag.sci.eg": 9.0,
    },
    ("world cup", "fifa", "كأس العالم", "مونديال"): {
        "fifa.com": 10.0, "espn.com": 7.0, "transfermarkt.com": 6.0,
    },
    ("weather", "طقس", "temperature", "حرارة"): {
        "accuweather.com": 8.0, "weather.com": 8.0,
    },
}


def _domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def _topic_boost(query: str, domain: str) -> float:
    q_lower = query.lower()
    boost = 0.0
    for keywords, domain_boosts in TOPIC_TRUST_BOOST.items():
        if any(kw in q_lower for kw in keywords):
            for trusted_domain, weight in domain_boosts.items():
                if domain == trusted_domain or domain.endswith("." + trusted_domain):
                    boost = max(boost, weight)
    return boost


def score_result(result: Dict[str, Any], query: str = "") -> float:
    score = 0.0
    url = result.get("url", "")
    snippet = result.get("snippet", "") or ""
    dom = _domain(url)

    score += _topic_boost(query, dom)

    if any(dom == d or dom.endswith("." + d) for d in HIGH_TRUST_DOMAINS):
        score += 5.0
    if dom.endswith(".gov") or dom.endswith(".edu") or ".gov." in dom or ".edu." in dom:
        score += 4.0
    if any(p in url.lower() for p in LOW_TRUST_PATTERNS):
        score -= 4.0

    if url.startswith("https://"):
        score += 0.5

    digits = len(re.findall(r"\d", snippet))
    score += min(digits * 0.15, 2.0)
    if re.search(r"\b(20\d{2}|19\d{2})\b", snippet):
        score += 1.0
    if 60 <= len(snippet) <= 400:
        score += 0.5

    return score


def _has_topic_authority(results: List[Dict[str, Any]], query: str) -> bool:
    q_lower = query.lower()
    for keywords, domain_boosts in TOPIC_TRUST_BOOST.items():
        if any(kw in q_lower for kw in keywords):
            trusted = set(domain_boosts.keys())
            return any(
                any(r["domain"] == d or r["domain"].endswith("." + d) for d in trusted)
                for r in results
            )
    return True


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 6) -> List[Dict[str, Any]]:
        ...


class DuckDuckGoProvider(SearchProvider):
    def _raw_search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
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
            item["score"] = score_result(item, query)
            results.append(item)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]

    def search(self, query: str, max_results: int = 6) -> List[Dict[str, Any]]:
        results = self._raw_search(query, max_results)
        if results and not _has_topic_authority(results, query):
            sharper_query = f"{query} official authoritative source"
            retry_results = self._raw_search(sharper_query, max_results)
            if _has_topic_authority(retry_results, query):
                results = retry_results
        return results


def format_evidence(results: List[Dict[str, Any]]) -> str:
    if not results:
        return ""
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']} — {r['snippet']} (source: {r['domain']})")
    return "\n".join(lines)


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
