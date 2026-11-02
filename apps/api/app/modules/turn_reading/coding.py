"""Whether a message is about code, and what it asks of it."""

from __future__ import annotations

import re
from typing import Literal

from app.services.text_normalize import collapse_ws

CodeAsk = Literal["explain", "debug", "run"]


# Pasted code is short; a long paste is scanned only from its start.
_MAX_SCAN = 6000


# Any one of these says the text holds code. Case-sensitive: `String x =` is
# Java, "string x" is prose. None of them occurs in a maths or science problem.
_CODE_SYNTAX = re.compile(
    r"\b(?:print|printf|println)\("
    r"|\bconsole\.(?:log|error)\("
    r"|\bSystem\.out\.print"
    r"|\bstd::|\bcout ?<<|#include ?<|\bfmt\.Print"
    r"|\bdef [A-Za-z_]\w{0,40} ?\("
    r"|\bfunction(?: [A-Za-z_$][\w$]{0,40})? ?\([^()\n]{0,80}\) ?\{"
    r"|\b(?:const|var) [A-Za-z_$][\w$]{0,40} ?="
    r"|\b(?:int|float|double|char|bool|boolean|String) [A-Za-z_]\w{0,40} ?(?:=|;|\[)"
    r"|\bpublic static\b|\belif\b"
    r"|\bfor ?\([^;()\n]{0,60};"
    r"|\bfor [a-z_]\w{0,30} in (?:range ?\(|\[|[a-z_][\w.]{0,40}\()"
    r"|Traceback \(most recent call last\)"
    r"|^ {0,8}File \"[^\"\n]{1,200}\", line \d"
    r"|^ {0,8}[A-Z]\w{0,40}(?:Error|Exception)\b",
    re.MULTILINE,
)


# A fence labelled with a programming language. A bare ``` may hold an equation.
_CODE_FENCE = re.compile(
    r"```[ \t]*(?:python|py|javascript|js|jsx|typescript|ts|tsx|java|c|cpp|c\+\+|csharp|cs|"
    r"go|golang|rust|rs|ruby|rb|php|swift|kotlin|kt|dart|scala|bash|sh|shell|zsh|sql|html|css|"
    r"r)\b",
    re.IGNORECASE,
)


# Each alone is ordinary in maths or prose ("x = 4", "f(x)"); two kinds together
# are code.
_WEAK_CODE: tuple[re.Pattern[str], ...] = (
    # total = 0, total += n, nums[i] = 1
    re.compile(r"(?:^|[\s;{(])[A-Za-z_]\w{0,40}(?:\[[^\]\n]{0,20}\])? ?[-+*/%]?=(?!=) ?[^\s=]"),
    # len(nums), obj.method(x)
    re.compile(r"\b[A-Za-z_][\w.]{0,40}\([^()\n]{0,80}\)"),
    # numbers[3]
    re.compile(r"\b[A-Za-z_]\w{0,40}\[[^\]\n]{1,30}\]"),
    # [1, 2, 3]
    re.compile(r"\[ ?[\w'\"]{1,20} ?(?:, ?[\w'\"]{1,20} ?){1,30}\]"),
    re.compile(r"==|!=|&&|\|\||\+=|-=|\*=|/=|=>|\b(?!c\+\+)[a-z_]\w{0,30}\+\+"),
    # { sum += i; }  /  foo();
    re.compile(r"\)\s?;|;\s?\}|\{\s?\}|;\s*$", re.MULTILINE),
    re.compile(r"\b(?:null|undefined|nullptr|lambda)\b"),
)


# "Explain this code", "line by line", "what does this print", "value of total
# after each iteration".
_EXPLAIN_ASK = re.compile(
    r"\bexplain\b|\bline[- ]by[- ]line\b|\bwalk\s+me\s+through\b|\bstep\s+through\b"
    r"|\btrace\b|\bbreak\s+(?:it\s+|this\s+|that\s+)?down\b|\bhelp\s+me\s+understand\b"
    r"|\bwhat\s+(?:does|do|will|would|did)\s+(?:this|that|it|the|my|these|following)\b"
    r"[^?.!]{0,40}?\b(?:do|does|print|prints|output|outputs|return|returns|mean|means|"
    r"produce|produces|display|displays|log|logs|doing)\b"
    r"|\bwhat(?:'s|\s+is|\s+will\s+be|\s+would\s+be)\s+(?:the\s+)?(?:output|result)\b"
    r"|\bpredict\s+the\s+output\b|\bafter\s+each\s+(?:iteration|loop|pass|step|line)\b"
    r"|\bvalues?\s+of\s+`?[a-z_]\w*`?\s+(?:after|at|on|in|during|for)\b"
    r"|\bhow\s+does\s+(?:this|that|it|the|my)\b[^?.!]{0,40}?\bwork\b"
    r"|\bwhat\s+happens\b|\bwhat\s+is\s+(?:this|that)\s+(?:code\s+)?doing\b",
    re.IGNORECASE,
)


