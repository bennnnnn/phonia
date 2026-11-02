"""Which writing deliverable a turn is asking for.

Email, message, social, prose, translation, and edit. Turn routing asks this
only to decide whether a draft should load profile context.
"""

import re

from app.modules.turn_reading.writing_locales import locale_draft_kind
from app.services.text_normalize import collapse_ws

# The words that name what an email or message is for may stand between the
# verb and the noun: "write a resignation email", "a follow-up email".
_DRAFT_PURPOSE_WORDS = r"(?:[a-z]+(?:-[a-z]+)? ){0,2}"
# Who it goes to may stand between "send" and the draft: "send my boss an email".
_SEND_TO = r"(?:(?:me|him|her|them|us) |(?:my |our )?[a-z'-]+ (?=an? ))?"

_EMAIL_WRITING = re.compile(
    r"\b(?:"
    r"send " + _SEND_TO + r"(?:an? )?email|"
    r"email (?:to|my)|"
    r"(?:write|draft|compose) (?:me )?(?:an? |the )?" + _DRAFT_PURPOSE_WORDS + r"e-?mail|"
    r"(?:reply|respond|answer)(?: back)?(?: to)? (?:this|that|the|her|his|their|my|an?) e-?mail"
    r")\b",
    re.IGNORECASE,
)

_MESSAGE_WRITING = re.compile(
    r"\b(?:"
    r"send " + _SEND_TO + r"(?:a )?" + _DRAFT_PURPOSE_WORDS + r"(?:text|message)|"
    r"(?:write|draft|compose) (?:me )?(?:an? )?"
    + _DRAFT_PURPOSE_WORDS
    + r"(?:text|message|sms|reply)|"
    r"(?:text|message|reply) (?:to|for|my)|"
    r"reply (?:to|saying|that says)|"
    r"(?:answer|respond to)(?: back)? (?:this|that|the|her|his|their|my) "
    r"(?:message|text|dm|sms|whatsapp)|"
    r"respond to (?:this|that|it|her|him|them)\b"
    r")\b",
    re.IGNORECASE,
)

# "Tell my landlord the heater is broken", "let my team know we moved to 3pm":
# Recall cannot pass it on, so it is a message to send. "Should I tell my boss
# I'm pregnant?" asks for advice: the line has to start with the request.
_TELL_RECIPIENT = re.compile(
    r"^(?:(?:(?:can|could|would|will) you|please)[,\s]+)*"
    r"(?:tell my [a-z'-]+(?: [a-z'-]+)? (?:that \w|(?:the|my|our|his|her|their|i|i'm|i'll|"
    r"i've|we|we're|we'll|it|it's|he|she|they|there)\b)|"
    r"let my [a-z'-]+(?: [a-z'-]+)? know\b)",
    re.IGNORECASE,
)

# "How should I reply to 'we need to talk'?" asks for the reply itself when it
# quotes or pastes the message; "how do I reply to emails faster" is advice.
_REPLY_HOWTO = re.compile(
    r"^how (?:should|do|can|would) i (?:reply|respond|answer)(?: back)?(?: to)?\b"
    r"(?=.*(?:[\"\u201c\u2018]|\s'|:\s*\S))",
    re.IGNORECASE,
)

_SOCIAL_WRITING = re.compile(
    r"\b(?:write|draft|compose|create|rewrite|make)\s+"
    r"(?:me\s+)?(?:(?:an?|the|my|one)\s+)?"
    r"(?:(?:(?:very\s+)?(?:short|long|brief|concise|detailed|formal|informal|"
    r"professional|personal|promotional|funny|casual)|"
    r"\d+(?:[- ](?:word|character)))\s+){0,2}"
    r"(?:linkedin (?:(?:update)\s+)?(?:post|note)|"
    r"facebook (?:(?:update)\s+)?(?:post|status)|fb post|"
    r"instagram (?:caption|post|story)|tiktok (?:caption|post)|threads post|"
    r"social(?: media)? post|"
    r"twitter post|x post|tweet|caption|dating (?:app )?bio|"
    # "write a post for facebook", "a status on fb"
    r"(?:post|status|update|caption) (?:for|on) "
    r"(?:facebook|fb|instagram|insta|ig|linkedin|twitter|x|threads|tiktok|social media))\b",
    re.IGNORECASE,
)

