"""Format search hits for prompts and mobile source cards."""

from __future__ import annotations

import json
import re
from typing import TypedDict

from app.gateways.web_search_gateway import WebSearchHit
from app.modules.web_search.patterns import (
    _ADDRESS_RE,
    _NUMBERED_VENUE_LINE,
    _PRICE_RE,
)
from app.modules.web_search.source_dates import (
    local_today,
    mark_dates,
    published_note,
    stale_note,
)
from app.modules.web_search.source_tables import flowed_snippet
from app.services.md_fence_scan import (
    iter_fences,
    strip_closed_fences,
)


def _extract_address_from_snippet(snippet: str) -> str | None:
    match = _ADDRESS_RE.search(snippet)
    if not match:
        return None
    return match.group(1).strip(" ,.")


def _extract_price_from_snippet(snippet: str) -> str | None:
    match = _PRICE_RE.search(snippet)
    return match.group(1) if match else None


WEB_SEARCH_HINT = (
    "Live web search results come as a **Web search results** block just before the "
    "user's latest message, or as the web_search tool's result. "
    "When either is present, ground your answer in those results "
    "(scores, dates, headlines, facts). If none of them answers the question, say so "
    'plainly ("I couldn\'t find a source that covers that") instead of stretching an '
    "off-topic result or filling in from memory. "
    'Say where a retrieved fact comes from by naming the source ("According to Reuters, '
    '...", or its [n] marker), never "the search results" or "the results"; keep your '
    "own explanation or background apart from what the sources say. "
    "Never say search failed or that you cannot browse when results were provided. "
    "For today/current/latest news, use the current local date in the time context and only "
    "call an event today's when a result explicitly supports that date. Older, future, or "
    "undated snippets are not today's news; say when fewer requested items can be verified. "
    "When the user asks about a specific team or country, only report that entity's results "
    "from the snippets — do NOT attach unrelated tournament results (e.g. World Cup group "
    "stage) to a team unless that team appears in the results. If results show the team "
    "did not qualify or has no match in that tournament, say so clearly. "
    "Do NOT offer fictional results, tournament-schedule guesses, or 'probably Matchday X' "
    "speculation. "
    "When the user asks for anything nearby or at a distance (venues, directions, "
    "how far, travel time), give a one-sentence intro then a ```places fence with JSON "
    "when listing findable places (see format hint). For mileage-only answers, state "
    "distance and time in prose — no ```places fence. "
    "The app renders places blocks natively — do NOT also hand-format a markdown list. "
    "If you must use markdown links instead, use [Name](https://url) with parentheses "
    "around the URL — never $url$ delimiters — and link only pages from the results. "
    "When search returned no hits, say you could not verify that live right now — "
    "do NOT guess why or fill in from training data. When the block says the search "
    "failed, say the search didn't work just now, not that nothing exists. "
    "Do NOT add a separate Sources section — the app renders source cards. "
    "Never role-play searching. "
    "If neither is in this prompt, do not claim you searched the live web: call the "
    "web_search tool when it is offered, else answer from knowledge or say you don't have "
    "live results. "
    "Recall does search the web when the user asks: never say you can't browse, can't "
    "search or have no internet access. If the user asked for a search and no results "
    "came with this turn, say you couldn't find it this time and ask them to name the "
    "person, place or thing in full, in one short sentence."
)


