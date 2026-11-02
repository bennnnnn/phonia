"""Asks whose answer is live: job openings, prices and rates, and visa rules.

A model's memory of either is stale by the time anyone asks. Both used to reach
only the web-search classifier (4 seconds, no backup model), so a slow or failed
call answered "find remote backend engineering jobs" or "how much does the iPhone
17 Pro cost" from training data. Each rule names what is looked up, so "I got the
job", "cron job", "job interview tips", "how should I price my course" and "the
price of freedom" stay ordinary chat. Whether a named thing is out yet is
``release_asks``'s.

Match against ``collapse_ws``-normalized input (single spaces).
"""

from __future__ import annotations

import re

from app.modules.web_search.patterns import collapse_ws

# Words that make "positions", "roles" or "openings" jobs ("yoga positions", "chess
# openings" are not).
_ROLE = (
    r"engineer(?:ing)?|developer|dev|programmer|designer|analyst|scientist|manager|"
    r"nurse|nursing|teacher|teaching|accountant|accounting|marketing|sales|data|software|"
    r"backend|back-end|frontend|front-end|full-?stack|devops|product|python|java|"
    r"javascript|typescript|react|node|golang|remote|entry-level|junior|senior|"
    r"graduate|part-time|full-time|freelance|research|writer|editor|driver|intern|tech|"
    r"security|cloud"
)
_ROLE_PHRASE = rf"(?:{_ROLE})(?: [\w-]+){{0,2}}"
# A listing by its name alone: "job openings", "vacancies", "developer openings".
_LISTING_NOUN = re.compile(
    rf"\bjob (?:openings?|postings?|listings?|vacanc(?:y|ies))\b|\bvacanc(?:y|ies)\b"
    rf"|\b{_ROLE_PHRASE} openings\b|\bwho(?:'s| is) hiring\b|\bhiring (?:now|in)\b",
    re.IGNORECASE,
)
# Jobs that a cue makes a listing: "remote jobs", "find data analyst roles".
_JOBS = re.compile(rf"\b(?:jobs|internships|{_ROLE_PHRASE} (?:positions|roles))\b", re.I)
_LISTING_CUE = re.compile(
    r"\b(?:find|search|look(?:ing)? for|show me|list|any|get me|hiring|posted|open|"
    r"available|remote|near me|today|this week|latest|new|where can i (?:find|apply))\b"
    r"|(?-i:\b(?:in|at|for) [A-Z][\w&.-]+)",
    re.IGNORECASE,
)
# One job needs a search verb and says what or where: "find me a job as a nurse in Nairobi".
_ONE_JOB = re.compile(
    r"\b(?:find|search for|show me|get me|list) (?:me )?(?:a |an )?(?:[\w-]+ ){0,3}?job"
    r"(?: as an? [\w-]+| in [\w-]+| near me| at [\w&.-]+)",
    re.IGNORECASE,
)
# A job of another kind, praise, a person, or a career question.
_NOT_A_LISTING = re.compile(
    r"\b(?:cron|kubernetes|k8s|batch|background|celery|sidekiq|worker|queued?|scheduled|"
    r"scheduler|ci|pipeline|print|spark|airflow|slurm|etl|nightly|async|gitlab|jenkins)"
    r" jobs?\b"
    r"|\b(?:good|great|nice|amazing|awesome|excellent|fantastic|brilliant|terrible|bad|"
    r"lovely|solid|decent|wonderful) job\b|\bsteve jobs\b|\bjobs to be done\b"
    r"|\bjob (?:interview|description|title|application|hunt(?:ing)?|search tips)\b"
    r"|\b(?:write|draft|compose|rewrite|edit|proofread|improve|review)\b"
    r"|\bhow (?:do|can|should|would|could) (?:i|you|we|one) (?:find|get|land|apply)\b",
    re.IGNORECASE,
)

