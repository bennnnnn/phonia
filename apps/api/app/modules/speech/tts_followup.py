"""One billed read-aloud slot for a reply spoken in parts: the lead, then rest clips.

A ``lead`` clip stores a small budget (clips and characters, keyed to a hash of
the lead text); each ``rest`` clip that names the same hash spends from it
instead of taking another daily slot.
"""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis
from redis.exceptions import ResponseError

_TTS_FOLLOWUP_TTL_SECONDS = 120
# One lead + this many rest clips stay on the same daily TTS slot.
_TTS_FOLLOWUP_MAX_CHUNKS = 32
# Lead + rest share one billed slot; cap unbilled rest text at one TTS request.
_TTS_FOLLOWUP_MAX_CHARS = 4000
_CONSUME_TTS_FOLLOWUP_LUA = """
local raw = redis.call('GET', KEYS[1])
if not raw then
  return 0
end
local clips, chars, stored_hash
local first = string.find(raw, ':')
if not first then
  clips = tonumber(raw) or 0
  chars = tonumber(ARGV[3]) or 0
  stored_hash = ''
else
  local second = string.find(raw, ':', first + 1)
  clips = tonumber(string.sub(raw, 1, first - 1)) or 0
  if second then
    chars = tonumber(string.sub(raw, first + 1, second - 1)) or 0
    stored_hash = string.sub(raw, second + 1)
  else
    chars = tonumber(string.sub(raw, first + 1)) or 0
    stored_hash = ''
  end
end
local want_hash = ARGV[4] or ''
if stored_hash == '' or want_hash == '' or stored_hash ~= want_hash then
  return 0
end
local need = tonumber(ARGV[1]) or 0
local ttl = tonumber(ARGV[2]) or 0
if clips < 1 or chars < need then
  return 0
end
clips = clips - 1
chars = chars - need
if clips < 1 or chars < 1 then
  redis.call('DEL', KEYS[1])
else
  redis.call('SET', KEYS[1], clips .. ':' .. chars .. ':' .. stored_hash, 'EX', ttl)
end
return 1
"""


def tts_followup_key(user_id: object) -> str:
    return f"speech_tts_followup:{user_id}"


def tts_lead_hash(lead_text: str) -> str:
    return hashlib.sha256(lead_text.encode("utf-8")).hexdigest()[:16]


def normalize_tts_part(raw: str | None) -> str:
    part = (raw or "full").strip().lower()
    if part in {"full", "lead", "rest"}:
        return part
    return "full"


def _tts_followup_payload(lead_text: str) -> str | None:
    remaining_chars = _TTS_FOLLOWUP_MAX_CHARS - len(lead_text)
    if remaining_chars <= 0:
        return None
    return f"{_TTS_FOLLOWUP_MAX_CHUNKS}:{remaining_chars}:{tts_lead_hash(lead_text)}"


async def store_tts_followup(redis: Redis, key: str, lead_text: str) -> None:
    """After a lead clip: the budget its rest clips spend instead of a daily slot."""
    payload = _tts_followup_payload(lead_text)
    if payload is not None:
        await redis.set(key, payload, ex=_TTS_FOLLOWUP_TTL_SECONDS)


def _parse_tts_followup(raw: object) -> tuple[int, int, str] | None:
    if raw is None:
        return None
    text = raw.decode() if isinstance(raw, bytes | bytearray) else str(raw)
    parts = text.split(":", 2)
    try:
        if len(parts) == 3:
            return int(parts[0]), int(parts[1]), parts[2]
        if len(parts) == 2:
            return int(parts[0]), int(parts[1]), ""
        return int(text), _TTS_FOLLOWUP_MAX_CHARS, ""
    except ValueError:
        return None


async def _try_consume_tts_followup_plain(
    redis: Redis, key: str, char_count: int, lead_hash: str
) -> bool:
    parsed = _parse_tts_followup(await redis.get(key))
    if parsed is None:
        return False
    clips, chars, stored_hash = parsed
    if not stored_hash or stored_hash != lead_hash:
        return False
    if clips < 1 or chars < char_count:
        return False
    clips -= 1
    chars -= char_count
    if clips < 1 or chars < 1:
        await redis.delete(key)
    else:
        await redis.set(
            key,
            f"{clips}:{chars}:{stored_hash}",
            ex=_TTS_FOLLOWUP_TTL_SECONDS,
        )
    return True


async def try_consume_tts_followup(redis: Redis, key: str, char_count: int, lead_hash: str) -> bool:
    """Spend one rest clip of *char_count* characters; False when it must be billed.

    Atomic via Lua; GET+SET fallback when EVAL is unavailable (some fakeredis setups).
    """
    try:
        result = await redis.eval(
            _CONSUME_TTS_FOLLOWUP_LUA,
            1,
            key,
            char_count,
            _TTS_FOLLOWUP_TTL_SECONDS,
            _TTS_FOLLOWUP_MAX_CHARS,
            lead_hash,
        )
        return int(result) == 1
    except ResponseError:
        return await _try_consume_tts_followup_plain(redis, key, char_count, lead_hash)
