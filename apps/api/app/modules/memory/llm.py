"""LLM prompts for atomic memory extract and pair merge."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.core.config import Settings
from app.gateways import litellm_gateway, mock_llm
from app.models.routing_lanes import ROUTING
from app.modules.memory.offline import offline_memory_facts, offline_section_merge
from app.modules.memory.schemas import MemoryFactUpdateResult, MemorySectionItem
from app.modules.memory.topics import STANDARD_TOPICS
from app.services.prompt_safety import wrap_untrusted

# What belongs in each document, for the model (the UI shows the short summary).
_TOPIC_HINTS = {
    "profile": "who the user is: name, job, employer, school, where they live or come "
    "from, languages they speak",
    "preferences": "how they want replies (length, tone, format, pushback) and how they "
    "like to learn or use the app",
    "interests": "hobbies and interests outside work that they come back to",
    "tech-stack": "languages, frameworks, tools, and services they use in their own work",
    "schedule": "standing routines and working hours only. A todo, reminder, "
    "appointment, flight, or one-off errand is not memory",
    "recent-work": "what they are working on lately that is not its own area",
    "goals": "what they are working toward: career, learning, health, life",
    "side-projects": "ideas and smaller things they build",
    "notes": "anything else durable",
}


def _documents_guide() -> str:
    lines = ["Each fact belongs to one memory document, its topic:"]
    lines.extend(f"- {spec.key}: {_TOPIC_HINTS[spec.key]}" for spec in STANDARD_TOPICS)
    lines.append(
        "- area:<slug>: one major named project, job, or part of the user's life, e.g. "
        "area:recall for Recall, an app they are building. Put a fact about a named project "
        "in its area, not in side-projects. Reuse an existing area's topic when the fact "
        "belongs to it. For a new area also give topic_title (its name, e.g. 'Recall') and "
        "topic_summary (one short line, e.g. 'Personal AI chat app built with Expo')."
    )
    return "\n".join(lines)


_OP_SHAPE = (
    '{"ops": [{"op": "add|update|supersede|delete|mute", '
    '"topic": "profile|preferences|interests|tech-stack|schedule|recent-work|goals|'
    'side-projects|notes|area:<slug>", '
    '"topic_title": "new area name, else omit", "topic_summary": "new area line, else omit", '
    '"type": "profile|preference|project|fact|focus", '
    '"text": "one sentence in third person", "confidence": 0.0-1.0, '
    '"sensitivity": "normal|health|finance|legal|relationship|identity|highly_sensitive", '
    '"importance": 0.0-1.0, "match_text": "existing fact text if updating"}]}'
)

# "Reply in Spanish from now on" was saved as a preference and answered an English app in
# Spanish (2026-10-24): a setting's choice is the setting's.
SETTING_PREFERENCE_RULE = (
    "- Do not store a preference an app setting decides: the reply language, emojis, the "
    "light or dark theme, or the default model. Those live in Settings, and a saved copy "
    "competes with them. Keep the rest of the preference: 'short replies in Spanish, no "
    "emojis' is 'User prefers short replies'. A language they speak or learn, or a model "
    "in their own work, is a fact."
)

# What belongs elsewhere: reminders, and a setting's choice.
_NOT_MEMORY_RULES = (
    "- Do not store a todo, reminder, appointment, flight, concert, or other one-off errand. "
    "Those are reminders, not memory. A standing routine (every evening, working hours) may "
    "be a schedule fact.\n" + SETTING_PREFERENCE_RULE
)

# On the Memory page the user asks directly, so the reply says where that setting is.
INSTRUCT_SETTING_RULE = (
    "- A preference an app setting decides (the reply language, emojis, the light or dark "
    "theme, the default model) is not memory: add no op for it, and the reply says where to "
    "set it (Settings → Language, Personalization, Appearance or Models; replies in a "
    "language other than the app's go in Personalization's custom instructions). Save the "
    "rest of the instruction as usual."
)

_SENSITIVITY_RULES = (
    "- sensitivity says what the fact reveals about the user's private life. "
    "normal: name, job, employer, school, city, home country, languages, "
    "projects, tools, interests, schedule, and reply preferences. "
    "health: their physical or mental health. finance: their income, debts, "
    "or accounts. legal: their own legal matters. relationship: their romantic "
    "life or partner. identity: gender identity, immigration status, or "
    "disability. highly_sensitive: race or ethnicity, religion, politics, "
    "sexual orientation, and sex life.\n"
    "- Label the user's life, not the subject of their work: building a dating "
    "app or a health tracker is a normal project fact."
)


def local_today(user_timezone: str | None) -> str:
    """The user's date, as the extraction rule names it: "Friday, Oct 23, 2026"."""
    from app.services import time_context as time_context_service

    now = datetime.now(time_context_service.resolve_timezone(user_timezone))
    return f"{now:%A}, {now:%b} {now.day}, {now.year}"


