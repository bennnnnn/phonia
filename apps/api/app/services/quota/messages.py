from app.models.orm import User
from app.modules.billing.entitlements import is_paid

# Plan names are the app's to show (i18n); server copy says "upgrade", never a
# plan name, and never a number that config owns.
# Shown when the daily quota is exhausted — avoid internal "token" wording.
# Counters reset at midnight UTC (not the user's local timezone).
QUOTA_EXCEEDED_MESSAGE_FREE = (
    "You've used up today's free limit. Upgrade for more — or try again after midnight UTC."
)
QUOTA_EXCEEDED_MESSAGE_PAID = "You've reached today's limit. Try again after midnight UTC."

IMAGE_LIMIT_EXCEEDED_MESSAGE_FREE = (
    "You've reached today's image upload limit. Upgrade for more — or try again after midnight UTC."
)
IMAGE_LIMIT_EXCEEDED_MESSAGE_PAID = (
    "You've reached today's image upload limit. Try again after midnight UTC."
)
DOCUMENT_LIMIT_EXCEEDED_MESSAGE_FREE = (
    "You've reached today's file upload limit. Upgrade for more — or try again after midnight UTC."
)
DOCUMENT_LIMIT_EXCEEDED_MESSAGE_PAID = (
    "You've reached today's file upload limit. Try again after midnight UTC."
)

SPEECH_LIMIT_EXCEEDED_MESSAGE = (
    "You've reached today's voice transcription limit. Try again after midnight UTC."
)
SPEECH_NOT_IN_PLAN_MESSAGE = "Voice input isn't part of your plan. Upgrade to dictate messages."
SPEECH_RATE_LIMIT_MESSAGE = "Too many voice requests. Please wait a moment and try again."
SPEECH_TTS_RATE_LIMIT_MESSAGE = "Too many read-aloud requests. Please wait a moment and try again."
SPEECH_TTS_LIMIT_EXCEEDED_MESSAGE = "Daily read-aloud limit reached. Try again tomorrow."
SPEECH_TTS_NOT_IN_PLAN_MESSAGE = (
    "Read aloud isn't part of your plan. Upgrade for it, or use your phone's voice."
)

IMAGE_GENERATION_LIMIT_EXCEEDED_MESSAGE_FREE = (
    "You've reached today's image generation limit. "
    "Upgrade for more — or try again after midnight UTC."
)
IMAGE_GENERATION_LIMIT_EXCEEDED_MESSAGE_PAID = (
    "You've reached today's image generation limit. Try again after midnight UTC."
)
IMAGE_GENERATION_NOT_IN_PLAN_MESSAGE = "Image generation isn't part of your plan. Upgrade for it."
IMAGE_GENERATION_SPEND_CAP_MESSAGE = "Image generation is temporarily unavailable. Try again later."

IMAGE_SEARCH_LIMIT_EXCEEDED_MESSAGE_FREE = (
    "You've reached today's photo lookup limit. Upgrade for more — or try again after midnight UTC."
)
IMAGE_SEARCH_LIMIT_EXCEEDED_MESSAGE_PAID = (
    "You've reached today's photo lookup limit. Try again after midnight UTC."
)
IMAGE_SEARCH_SPEND_CAP_MESSAGE = "Photo lookup is temporarily unavailable. Try again later."

LIVE_TALK_NOT_IN_PLAN_MESSAGE = (
    "Live talk isn't part of your plan. Upgrade to talk with Recall out loud."
)
LIVE_TALK_MINUTES_USED_MESSAGE = (
    "You've used this month's live talk minutes. They renew on the 1st (UTC)."
)
LIVE_TALK_RATE_LIMIT_MESSAGE = "Too many live talk requests. Please wait a moment and try again."
LIVE_TALK_SAVES_USED_MESSAGE = (
    "This live talk call can't save more turns. Hang up and start a new call to keep going."
)

VOICE_SPEND_CAP_MESSAGE = "Voice is temporarily unavailable. Try again later."

# The global spend cap, not the user's allowance: no upgrade offer, and none of
# the phone's quota phrases ("daily limit", "today's limit"), which it reads as
# the user's own limit.
CHAT_SPEND_CAP_MESSAGE = (
    "Recall is at capacity for today, so new messages are paused for everyone. "
    "Try again after midnight UTC."
)


def plan_message(user: User, *, free: str, paid: str) -> str:
    return paid if is_paid(user) else free


def quota_exceeded_message(user: User) -> str:
    return plan_message(user, free=QUOTA_EXCEEDED_MESSAGE_FREE, paid=QUOTA_EXCEEDED_MESSAGE_PAID)
