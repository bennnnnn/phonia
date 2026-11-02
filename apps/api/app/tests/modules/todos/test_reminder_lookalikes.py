"""Ordinary turns that only sound like reminders keep the model's reply.

Found by the behavior sweep (``app/tests/behavior/sweep.py``): "Can you add
3 + 4 using the same method?" was answered "When should I remind you?".
"""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules import todos as todos_service
from app.modules.todos import repository as todos_repo
from app.modules.todos.read_asks import asks_to_read_reminders
from app.modules.todos.reply_check import (
    claims_a_reminder_change,
    edits_prior_reply,
    mentions_reminders,
    reply_when_nothing_saved,
)
from app.modules.todos.spoken_add import parse_spoken_add
from app.tests.fakes import fake_session

REACT_TODO_REPLY = (
    "Create a new array instead of mutating the old one:\n\n"
    "```tsx\ntype Todo = { id: number; text: string; done: false };\n"
    "const [todos, setTodos] = useState<Todo[]>([]);\n```\n\n"
    "The key part is `setTodos((prev) => [...prev, newItem])`."
)
TRIP_PLAN = (
    "Day 1 (Fri): Addis → Debre Markos, overnight there. "
    "Day 2 (Sat): Debre Markos → Gondar via Bahir Dar. Day 3: Gondar's castles."
)
TRIP_REPLY = (
    "Here's the updated road trip:\n\n- **Fri:** Addis → Debre Markos\n"
    "- **Sat, 9:00 AM:** Arrive in **Bahir Dar**, boat out to the Lake Tana monasteries\n"
    "- **Sun:** Gondar's castles"
)
SEEDED = ("call mom", "dentist appointment", "gym", "pay rent")


def _saved(title: str) -> MagicMock:
    item = MagicMock()
    item.id = uuid4()
    item.content = title
    item.topic = "Reminders"
    item.checked = False
    item.due_at = None
    item.recurrence_rule = None
    item.source = "chat"
    return item


async def _finalize(
    user_text: str, reply: str, *, prior: str | None = None, prior_user: str | None = None
) -> tuple[str, int, AsyncMock, AsyncMock]:
    items = [_saved(title) for title in SEEDED]
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(todos_repo, "list_for_user", AsyncMock(return_value=items))
        )
        create = stack.enter_context(
            patch.object(
                todos_repo,
                "create",
                AsyncMock(side_effect=lambda _session, **fields: SimpleNamespace(**fields)),
            )
        )
        update = stack.enter_context(patch.object(todos_repo, "update", AsyncMock()))
        stack.enter_context(
            patch.object(todos_repo, "get_open_dated_duplicate", AsyncMock(return_value=None))
        )
        text, applied = await todos_service.materialize_reminder_fences(
            fake_session(),
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=reply,
            user_timezone="Africa/Nairobi",
            user_text=user_text,
            prior_assistant=prior,
            prior_user=prior_user,
        )
    return text, applied, create, update


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_text", "reply", "prior"),
    [
        (
            "Can you add 3 + 4 using the same method?",
            "Same method: start at 3 and count up 4 more.\n\n**3 + 4 = 7**",
            "Start at 3 and count up 3 more. **3 + 3 = 6**",
        ),
        ("how do I add a todo item to a list in React state?", REACT_TODO_REPLY, None),
        (
            "Make a grocery list for tacos",
            "Here's a grocery list for **taco night**:\n\n- Tortillas\n- Ground beef\n- Limes",
            None,
        ),
        (
            "change of plans: it's pouring, so no grill. what should I cook?",
            "Try smash burgers in a skillet.\n\n**Quick grocery list**\n- 1 onion\n- Buns",
            "For four, figure about 1.5 lb of ground beef.",
        ),
        (
            "remind me how to convert Celsius to Fahrenheit",
            "Quick reminder — it's °F = °C × 9/5 + 32.",
            None,
        ),
        ("finish the story", "…and the lantern never went out again. **The End.**", None),
        ("delete a git branch", "Run `git branch -d my-branch`.", None),
        ("Add a stop in Bahir Dar on Saturday at 9am", TRIP_REPLY, TRIP_PLAN),
        ("mark it done", "Here's the essay with the edits marked.", "A draft essay about rain."),
    ],
)
async def test_lookalike_turn_keeps_the_reply(user_text, reply, prior):
    text, applied, create, update = await _finalize(user_text, reply, prior=prior)
    assert (text, applied) == (reply, 0)
    create.assert_not_awaited()
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_that_after_a_draft_edits_the_draft():
    draft = "```email\nSubject: Running late\n\nHi team, …\n```"
    reply = "```email\nSubject: Running late\n\nHi team, I'll be late tomorrow at 9am.\n```"
    text, applied, create, _ = await _finalize(
        "add that I'll be late tomorrow at 9am", reply, prior=draft
    )
    assert (text, applied) == (reply, 0)
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_change_claim_for_a_missing_reminder_is_not_passed_on():
    text, applied, _, update = await _finalize("uncheck buy milk", "Reopened: buy milk.")
    assert applied == 0
    assert text.startswith("Could not")
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_real_add_after_an_unrelated_reply_still_saves():
    text, applied, create, _ = await _finalize(
        "add call the bank tomorrow at 9am",
        "Set: call the bank — tomorrow, 9:00 AM.",
        prior="Here's a pasta recipe: boil the water, add salt.",
    )
    assert applied == 1
    create.assert_awaited_once()
    assert "call the bank" in text.lower()


