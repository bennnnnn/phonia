"""A question in parts the solver reads one part of: each part solved on its own.

"A crane lifts a 450 kg concrete to the top of a 50 m building in 5 s … a) The potential
energy of the concrete. b) The power developed by the crane" was solved for the energy
alone, and that one card sat under the reply's last Answer as if it answered both
(2026-10-29, a grade 7 physics book). The solver reads one ask, so each part is read
alone: the question's givens with that part's ask, or the question up to that ask. Every
part must solve, each to a different answer, or nothing here is used.

Two parts asking for the same kind of quantity ("the normal reaction force" and "the
frictional force", both newtons) are only taken when each part brings numbers of its
own ("the earth, where g = 10 m/s²", "the moon, where g = 1.6 m/s²"): a dimension does
not tell a normal force from a friction, and the friction answered both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from app.core.config import Settings
from app.modules.physics.ask import QUANTITY, SENTENCE, asked_dimensions
from app.modules.physics.block import build_verified_physics_block, part_title
from app.modules.physics.extract import extract_physics_intent
from app.modules.physics.numbers import normalize_physics_units
from app.services.law_binding.ask import ASK_VERBS
from app.services.solving import PhysicsPartWorking, VerifiedPhysicsBlock
from app.services.workout import PHYSICS_WORKOUT_PARTS_PROMPT

# "a) What is…", "(b) the moon…", "c. input work": a part's label after a space.
_LABEL = re.compile(r"(?:^|(?<=[\s,;:.?!]))\(?([a-h])[).]\s", re.IGNORECASE)
# "how long does it take" finds a time: the label names it as a noun.
_HOW_NOUNS = {"how long": "Time", "how far": "Distance", "how fast": "Speed", "how high": "Height"}
_MAX_PARTS = 8
# A part that depends on another or on a change ("3 s later", "in the next 3 s", "its
# kinetic energy if the speed doubles") is no question on its own: read alone it was
# answered for the unchanged values (review, 2026-10-29).
_RELATIVE = re.compile(
    r"\b(?:if|instead|later|next|then|again|another|more|doubles?|doubled|halve[sd]?|"
    r"triples?|tripled|during|remaining)\b|\b(?:after\s+that|the\s+rest\s+of)\b",
    re.IGNORECASE,
)
# The units of the values an ask states itself: "where g = 1.6 m/s^2" is m/s^2.
# Read from the start of a number only: tried at every digit, a long run was quadratic.
_VALUE_UNIT = re.compile(r"(?<![\d.])\d[\d.]*\s*([A-Za-zµμ°Ω][\w/^²³*·]*)")


@dataclass(frozen=True)
class _Parts:
    givens: str
    asks: list[str]
    # The question without the asks after each part: its own and the earlier ones,
    # with every given wherever it was written.
    through: list[str]


def _sentences(text: str) -> list[str]:
    return [match.group().strip() for match in SENTENCE.finditer(text) if match.group().strip()]


def _asks(sentence: str) -> bool:
    return sentence.endswith("?") or ASK_VERBS.search(sentence) is not None


def _split(text: str) -> _Parts | None:
    """The givens, each part's ask, and each part's reading with the later asks out.

    A sentence that asks nothing is a given wherever it stands: "(Take g = 10 m/s²)"
    after the last part holds for every part, and read as that part's alone, the first
    part was solved with 9.8 (review, 2026-10-29).
    """
    labels = list(_LABEL.finditer(text))
    letters = [match.group(1).lower() for match in labels]
    if len(labels) >= 2 and letters == list("abcdefgh"[: len(labels)]):
        ends = [match.start() for match in labels[1:]] + [len(text)]
        stem = text[: labels[0].start()].strip()
        asks: list[str] = []
        givens: list[str] = [stem] if stem else []
        for match, end in zip(labels, ends, strict=True):
            sentences = _sentences(text[match.end() : end].strip(" ,;"))
            if not sentences:
                return None
            # A part's first sentence is its ask, with or without a question word.
            asks.append(sentences[0])
            givens.extend(sentence for sentence in sentences[1:] if not _asks(sentence))
        tail = " ".join(givens[1:] if stem else givens)
        through = [
            " ".join([stem, *asks[: number + 1], tail]).strip() for number in range(len(asks))
        ]
        return _Parts(" ".join(givens), asks, through)
    sentences = _sentences(text)
    asking = [_asks(sentence) for sentence in sentences]
    if sum(asking) < 2:
        return None
    asks = [sentence for sentence, asks_one in zip(sentences, asking, strict=True) if asks_one]
    through = []
    for number in range(len(asks)):
        later = set(asks[number + 1 :])
        through.append(" ".join(sentence for sentence in sentences if sentence not in later))
    stated = " ".join(
        sentence for sentence, asks_one in zip(sentences, asking, strict=True) if not asks_one
    )
    return _Parts(stated, asks, through)


def _own_values(asks: list[str]) -> bool:
    """Every part states its own values, of the same kinds ("the earth, where g = 10
    m/s²", "the moon, where g = 1.6 m/s²"), so no part needs another's."""
    kinds = [frozenset(unit.lower() for unit in _VALUE_UNIT.findall(ask)) for ask in asks]
    return all(kinds) and len(set(kinds)) == 1


def _solved(text: str, settings: Settings) -> VerifiedPhysicsBlock | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    try:
        return build_verified_physics_block(intent, settings)
    except Exception:
        return None


def _title(ask: str, op: str, symbol: str, givens: str) -> str:
    """The part's label from its own ask ("The power developed…" is "Power"), or from the
    question's ("What is her weight on: a) the earth" is "Weight")."""
    asked = [sentence for sentence in _sentences(givens) if _asks(sentence)]
    named = QUANTITY.search(ask) or (QUANTITY.search(asked[-1]) if asked else None)
    if named is None:
        return part_title(op, symbol)
    phrase = named.group(0).lower()
    return _HOW_NOUNS.get(phrase, phrase[:1].upper() + phrase[1:])


def _working(block: VerifiedPhysicsBlock, ask: str, givens: str) -> PhysicsPartWorking | None:
    intent = block.physics_intent
    if intent is None or not block.display_answer or not block.physics_formulas:
        return None
    op = intent.physics_op or ""
    symbol = block.physics_formulas[0].split(" = ", 1)[0].strip()
    return PhysicsPartWorking(
        op=op,
        symbol=symbol,
        title=_title(ask, op, symbol, givens),
        formulas=block.physics_formulas,
        substitutions=block.physics_substitutions,
        answer=block.canonical_answer or block.display_answer,
        display_answer=block.display_answer,
    )


def _first_new_part(
    ask: str,
    candidates: tuple[str, ...],
    workings: list[PhysicsPartWorking],
    settings: Settings,
    givens: str,
) -> tuple[VerifiedPhysicsBlock, PhysicsPartWorking] | None:
    """The first reading of a part that solves to an answer no earlier part has."""
    for candidate in candidates:
        block = _solved(candidate, settings)
        working = None if block is None else _working(block, ask, givens)
        if (
            block is not None
            and working is not None
            and all(working.display_answer != seen.display_answer for seen in workings)
        ):
            return block, working
    return None


def solve_in_parts(text: str, settings: Settings) -> VerifiedPhysicsBlock | None:
    """One verified block holding every part of ``text``, each solved on its own; None
    unless every part solves to its own answer."""
    # Read as the laws read the whole question: "a) Find the VR. b) Find the MA." of a
    # plank names its machine once, and each part read alone lost it (review, 2026-10-30).
    parts = _split(normalize_physics_units(text))
    if parts is None or len(parts.asks) > _MAX_PARTS:
        return None
    if any(_RELATIVE.search(ask) for ask in parts.asks):
        return None
    own = _own_values(parts.asks)
    blocks: list[VerifiedPhysicsBlock] = []
    workings: list[PhysicsPartWorking] = []
    for number, ask in enumerate(parts.asks):
        # A value written in another part's ask ("taking g = 10 m/s²") may hold for this
        # one: it is read alone only when each part states its own values, or no other does.
        others_state = any(
            _VALUE_UNIT.search(other) for index, other in enumerate(parts.asks) if index != number
        )
        alone = f"{parts.givens} {ask}".strip()
        through = parts.through[number]
        candidates = (alone, through) if own or not others_state else (through,)
        part = _first_new_part(ask, candidates, workings, settings, parts.givens)
        if part is None:
            return None
        blocks.append(part[0])
        workings.append(part[1])
    dimensions = [asked_dimensions(f"{parts.givens} {ask}") for ask in parts.asks]
    # The asks as the laws read them: "MA of the machine" names "mechanical advantage".
    read = [normalize_physics_units(ask).lower() for ask in parts.asks]
    names = [_law_name(working.op, ask) for working, ask in zip(workings, read, strict=True)]
    for first in range(len(parts.asks)):
        for second in range(first + 1, len(parts.asks)):
            shared = set(dimensions[first]) & set(dimensions[second])
            if (shared or not dimensions[first] or not dimensions[second]) and not (
                own or _named_apart(names, read, first, second)
            ):
                return None
    return _joined(blocks, workings)


def _law_name(op: str, ask: str) -> str | None:
    """The longest phrase the part's law is asked by that its own ask says."""
    from app.modules.physics.catalog import formula_spec

    spec = formula_spec(op)
    if spec is None or spec.binding is None:
        return None
    said = [phrase for phrase in spec.binding.asks if phrase in ask]
    return max(said, key=len) if said else None


def _named_apart(names: list[str | None], asks: list[str], first: int, second: int) -> bool:
    """Two parts of one kind each ask for their own law by its name, and neither name is
    in the other's ask: "the velocity ratio" and "the mechanical advantage" are two
    numbers; "the normal reaction force" and "the frictional force" both say "force"."""
    one, other = names[first], names[second]
    return (
        one is not None
        and other is not None
        and one not in asks[second]
        and other not in asks[first]
    )


def reads_in_parts(text: str) -> bool:
    """A lettered question one of whose parts a law reads: physics, though the whole is
    read by none ("What is her weight on: a) the earth, where g = 10 m/s²? b) the moon…")."""
    from app.modules.physics.binding import bind_physics_intent

    if len(_LABEL.findall(text)) < 2:
        return False
    parts = _split(normalize_physics_units(text))
    return parts is not None and any(
        bind_physics_intent(f"{parts.givens} {ask}") is not None for ask in parts.asks
    )


def _pictures(block: VerifiedPhysicsBlock) -> list[dict[str, object]]:
    specs = [block.canonical_fence, *block.canonical_fences]
    return [spec for spec in specs if spec is not None and spec.get("type") != "answer"]


def _joined(
    blocks: list[VerifiedPhysicsBlock], workings: list[PhysicsPartWorking]
) -> VerifiedPhysicsBlock:
    lines = [
        f"This question has {len(blocks)} parts. Each part below was solved and verified "
        "on its own, in the order asked; copy each part's verified numbers.",
        PHYSICS_WORKOUT_PARTS_PROMPT,
    ]
    for letter, block in zip("abcdefgh", blocks, strict=False):
        lines.extend([f"Part ({letter}):", block.text])
    pictures = next((spec for spec in map(_pictures, blocks) if spec), [])
    card = r";\quad ".join(working.display_answer for working in workings)
    first = blocks[0]
    return replace(
        first,
        text="\n".join(lines),
        canonical_fence={"type": "answer", "content": card},
        canonical_fences=list(pictures),
        canonical_answer="; ".join(working.answer for working in workings),
        display_answer=card,
        allow_direct=False,
        physics_working="\n\n".join(block.physics_working or "" for block in blocks),
        physics_formulas=tuple(row for working in workings for row in working.formulas),
        physics_substitutions=tuple(row for working in workings for row in working.substitutions),
        physics_parts=tuple(workings),
    )
