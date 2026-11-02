"""What memory's model calls answer in mock mode (no provider key).

Deterministic stand-ins, so a development API without a key still learns and merges
facts. They lived in ``gateways/mock_llm``, which then had to import memory's schemas
(code-health audit ARCH-04).
"""

from typing import cast, get_args

from app.models.schemas.common import MemoryType
from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult, MemorySectionItem


async def offline_memory_facts(
    user_message: str, existing_facts: list[dict[str, str]]
) -> MemoryFactUpdateResult | None:
    del existing_facts
    if len(user_message.strip()) < 10:
        return None
    return MemoryFactUpdateResult(
        ops=[
            MemoryFactOp(
                op="add",
                type="focus",
                text=f"Recently discussed: {user_message[:200]}",
                confidence=0.6,
                sensitivity="normal",
                importance=0.4,
            )
        ]
    )


async def offline_section_merge(section_type: str, prior_text: str) -> MemorySectionItem:
    valid_memory_types = frozenset(get_args(MemoryType))
    sentences = [part.strip() for part in prior_text.split(".") if part.strip()]
    unique: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(sentence)
    summary = ". ".join(unique).strip()
    if summary and not summary.endswith("."):
        summary += "."
    return MemorySectionItem(
        type=cast(
            MemoryType,
            section_type if section_type in valid_memory_types else "fact",
        ),
        summary=summary or prior_text[:300],
        confidence=0.9,
    )