def test_code_is_not_reminder_talk():
    assert not mentions_reminders(REACT_TODO_REPLY)
    assert not mentions_reminders("```python\ntodos = []\nreminders = {}\n```")
    assert mentions_reminders("Your reminders: call mom at 6.")


@pytest.mark.parametrize(
    ("text", "about"),
    [
        ("Quick reminder — it's 9/5 + 32.", False),
        ("Here's a grocery list for taco night.", False),
        ("I'll add milk to your grocery list.", True),
        ("Set: read — Monday, Oct 12, 8:00 AM.", True),
    ],
)
def test_mentions_reminders(text, about):
    assert mentions_reminders(text) is about


def test_change_claims_outside_code_only():
    assert claims_a_reminder_change("Reopened: buy milk.")
    assert not claims_a_reminder_change("```ts\nconst t = { done: false };\n```")
    assert not claims_a_reminder_change(None)


def test_code_field_lines_are_not_stripped_as_claims():
    reply = "```yaml\ndone: false\nset: 3\n```\n\nYour reminders are unchanged."
    assert reply_when_nothing_saved(reply, "how do I mark a task done in yaml?") == reply


@pytest.mark.parametrize(
    "user_text",
    [
        "remind me how to convert Celsius to Fahrenheit",
        "remind me what pv=nrt means",
        "remind me why the sky is blue",
        "add that I'll be late",
    ],
)
def test_questions_are_not_spoken_adds(user_text):
    assert parse_spoken_add(user_text) is None


@pytest.mark.parametrize(
    ("user_text", "reads"),
    [
        ("What's scheduled at the Hollywood Bowl this weekend?", False),
        ("what's scheduled in Paris", False),
        ("whats scheduled for tomorrow", True),
        ("what is scheduled at 3pm", True),
        ("what is scheduled in the morning", True),
        ("what reminders do I have", True),
        # Live 2026-10-25: the model answered both from the chat.
        ("ok last thing, what's on my to do list right now?", True),
        ("hmm are you sure? check my to-do list again", True),
        ("what's on my to-do list?", True),
        ("whats on my todo list", True),
        ("show me my to-dos", True),
        ("wait what's on my to-do list", True),
        ("list my to do list please", True),
        ("what's on my schedule tomorrow", True),
        ("what's on my list and what's 2 + 2?", False),
        ("what are my reminders and can you add milk", False),
        ("check my to-do list and mark gym done", False),
        ("add milk to my to-do list", False),
        ("things to do in lisbon?", False),
        ("what should I add to my to-do list before moving house?", False),
        ("what's on my list for the party? i need ideas", False),
        ("what is the best to-do list app?", False),
        ("Make a to-do plan for my day today", False),
    ],
)
def test_asks_to_read_reminders(user_text, reads):
    assert asks_to_read_reminders(user_text) is reads