_CURRENCY = (
    r"usd|eur|gbp|jpy|cny|inr|etb|kes|ngn|zar|chf|cad|aud|mxn|aed|sar|krw|try|"
    r"dollars?|euros?|pounds?|yen|yuan|rupees?|birr|shillings?|naira|rand|francs?|pesos?|"
    r"rubles?|lira|dirhams?|riyals?|won"
)
_ASSET = (
    r"bitcoin|btc|ethereum|eth|solana|dogecoin|crypto|gold|silver|platinum|oil|crude|"
    r"brent|petrol|gasoline|diesel|fuel"
)
# A named thing: a capital mid-sentence, a model number ("PS5", "M4"), or a product line.
_NAMED_THING = (
    r"(?:(?-i:(?!I\b)[A-Z][\w-]*)|[a-z]+\d[\w-]*|\d+[a-z]+\b|iphone|ipad|macbook|pixel|"
    r"galaxy|playstation|xbox|airpods|tesla|rtx|nintendo|kindle|surface)"
)
_PRICE = re.compile(
    rf"\bexchange rates?\b"
    rf"|\b(?:{_CURRENCY}) (?:to|in|vs|against) (?:{_CURRENCY})\b"
    rf"|\bhow many (?:{_CURRENCY}) (?:is|are|for|in|to) (?:a|an|one|1) (?:{_CURRENCY})\b"
    rf"|\b(?:{_ASSET})(?: [\w-]+)? (?:prices?|rates?|value)\b"
    rf"|\b(?:prices?|cost|value) of (?:a |an |the |one |1 )?(?:{_ASSET})\b"
    rf"|\b(?:stock|share) price\b|\bprice of (?:a |an |the )?(?:[\w-]+ ){{0,2}}(?:stock|shares)\b"
    rf"|\b(?:prices?|cost) of (?:a |an |the |one )?(?:[\w-]+ ){{0,2}}{_NAMED_THING}"
    rf"|\bhow much (?:does|do|is|are|did) (?:a |an |the |one )?(?:[\w-]+ ){{0,3}}?"
    rf"{_NAMED_THING}(?: [\w-]+){{0,3}} (?:cost|costs|go for|sell for|retail for)\b"
    rf"|\bhow much (?:is|are) (?:a |an |the )?(?:[\w-]+ ){{0,2}}?{_NAMED_THING}(?: [\w-]+){{0,2}}?"
    rf"(?: now| today| these days| right now)?\??$",
    re.IGNORECASE,
)
NOT_A_PRICE = re.compile(
    # A price the question states is a word problem: "if apples cost $2 each".
    r"[$€£¥] ?\d|[=+*/^]|\b(?:each|per)\b|"
    r"\bprice of (?:freedom|fame|success|love|happiness|war|peace|progress|beauty|greatness|"
    r"silence|admission)\b|\bprice (?:elasticity|discrimination|ceiling|floor|gouging|war|"
    r"index|level|point)s?\b|\bpricing (?:strategy|model|page|plan)\b"
    r"|\b(?:what|how) (?:should|would|do|can) (?:i|we) (?:price|charge)\b|\bprice (?:my|our)\b"
    r"|\b(?:write|draft|compose|rewrite|edit|proofread)\b",
    re.IGNORECASE,
)


# Entry rules change with policy: "UK visa rules for Ethiopians", "do I need a visa for Japan".
_ENTRY_RULES = re.compile(
    r"\b(?:visa|entry|transit) (?:requirements?|rules?|polic(?:y|ies)|fees?|"
    r"processing times?|on arrival)\b|\bdo (?:i|we|you) need an? (?:visa|e-?visa)\b"
    r"|\bvisa[- ]free (?:countries|travel|entry)\b",
    re.IGNORECASE,
)


# What an institution charges is set by it and changes: "the exact transaction charges for
# NSE shares", "official stamp duty on a car", "M-PESA withdrawal fees". A model answers these
# from memory with figures that look exact; a search reads them off the schedule.
_OFFICIAL_CHARGES = re.compile(
    r"\b(?:exact|official|actual|current|real|up[\s-]to[\s-]date)\b[\w\s,()/&-]{0,40}?"
    r"\b(?:fees?|charges?|levy|levies|duty|duties|commissions?|tariffs?|taxes)\b"
    r"|\b(?:how\s+much|what\s+(?:are|is)\s+the|list|table|breakdown\s+of)\b[\w\s,()/&-]{0,50}?"
    r"\b(?:transaction|brokerage|stamp|registration|licen[cs]e|filing|processing|"
    r"withdrawal|transfer|cash[- ]out)\s+(?:fees?|charges?|duty|levy|levies)\b",
    re.IGNORECASE,
)
# Working a figure out is for the solver, not the web.
_WORKING_OUT = re.compile(r"\b(?:calculate|compute|work\s+out|solve|formula)\b", re.IGNORECASE)


def asks_for_official_charges(text: str) -> bool:
    """The fees, levies or duties an institution sets: a figure to read, not to recall."""
    cleaned = collapse_ws(text)
    return _OFFICIAL_CHARGES.search(cleaned) is not None and _WORKING_OUT.search(cleaned) is None


def asks_for_job_listings(text: str) -> bool:
    """ "Find remote backend jobs", "python developer openings in Berlin", "who is hiring"."""
    cleaned = collapse_ws(text)
    if _NOT_A_LISTING.search(cleaned):
        return False
    if _LISTING_NOUN.search(cleaned) or _ONE_JOB.search(cleaned):
        return True
    return _JOBS.search(cleaned) is not None and _LISTING_CUE.search(cleaned) is not None


def asks_for_a_price(text: str) -> bool:
    """A price or rate of a named thing: "iPhone 17 Pro cost", "bitcoin price", "USD to ETB"."""
    cleaned = collapse_ws(text)
    return _PRICE.search(cleaned) is not None and NOT_A_PRICE.search(cleaned) is None


def asks_for_entry_rules(text: str) -> bool:
    """Visa and entry rules for a trip: policy that changes after any training cut-off."""
    cleaned = collapse_ws(text)
    return _ENTRY_RULES.search(cleaned) is not None and _NOT_A_LISTING.search(cleaned) is None