_DIRECT_REQUEST_INTRO = (
    r"(?:(?:(?:can|could|would|will) you|please|por favor|s'il vous plaît|"
    r"bitte|per favore|lütfen|maaloo)[,\s]+)*"
    r"(?:(?:help me(?: to)?|i (?:want|need)(?: you)? to)[,\s]+)?"
)

_TRANSLATION_WRITING = re.compile(
    r"^(?:" + _DIRECT_REQUEST_INTRO + r"(?:"
    r"(?:translate|traduc(?:e|ir)|traduis|traduire|[uü]bersetze|traduci|"
    r"traduz(?:a|ir)?|cevir|çevir|hiiki)\b|"
    r"(?:переведи|ተርጉም)\b|"
    r"translation\s*:))",
    re.IGNORECASE,
)

_UNSPACED_TRANSLATION_COMMAND = re.compile(
    r"^(?:"
    r"(?:请|請)?(?:翻译|翻譯)(?:"
    r"(?:一下)?(?:这句话|這句話|这个句子|這個句子|这段文字|這段文字|"
    r"这篇文章|這篇文章|这封邮件|這封郵件|以下内容|以下內容|下面内容|下面內容|"
    r"上述内容|上述內容)(?=$|[.!?\u3002\uFF01\uFF1F]|"
    r"(?:成|为|為)(?:英文|英语|英語|中文|汉语|漢語|日文|日语|日語|韩文|韓文|"
    r"韩语|韓語|法文|法语|法語|德文|德语|德語|西班牙文|西班牙语|西班牙語|"
    r"俄文|俄语|俄語|阿拉伯文|阿拉伯语|阿拉伯語)"
    r"(?=$|[.!?\u3002\uFF01\uFF1F]|[:\uFF1A\"'“\u2018「『])|"
    r"[:\uFF1A\"'“\u2018「『])|"
    r"一下(?=$|[.!?\u3002\uFF01\uFF1F])|"
    r"(?:成|为|為)(?:英文|英语|英語|中文|汉语|漢語|日文|日语|日語|韩文|韓文|"
    r"韩语|韓語|法文|法语|法語|德文|德语|德語|西班牙文|西班牙语|西班牙語|"
    r"俄文|俄语|俄語|阿拉伯文|阿拉伯语|阿拉伯語)"
    r"(?=$|[.!?\u3002\uFF01\uFF1F]|[:\uFF1A\"'“\u2018「『])|"
    r"[:\uFF1A\"'“\u2018「『]|\s+(?=[\"'“\u2018「『A-Za-z0-9])|(?=[A-Za-z0-9]))|"
    r"(?:翻訳してください|訳してください)(?=$|[\s.!?:\u3002\uFF01\uFF1F\uFF1A])|"
    r"(?:翻訳して|訳して)\s+ください(?=$|[\s.!?:\u3002\uFF01\uFF1F\uFF1A])|"
    r"(?:翻訳して|訳して)(?=$|[.!?:\u3002\uFF01\uFF1F\uFF1A])|"
    r"(?:번역)\s*(?:좀\s*)?"
    r"(?:해\s*(?:주세요|줘)|하세요|(?:을\s*)?부탁(?:드립니다|드려요|해요|해\s*(?:주세요|줘))?)"
    r"(?=$|[\s.!?:\u3002\uFF01\uFF1F\uFF1A])|"
    r"(?:번역해)(?=$|[.!?:\u3002\uFF01\uFF1F\uFF1A])"
    r")",
    re.IGNORECASE,
)