def test_edits_prior_reply_needs_overlap_and_no_reminder_talk():
    assert edits_prior_reply("a stop in Bahir Dar", prior_assistant=TRIP_PLAN, reply=TRIP_REPLY)
    assert not edits_prior_reply("call mom", prior_assistant=TRIP_PLAN, reply=TRIP_REPLY)
    assert not edits_prior_reply(
        "a stop in Bahir Dar", prior_assistant=TRIP_PLAN, reply="Set: a stop — Saturday, 9:00 AM."
    )
    assert not edits_prior_reply(
        "a stop in Bahir Dar", prior_assistant="Your reminders: Bahir Dar trip.", reply=TRIP_REPLY
    )


WORKOUT_PLAN = (
    "**Weekly Workout Plan**\n\n| Day | Workout |\n|---|---|\n"
    "| **Mon** | Gym — Push |\n| **Tue** | Run — 5 km |\n| **Wed** | Gym — Pull |"
)
STUDENT_EMAIL = (
    "**Subject:** Reminder: Assignment Due Friday\n\nDear students,\n\n"
    "This is a reminder that your assignment is due this **Friday**."
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_text", "reply", "prior"),
    [
        # Edits of what the assistant just wrote never touch saved reminders.
        (
            "remove the gym on monday i have class that day",
            "| Day | Workout |\n|---|---|\n| **Mon** | Rest (class day) |",
            WORKOUT_PLAN,
        ),
        (
            "make it 5pm friday and more friendly",
            "**Subject:** Friendly reminder: assignment due Friday at 5 PM",
            STUDENT_EMAIL,
        ),
        (
            "add a line reminding him the rent for this month is already paid",
            "Dear Ato Tesfaye, … P.S. This month's rent is already paid.",
            "**Subject:** Kitchen Sink Leak\n\nDear Ato Tesfaye, the sink is leaking.",
        ),
        (
            "add a stop in Hawassa on Saturday at 10am",
            "**Saturday** — 10:00 AM Hawassa stop: Amora Gedel fish market.",
            "**Friday** — Leave Addis\n**Saturday** — Wondo Genet → Arba Minch",
        ),
        (
            "make me a study schedule for my physics exam next thursday, "
            "i'm only free after 5pm on weekdays",
            "| Day | Time | Focus |\n|---|---|---|\n| Thu | 5:30 PM | Kinematics |",
            None,
        ),
        (
            "add lunch with Dawit to my calendar on Thursday from 1pm to 2pm",
            "Ready to add — confirm below.",
            None,
        ),
    ],
)
async def test_content_edits_leave_reminders_alone(user_text, reply, prior):
    text, applied, create, update = await _finalize(user_text, reply, prior=prior)
    assert (text, applied) == (reply, 0)
    create.assert_not_awaited()
    update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_text", "title"),
    [
        ("remind me tomorrow at 6pm to call the bank", "call the bank"),
        ("remind me tmrw 8am buy injera", "buy injera"),
        ("set a reminder tomorrow 11am - meet abel at tomoca", "meet abel at tomoca"),
        (
            "add submit the quarterly report to my reminders for tomorrow 9am",
            "submit the quarterly report",
        ),
        ("can you remind me at 7pm tomorrow to water the garden", "water the garden"),
        ("ok can you remind me to water the plants tomorrow at 5pm", "water the plants"),
    ],
)
async def test_spoken_adds_save_without_a_fence(user_text, title):
    _, applied, create, _ = await _finalize(user_text, "Set: done.")
    assert applied == 1
    assert create.await_args.kwargs["content"] == title


@pytest.mark.asyncio
async def test_a_claimed_change_that_did_not_happen_is_not_passed_on():
    prior = "Set: call mom — Saturday, Oct 17, 10:00 AM."
    text, applied, _, update = await _finalize(
        "reschedule it whenever works", "Moved **call mom** to Sunday, Oct 18.", prior=prior
    )
    assert (text, applied) == ("I didn't change your reminders.", 0)
    update.assert_not_awaited()


