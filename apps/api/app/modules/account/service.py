from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import user_cache
from app.core.config import Settings
from app.core.validation import claim_is_true, normalize_display_name
from app.exceptions import AuthenticationError

# Re-exported for the account API (maps them to 503, not 401).
from app.gateways.apple_auth import AppleAuthUnavailableError as AppleAuthUnavailableError
from app.gateways.apple_auth import verify_apple_id_token
from app.gateways.google_auth import (
    GoogleAuthUnavailableError as GoogleAuthUnavailableError,
)
from app.gateways.google_auth import verify_google_id_token
from app.models.orm import User
from app.models.schemas import AuthResponse, UserOut
from app.modules.account import profile, quota_carryover, signin_limit
from app.modules.account import tokens as tokens_service

# Re-exported for the account API (maps it to 409 naming the earlier sign-in).
from app.modules.account.email_authority import AccountExistsError as AccountExistsError
from app.modules.account.email_authority import (
    apple_owns_email,
    google_owns_email,
    previous_sign_in,
)
from app.modules.notifications import enqueue_welcome_email
from app.repositories import users as users_repo


async def _signed_in(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    user: User,
    *,
    is_new_user: bool,
    device_label: str | None,
    platform: str | None,
    ai_data_consent: bool,
) -> AuthResponse:
    """Finish any sign-in: record an agreement made by the tap, welcome a new account,
    then issue its token pair."""
    if ai_data_consent and user.ai_data_consent_at is None:
        # Before the tokens: the reply already carries the agreement, so no request the
        # app makes next meets ``consent_required``. An earlier agreement keeps its time.
        agreed = profile.with_ai_data_consent({"ai_data_consent": True}, now=datetime.now(UTC))
        user = await users_repo.update(session, user, **agreed)
    if is_new_user and settings.email_enabled:
        # Best-effort: never let a welcome email block signup.
        await enqueue_welcome_email(redis, user.id)

    access_token, refresh_token = await tokens_service.issue_token_pair(
        redis,
        user.id,
        settings,
        device_label=device_label,
        platform=platform,
    )
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )


async def _create_account(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    *,
    provider: str,
    sub: str,
    email: str,
    name: str | None,
    avatar_url: str | None,
) -> User:
    """A new account, committed only once its sign-in's and email's carried counters are
    restored.

    A restore Redis refuses raises ``RedisUnavailableError`` before the commit, so the
    sign-in answers 503 ``sign_in_unavailable`` with no account made, and the retry
    restores (``quota_carryover``). Committed first, the retry found the account and the
    deleted one's limits were gone.
    """
    user = await users_repo.create(
        session,
        google_sub=sub if provider == "google" else None,
        apple_sub=sub if provider == "apple" else None,
        email=email,
        name=name,
        avatar_url=avatar_url,
        commit=False,
    )
    await _commit_with_carried_usage(session, redis, settings, user, provider=provider, sub=sub)
    return user


async def _link_identity(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    user: User,
    *,
    provider: str,
    sub: str,
) -> User:
    """Add a sign-in identity to the account that holds its email, with its carried counters.

    The identity, or this account's email, may be one whose account was deleted today: its
    snapshot raises this account's counters as it would a new account's, so deleting an
    Apple account and then signing in with Apple to the Google account on the same address
    starts nothing over. Once: the next sign-in finds the identity on the account and never
    comes here.
    """
    field = "google_sub" if provider == "google" else "apple_sub"
    user = await users_repo.update(session, user, commit=False, **{field: sub})
    await _commit_with_carried_usage(session, redis, settings, user, provider=provider, sub=sub)
    await user_cache.publish_change(user.id)
    return user


async def _commit_with_carried_usage(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    user: User,
    *,
    provider: str,
    sub: str,
) -> None:
    """Commit the account that just gained this identity, after raising its counters to the
    carried snapshots of the identity and of the account's email (raise-only,
    ``quota_carryover``), then drop the snapshots applied.

    The only callers are a new account and a new link, so an account signing in again never
    restores twice. A restore Redis refuses rolls the account or link back, so the sign-in
    answers 503 ``sign_in_unavailable`` and its retry restores.
    """
    try:
        restored = await quota_carryover.restore_for_new_account(
            redis, settings, user.id, provider=provider, sub=sub, email=user.email
        )
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    await quota_carryover.drop_restored(redis, restored)


