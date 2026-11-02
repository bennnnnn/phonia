"""Reject classic STT hallucinations on weak/short clips.

Do not blacklist these phrases globally — a user may actually say them.
Only drop the transcript when the clip is too small to be real speech.
"""

from __future__ import annotations

# Typical Whisper/YouTube outros on silence or fan noise.
_HALLUCINATION_PHRASES = frozenset(
    {
        "thank you for watching",
        "thanks for watching",
        "please subscribe",
        "thanks for listening",
        "subscribe to my channel",
        "thank you for listening",
    }
)
# ~1-2s of compressed voice is larger than this; silence containers are not.
_WEAK_AUDIO_BYTES = 24_000


def _normalized_phrase(text: str) -> str:
    lowered = text.lower()
    chars: list[str] = []
    prev_space = True
    for char in lowered:
        if char.isalnum():
            chars.append(char)
            prev_space = False
        elif char.isspace():
            if not prev_space:
                chars.append(" ")
                prev_space = True
    return "".join(chars).strip()


def sanitize_transcript(text: str, *, audio_size: int) -> str:
    """Return the transcript, or empty when it looks like a no-speech hallucination."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return ""
    if audio_size >= _WEAK_AUDIO_BYTES:
        return cleaned
    if _normalized_phrase(cleaned) in _HALLUCINATION_PHRASES:
        return ""
    return cleaned