@pytest.mark.parametrize(
    ("text", "title", "day", "clock"),
    [
        ("reminder: renew my passport, oct 20 at 10am", "renew my passport", "10-20", (10, 0)),
        ("remind me tonight at 9 to text selam", "text selam", "today", (21, 0)),
        (
            "remind me next wednesday at noon to call grandma",
            "call grandma",
            "next wednesday",
            (12, 0),
        ),
        ("remind me to pay rent on oct 31 at 9 in the morning", "pay rent", "10-31", (9, 0)),
        ("remind me to call mom tomorrow", "call mom", "tomorrow", (None, None)),
        # Filler before "remind me" is not part of the task.
        (
            "ok can you remind me to water the plants tomorrow at 5pm",
            "water the plants",
            "tomorrow",
            (17, 0),
        ),
        (
            "ok remind me to leave for the doctor tomorrow at 8:30am",
            "leave for the doctor",
            "tomorrow",
            (8, 30),
        ),
        (
            "Okay, can you remind me to call the bank tomorrow at 6pm",
            "call the bank",
            "tomorrow",
            (18, 0),
        ),
        ("oh wait, remind me to text selam tonight at 9", "text selam", "today", (21, 0)),
        (
            "Thanks! Ok can you remind me to pay rent tomorrow at 9am",
            "pay rent",
            "tomorrow",
            (9, 0),
        ),
        ("ok. sat 9am wash the car. remind me", "wash the car", "saturday", (9, 0)),
        # The same words when they are the task.
        (
            "wait for the plumber, remind me at 9am tomorrow",
            "wait for the plumber",
            "tomorrow",
            (9, 0),
        ),
        (
            "oh, wait for the plumber, remind me at 9am tomorrow",
            "wait for the plumber",
            "tomorrow",
            (9, 0),
        ),
        (
            "pls remind me to say sorry to mom tomorrow at 6pm",
            "say sorry to mom",
            "tomorrow",
            (18, 0),
        ),
    ],
)
def test_spoken_add_finds_the_day_and_clock_anywhere(text, title, day, clock):
    parsed = parse_spoken_add(text)
    assert parsed is not None
    assert (parsed.title, parsed.day, (parsed.hour, parsed.minute)) == (title, day, clock)


@pytest.mark.parametrize("text", ["remind me tomorrow at 5pm", "ok, remind me tomorrow at 5pm"])
def test_filler_alone_is_not_a_task(text):
    assert parse_spoken_add(text) is None


def test_a_clock_needs_am_pm_or_a_part_of_the_day():
    from app.modules.todos.spoken_add import user_named_a_clock

    assert user_named_a_clock("remind me tonight at 9")
    assert user_named_a_clock("at 9 in the morning")
    assert not user_named_a_clock("remind me at 9")
    parsed = parse_spoken_add("remind me at 9 to stretch")
    assert parsed is not None and (parsed.day, parsed.hour) == (None, None)


def test_next_weekday_and_dates():
    from datetime import date, datetime

    from app.modules.todos.spoken_when import date_for_day

    wednesday = datetime(2026, 10, 14, 10, 0)
    assert date_for_day("today", wednesday) == date(2026, 10, 14)
    assert date_for_day("tomorrow", wednesday) == date(2026, 10, 15)
    assert date_for_day("wednesday", wednesday) == date(2026, 10, 14)
    assert date_for_day("next wednesday", wednesday) == date(2026, 10, 21)
    assert date_for_day("next friday", wednesday) == date(2026, 10, 16)
    assert date_for_day("monday", wednesday) == date(2026, 10, 19)
    assert date_for_day("10-20", wednesday) == date(2026, 10, 20)
    assert date_for_day("10-14", wednesday) == date(2026, 10, 14)
    assert date_for_day("01-05", wednesday) == date(2027, 1, 5)
    assert date_for_day("02-30", wednesday) is None
    assert date_for_day("tonight", wednesday) is None
    assert date_for_day("fri", wednesday) is None


@pytest.mark.parametrize(
    ("text", "clock"),
    [
        ("6", (18, 0)),
        # A bare hour reads the same with minutes: the evening, like "6".
        ("6:30", (18, 30)),
        ("at 6:30.", (18, 30)),
        ("11", (23, 0)),
        ("12", (12, 0)),
        ("12:45", (12, 45)),
        ("18", (18, 0)),
        ("23:59", (23, 59)),
        ("6pm", (18, 0)),
        ("6 PM", (18, 0)),
        ("at 7:30 a.m.", (7, 30)),
        ("12am", (0, 0)),
        ("12pm!", (12, 0)),
        # Not a clock. "0" is not noon: midnight is said as midnight or 12am.
        ("0", None),
        ("0:30", None),
        ("00", None),
        ("24", None),
        ("6:75", None),
        ("6:3", None),
        ("1 8", None),
        ("13pm", None),
        ("0am", None),
        ("6pm tomorrow", None),
        ("6pm Sam", None),
        ("call mom", None),
        ("", None),
    ],
)
def test_a_reply_that_is_only_a_clock(text, clock):
    from app.modules.todos.spoken_when import parse_clock_only

    assert parse_clock_only(text) == clock