def format_search_block(
    hits: list[WebSearchHit],
    *,
    team: str | None = None,
    local_places: bool = False,
    user_location: str | None = None,
    user_timezone: str | None = None,
) -> str:
    lines = [
        "Web search results (retrieved just now — ground your answer in these):",
    ]
    if local_places and not (user_location or "").strip():
        lines.append(
            "User location is not set — nearby results may be less precise. "
            "If they asked for 'near me', briefly suggest Settings → Location."
        )
    if team:
        lines.append(
            f"The user asked about **{team}**. Only report scores or tournament status for "
            f"{team} — do not attribute other teams' World Cup results to them."
        )
    # Each dated day says how long ago it was, and a page that calls a time already past
    # still to come says it is a forecast.
    today = local_today(user_timezone)
    for index, hit in enumerate(hits, start=1):
        snippet = flowed_snippet(mark_dates(hit.snippet, today), indent="   ")
        note = published_note(hit.published, today, user_timezone) + stale_note(hit.snippet, today)
        lines.append(f"{index}. {hit.title} ({hit.url}) — {note}{snippet}")
    if local_places:
        seed = places_payload_from_hits(hits)
        seed_block = ""
        if seed:
            seed_block = (
                "\nStarter JSON (refine name/url/note from snippets; include every real venue):\n"
                f"```places\n{json.dumps(seed, ensure_ascii=False)}\n```\n"
            )
        lines.append(
            "Required: one-sentence intro, then a ```places fence with JSON array "
            '[{"name":"Venue","url":"https://www.google.com/maps/search/?api=1&query=...",'
            '"note":"optional","address":"street when known","price":"$$"}]. '
            "url must be a Google Maps link to the venue address — never a generic search page. "
            "Do NOT also output a markdown numbered list of venues."
            f"{seed_block}"
        )
    elif team:
        lines.append(
            f"Required: answer using the results above for **{team}** only. "
            "Include concrete scores and dates when snippets mention them. "
            f"If none of them gives {team}'s result, say so; do not guess one. "
            "Do not paste this list — the app shows source cards."
        )
    else:
        lines.append(
            "Required: answer the user's question from the results above, saying which "
            "site a fact comes from. If none of them answers it, say you couldn't find a "
            "source that covers it — do not fill the gap from memory or stretch an unrelated "
            "result. "
            "If they named a team or country, only use snippets about that entity — never "
            "attribute generic tournament results to them unless they appear in the snippet. "
            "If snippets show they did not qualify for a tournament, say so. "
            "Include concrete scores, teams, and dates when the snippets mention them. "
            "Do not paste this list — the app shows source cards."
        )
    return "\n".join(lines)


LOCAL_PLACES_FORMAT_HINT = (
    "Local places output (any nearby venue the user asked for):\n"
    "- One short intro sentence, then ONLY a ```places JSON fence — no duplicate markdown list.\n"
    '- Schema: [{"name":"Venue","url":"https://www.google.com/maps/search/?api=1&query=...",'
    '"note":"rating/cuisine","address":"street, city","price":"$$"}]\n'
    "- url MUST open the venue on Google Maps (use address in the query). "
    "Never use generic Yelp/Google search pages.\n"
    "- address is required when the snippet mentions a street or neighborhood.\n"
    "- price is optional plain text like $, $$, or $$$ — never inside the url field."
)

AMBIGUOUS_NEARBY_HINT = (
    "The user's nearby request is underspecified (e.g. 'nearest house' without sale vs rent "
    "vs a specific address). Do NOT web-search or guess listings yet. Ask 1-3 concise "
    "clarifying questions — e.g. homes for sale near their location, rentals, or nearest to "
    "a specific address. No ```places fence and no listing links until they clarify."
)

GEO_DISTANCE_HINT = (
    "Distance / travel query: use the user's location and search results. Give concrete "
    "miles or km and drive/walk time when available. Do NOT use a ```places fence unless "
    "they also asked to find venues."
)

GEO_ACTIVE_LOCATION_HINT = (
    "The user's current device location for this nearby/distance query is shown above. "
    "Use that location in your answer — do not substitute another city from memory or profile."
)


def _is_generic_search_url(url: str) -> bool:
    lowered = url.strip().lower()
    if not lowered:
        return True
    if "yelp.com/search" in lowered:
        return True
    if "google.com/search" in lowered:
        return True
    if "bing.com/search" in lowered:
        return True
    return False


def _maps_url_for_place(name: str, address: str | None = None) -> str:
    query = name.strip()
    if address and address.strip():
        addr = address.strip()
        if query.lower() not in addr.lower():
            query = f"{query}, {addr}"
        else:
            query = addr
    from urllib.parse import quote

    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"


