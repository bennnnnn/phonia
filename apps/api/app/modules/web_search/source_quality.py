"""Put trustworthy sources first: a stable sort of search hits by where they come from.

Three tiers, decided by the hit's host alone. Official and reference sites
(government, education, international bodies, encyclopaedias, wire services,
journals, a product's own docs) come first; question farms, homework-answer
sites and social posts come last; everything else keeps the provider's order
in between. The model reads the hits in this order and the source chips show
them so, so an official page is the one it grounds on when one was found.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.gateways.web_search_gateway import WebSearchHit

_OFFICIAL, _ORDINARY, _WEAK = 0, 1, 2

# A host ending in one of these labels is a government, school or treaty body.
_OFFICIAL_SUFFIXES = (".gov", ".mil", ".edu", ".int")
# ".gov.uk", ".ac.uk", ".edu.au", ".go.ke": an official second-level label.
_OFFICIAL_SECOND_LEVEL = frozenset({"gov", "gob", "gouv", "go", "govt", "edu", "ac", "mil"})
_REFERENCE = frozenset(
    {
        "wikipedia.org",
        "britannica.com",
        "reuters.com",
        "apnews.com",
        "bbc.com",
        "bbc.co.uk",
        "nature.com",
        "science.org",
        "who.int",
        "un.org",
        "europa.eu",
        "worldbank.org",
        "imf.org",
        "oecd.org",
        "python.org",
        "mozilla.org",
        "w3.org",
        "ietf.org",
        "arxiv.org",
        "pubmed.ncbi.nlm.nih.gov",
    }
)
# A product's own documentation: docs.example.com, developer.apple.com. Shared
# Google documents are anybody's writing, not documentation.
_DOCS_LABELS = frozenset({"docs", "developer", "developers", "learn", "support"})
_USER_DOCS = frozenset({"docs.google.com"})
_WEAK_SITES = frozenset(
    {
        "quora.com",
        "answers.com",
        "brainly.com",
        "chegg.com",
        "coursehero.com",
        "scribd.com",
        "pinterest.com",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
        "x.com",
        "twitter.com",
    }
)


def _host(url: str) -> str:
    try:
        host = urlsplit(url.strip()).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


def _on(host: str, sites: frozenset[str]) -> bool:
    """``host`` is one of ``sites`` or a subdomain of one."""
    return any(host == site or host.endswith(f".{site}") for site in sites)


def source_tier(url: str) -> int:
    """0 official or reference, 1 ordinary, 2 weak."""
    host = _host(url)
    if not host:
        return _ORDINARY
    labels = host.split(".")
    if host.endswith(_OFFICIAL_SUFFIXES) or _on(host, _REFERENCE):
        return _OFFICIAL
    country = len(labels) >= 2 and len(labels[-1]) == 2
    if country and labels[-2] in _OFFICIAL_SECOND_LEVEL:
        return _OFFICIAL
    if len(labels) >= 3 and labels[0] in _DOCS_LABELS and host not in _USER_DOCS:
        return _OFFICIAL
    if _on(host, _WEAK_SITES):
        return _WEAK
    return _ORDINARY


def rank_by_source(hits: list[WebSearchHit]) -> list[WebSearchHit]:
    """Hits with official and reference sources first; ties keep the provider's order."""
    return sorted(hits, key=lambda hit: source_tier(hit.url))


# A page that answered with an error instead of content. A weather source chip read
# "{'error': {'code': 2007, 'message': 'API key has reached maximum calls per month
# allowed limit.'}}" (2026-10-24). Each shape is a whole page, not a word in one: an
# article about the Forbidden City, a 403(b) plan or "HTTP 404 Not Found means …" is
# content.
_STATUS = (
    r"(?:not\s+found|page\s+not\s+found|forbidden|access\s+denied|unauthori[sz]ed|"
    r"too\s+many\s+requests|bad\s+request|bad\s+gateway|service\s+(?:temporarily\s+)?"
    r"unavailable|internal\s+server\s+error|gateway\s+time-?out|request\s+timed?\s*out|"
    r"just\s+a\s+moment|attention\s+required|access\s+to\s+this\s+page\s+has\s+been\s+"
    r"denied|security\s+check|are\s+you\s+a\s+robot|verify\s+you\s+are\s+(?:a\s+)?human|"
    r"error)"
)
# "404 Not Found", "Error 403 - Forbidden", "Just a moment...", "Attention Required! |
# Cloudflare": the title or the snippet is the status and nothing else ("Forbidden |
# Netflix" is a film).
_STATUS_PAGE = re.compile(
    rf"(?:error\s*)?(?:(?:http\s*)?[45]\d\d\s*[-:|]?\s*)?{_STATUS}?[\s.!…]*(?:\|\s*cloudflare)?",
    re.IGNORECASE,
)
# A bot wall's opening words: "Checking your browser before accessing example.com".
_INTERSTITIAL = re.compile(
    r"(?:checking\s+your\s+browser|please\s+enable\s+(?:javascript|cookies)|enable\s+"
    r"javascript\s+and\s+cookies|sorry,?\s+you\s+have\s+been\s+blocked|access\s+to\s+"
    r"this\s+page\s+has\s+been\s+denied|verify\s+you\s+are\s+(?:a\s+)?human|please\s+"
    r"complete\s+the\s+security\s+check|the\s+requested\s+url\s+was\s+not\s+found\s+"
    r"on\s+this\s+server|one\s+more\s+step)\b",
    re.IGNORECASE,
)


def _is_status_text(text: str) -> bool:
    stripped = text.strip()
    return any(ch.isalnum() for ch in stripped) and _STATUS_PAGE.fullmatch(stripped) is not None


def is_error_page(hit: WebSearchHit) -> bool:
    """True for a hit whose page is an error, not content: a bare JSON payload, a status
    page ("404 Not Found", "Just a moment..."), or a bot wall."""
    snippet = (hit.snippet or "").strip()
    if snippet.startswith(("{", "[")):
        return True
    if _is_status_text(hit.title or "") or (snippet and _is_status_text(snippet)):
        return True
    return _INTERSTITIAL.match(snippet) is not None