@pytest.mark.parametrize(
    ("text", "clock"),
    [
        ("make it 7", (19, 0)),
        ("make it 7 instead", (19, 0)),
        # The same bare-hour rule as a reply to "when?": minutes are kept.
        ("make it 6:30", (18, 30)),
        ("change gym to 7:30", (19, 30)),
        ("make it 18:45", (18, 45)),
        ("make it 12", (12, 0)),
        ("make it 18", (18, 0)),
        ("make it 8:00 AM", (8, 0)),
        ("make it 8pm", (20, 0)),
        ("move gym to 7pm", (19, 0)),
        ("make gym 9:15 pm daily", (21, 15)),
    ],
)
def test_a_change_reads_its_clock(text, clock):
    from app.modules.todos.spoken_change import parse_spoken_reminder_change

    change = parse_spoken_reminder_change(text)
    assert change is not None and change.keep_date
    assert (change.hour, change.minute) == clock


@pytest.mark.parametrize(
    "text",
    [
        "make it 0",
        "make it 24",
        "make it 123",
        "make it 6:3",
        "make it 7.5",
        "make it $7",
        "make it 6 amazing",
    ],
)
def test_a_change_without_a_clock_keeps_the_time(text):
    from app.modules.todos.spoken_change import parse_spoken_reminder_change

    change = parse_spoken_reminder_change(text)
    assert change is None or not change.keep_date


@pytest.mark.parametrize(
    ("text", "due", "repeat"),
    [
        ("move gym to next friday at 7:30 pm weekly", (16, 19, 30), "weekly"),
        ("move gym to saturday at 7am", (17, 7, 0), None),
        ("move gym to friday at 7", (16, 19, 0), None),
        ("move gym to friday at 6:30", (16, 18, 30), None),
        ("change call mom to tomorrow at 8:15 am", (15, 8, 15), None),
    ],
)
def test_a_move_to_a_day_reads_its_clock(text, due, repeat):
    from datetime import UTC, datetime

    from app.modules.todos.spoken_change import parse_spoken_reminder_change

    wednesday = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
    change = parse_spoken_reminder_change(text, user_timezone="UTC", now=wednesday)
    assert change is not None and change.action == "set_due"
    day, hour, minute = due
    assert change.due_at == datetime(2026, 10, day, hour, minute, tzinfo=UTC)
    assert change.repeat == repeat


def test_a_move_to_a_day_without_a_clock_asks_when():
    from app.modules.todos.spoken_change import parse_spoken_reminder_change

    for text in ("move gym to friday at 0", "change call mom to friday"):
        change = parse_spoken_reminder_change(text)
        assert change is not None and change.needs_time, text


@pytest.mark.parametrize(
    ("text", "fields"),
    [
        ("push it to next week same day", {"use_latest": True, "shift_days": 7}),
        ("actually move it to sunday same time", {"use_latest": True, "day": "sunday"}),
        ("i paid rent, check it off", {"action": "complete", "context_hint": "i paid rent"}),
        ("delete it, my roommate does it now", {"action": "delete", "use_latest": True}),
        ("done with the read reminder ✅", {"action": "complete", "title_hint": "read"}),
        ("make it 7 instead", {"keep_date": True, "hour": 19}),
    ],
)
def test_spoken_changes_in_everyday_words(text, fields):
    from app.modules.todos.spoken_change import parse_spoken_reminder_change

    parsed = parse_spoken_reminder_change(text, user_timezone="Africa/Nairobi")
    assert parsed is not None
    for name, value in fields.items():
        assert getattr(parsed, name) == value, name