def _history_rule(from_history: bool) -> str:
    if not from_history:
        return ""
    return (
        "- These User lines come from an earlier chat, so the existing facts may be "
        "newer. Only add facts that are missing; never update, supersede, or delete an "
        "existing fact because of these lines.\n"
    )


def _dates_rule(today: str | None) -> str:
    """A fact is read days later: "has an anatomy exam next Friday" was saved as said."""
    rule = (
        "- A fact with a date keeps it as a date ('has an anatomy exam on Friday, Oct 30, "
        "2026'), never a relative one ('next Friday', 'this weekend', 'in two weeks'). "
    )
    if today:
        return f"{rule}Today is {today} for the user.\n"
    return f"{rule}Leave out a relative date you cannot place.\n"


def _compact_json(value: Any) -> str:
    """The saved facts or areas for the prompt, without the spaces after , and : (about
    six tokens a fact)."""
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _extract_input(
    existing_block: str, areas_block: str, transcript: str, *, from_history: bool, earlier: str
) -> str:
    """The saved facts, then the lines to read; ``earlier`` is the exchange before them."""
    before = (
        "Just before (already read; only says what 'that' or 'this' points at, "
        f"never a source of facts):\n{wrap_untrusted('earlier exchange', earlier)}\n\n"
        if earlier
        else ""
    )
    return (
        f"Existing facts JSON:\n{existing_block}\n\n"
        f"Existing areas JSON:\n{areas_block}\n\n"
        f"{before}"
        f"{'Earlier conversation' if from_history else 'New conversation'}:\n"
        f"{wrap_untrusted('conversation transcript', transcript)}"
    )