# "Why does this code fail", "how would you fix it", "what's wrong with this".
_DEBUG_ASK = re.compile(
    r"\bwhy\s+(?:does|do|did|is|isn'?t|doesn'?t|won'?t|can'?t|am\s+i|are)\b[^?.!]{0,60}?"
    r"\b(?:fail|fails|failing|error|errors|crash|crashes|break|breaks|broken|wrong|throw|"
    r"throws|raise|raises|work|working|compile|run|undefined|none|null|nan)\b"
    r"|\bwhy\s+(?:this|it|my|the)\b[^?.!]{0,40}?\b(?:fails?|errors?|crash(?:es)?|breaks?|"
    r"throws?|raises?)\b"
    r"|\bhow\s+(?:would|do|can|could|should|to)\s+(?:you\s+|i\s+|we\s+)?fix\b"
    r"|\bfix\s+(?:this|it|my|the)\b|\bwhat(?:'s|\s+is|\s+went)\s+wrong\b|\bdebug\b"
    r"|\b(?:find|where(?:'s|\s+is))\s+the\s+(?:bug|error|mistake)\b"
    r"|\b(?:get|getting|got|having|see|seeing)\s+(?:this|an?|the)\s+(?:\w+\s+)?(?:error|exception)\b"
    r"|\b(?:doesn'?t|does\s+not|won'?t|isn'?t|is\s+not)\s+(?:work|working|run|running|compile)\b"
    r"|\bnot\s+working\b",
    re.IGNORECASE,
)


# "Run this python code: print(1+1)", "execute it", "can you compile and run this".
_RUN_ASK = re.compile(
    r"\b(?:run|execute|exec|compile\s+and\s+run)\s+(?:this|that|it|the|my|following|these|"
    r"some|(?:a|this|the|my)\s+\w+\s+(?:code|script|program|snippet))\b"
    r"|\brun\s+(?:\w+\s+)?(?:code|script|program|snippet)\b"
    r"|\b(?:compile\s+and\s+)?(?:run|execute)\s*:",
    re.IGNORECASE,
)


_TRACEBACK = re.compile(
    r"Traceback \(most recent call last\)|^ {0,8}[A-Z]\w{0,40}(?:Error|Exception)\b",
    re.MULTILINE,
)


_FENCED = re.compile(r"```[^\n]*\n.*?(?:```|$)", re.DOTALL)


# Programming, said in words: "what is recursion", "a python function".
_PROGRAMMING_WORDS = re.compile(
    r"\b(?:code|codes|coding|coder|programming|programmer|function|functions|variable|"
    r"variables|loop|loops|array|arrays|algorithm|algorithms|compiler|debug|debugging|syntax|"
    r"regex|regexp|script|scripts|api|apis|sql|javascript|typescript|html|css|json|recursion|"
    r"recursive|traceback|stack\s+trace|leetcode|big[- ]o|data\s+structures?|linked\s+lists?|"
    r"binary\s+search|hash\s*maps?|frontend|backend|runtime|compile|github)\b"
    r"|\b(?:python|java|kotlin|swift|rust|ruby|go|golang|c\+\+|c#|php|dart|scala|react|"
    r"django|flask|node(?:\.js)?)\s+(?:code|function|program|script|class|list|lists|dict|"
    r"dictionary|loop|error|syntax|package|module|app|project|tutorial|developer|interview)\b"
    r"|\b(?:in|using|learn|learning)\s+(?:python|java|javascript|typescript|kotlin|swift|"
    r"rust|golang|c\+\+|c#|php|dart)\b",
    re.IGNORECASE,
)


def has_code_syntax(text: str) -> bool:
    """True for syntax only a program has: `print(`, `for (int i = 0;`, a traceback.

    Subject routing asks this before reading `i <= 3` or `n * 2` as algebra.
    """
    sample = (text or "")[:_MAX_SCAN]
    return bool(_CODE_SYNTAX.search(sample) or _CODE_FENCE.search(sample))


def looks_like_pasted_code(text: str) -> bool:
    """True when the message holds a code snippet, fenced or pasted on one line."""
    sample = (text or "")[:_MAX_SCAN]
    if not sample.strip():
        return False
    if "```" in sample or has_code_syntax(sample):
        return True
    kinds = sum(1 for pattern in _WEAK_CODE if pattern.search(sample))
    return kinds >= 2


def code_question_kind(text: str) -> CodeAsk | None:
    """The kind of question about pasted code: "debug", "explain", or None.

    "Explain the code of conduct" and "why does my car fail inspection" have no
    code, so they are not code questions.
    """
    sample = (text or "")[:_MAX_SCAN]
    if not looks_like_pasted_code(sample):
        return None
    # Read the ask in the prose: words inside a fenced block are the code's own.
    prose = collapse_ws(_FENCED.sub(" ", sample))
    if _DEBUG_ASK.search(prose) or _TRACEBACK.search(sample):
        return "debug"
    if _RUN_ASK.search(prose):
        return "run"
    if _EXPLAIN_ASK.search(prose):
        return "explain"
    return None


def is_programming_turn(text: str) -> bool:
    """Pasted code, or a question about programming in words."""
    if not text or not text.strip():
        return False
    return looks_like_pasted_code(text) or bool(_PROGRAMMING_WORDS.search(text[:_MAX_SCAN]))