@pytest.mark.asyncio
async def test_check_it_off_finds_the_reminder_the_message_names():
    _, applied, _, update = await _finalize("i paid rent, check it off", "Checked off.")
    assert applied == 1
    assert update.await_args.args[1].content == "pay rent"


@pytest.mark.parametrize(
    ("text", "title", "day", "repeat", "clock"),
    [
        ("remimd me to pay electric bill fri 6pm", "pay electric bill", "friday", None, (18, 0)),
        ("pls remind me 2 call dad at 7 tonight", "call dad", "today", None, (19, 0)),
        (
            "every monday at 8am remind me to take out the trash",
            "take out the trash",
            "monday",
            "weekly",
            (8, 0),
        ),
        (
            "remind me to call Getachew \u1290\u1308 at 10am",
            "call Getachew",
            "tomorrow",
            None,
            (10, 0),
        ),
        ("sat 9am wash the car. remind me", "wash the car", "saturday", None, (9, 0)),
        ("set a reminder for my meds at 9pm every night", "my meds", None, "daily", (21, 0)),
        (
            "perfect. can u remind me sunday 6pm to post it on insta",
            "post it on insta",
            "sunday",
            None,
            (18, 0),
        ),
        (
            "i need to finish the essay by fri 5pm, remind me",
            "finish the essay",
            "friday",
            None,
            (17, 0),
        ),
    ],
)
def test_spoken_add_reads_casual_phrasing(text, title, day, repeat, clock):
    parsed = parse_spoken_add(text)
    assert parsed is not None
    assert (parsed.title, parsed.day, parsed.repeat, (parsed.hour, parsed.minute)) == (
        title,
        day,
        repeat,
        clock,
    )


@pytest.mark.parametrize("text", ["you remind me of my sister", "this reminds me of home"])
def test_remind_me_in_conversation_saves_nothing(text):
    parsed = parse_spoken_add(text)
    assert parsed is None or parsed.hour is None


@pytest.mark.asyncio
async def test_a_nightly_reminder_with_no_day_is_saved():
    _, applied, create, _ = await _finalize(
        "set a reminder for my meds at 9pm every night", "Set: meds — nightly."
    )
    assert applied == 1
    assert create.await_args.kwargs["recurrence_rule"] == "daily"


@pytest.mark.parametrize(
    ("text", "day"),
    [
        # 09:00 in Nairobi: 7pm is still ahead, 6:30am has passed.
        ("remind me to plate the dinner at 7pm", "today"),
        ("remind me to call mom at 7pm", "today"),
        ("remind me at 6:30am to take my pills", "tomorrow"),
        ("set a reminder to start the oven at 6pm", "today"),
        ("can you remind me at 8pm to take out the trash", "today"),
        ("ok remind me to water the plants at noon", "today"),
    ],
)
def test_a_bare_clock_is_the_next_one(text, day):
    from datetime import UTC, datetime

    from app.modules.todos.spoken_add import day_for_a_bare_clock

    parsed = parse_spoken_add(text)
    assert parsed is not None and parsed.day is None
    now = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
    dated = day_for_a_bare_clock(parsed, text, user_timezone="Africa/Nairobi", now=now)
    assert (dated.title, dated.day, dated.hour) == (parsed.title, day, parsed.hour)


