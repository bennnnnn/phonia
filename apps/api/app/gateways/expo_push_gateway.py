"""Expo Push API gateway."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
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


@dataclass
class PushSendResult:
    """Per-message Expo ticket outcomes (parallel to the input list)."""

    invalid_tokens: list[str]
    delivered: list[bool]
    receipt_tickets: list[tuple[str, str]] = field(default_factory=list)


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


async def _send_chunk(
    client: httpx.AsyncClient,
    messages: list[dict[str, Any]],
    offset: int,
    delivered: list[bool],
    invalid: list[str],
    receipt_tickets: list[tuple[str, str]],
) -> None:
    chunk = messages[offset : offset + MAX_MESSAGES_PER_REQUEST]
    try:
        response = await client.post(
            EXPO_PUSH_URL,
            json=chunk,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        response.raise_for_status()
    except Exception:
        logger.exception("Expo push send failed offset=%s count=%s", offset, len(chunk))
        return
    try:
        body = response.json()
        tickets = body.get("data", [])
        for i, ticket in enumerate(tickets):
            idx = offset + i
            if idx >= len(messages):
                break
            if not isinstance(ticket, dict):
                continue
            token = str(messages[idx].get("to", "") or "")
            if ticket.get("status") == "ok":
                ticket_id = ticket.get("id")
                if isinstance(ticket_id, str) and ticket_id:
                    delivered[idx] = True
                    if token:
                        receipt_tickets.append((ticket_id, token))
                continue
            if ticket.get("status") == "error":
                details = ticket.get("details", {})
                if _error_code(details) == _CREDENTIALS_ERROR:
                    logger.critical("Expo push credentials invalid — check APNs/FCM config")
                    continue
                err = _invalid_token_from_error(details)
                if err and token:
                    invalid.append(token)
    except Exception:
        logger.debug("Expo response parse failed offset=%s", offset, exc_info=True)


async def send_push_messages(messages: list[dict[str, Any]]) -> PushSendResult:
    """Send push messages via Expo.

    ``PushSendResult.delivered[i]`` is True when Expo returns ticket ``status: ok`` for
    message *i* — not when a receipt confirms device delivery. Receipts are polled
    later by ``push_notifications.poll_deferred_push_receipts`` for token pruning only.

    On transport/API failure for a given chunk, that chunk's messages are left
    unmarked so the caller can retry on the next scheduler cycle without duplicate
    sends for already-accepted tickets. Expo caps each request at
    ``MAX_MESSAGES_PER_REQUEST`` messages, so larger batches are split into
    sequential chunks — a failure in one chunk doesn't affect the others.
    """
    if not messages:
        return PushSendResult(invalid_tokens=[], delivered=[])

    invalid: list[str] = []
    delivered: list[bool] = [False] * len(messages)
    receipt_tickets: list[tuple[str, str]] = []

    client = get_pooled_client(EXPO_TIMEOUT_SECONDS)
    for offset in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
        await _send_chunk(client, messages, offset, delivered, invalid, receipt_tickets)

    return PushSendResult(
        invalid_tokens=invalid,
        delivered=delivered,
        receipt_tickets=receipt_tickets,
    )
