"""Adaptive tutoring and learning-plan routing.

Teach-me turns are conversations, not pass/fail quizzes. The assistant shows a
small roadmap, teaches one concept at a time, and adapts to correct, wrong,
confused, accidental, or off-topic follow-ups without replaying already-seen
content.

Learning-plan requests ("70-day Python plan", "4-week roadmap") are separate:
they should return a complete actionable roadmap with examples, practice,
projects, and milestones rather than entering the one-step-at-a-time tutor.
"""

from __future__ import annotations

from app.modules.turn_reading.teaching import programming_tag

LEARNING_PLAN_HINT = (
    "The user wants a complete learning roadmap now, not a thin topic list and not "
    "an interactive quiz. Make the plan actionable and easy to scan on mobile.\n"
    "- Match the requested duration and target. If the target is unrealistic as a job "
    "title or experience level, calibrate it in one sentence, then still give the "
    "strongest achievable knowledge/skill plan.\n"
    "- Start with an at-a-glance progression: phase/day ranges, focus, and the concrete "
    "ability the learner should have at the end of each phase. When it improves clarity, show "
    "the path as a compact arrow progression such as `Foundations → Core skills → Projects`. "
    "Use short headings and lists, not a schedule-style table unless the user explicitly asked for one.\n"
    "- Then make the roadmap specific. For a named N-day plan up to about 90 days, write "
    "one compact entry for every day, in order. A 70-day plan must explicitly contain "
    "`Day 1` through `Day 70` with no missing day and no broad multi-week ranges. Only group "
    "2-3 adjacent days when the user explicitly asks for grouping. Do not collapse a 70-day "
    "request into ten vague weekly bullets.\n"
    "- Keep a long daily plan within the response budget: make each day one compact line "
    "(roughly 20-30 words) in the shape `Topic → Practice/build → Done when ...`. Put one "
    "short runnable example after each major phase instead of expanding every day into a "
    "mini-essay. Reserve room for the final day, milestones, daily routine, and caveat.\n"
    "- Every phase must name what to learn, show a concrete example, say exactly what to "
    "practice/build, and make the expected outcome verifiable. For a programming roadmap, "
    "include small runnable code examples in tagged fences throughout the progression—not only prose. "
    "For a plan around 70 days, 4-6 short code blocks spread across phases is enough.\n"
    "- Include progressive exercises and projects, review/checkpoint days, milestones, and a "
    "repeatable daily study routine. End with what the learner should be able to do by the "
    "final day and what still requires longer-term real-world practice or experience; for "
    "software engineering, distinguish learned skills from actual production experience. Before "
    "sending a named daily plan, silently verify that its last requested day is present.\n"
    "- Avoid empty advice such as 'master X', 'practice Y', or 'learn best practices' without "
    "naming the subskills, exercise, deliverable, or success criterion."
)


def programming_lesson_contract(text: str) -> str:
    """Return a hard tagged-fence requirement for a named programming topic."""
    tag = programming_tag(text)
    if tag is None:
        return ""
    return (
        "HARD PROGRAMMING-LESSON ACCEPTANCE CHECK (a lesson only; an outline of a whole "
        "language has no code): Before answering, verify the response contains "
        f"the literal opening fence ```{tag}, runnable code on following lines, and a closing ```. "
        "This is mandatory even when the lesson starts with a concept. An inline snippet, pseudo-code, or "
        "untagged fence fails the requested output. Keep the example short, then end with the "
        "lesson's `Your turn` ```quiz and the one-line preview of the next lesson."
    )


