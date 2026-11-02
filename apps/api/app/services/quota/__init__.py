"""Usage limits in Redis.

``tokens`` is the daily token budget, ``counters`` the per-feature daily caps
(``counters.reserve("image_search", ...)``), ``live_talk`` the monthly live talk
seconds, ``carryover`` what account delete hands to a new account for the same
sign-in or email address, and ``spend`` the global daily spend breaker (its counter is
``core/spend_counter``). ``messages`` is the copy a refused request shows.
"""

from app.services.quota import counters
from app.services.quota.carryover import (
    CarriedUsage,
    apply_carried_usage,
    read_carried_usage,
)
from app.services.quota.counters import utc_today
from app.services.quota.live_talk import (
    LIVE_TALK_SAVES_PER_MINUTE,
    live_talk_allowance_seconds,
    live_talk_used_seconds,
    next_month_start,
    record_live_talk_reservation,
    release_live_talk_seconds,
    reserve_live_talk_seconds,
    settle_live_talk_session,
    take_live_talk_save,
    utc_month,
)
from app.services.quota.messages import (
    CHAT_SPEND_CAP_MESSAGE,
    IMAGE_GENERATION_NOT_IN_PLAN_MESSAGE,
    IMAGE_GENERATION_SPEND_CAP_MESSAGE,
    IMAGE_SEARCH_SPEND_CAP_MESSAGE,
    LIVE_TALK_MINUTES_USED_MESSAGE,
    LIVE_TALK_NOT_IN_PLAN_MESSAGE,
    LIVE_TALK_RATE_LIMIT_MESSAGE,
    LIVE_TALK_SAVES_USED_MESSAGE,
    SPEECH_NOT_IN_PLAN_MESSAGE,
    SPEECH_RATE_LIMIT_MESSAGE,
    SPEECH_TTS_NOT_IN_PLAN_MESSAGE,
    SPEECH_TTS_RATE_LIMIT_MESSAGE,
    VOICE_SPEND_CAP_MESSAGE,
    quota_exceeded_message,
)
from app.services.quota.spend import (
    IMAGE_GEN_SPEND_USD,
    IMAGE_SEARCH_SPEND_USD,
    MATH_SCAN_READ_SPEND_USD,
    STT_SPEND_USD,
    TTS_SPEND_USD,
    get_global_spend_micro_usd,
    global_spend_exceeded,
    record_global_spend,
    record_voice_spend,
)
from app.services.quota.tokens import (
    adjust_usage,
    clear_usage_needs_heal,
    daily_limit_for_user,
    get_daily_usage,
    has_daily_usage_key,
    heal_usage_drift,
    mark_usage_needs_heal,
    refund_usage,
    reserve_usage_up_to,
    reset_daily_usage,
    seed_usage_if_missing,
    usage_needs_heal,
)

__all__ = [
    "CHAT_SPEND_CAP_MESSAGE",
    "IMAGE_GENERATION_NOT_IN_PLAN_MESSAGE",
    "IMAGE_GENERATION_SPEND_CAP_MESSAGE",
    "IMAGE_GEN_SPEND_USD",
    "IMAGE_SEARCH_SPEND_CAP_MESSAGE",
    "IMAGE_SEARCH_SPEND_USD",
    "LIVE_TALK_MINUTES_USED_MESSAGE",
    "LIVE_TALK_NOT_IN_PLAN_MESSAGE",
    "LIVE_TALK_RATE_LIMIT_MESSAGE",
    "LIVE_TALK_SAVES_PER_MINUTE",
    "LIVE_TALK_SAVES_USED_MESSAGE",
    "MATH_SCAN_READ_SPEND_USD",
    "SPEECH_NOT_IN_PLAN_MESSAGE",
    "SPEECH_RATE_LIMIT_MESSAGE",
    "SPEECH_TTS_NOT_IN_PLAN_MESSAGE",
    "SPEECH_TTS_RATE_LIMIT_MESSAGE",
    "STT_SPEND_USD",
    "TTS_SPEND_USD",
    "VOICE_SPEND_CAP_MESSAGE",
    "CarriedUsage",
    "adjust_usage",
    "apply_carried_usage",
    "clear_usage_needs_heal",
    "counters",
    "daily_limit_for_user",
    "get_daily_usage",
    "get_global_spend_micro_usd",
    "global_spend_exceeded",
    "has_daily_usage_key",
    "heal_usage_drift",
    "live_talk_allowance_seconds",
    "live_talk_used_seconds",
    "mark_usage_needs_heal",
    "next_month_start",
    "quota_exceeded_message",
    "read_carried_usage",
    "record_global_spend",
    "record_live_talk_reservation",
    "record_voice_spend",
    "refund_usage",
    "release_live_talk_seconds",
    "reserve_live_talk_seconds",
    "reserve_usage_up_to",
    "reset_daily_usage",
    "seed_usage_if_missing",
    "settle_live_talk_session",
    "take_live_talk_save",
    "usage_needs_heal",
    "utc_month",
    "utc_today",
]
