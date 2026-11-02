"""What each plan allows per day or month, and the global daily spend cap."""

from pydantic import BaseModel


class PlanAllowanceSettings(BaseModel):
    """One number per plan: ``<base>`` is free, ``<base>_plus`` and ``<base>_pro`` the paid plans.

    ``modules/billing/entitlements.py`` (the one place plan policy lives) reads
    them by that name. 0 = not part of that plan. A new allowance is three
    fields here and one ``Allowance`` entry there.
    """

    # Daily image-upload cap (per user, UTC day). Vision/image inputs cost more
    # than text, so cap uploads separately from the token quota. Enforced at
    # presign so a user can't accumulate uploads past the limit.
    daily_image_limit: int = 5
    daily_image_limit_plus: int = 30
    daily_image_limit_pro: int = 30
    # Daily document (PDF, Word, text) uploads, for the same reason: each is read and
    # parsed on the API machine. Also enforced at presign.
    daily_document_limit: int = 10
    daily_document_limit_plus: int = 50
    daily_document_limit_pro: int = 100
    # Paid Tavily queries per user per UTC day; when exceeded, fall back to DuckDuckGo.
    daily_tavily_searches: int = 20
    daily_tavily_searches_plus: int = 150
    daily_tavily_searches_pro: int = 150
    # Voice input and read-aloud per UTC day.
    daily_speech_transcriptions: int = 0
    daily_speech_transcriptions_plus: int = 200
    daily_speech_transcriptions_pro: int = 200
    daily_speech_tts: int = 0
    daily_speech_tts_plus: int = 100
    daily_speech_tts_pro: int = 100
    # Live talk minutes per UTC calendar month.
    monthly_live_talk_minutes: int = 0
    monthly_live_talk_minutes_plus: int = 0
    monthly_live_talk_minutes_pro: int = 60
    # AI pictures and reference-photo lookups per UTC day.
    daily_image_generations: int = 3
    daily_image_generations_plus: int = 10
    daily_image_generations_pro: int = 15
    daily_image_searches: int = 15
    daily_image_searches_plus: int = 60
    daily_image_searches_pro: int = 60

    # Auto's everyday turns on the stronger model (``ROUTING.everyday_strong``), not
    # the cheap one (``ROUTING.everyday``). Hard and maths turns route as before.
    strong_everyday_model: bool = False
    strong_everyday_model_plus: bool = False
    strong_everyday_model_pro: bool = True

    # Chat tokens per UTC day (the per-user cost guardrail).
    daily_token_limit: int = 100_000
    daily_token_limit_plus: int = 500_000
    daily_token_limit_pro: int = 500_000
    # UTC-day OpenRouter spend ceiling (foreground + background). 0 = unlimited
    # (dev/tests). Production boot requires a positive value.
    daily_global_spend_usd: float = 0.0