_PROSE_WRITING = re.compile(
    r"\b(?:write|draft|compose|rewrite|create)(?: me)?\s+"
    r"(?:(?:an?|one|the)\s+)?"
    r"(?:(?:(?:very\s+)?(?:short|long|brief|concise|detailed|formal|informal|"
    r"professional|personal|persuasive|creative|academic)|"
    r"\d+(?:[- ](?:word|paragraph|page))?)\s+){0,3}"
    r"(?:paragraph|essay|article|story|poem|cover\s+letter|letter|statement|"
    r"announcement|description|script|outline|r[eé]sum[eé]s?|cv|biograph(?:y|ies)|"
    r"bio)\b|"
    # The user's own record: "write my resume", "make a CV for a nurse", "polish my cover letter".
    r"\b(?:write|draft|compose|rewrite|create|make|build|prepare|redo|polish|improve)"
    r"(?: me| up)?\s+(?:(?:an?|one|the|my)\s+)?(?:(?:new|short|professional|simple|basic|"
    r"good|better|strong)\s+)?(?:cover\s+letter|r[eé]sum[eé]|cv)\b",
    re.IGNORECASE,
)

_EDIT_WRITING = re.compile(
    r"(?:^" + _DIRECT_REQUEST_INTRO + r"(?:"
    r"(?:correct(?: this)?|proofread|rewrite (?:this|it)|"
    r"fix (?:the |my |this )?(?:sentence|grammar|spelling|typos?)|"
    r"correct (?:the |my )?(?:grammar|spelling)|"
    r"grammar check|check (?:the |my |this )?(?:sentence|grammar|spelling))\b|"
    r"\bis this (?:sentence )?(?:correct|right|grammatical)\b))",
    re.IGNORECASE,
)

# A change of tone or length to text the user pasted: "make this more polite:
# ...". The result is wording they will paste and send, so it is a copy block,
# not a corrected sentence with notes.
_TONES = (
    r"(?:professional|polite|formal|informal|casual|friendly|friendlier|nice|nicer|kind|"
    r"kinder|warm|warmer|soft|softer|firm|firmer|gentle|gentler|respectful|confident|"
    r"assertive|apologetic|grateful|positive|persuasive|diplomatic|natural|human|clear|"
    r"clearer|simple|simpler|concise|short|shorter|long|longer|better|smooth|smoother|"
    r"funny|funnier|fun|cute|romantic|sweet|sweeter|serious|enthusiastic|excited|happy|"
    r"cheerful|empathetic|sincere)"
)
_REWRITE_WRITING = re.compile(
    r"^" + _DIRECT_REQUEST_INTRO + r"(?:"
    r"(?:make|rewrite|rephrase|reword|turn|change|edit|write) "
    r"(?P<object>this|it|that|my (?:message|text|email|post|reply|caption)|"
    r"the (?:message|text|email|post|reply|caption))"
    r"(?: to)?(?: (?:sound|look|read|be))? (?:(?:a )?(?:bit|little|lot|much|way) )?"
    r"(?:more |less |too )?" + _TONES + r"|"
    r"(?:rephrase|reword|paraphrase|polish|shorten|simplify|soften|tone down) "
    r"(?P<short_object>this|it|that|my|the)\b"
    r")",
    re.IGNORECASE,
)
# A message or email pasted after a colon, on its own lines, or in quotes is
# what a reply answers or a rewrite changes.
PASTED_TEXT = re.compile(r":\s*\S+(?:\s+\S+){2,}|\n\s*\S|[\"\u201c]")


def _is_rewrite(cleaned: str, written: str) -> bool:
    """A tone or length change to text in this message, or to a named message.

    "Make it shorter" with nothing pasted refers to the previous reply, which
    the follow-up contract handles; it is not new text to paste and send.
    ``written`` keeps the line breaks a pasted message starts on.
    """
    match = _REWRITE_WRITING.search(cleaned)
    if match is None:
        return False
    target = (match.group("object") or match.group("short_object") or "").lower()
    if target in {"this", "it", "that", "the", "my"}:
        return PASTED_TEXT.search(written) is not None
    return True