async def revise_memory_facts(
    settings: Settings,
    transcript: str,
    *,
    existing_facts: list[dict[str, Any]] | None = None,
    existing_areas: list[dict[str, Any]] | None = None,
    from_history: bool = False,
    earlier: str = "",
    today: str | None = None,
) -> MemoryFactUpdateResult | None:
    if mock_llm.should_mock_llm(settings):
        return await offline_memory_facts(transcript, existing_facts or [])

    existing = existing_facts or []
    history_rule = _history_rule(from_history)
    existing_block = _compact_json(existing)
    areas_block = _compact_json(existing_areas or [])

    messages = [
        {
            "role": "system",
            "content": (
                "You maintain long-term memory about the user as individual facts, "
                "grouped into documents the user can read. "
                f"Return ONLY JSON (no markdown): {_OP_SHAPE} .\n"
                f"{_documents_guide()}\n\n"
                "Type meanings (the topic usually decides it):\n"
                "- profile: who the user is. "
                "A name is theirs only when they claim it ('my name is', 'I'm', "
                "'call me', 'I go by'). The only name sentence is "
                "'User's name is John' or 'User's name is John; also goes by X.'\n"
                "- preference: how they like to learn, communicate, or use the app\n"
                "- project: what the user is working on or building, including one they name\n"
                "- fact: stable misc facts\n"
                "- focus: current priorities\n\n"
                "Rules:\n"
                "- Use only what the User lines state or clearly show about the user; "
                "never assistant inferences, suggestions, or restatements.\n"
                "- Capture durable context the user reveals while asking for help, not only "
                "in introductions: the projects they build (with their names), the stack "
                "they build with, their job and role, goals, routines, and interests they "
                "come back to. 'Fix the drawer in my Expo app Recall' says the user builds "
                "Recall with Expo.\n"
                "- A one-off question is not a fact about the user: asking the capital of "
                "France is not an interest in France.\n"
                "- Natural phrasing still counts: 'As a software engineer at Uber' is an "
                "explicit job/employer fact even without 'I am'.\n"
                "- Store durable reply-style feedback as a preference when the user describes "
                "what they prefer, asks for an ongoing behavior, or corrects how the assistant "
                "usually responds. Do not store formatting requested only for the current task.\n"
                "- How they want to be taught is a preferences fact even with no topic yet: "
                "'When teaching me, explain one concept at a time and give me an exercise "
                "before moving on' is 'User wants lessons one concept at a time, with a short "
                "exercise before moving on.'\n"
                "- Each op is ONE fact — never a paragraph of unrelated ideas.\n"
                "- Return ONLY ops for facts that changed or are new this turn.\n"
                "- On conflicting facts (e.g. moved cities), op=supersede with match_text "
                "of the old fact and text of the new one. Two current places cannot "
                "both stay. Current schooling cannot stay next to an earlier stage "
                "(12th grade and a university). A correction is the same: 'that's wrong, "
                "I'm at Stripe now' or 'actually I switched from FastAPI to Django' "
                "supersedes the old fact with the new one.\n"
                "- Record a decision the user states about their own project or life, "
                "with what it was chosen over: 'For Recall I decided to use Neon instead "
                "of Supabase' is 'Recall uses Neon (chosen over Supabase)' in that area.\n"
                f"{_NOT_MEMORY_RULES}\n"
                "- Distinguish current facts from aspirations and hypotheticals. For example, "
                "'I work at Uber but want to move to Google' keeps Uber as the current employer "
                "and adds Google as a career goal; it must not claim the user works at Google.\n"
                "- If the User line explicitly asks to remember a fact, add it.\n"
                "- If the User line explicitly asks to forget a fact, op=delete with "
                "match_text of that fact (empty the fact if nothing remains). A bare "
                "'forget that' means the fact the exchange just before stated or used.\n"
                "- If the User line asks you to stop using or mentioning a saved fact "
                "('stop mentioning my job', 'don't bring up my divorce again'), op=mute "
                "with match_text of each fact it covers; muting keeps the fact but stops "
                "its use. If no saved fact matches, add a preferences fact saying what not "
                "to bring up.\n"
                "- When the user says what they are working on, building, or focusing on, "
                "add that project or focus fact. Do not drop it and do not treat it as "
                "the Learning projects feature.\n"
                "- Skip small talk. Return empty ops only when the user stated nothing "
                "durable about themselves.\n"
                "- Do not invent facts.\n"
                f"{_dates_rule(today)}"
                "- A clock hour keeps its part of day. Morning is AM. Afternoon, evening, "
                "and night are not the morning: 4 in the evening is 16:00, never 04:00. "
                "Keep evening, afternoon, or night in the fact; do not rewrite them as AM.\n"
                "- Never store a name from a word problem, story, example, or "
                "anyone other than the user. 'Bebe has 2 pens and gives them to "
                "Cal' is not the user's name.\n"
                f"{history_rule}"
                f"{_SENSITIVITY_RULES}"
            ),
        },
        {
            "role": "user",
            "content": _extract_input(
                existing_block, areas_block, transcript, from_history=from_history, earlier=earlier
            ),
        },
    ]
    return await litellm_gateway.complete_structured(
        settings=settings,
        model_alias=ROUTING.background,
        messages=messages,
        schema=MemoryFactUpdateResult,
        # Room for several ops; a reply cut off mid-JSON is discarded whole.
        max_tokens=2048,
        # A background job: bad JSON asks the fallback model once, not drops the turn.
        fallback_on_invalid=True,
    )


