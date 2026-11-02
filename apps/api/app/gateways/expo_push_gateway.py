"""Expo Push API gateway."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

from app.gateways.http_client import get_pooled_client

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
MAX_RECEIPTS_PER_REQUEST = 100
EXPO_TIMEOUT_SECONDS = 15.0
# Only DeviceNotRegistered proves a token is dead. InvalidCredentials means our own
# APNs/FCM credentials are misconfigured: every send returns it, so reading it as a
# dead token would delete every user's token on the next cycle.
_INVALID_TOKEN_ERRORS = frozenset({"DeviceNotRegistered"})
_CREDENTIALS_ERROR = "InvalidCredentials"


class HoldReason(StrEnum):
    """Why a message must not simply go again next minute."""

    # The request may have reached Expo (a read timeout, an unreadable answer): resent at
    # once, an accepted push would show twice.
    AMBIGUOUS = "ambiguous"
    # Expo asked us to slow down (429).
    THROTTLED = "throttled"
    # Expo failed on its side (5xx) or refused our request as a whole (401, 403, ...).
    SERVER = "server"
    # Expo refused this one message (a 400 for a request of one).
    REJECTED = "rejected"


@dataclass(frozen=True)
class PushHold:
    reason: HoldReason
    # Expo's Retry-After, in seconds.
    retry_after: float | None = None


@dataclass
class PushSendResult:
    """Per-message Expo ticket outcomes (parallel to the input list)."""

    invalid_tokens: list[str]
    delivered: list[bool]
    receipt_tickets: list[tuple[str, str]] = field(default_factory=list)
    # Per message: why it waits before its next try; None for the ordinary next cycle (a
    # request that never reached Expo goes again then, as does an undelivered ticket).
    holds: list[PushHold | None] = field(default_factory=list)
    # Expo answered 429: no later request went, and the cycle stops for this channel.
    throttled: bool = False


def _invalid_token_from_error(details: object) -> str | None:
    if not isinstance(details, dict):
        return None
    err = details.get("error", "")
    return err if isinstance(err, str) and err in _INVALID_TOKEN_ERRORS else None


def _error_code(details: object) -> str | None:
    if not isinstance(details, dict):
        return None
    err = details.get("error")
    return err if isinstance(err, str) else None


async def fetch_push_receipts(ticket_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Return receipt payloads keyed by Expo ticket id."""
    if not ticket_ids:
        return {}

    receipts: dict[str, dict[str, Any]] = {}
    client = get_pooled_client(EXPO_TIMEOUT_SECONDS)
    for offset in range(0, len(ticket_ids), MAX_RECEIPTS_PER_REQUEST):
        chunk = ticket_ids[offset : offset + MAX_RECEIPTS_PER_REQUEST]
        try:
            response = await client.post(
                EXPO_RECEIPTS_URL,
                json={"ids": chunk},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.exception("Expo push receipt fetch failed count=%s", len(chunk))
            continue
        data = body.get("data")
        if not isinstance(data, dict):
            continue
        for ticket_id, receipt in data.items():
            if isinstance(receipt, dict):
                receipts[str(ticket_id)] = receipt
    return receipts


def receipt_indicates_invalid_token(receipt: dict[str, Any]) -> bool:
    if receipt.get("status") != "error":
        return False
    details = receipt.get("details", {})
    if _error_code(details) == _CREDENTIALS_ERROR:
        logger.critical("Expo push credentials invalid (receipt) — check APNs/FCM config")
        return False
    return _invalid_token_from_error(details) is not None


MAX_MESSAGES_PER_REQUEST = 100


# Never reached Expo: nothing can have been delivered, so the next cycle sends it again.
_UNSENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
# A request Expo refused as a whole because of what it holds: a bad message, or tokens of
# two projects. Halves go again, down to one message, so one bad token cannot hold back
# the other 99 reminders until they age out.
_SPLIT_STATUSES = frozenset({400, 413})


async def _send_range(
    client: httpx.AsyncClient,
    messages: list[dict[str, Any]],
    start: int,
    end: int,
    out: PushSendResult,
) -> None:
    """Send ``messages[start:end]`` as one request and record each message's outcome."""
    chunk = messages[start:end]
    try:
        response = await client.post(
            EXPO_PUSH_URL,
            json=chunk,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    except _UNSENT_ERRORS:
        logger.warning("Expo push not sent offset=%s count=%s", start, len(chunk), exc_info=True)
        return
    except httpx.TransportError:
        # The request may have gone out (a read timeout, a dropped connection).
        logger.exception("Expo push send failed offset=%s count=%s", start, len(chunk))
        _hold(out, start, end, PushHold(HoldReason.AMBIGUOUS))
        return
    except Exception:
        # Failed before any byte went (building the request): nothing can have been
        # delivered, so it is not held as maybe accepted.
        logger.exception("Expo push not sent offset=%s count=%s", start, len(chunk))
        return
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        await _refused(client, messages, start, end, out, exc.response)
        return
    try:
        _read_tickets(response.json(), messages, start, end, out)
    except Exception:
        # Expo answered 2xx: the pushes were most likely accepted.
        logger.warning("Expo response unreadable offset=%s", start, exc_info=True)
        _hold(out, start, end, PushHold(HoldReason.AMBIGUOUS))


async def _refused(
    client: httpx.AsyncClient,
    messages: list[dict[str, Any]],
    start: int,
    end: int,
    out: PushSendResult,
    response: httpx.Response,
) -> None:
    status = response.status_code
    if status in _SPLIT_STATUSES and end - start > 1:
        logger.warning(
            "Expo refused a push request status=%s count=%s; splitting", status, end - start
        )
        middle = (start + end) // 2
        await _send_range(client, messages, start, middle, out)
        if not out.throttled:
            await _send_range(client, messages, middle, end, out)
        return
    if status in _SPLIT_STATUSES:
        logger.error("Expo refused a push message status=%s offset=%s", status, start)
        _hold(out, start, end, PushHold(HoldReason.REJECTED))
        return
    if status == 429:
        logger.warning("Expo push throttled count=%s; sending no more this cycle", end - start)
        _hold(out, start, end, PushHold(HoldReason.THROTTLED, _retry_after(response)))
        out.throttled = True
        return
    logger.error("Expo push request failed status=%s count=%s", status, end - start)
    _hold(out, start, end, PushHold(HoldReason.SERVER, _retry_after(response)))


def _hold(out: PushSendResult, start: int, end: int, hold: PushHold) -> None:
    for index in range(start, end):
        out.holds[index] = hold


def _retry_after(response: httpx.Response) -> float | None:
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


def _read_tickets(
    body: Any, messages: list[dict[str, Any]], start: int, end: int, out: PushSendResult
) -> None:
    tickets = body.get("data", [])
    for i, ticket in enumerate(tickets):
        idx = start + i
        if idx >= end:
            break
        if not isinstance(ticket, dict):
            continue
        token = str(messages[idx].get("to", "") or "")
        if ticket.get("status") == "ok":
            ticket_id = ticket.get("id")
            if isinstance(ticket_id, str) and ticket_id:
                out.delivered[idx] = True
                if token:
                    out.receipt_tickets.append((ticket_id, token))
            continue
        if ticket.get("status") == "error":
            details = ticket.get("details", {})
            if _error_code(details) == _CREDENTIALS_ERROR:
                logger.critical("Expo push credentials invalid — check APNs/FCM config")
                continue
            err = _invalid_token_from_error(details)
            if err and token:
                out.invalid_tokens.append(token)


async def send_push_messages(messages: list[dict[str, Any]]) -> PushSendResult:
    """Send push messages via Expo.

    ``PushSendResult.delivered[i]`` is True when Expo returns ticket ``status: ok`` for
    message *i* — not when a receipt confirms device delivery. Receipts are polled
    later by ``push_notifications.poll_deferred_push_receipts`` for token pruning only.

    On a failed chunk its messages are left unmarked, and ``holds`` says which must wait
    before the next try: one that may have been accepted, throttled, refused or failed on
    Expo's side (``HoldReason``). One that never reached Expo goes again next cycle. Expo
    caps each request at ``MAX_MESSAGES_PER_REQUEST`` messages, so larger batches are
    split into sequential chunks — a failure in one chunk doesn't affect the others — and
    a chunk Expo refuses as a whole (a 400) is split in halves until the bad one is alone.
    A 429 ends the sending: later chunks are left for a later cycle (``throttled``).
    """
    out = PushSendResult(
        invalid_tokens=[],
        delivered=[False] * len(messages),
        holds=[None] * len(messages),
    )
    client = get_pooled_client(EXPO_TIMEOUT_SECONDS)
    for offset in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
        if out.throttled:
            break
        end = min(offset + MAX_MESSAGES_PER_REQUEST, len(messages))
        await _send_range(client, messages, offset, end, out)
    return out