_WRITING_SEQUENCE_PREFIX = re.compile(r"^(?:then|now|also|next)[,\s]+", re.IGNORECASE)

_DIRECT_REQUEST_PREFIX = re.compile(r"^" + _DIRECT_REQUEST_INTRO, re.IGNORECASE)

_WRITING_HOWTO = re.compile(
    r"^(?:how (?:do|can|should|would) i|how to)\b",
    re.IGNORECASE,
)


def _normalize_writing_followup(text: str) -> str:
    return _WRITING_SEQUENCE_PREFIX.sub("", text.strip(), count=1)


def _starts_direct_writing_request(text: str) -> bool:
    candidate = _normalize_writing_followup(text)
    if (
        _TRANSLATION_WRITING.search(candidate)
        or _UNSPACED_TRANSLATION_COMMAND.search(candidate)
        or _EDIT_WRITING.search(candidate)
        or locale_draft_kind(candidate) is not None
    ):
        return True
    prefix = _DIRECT_REQUEST_PREFIX.match(candidate)
    prefix_end = prefix.end() if prefix else 0
    return any(
        (match := pattern.search(candidate)) is not None and match.start() <= prefix_end
        for pattern in (_EMAIL_WRITING, _MESSAGE_WRITING, _SOCIAL_WRITING, _PROSE_WRITING)
    )


def _has_later_closing_single_quote(text: str, index: int, quote: str) -> bool:
    """Check for a later quote terminator, ignoring contraction apostrophes."""
    for later in range(index + 1, len(text)):
        if text[later] != quote:
            continue
        if 0 < later < len(text) - 1:
            if text[later - 1].isalnum() and text[later + 1].isalnum():
                continue
        before = text[later - 1] if later > 0 else ""
        after = text[later + 1] if later + 1 < len(text) else ""
        if not after or before in ".!?" or after in ".!?;:,":
            return True
    return False


def _is_strong_single_quote_closer(text: str, index: int) -> bool:
    before = text[index - 1] if index > 0 else ""
    after = text[index + 1] if index + 1 < len(text) else ""
    return not after or before in ".!?" or after in ".!?;:,"


def _next_sentence_tail(text: str) -> str | None:
    """Return text after the next plausible sentence boundary."""
    quote_closers = {
        '"': '"',
        "'": "'",
        "“": "”",
        "\u2018": "\u2019",
        "「": "」",
        "『": "』",
    }
    closing_quote: str | None = None
    require_strong_single_quote_closer = False
    delimiter_stack: list[str] = []
    boundary_end: int | None = None
    for index, char in enumerate(text):
        if closing_quote is not None:
            if char in ".!?" and index + 1 < len(text):
                quote_end = index + 1
                if text[quote_end] == closing_quote:
                    quote_end += 1
                    if not delimiter_stack and (
                        quote_end == len(text) or text[quote_end].isspace()
                    ):
                        tail = text[quote_end:].strip()
                        if tail and _starts_direct_writing_request(tail):
                            return tail
            if char == closing_quote:
                if char in {"'", "\u2019"} and 0 < index < len(text) - 1:
                    if text[index - 1].isalnum() and text[index + 1].isalnum():
                        continue
                    if require_strong_single_quote_closer and not _is_strong_single_quote_closer(
                        text, index
                    ):
                        continue
                closing_quote = None
                require_strong_single_quote_closer = False
            continue
        if char in quote_closers:
            # Apostrophes following a word are contractions or possessives,
            # never the opening delimiter for a new single-quoted span.
            if char == "'" and index > 0 and text[index - 1].isalnum():
                continue
            closing_quote = quote_closers[char]
            require_strong_single_quote_closer = char in {"'", "\u2018"} and (
                _has_later_closing_single_quote(text, index, closing_quote)
            )
            continue
        if char in "([{":
            delimiter_stack.append({"(": ")", "[": "]", "{": "}"}[char])
            continue
        if delimiter_stack and char == delimiter_stack[-1]:
            delimiter_stack.pop()
            continue
        if delimiter_stack:
            continue
        if char not in ".!?":
            continue
        next_index = index + 1
        while next_index < len(text) and text[next_index] in ".!?":
            next_index += 1
        if next_index < len(text) and not text[next_index].isspace():
            continue
        if char == ".":
            prefix = text[:next_index].lower()
            abbreviation = re.search(
                r"(?:\b(?:mr|mrs|ms|dr|prof|sr|jr|st|vs|etc)\.|(?:\b[a-z]\.){2,})$",
                prefix,
            )
            if abbreviation:
                is_etc_sequence = prefix.endswith("etc.") and _WRITING_SEQUENCE_PREFIX.match(
                    text[next_index:].lstrip()
                )
                if not is_etc_sequence:
                    continue
        boundary_end = next_index
        break
    if boundary_end is None:
        return None
    tail = text[boundary_end:].strip()
    return tail or None


