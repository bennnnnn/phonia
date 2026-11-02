import re
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.validation import (
    LOCALE_NAMES,
    normalize_avatar_url,
    normalize_display_name,
    normalize_locale_code,
)
from app.models.model_catalog import validate_user_alias
from app.models.schemas.common import EmojiUse, ResponseTone, UserVoice
from app.models.schemas.text import UserText

# The longest custom instructions a user may save; the prompt builders read this too.
CUSTOM_INSTRUCTIONS_MAX_CHARS = 1000


def chosen_model_id(enabled_models: list[str] | None) -> str:
    """The model a message uses: "auto", or with Auto off the first model turned on.

    ``enabled_models`` is the one source: the phone's "Messages use" row and the chat's
    settings card both reorder it. ``users.default_model`` is only a stored copy.
    """
    if enabled_models is None or "auto" in enabled_models:
        return "auto"
    return next((model for model in enabled_models if model != "auto"), "auto")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str | None
    avatar_url: str | None
    plan: str = "free"
    enabled_models: list[str] | None = None
    response_tone: str = "casual"
    emoji_use: str = "some"
    memory_enabled: bool
    follow_up_suggestions_enabled: bool = True
    memory_include_sensitive: bool = False
    web_search_enabled: bool = True
    # When the user agreed to what is sent to outside AI services; null until then.
    ai_data_consent_at: datetime | None = None
    push_notifications_enabled: bool = True
    push_reminders_enabled: bool = True
    tts_voice: str | None = None
    email_reminders_enabled: bool = False
    reminder_lead_minutes: int = 10
    quiet_hours_enabled: bool = False
    quiet_hours_start_minute: int = 1320
    quiet_hours_end_minute: int = 420
    locale: str = "en"
    timezone: str = "UTC"
    location: str | None = None
    location_enabled: bool = False
    custom_instructions: str | None = None
    age: int | None = None
    country: str | None = None
    job: str | None = None
    created_at: datetime
    google_sub: str | None = Field(default=None, exclude=True)
    apple_sub: str | None = Field(default=None, exclude=True)

    # mypy rejects a decorator over @property; pydantic documents this ignore.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def default_model(self) -> str:
        """Derived from ``enabled_models`` (``chosen_model_id``), never stored apart."""
        return chosen_model_id(self.enabled_models)

    # mypy rejects a decorator over @property; pydantic documents this ignore.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def sign_in_provider(self) -> str:
        google = self.google_sub if isinstance(self.google_sub, str) and self.google_sub else None
        apple = self.apple_sub if isinstance(self.apple_sub, str) and self.apple_sub else None
        if google and not google.startswith("dev:"):
            return "google"
        if apple:
            return "apple"
        if google and google.startswith("dev:"):
            return "dev"
        return "dev"

    # mypy rejects a decorator over @property; pydantic documents this ignore.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def apple_linked(self) -> bool:
        """Signs in with Apple (alone or beside Google): deleting the account on
        iOS asks Apple once more so the server can revoke the Apple grant."""
        return isinstance(self.apple_sub, str) and bool(self.apple_sub)

    # mypy rejects a decorator over @property; pydantic documents this ignore.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def features(self) -> list[str]:
        """What this plan includes, so the app can show locks. The server still
        checks every request; this is display only."""
        from app.core.config import get_settings
        from app.modules.billing.entitlements import features_for

        return list(features_for(self.plan, get_settings()))

    # mypy rejects a decorator over @property; pydantic documents this ignore.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def email_reminders_available(self) -> bool:
        """False when this server cannot send reminder emails (no provider key in
        production, or turned off), so the app can hide the email-reminder switch."""
        from app.core.config import get_settings
        from app.gateways import email_gateway

        settings = get_settings()
        return settings.email_reminders_scheduler_enabled and email_gateway.can_send(settings)