async def login_with_google(
    session: AsyncSession,
    settings: Settings,
    id_token: str,
    redis: Redis,
    *,
    device_label: str | None = None,
    platform: str | None = None,
    ai_data_consent: bool = False,
) -> AuthResponse:
    payload = await verify_google_id_token(id_token, settings)
    google_sub = payload["sub"]
    # Once the token verifies, before the account is read or a session made.
    await signin_limit.require_identity(redis, settings, "google", google_sub)
    email = (payload.get("email") or "").strip()
    name = payload.get("name")
    avatar_url = payload.get("picture")

    user = await users_repo.get_by_google_sub(session, google_sub)
    is_new_user = user is None
    # No account has this Google id. One that holds the email (e.g. made with
    # Apple) gains this Google login only when Google owns the address; email
    # is unique, so otherwise the user signs in the way they did before.
    if user is None and email:
        existing = await users_repo.get_by_email(session, email)
        if existing is not None:
            if existing.google_sub or not google_owns_email(payload, email):
                raise AccountExistsError(previous_sign_in(existing, "google"))
            user = await _link_identity(
                session, redis, settings, existing, provider="google", sub=google_sub
            )
            is_new_user = False

    if user is None:
        if not email:
            raise AuthenticationError(
                "Google did not share an email. Check that the Google account "
                "has a verified email, or use Apple Sign-In.",
                code="google_email_missing",
            )
        user = await _create_account(
            session,
            redis,
            settings,
            provider="google",
            sub=google_sub,
            email=email,
            name=name,
            avatar_url=avatar_url,
        )
    else:
        # Decide against the current locked row: a profile save may have
        # finished after the identity lookup above. This flow locks no photos.
        await users_repo.refresh_for_update(session, user)
        # A selected profile photo belongs to Recall; subsequent Google login
        # may refresh a provider picture but must not replace a custom upload.
        current_avatar = user.avatar_url
        if isinstance(current_avatar, str) and current_avatar.startswith("/attachments/"):
            avatar_url = current_avatar
        user = await users_repo.update(
            session,
            user,
            email=email or user.email,
            name=user.name if isinstance(user.name, str) and user.name.strip() else name,
            avatar_url=avatar_url or user.avatar_url,
        )

    return await _signed_in(
        session,
        redis,
        settings,
        user,
        is_new_user=is_new_user,
        device_label=device_label,
        platform=platform,
        ai_data_consent=ai_data_consent,
    )


async def login_with_apple(
    session: AsyncSession,
    settings: Settings,
    id_token: str,
    redis: Redis,
    *,
    name: str | None = None,
    nonce: str | None = None,
    device_label: str | None = None,
    platform: str | None = None,
    ai_data_consent: bool = False,
) -> AuthResponse:
    # L1: validate the client-supplied display name (trim, collapse, length)
    name = normalize_display_name(name)
    payload = await verify_apple_id_token(id_token, settings, nonce=nonce)
    apple_sub = payload["sub"]
    await signin_limit.require_identity(redis, settings, "apple", apple_sub)
    email = payload.get("email")
    # Apple sends `email_verified` as the string "true"/"false" (not a bool),
    # and omits the claim entirely for relayed tokens. Treat anything that
    # isn't an explicit, unambiguous "true" as unverified — the same intent
    # as Google's `not payload.get("email_verified")` but robust to the
    # string form and to a missing claim (which must not silently pass).
    email_verified = payload.get("email_verified")
    if not claim_is_true(email_verified):
        raise AuthenticationError(
            "Apple email address is not verified", code="apple_email_unverified"
        )

    user = await users_repo.get_by_apple_sub(session, apple_sub)
    is_new_user = user is None
    # As with Google: an account holding the email gains this Apple login only
    # when Apple owns the address (its relay, iCloud, me.com, mac.com).
    if user is None and email:
        existing = await users_repo.get_by_email(session, email)
        if existing is not None:
            if existing.apple_sub or not apple_owns_email(payload, email):
                raise AccountExistsError(previous_sign_in(existing, "apple"))
            user = await _link_identity(
                session, redis, settings, existing, provider="apple", sub=apple_sub
            )
            is_new_user = False

    if user is None:
        if not email:
            raise AuthenticationError(
                "Apple did not share an email. Revoke Recall in Apple ID settings "
                "and sign in again, or use Google Sign-In.",
                code="apple_email_missing",
            )
        user = await _create_account(
            session,
            redis,
            settings,
            provider="apple",
            sub=apple_sub,
            email=email,
            name=name,
            avatar_url=None,
        )
    else:
        if name:
            await users_repo.refresh_for_update(session, user)
        updates: dict[str, str | None] = {}
        if email:
            updates["email"] = email
        if name and not (isinstance(user.name, str) and user.name.strip()):
            updates["name"] = name
        if updates:
            user = await users_repo.update(session, user, commit=True, **updates)

    return await _signed_in(
        session,
        redis,
        settings,
        user,
        is_new_user=is_new_user,
        device_label=device_label,
        platform=platform,
        ai_data_consent=ai_data_consent,
    )


async def login_dev(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    name: str,
    redis: Redis,
    device_label: str | None = None,
    platform: str | None = None,
    ai_data_consent: bool = False,
) -> AuthResponse:
    if not settings.dev_auth_enabled:
        raise AuthenticationError("Dev auth is disabled", code="dev_auth_disabled")

    google_sub = f"dev:{email}"
    user = await users_repo.get_by_google_sub(session, google_sub)
    is_new_user = user is None
    if user is None:
        user = await _create_account(
            session,
            redis,
            settings,
            provider="google",
            sub=google_sub,
            email=email,
            name=name,
            avatar_url=None,
        )
    elif name and user.name != name:
        # Keep dev re-login in step with Google/Apple, which refresh the name
        # each time — so renaming the dev identity takes effect for an existing
        # account instead of being stuck at the name it was first created with.
        user = await users_repo.update(session, user, name=name)

    return await _signed_in(
        session,
        redis,
        settings,
        user,
        is_new_user=is_new_user,
        device_label=device_label,
        platform=platform,
        ai_data_consent=ai_data_consent,
    )