def _after_initial_writing_howto(text: str) -> str | None:
    """Drop a leading how-to sentence, but retain later text."""
    if not _WRITING_HOWTO.search(text):
        return text
    return _next_sentence_tail(text)


def _find_direct_writing_followup(text: str) -> str | None:
    """Find the first sentence after a how-to that starts a writing command."""
    candidate: str | None = text
    while candidate:
        if _starts_direct_writing_request(candidate):
            return _normalize_writing_followup(candidate)
        candidate = _next_sentence_tail(candidate)
    return None


def writing_request_kind(text: str) -> str | None:
    """Return the writing shape the response contract should preserve."""
    cleaned = collapse_ws(text)
    if not cleaned:
        return None
    if _REPLY_HOWTO.search(cleaned):
        return "message"
    # Questions about how to produce or manage a writing artifact are advice,
    # not requests for Recall to draft it. A later sentence can still contain
    # an explicit deliverable request and must keep its output contract.
    had_initial_howto = bool(_WRITING_HOWTO.search(cleaned))
    writing_candidate = _after_initial_writing_howto(cleaned)
    if writing_candidate is None:
        return None
    cleaned = writing_candidate
    if had_initial_howto:
        direct_followup = _find_direct_writing_followup(cleaned)
        if direct_followup is None:
            return None
        cleaned = direct_followup
    # Translation leads before quoted-source classifiers: `Translate "write
    # me an email" into Spanish` is a translation, not a request to draft an
    # email. An actual email deliverable such as "write an email in Spanish"
    # has no translation verb and still routes to email below.
    if _TRANSLATION_WRITING.search(cleaned) or _UNSPACED_TRANSLATION_COMMAND.search(cleaned):
        return "translation"
    # "Rewrite this to sound friendlier: ..." is a new tone, not a proofread.
    if _is_rewrite(cleaned, text):
        return "rewrite"
    if _EDIT_WRITING.search(cleaned):
        return "edit"
    shape_matches: list[tuple[int, int, str]] = []
    for priority, (kind, pattern) in enumerate(
        (
            ("email", _EMAIL_WRITING),
            ("message", _MESSAGE_WRITING),
            ("social", _SOCIAL_WRITING),
            ("prose", _PROSE_WRITING),
        )
    ):
        if match := pattern.search(cleaned):
            shape_matches.append((match.start(), priority, kind))
    if _TELL_RECIPIENT.match(cleaned):
        shape_matches.append((0, 1, "message"))
    # "Escribe un correo a mi jefe…", "patronuma bir e-posta yaz".
    locale_kind = locale_draft_kind(cleaned)
    if locale_kind is not None:
        shape_matches.append((0, -1, locale_kind))
    if shape_matches:
        return min(shape_matches)[2]
    return None


def is_writing_deliverable_request(text: str) -> bool:
    """True for drafts, translations, prose writing, and writing edits."""
    return writing_request_kind(text) is not None


def is_email_or_message_request(text: str) -> bool:
    """True only when recipient/profile context can improve a direct draft."""
    return writing_request_kind(text) in {"email", "message"}