@pytest.mark.parametrize(
    "text",
    [
        # Not a request for a reminder.
        "you forgot to remind me to take my pills at 8pm",
        "did you remind me to plate the dinner at 7pm?",
        "why didn't you remind me to call mom at 5pm",
        # No clock, or no part of the day for a bare "at 7".
        "remind me to plate the dinner",
        "remind me to plate the dinner at 7",
        # A day or a repeat is already said.
        "remind me to plate the dinner tomorrow at 7pm",
        "remind me to take my meds at 9pm every night",
    ],
)
def test_a_bare_clock_needs_a_reminder_request_and_nothing_else(text):
    from app.modules.todos.spoken_add import day_for_a_bare_clock

    parsed = parse_spoken_add(text)
    if parsed is None:
        return
    assert day_for_a_bare_clock(parsed, text, user_timezone="Africa/Nairobi") == parsed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    ["Set: Plate the dinner — today, Oct 14, 7:00 PM.", "Sure, I'll remind you at 7 PM."],
)
async def test_a_reminder_with_a_clock_and_no_day_is_saved(reply):
    """Neither "plate" nor "dinner" is read as anything; the missing day was the gap."""
    text, applied, create, _ = await _finalize("remind me to plate the dinner at 7pm", reply)
    assert applied == 1
    assert create.await_args.kwargs["content"] == "plate the dinner"
    assert not text.startswith("I didn't")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_text", "reply"),
    [
        (
            "you forgot to remind me to take my pills at 8pm",
            "Sorry about that! Want me to set it again for tonight?",
        ),
        (
            "the recipe says to plate the dinner at 7pm sharp",
            "Plating right at 7 keeps everything hot.",
        ),
    ],
)
async def test_a_clock_in_conversation_saves_nothing(user_text, reply):
    text, applied, create, _ = await _finalize(user_text, reply)
    assert (text, applied) == (reply, 0)
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_done_after_a_question_about_reminders_completes_it():
    _, applied, _, update = await _finalize(
        "done ✅ just talked to her",
        "Marked **call mom** as done.",
        prior="Next up: **call mom** — today at 6:00 PM.",
        prior_user="whats next on my reminders",
    )
    assert applied == 1
    update.assert_awaited()


@pytest.mark.asyncio
async def test_a_todo_app_is_not_a_question_about_reminders():
    reply = "Add a button inside each item:\n\n```tsx\n<button onClick={() => remove(t.id)}>x</button>\n```"
    text, applied, create, _ = await _finalize(
        "Add a delete button to each task",
        reply,
        prior="```tsx\nexport function TodoList() {}\n```",
        prior_user="build me a todo app in react",
    )
    assert (text, applied) == (reply, 0)
    create.assert_not_awaited()


@pytest.mark.parametrize(
    ("text", "parsed"),
    [
        ("done ✅ just talked to her", ("complete", "", True)),
        ("did it", ("complete", "", True)),
        ("done with the read reminder", ("complete", "read", False)),
        ("mark the first 3 as done and show whats left", None),
    ],
)
def test_short_done_and_bulk_marks(text, parsed):
    from app.modules.todos.spoken_change import parse_spoken_reminder_change

    change = parse_spoken_reminder_change(text)
    if parsed is None:
        assert change is None
    else:
        assert change is not None
        assert (change.action, change.title_hint, change.use_latest) == parsed


@pytest.mark.parametrize(
    "user_text",
    ["always remind me to drink water", "also remind me to call mom", "just remind me to stretch"],
)
def test_a_lead_word_still_asks_for_a_reminder(user_text: str) -> None:
    # "Always remind me to drink water" got "I've set up a daily reminder" with
    # nothing saved: the leading word hid the request.
    claim = "I've set up a daily reminder for you. Would you like me to adjust the time?"
    assert reply_when_nothing_saved(claim, user_text) == "When should I remind you?"


def test_a_statement_with_always_is_not_a_request() -> None:
    reply = "Staying hydrated is easier with a bottle on your desk."
    assert reply_when_nothing_saved(reply, "I always forget to drink water") == reply


@pytest.mark.parametrize(
    "claim",
    [
        # Live: a reply said this while the reminder stayed at 7 PM.
        "Updated: Study bio — Friday, Oct 23, 8:00 PM.",
        "Changed: Study bio — Friday, Oct 23, 8:00 PM.",
        "Rescheduled: gym — Thursday, 6:00 PM.",
        "Completed: call mom — today.",
    ],
)
def test_a_change_claimed_with_any_result_word_is_not_kept(claim: str) -> None:
    reply = reply_when_nothing_saved(claim, "no not that one, the study one. 8pm")
    assert reply == "I didn't change your reminders."


def test_updated_above_an_edited_draft_is_not_a_claim() -> None:
    # Sweep l2-046: "no, friday" edited an invitation; the reply opened "Updated:".
    reply = "Updated:\n\n> Hey everyone! Party on Friday at 7pm, see you there."
    assert reply_when_nothing_saved(reply, "no, friday") == reply


def test_a_result_word_outside_reminder_talk_stays() -> None:
    reply = "Python 3.13 is the newest.\n\nUpdated: October 2024 release notes."
    assert reply_when_nothing_saved(reply, "what is the newest python?") == reply