# The lesson's shape, shared by a first lesson, a one-idea lesson and the next
# lesson. The ```quiz, ```array and ```steps cards are drawn by the phone
# (apps/mobile/components/rich/QuizCard.tsx, ArrayBlock.tsx, StepList.tsx).
_LESSON_SHAPE = (
    "- Title: `### Lesson N: <topic>` (the word Lesson in the reply language), N counting the "
    "lessons in this chat. Then 3-5 numbered sections, each a `### 1. <title>` heading, for "
    "example `### 1. Understand the problem`, `### 2. Solution one: Brute force`, "
    "`### 3. Apply it to backend development`. Each section teaches one idea in two or three "
    "short paragraphs with a concrete, real-world example (for code: an API, a table of users; "
    "otherwise a worked example, an event, a source).\n"
    "- Code: short language-tagged blocks such as ```python. Explain it the way a tutor does: "
    "a `# 18` comment for what a line gives, then a bullet per idea that opens with the code "
    'in `inline code` ("`ages[0]` gets the first item."), or `**How it works:**` with '
    "numbered steps for a loop, or `Let's break down the important parts:` with bullets. Only "
    "for the key function of an algorithm lesson (four or more lines), go line by line "
    "instead: the label `Line 1` on its own line, that one line alone in its own ```python "
    "block, then one sentence; never group lines (no `Line 3-5`). After code that prints, "
    "`Output:` with what it prints in a ```text block; after code that only defines a "
    "function, `Test it:` with a ```python block that calls it, then `Output:`. Never write "
    "`>>>` prompts.\n"
    "- A list or array: show its values over their indexes with an ```array fence holding JSON "
    '{"title": "Think of a Python list as a row of numbered boxes.", "values": [18, 25, 32, '
    '40], "note": "Python starts counting indexes at **0**, not 1."}, or for an algorithm '
    '{"values": [2, 7, 11, 15], "highlight": [0, 1], "caption": "2 + 7 = 9", "note": "We '
    'return indexes, not the numbers themselves."}. Title (a line above the boxes), '
    "highlight, caption (a short result under them) and note are optional; write them as "
    "plain text, not LaTeX.\n"
    "- A trace of an algorithm or process: a ```steps fence, one numbered line per step with a "
    "bold title, and plain lines under it for what happens and the state, for example:\n"
    "```steps\n1. **Read `2` at index `0`**\nWe need `9 - 2 = 7`. Not seen yet, so save "
    "`2: 0`.\nDictionary: `{2: 0}`\n```\n"
    "- Cost in math: time $O(n^2)$, extra space $O(1)$. A key idea may be one display formula "
    "in a ```math fence. Compare approaches in a markdown table.\n"
    "- The last section is `### N. Your turn`, plus what it asks when it helps (code: `— predict "
    "the output`; history: `— check your understanding`). One practice question as a ```quiz "
    'fence, ```quiz alone on its line and the JSON on the next: {"label": "Exercise 1", '
    '"question": "What will this Python code print?", "code": "<the code it needs, lines joined '
    'with \\n; empty without code>", "options": ["...", "...", "...", "..."], "answer": <0-based '
    'index of the right option>, "explanation": "<why, in one or two sentences>"}. The app draws '
    "the label, question and code in one card; never repeat the code above it. For code prefer "
    '"predict the output" or "what should it return"; make the wrong options real mistakes. Options and the explanation may use '
    "`inline code`; the explanation may end with a short fenced code block. The app lets the "
    "learner pick and check; never reveal the answer in the text.\n"
    "- End with one sentence previewing the next lesson: \"Once you get this, we'll move to A, "
    'B and C." When they asked for one idea, the preview goes deeper into that same idea '
    "(for dictionaries: looping over one, nesting). No course outline, no table of "
    'contents, no "ready to continue?" question.\n'
    "- Unless emoji are off, one fitting emoji in the opening line (🐍 for Python) and 🎉 "
    "after a correct answer, no others."
)

_LESSON_OPENING = (
    "- A lesson is the exception to the general layout rules: it opens with a short hook "
    "instead of the answer, and uses the app's ```quiz, ```array and ```steps cards below.\n"
    "- Open with one or two sentences before the title: what they will learn, why it matters, "
    'and how it fits their goal or level when the profile or memory says ("Since you already '
    "know some Python basics, we'll build on them instead of starting with what a variable "
    'is."). Without that, never claim what they already know.\n'
)

# A whole subject is a map before it is a lesson: "teach me Python" gets the
# topics in order and one question; "teach me Python dictionaries" gets the
# lesson. The model judges the size, in any subject and language.
_SUBJECT_OUTLINE = (
    'First check memory: if it says they are already learning this subject ("Learning '
    'Python: reached Lesson 3, Dictionaries ... Covered: ...") reply with only two lines '
    "and no list: where they got to, then one question offering the next topic after the "
    'last one covered or a fresh start ("Last time we got to dictionaries. Pick up with '
    'functions, or start over?"). Otherwise judge the size of what they asked for.\n'
    "- A whole subject (Python, English, cooking, calculus, guitar, chemistry): do not teach "
    "yet. Reply with one sentence on what it opens up for them, then a numbered list of 5-8 "
    "topics in the order to learn them, each a **bold name** and a few words on what it "
    "lets them do, then one short question: where they are and where to start (for "
    'example "New to it, or do you know some already? Pick a number, or tell me what you '
    'want to make with it."). Tailor the list to a level or goal they or the profile or '
    "memory already gave. No lesson title, no code, no quiz, no headings; under 150 words.\n"
    "- One idea, skill, rule or dish (Python dictionaries, the present perfect, derivatives, "
    "knife skills, an omelette): teach exactly that and nothing past it.\n"
)

TEACHING_HINT = (
    "The user wants to learn something. "
    + _SUBJECT_OUTLINE
    + "For one idea, teach Lesson 1 now, complete, in this shape:\n"
    + _LESSON_OPENING
    + "- Start where they are: skip what they already know, and tie the example to their "
    "goal.\n" + _LESSON_SHAPE
)


WALKTHROUGH_HINT = (
    "The user wants to understand one specific idea, problem or algorithm. Teach it as one "
    "complete lesson now, in this shape:\n"
    + _LESSON_OPENING
    + "- Build to the answer: understand the problem with a tiny example, the simple solution "
    "and its cost, the key insight behind the better one, a trace of it, a table comparing "
    "the approaches, then practice.\n" + _LESSON_SHAPE
)


STANDING_PREFERENCE_HINT = (
    "The user is telling you how to teach or answer them from now on; there is no question "
    "to answer yet. Do not start a lesson, answer a topic, or mention photos, images or "
    "files. Reply with one or two sentences agreeing, then a short bullet list restating "
    "what you will do in their terms (for example: one concept at a time; a practical "
    "example for each; a short exercise for them to solve before moving on), then one "
    "question asking what they want to learn first. If this chat already has a topic or "
    "lesson, offer to continue it that way instead. For a preference about answers rather "
    "than teaching (shorter replies, no emoji), one sentence is enough. Keep to it in later "
    "replies."
)