async def instruct_memory(
    settings: Settings,
    instruction: str,
    *,
    existing_facts: list[dict[str, Any]],
    existing_areas: list[dict[str, Any]],
    focus_topic: str | None = None,
) -> MemoryFactUpdateResult | None:
    """Turn the user's own edit ("keep lists under five things") into memory ops."""
    if mock_llm.should_mock_llm(settings):
        return MemoryFactUpdateResult(ops=[], reply="Memory editing needs a live model.")

    focus = (
        f"The user is looking at the {focus_topic} document; prefer it for new facts and "
        "edits unless the instruction clearly belongs elsewhere.\n"
        if focus_topic
        else ""
    )
    messages = [
        {
            "role": "system",
            "content": (
                "The user is editing their long-term memory directly. Turn their "
                "instruction into ops over the existing facts. Return ONLY JSON (no "
                f"markdown): {_OP_SHAPE[:-2]}], "
                '"reply": "one short sentence to the user"} .\n'
                f"{_documents_guide()}\n\n"
                "Rules:\n"
                "- The instruction is the user speaking about themselves, so it counts as "
                "stated. Follow it exactly and do not invent anything beyond it.\n"
                "- How they want replies ('you can disagree with me more', 'keep lists under "
                "five things') is a preferences fact.\n"
                f"{INSTRUCT_SETTING_RULE}\n"
                "- To correct a fact, op=update with match_text of that fact. To remove one, "
                "op=delete with match_text. To stop using one without deleting it, op=mute "
                "with match_text. To move one to another document, op=update with the new "
                "topic. To add, op=add.\n"
                "- Each op is ONE fact in third person ('User prefers ...').\n"
                "- reply: one short plain sentence saying what changed, or why nothing did "
                "(for example when the message is not about memory). No markdown.\n"
                f"{focus}"
                f"{_SENSITIVITY_RULES}"
            ),
        },
        {
            "role": "user",
            "content": (
                "Existing facts JSON:\n"
                f"{_compact_json(existing_facts)}\n\n"
                "Existing areas JSON:\n"
                f"{_compact_json(existing_areas)}\n\n"
                f"{wrap_untrusted('memory instruction', instruction)}"
            ),
        },
    ]
    return await litellm_gateway.complete_structured(
        settings=settings,
        model_alias=ROUTING.background,
        messages=messages,
        schema=MemoryFactUpdateResult,
        max_tokens=2048,
    )


async def merge_memory_section(
    settings: Settings,
    *,
    section_type: str,
    prior_text: str,
) -> MemorySectionItem | None:
    """Merge two near-duplicate fact texts without dropping distinct facts."""
    clean = prior_text.strip()
    if not clean:
        return None
    if mock_llm.should_mock_llm(settings):
        return await offline_section_merge(section_type, clean)

    messages = [
        {
            "role": "system",
            "content": (
                "You merge two near-duplicate memory facts into one canonical fact. "
                "Return ONLY JSON (no markdown): "
                '{"type": "profile|preference|project|fact|focus", '
                '"summary": "one sentence in third person", "confidence": 0.0-1.0}. '
                "Rules:\n"
                "- Preserve EVERY distinct fact from the draft — do not drop names, orgs, "
                "emails, numbers, or preferences.\n"
                "- Deduplicate near-duplicate sentences.\n"
                "- The first fact in the draft is the newer one. On contradictions, keep "
                "it and drop the older one.\n"
                "- Output ONE sentence (not a bullet list).\n"
                "- Do not invent facts not supported by the draft.\n"
                f"- The section type must remain `{section_type}`."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Section type: {section_type}\n"
                f"Draft facts JSON:\n{json.dumps({'text': clean}, ensure_ascii=False)}"
            ),
        },
    ]
    return await litellm_gateway.complete_structured(
        settings=settings,
        model_alias=ROUTING.background,
        messages=messages,
        schema=MemorySectionItem,
        max_tokens=1024,
    )