def places_payload_from_hits(hits: list[WebSearchHit]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for hit in hits[:8]:
        name = hit.title.strip()
        if not name:
            continue
        url = hit.url.strip()
        snippet = hit.snippet.replace("\n", " ").strip()
        address = _extract_address_from_snippet(snippet)
        price = _extract_price_from_snippet(snippet)
        row: dict[str, str] = {"name": name}
        note = snippet
        if price:
            row["price"] = price
            note = note.replace(price, "").strip(" ,-\u2013\u2014()")
        if address:
            row["address"] = address
        if note:
            row["note"] = _sanitize_fence_json_text(note[:160])
        if url and not _is_generic_search_url(url):
            row["url"] = url
        else:
            row["url"] = _maps_url_for_place(name, address or (snippet[:120] if snippet else None))
        rows.append(row)
    return rows


def format_places_fence(hits: list[WebSearchHit]) -> str:
    from app.services.places_fence import parse_places_payload, places_payload_dicts

    payload = places_payload_dicts(parse_places_payload(places_payload_from_hits(hits)))
    if not payload:
        return ""
    return f"\n\n```places\n{json.dumps(payload, ensure_ascii=False)}\n```"


def strip_duplicate_venue_list(text: str) -> str:
    """Drop model-numbered venue lists when the app renders a ```places block."""
    lines = text.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        if _NUMBERED_VENUE_LINE.match(lines[index]):
            run_end = index
            count = 0
            while run_end < len(lines):
                line = lines[run_end]
                if _NUMBERED_VENUE_LINE.match(line):
                    count += 1
                    run_end += 1
                elif not line.strip():
                    run_end += 1
                else:
                    break
            if count >= 2:
                index = run_end
                continue
        out.append(lines[index])
        index += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


_SOURCES_LABEL_RE = re.compile(r"(?:\*\*)?sources(?:\*\*)?\s*:?\s*$", re.IGNORECASE)


def _sanitize_fence_json_text(value: str) -> str:
    """Backticks inside a fenced JSON body would terminate the fence on reload."""
    return value.replace("```", "'''").replace("`", "'")


def _parse_sources_json(raw: str) -> list[dict[str, str]]:
    # A closer the model left glued to the JSON.
    text = raw.strip().rstrip("`").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    rows: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title and not url:
            continue
        row = {"title": title or url, "url": url}
        snippet = str(item.get("snippet") or "").strip()
        if snippet:
            row["snippet"] = snippet
        rows.append(row)
    return rows


def _strip_bare_source_array_fences(text: str) -> str:
    """Drop unlabeled ``` fences whose body is a sources JSON array."""
    pieces: list[str] = []
    index = 0
    for fence in iter_fences(text):
        body = text[fence.body_start : fence.body_end]
        if fence.closed and not fence.opener.info and _parse_sources_json(body):
            pieces.append(text[index : fence.start])
            index = fence.end
    pieces.append(text[index:])
    return "".join(pieces)


def strip_sources_from_text(text: str) -> str:
    """Remove ```sources fences and unlabeled source-JSON fences from assistant text."""
    cleaned = strip_closed_fences(text, "sources")
    cleaned = _strip_bare_source_array_fences(cleaned)
    cleaned = _SOURCES_LABEL_RE.sub("", cleaned).rstrip()
    return cleaned.rstrip()


def format_sources_fence(hits: list[WebSearchHit]) -> str:
    if not hits:
        return ""
    return f"\n\n```sources\n{json.dumps(sources_payload(hits), ensure_ascii=False)}\n```"


class SearchSource(TypedDict):
    """One source chip under a searched reply."""

    title: str
    url: str
    snippet: str


def sources_payload(hits: list[WebSearchHit]) -> list[SearchSource]:
    rows: list[SearchSource] = []
    for hit in hits:
        snippet = _sanitize_fence_json_text(hit.snippet[:280])
        rows.append({"title": hit.title, "url": hit.url, "snippet": snippet})
    return rows


def format_search_empty_block(
    queries: list[str], *, local_places: bool = False, failed: bool = False
) -> str:
    """The block for a search that came back with nothing, or that failed (``failed``)."""
    tried = ", ".join(f'"{q}"' for q in queries[:3])
    if failed:
        return (
            f"Web search was attempted ({tried}) but the search service failed, so "
            "nothing was retrieved.\n"
            "Tell the user in one sentence that the search didn't work just now and to try "
            "again shortly. Do not say nothing exists, and do not present an answer from "
            "memory as checked or current."
        )
    if local_places:
        return (
            f"Web search was run ({tried}) but returned no usable results.\n"
            "Tell the user live search found nothing useful — one short sentence only. "
            "Do NOT invent restaurant names, addresses, or ratings from memory."
        )
    return (
        f"Web search was run ({tried}) but returned no usable results.\n"
        "Reply in one sentence that you could not verify that live right now. "
        "Do NOT invent tournament schedules, Matchday guesses, off-season explanations, "
        "or scores from memory. Do not fill in from training data."
    )