class UserUpdate(BaseModel):
    name: UserText | None = Field(default=None, min_length=1, max_length=80)
    avatar_url: UserText | None = Field(default=None, max_length=64)
    default_model: str | None = None
    enabled_models: list[str] | None = None
    response_tone: ResponseTone | None = None
    emoji_use: EmojiUse | None = None
    memory_enabled: bool | None = None
    follow_up_suggestions_enabled: bool | None = None
    memory_include_sensitive: bool | None = None
    web_search_enabled: bool | None = None
    # true records agreement to the outside-AI disclosure at the server's clock;
    # false withdraws it. The client never sends the time itself.
    ai_data_consent: bool | None = None
    push_notifications_enabled: bool | None = None
    push_reminders_enabled: bool | None = None
    # null puts the server default back.
    tts_voice: UserVoice | None = None
    email_reminders_enabled: bool | None = None
    reminder_lead_minutes: int | None = Field(default=None, ge=5, le=60)
    quiet_hours_enabled: bool | None = None
    quiet_hours_start_minute: int | None = Field(default=None, ge=0, le=1439)
    quiet_hours_end_minute: int | None = Field(default=None, ge=0, le=1439)
    locale: UserText | None = None
    timezone: UserText | None = Field(default=None, max_length=64)
    location: UserText | None = Field(default=None, max_length=128)
    location_enabled: bool | None = None
    custom_instructions: UserText | None = Field(
        default=None, max_length=CUSTOM_INSTRUCTIONS_MAX_CHARS
    )
    age: int | None = Field(default=None, ge=13, le=120)
    country: UserText | None = Field(default=None, max_length=64)
    job: UserText | None = Field(default=None, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_display_name(value)
        if not normalized:
            raise ValueError("Name must be 1\u201380 characters.")
        return normalized

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_avatar_url(value)

    @field_validator("default_model")
    @classmethod
    def validate_default_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        validate_user_alias(value, allow_auto=True)
        return value

    @field_validator("enabled_models")
    @classmethod
    def validate_enabled_models(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("Turn on Auto or at least one model.")
        for entry in value:
            if entry == "auto":
                continue
            validate_user_alias(entry)
        return value

    @field_validator("reminder_lead_minutes")
    @classmethod
    def validate_reminder_lead_minutes(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in {5, 10, 15, 30, 60}:
            raise ValueError("reminder_lead_minutes must be 5, 10, 15, 30, or 60")
        return value

    @field_validator("custom_instructions", "country", "job")
    @classmethod
    def validate_optional_profile_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Empty/whitespace locale → no change (treat as unset), matching the
        # custom_instructions blank-clears behavior.
        if not value.strip():
            return None
        code = normalize_locale_code(value)
        if code not in LOCALE_NAMES:
            supported = ", ".join(sorted(LOCALE_NAMES))
            raise ValueError(f"Unsupported locale code. Supported: {supported}.")
        return code

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return ZoneInfo(cleaned).key
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Invalid IANA timezone name.") from exc


class DeviceSessionIn(BaseModel):
    device_label: UserText | None = Field(default=None, max_length=80)
    platform: UserText | None = Field(default=None, max_length=16)


class SignInRequest(DeviceSessionIn):
    # true: the button tapped sits under the outside-AI disclosure (the phone's sign-in
    # page), so the tap is the agreement and the sign-in records ``ai_data_consent_at``.
    # Absent (an older phone, the web): consent is asked after sign-in, as before.
    ai_data_consent: bool = False


class GoogleAuthRequest(SignInRequest):
    id_token: str


class AppleAuthRequest(SignInRequest):
    id_token: str
    name: UserText | None = None
    # The raw nonce; the app gave Apple its SHA-256, which the token carries.
    nonce: str | None = Field(default=None, max_length=256)


# One address: something before an @, a dotted domain after it, no spaces. Not a
# deliverability check (dev addresses use .local), only enough to refuse "not-an-email".
_EMAIL_SHAPE = re.compile(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+")


class DevAuthRequest(SignInRequest):
    email: UserText = Field(default="dev@recall.local", max_length=254)
    name: UserText = "bini"

    @field_validator("email")
    @classmethod
    def _is_an_email(cls, value: str) -> str:
        cleaned = value.strip()
        if not _EMAIL_SHAPE.fullmatch(cleaned):
            raise ValueError("not an email address")
        return cleaned


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
    csrf_token: str | None = None


class RefreshRequest(DeviceSessionIn):
    refresh_token: str | None = None


class AuthSessionOut(BaseModel):
    id: str
    device_label: str | None = None
    platform: str | None = None
    created_at: str | None = None
    last_seen_at: str | None = None
    current: bool = False


class AuthSessionListOut(BaseModel):
    sessions: list[AuthSessionOut]


class LogoutRequest(BaseModel):
    refresh_token: str | None = None
    # This device's Expo push token: logout forgets it, so the account's reminders stop.
    expo_push_token: str | None = Field(default=None, min_length=8, max_length=512)


class AccountDeleteRequest(BaseModel):
    # A fresh Sign in with Apple code (Apple-linked accounts on iOS); the
    # server trades it for the user's Apple token and revokes that.
    apple_authorization_code: str | None = Field(default=None, max_length=2048)


class SettingsChangeOut(BaseModel):
    field: str
    value: str
    label: str


class SettingsConfirmOut(BaseModel):
    user: UserOut
    appearance: str | None = None
    applied: list[SettingsChangeOut]
