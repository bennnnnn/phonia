# Clarifying questions: a card the user answers with a tap

People rarely ask in full the first time ("What is the best country?"). When the best answer
depends on what the user means or wants (what "best" means to them, their goal, budget, level),
Recall starts the answer, then asks with a card of choices instead of a paragraph of questions.
The user taps, presses the card's button, and the picks go back as their next message; Recall
then answers with them in mind. It works like ChatGPT's; decided with the user on 2026-10-23
(replacing the first/after card of 2026-10-22).

## The reply that asks

Three parts, in this order:

1. **A short useful start.** The strongest few options, one bold line each with a short why
   ("🇨🇭 **Switzerland — best for quality of life**"). When anything more would be a guess
   ("plan my week"), one short sentence instead.
2. **The ask.** A bold lead-in on its own line that fits the start and the card: **But let me
   ask you one thing.** for one question, **But let me ask you a couple of things.** for two or
   three, and no "But" when no options came before it (**Let me ask you one thing.**). Then one
   short line naming what Recall needs (What do you mean by *best*?).
3. **The card**, last.

Recall asks only when the picks would change the answer in a real way. When a good general
answer exists it gives it in full and does not ask. **Never** for a plain fact, a sum or a
STEM problem, a greeting, a reminder, a picture, a draft whose purpose was given, a question
about an idea or project the chat is already about (it takes Recall's view), or a message
that is merely garbled (that keeps its one-line "did you mean…?" reply,
`prompt_constants/unclear.py`). It never asks what a plain word means ("clean food",
"healthy", "cheap") when the everyday sense, or the chat's, is enough to answer, and it reads
a typo as the word meant. Live (2026-10-25): "Don't uses want to see clean food?", in a chat
about a grocery app that scores food, got a card asking what "clean food" means. "Best" is
different: what it means is the user's own criterion. Memory, the chat so far and the
question itself come first: Recall never asks what it already knows.

## The card

- One to three questions, each a bold question and 2 to 8 choices, one pick per question.
  Choices usually start with an emoji ("💰 Making money").
- The first choice of each question is picked when the card appears (the model puts the
  likeliest first), so the button works at once.
- One full-width button named for what it does ("Find my best country"); "Submit" when the
  card names none. No Other or Skip: typing a normal message instead works, and the server
  needs no word list for it (any message after a card that is not the picks gets the same
  hint: answer the request now with the best general reading, or answer the new question).
- After the button the card stays, read-only, with the picks ticked and no button. A card
  answered by typing shows nothing ticked.
- A reply that asks gets no follow-up questions under it (`related_questions.follow_up_topic`,
  and the phone's `asksWithCard`): they would compete with the card.
- The turn after a card never asks again, whatever the user sent: no card and no questions;
  anything still unknown gets a sensible default said in one short line. A card the model
  writes anyway is removed at finalize, with the ask that led into it (`after_card`).

## What is sent

The picks are the user's next message, a normal bubble, one paragraph: the card's `request`,
then `Label: value.` for each question, then its `closing`:

```
Recommend the best country for me. Main priority: Making money. Geographic preference: Anywhere. Compare the strongest options with practical pros and cons.
```

The phone writes it from the card. The server knows it answers the card because the previous
assistant reply holds the card and every question's label is in the message with a pick after
it (one `Label: pick` line per question, what older phones sent, reads the same). Its prompt
then says: open with a direct recommendation tied to the picks (and to memory when it fits),
then the complete answer the message asks for; no picks listed back, no new card. That turn
gets no asking rule (`prompt_format._may_ask_with_card`), and the card's own "Compare the
strongest options…" closing does not make it an X-vs-Y turn that leads with a table.

## The `clarify` fence

Written by the model, checked and normalised by the server before it is saved (Pydantic): a
card that breaks the rules is removed, and a reply left with no question gets the questions as
plain prose. JSON, one object; this is what the server keeps:

```json
{
  "questions": [
    {"id": "priority", "label": "Main priority", "question": "What matters most to you?",
     "options": ["💰 Making money", "🌿 Quality of life", "🛡️ Safety"],
     "values": ["Making money", "Quality of life", "Safety"]},
    {"id": "region", "label": "Geographic preference", "question": "Which region are you considering?",
     "options": ["🌍 Anywhere", "🇪🇺 Europe", "🌎 The Americas"],
     "values": ["Anywhere", "Europe", "The Americas"]}
  ],
  "request": "Recommend the best country for me.",
  "closing": "Compare the strongest options with practical pros and cons.",
  "submit": "Find my best country"
}
```

- `options` are drawn as written; `values` are what the message says. The model writes only
  `options`; the server adds `values` by taking the leading emoji off each one.
- `label` is the short name used in the sent message; `question` is what the card shows.
- `request`, `closing` and `submit` are optional; one too long to show is dropped, not the card.
- More than three questions keeps the first three, more than eight choices the first eight;
  repeats (the same value, any case) are dropped. A question left with fewer than two choices
  makes the card invalid.
- Text is in the user's language.
- Cards saved before 2026-10-23 (`when`, `multi`, up to four choices, no `values`) still read:
  `when` and `multi` are ignored, each value is its option, and the button says "Submit".
- In the chat history the model reads a card as one compact line ("Asked: What matters most to
  you? [Making money / Quality of life / Safety]; …"), so the next message makes sense.

## Where it lives

| Part | Path |
|------|------|
| When to ask, the reply's shape, the card's shape, the next turn's hints (prompt) | `apps/api/app/modules/chat/prompt_constants/clarify.py` |
| Check and normalise the fence (finalize pass `clarify_card`) | `apps/api/app/modules/chat/clarify_card.py`, `finalize_text.settle_clarify` |
| The card in history, and the turn after a card | `apps/api/app/modules/chat/clarify_turn.py` (read by `prompt_window.py`, `prompt_sections.py`, `turn_prep/mode.py`) |
| The card | `apps/mobile/components/rich/ClarifyCard.tsx` (button: `ui/controls/Button` `contrast`) |
| The first picks, the sent message, and a sent message read back onto its card | `apps/mobile/lib/clarify/clarifyCard.ts` |
| What the card reads from the chat: the send path, busy, newest reply, the answer | `apps/mobile/components/rich/clarifyContext.tsx`, provided by `features/chat/components/ChatReplyProviders.tsx` and `MessageBubble.tsx` |

On the phone a card can be answered only on the newest reply while nothing streams (while a
reply streams or saves, the button shows but does nothing). A send the chat refuses before it
goes out (offline) leaves the card live, so the button works again. Once answered it stays read-only
with the picks ticked, read back from the user message after it, so no store is needed across
list recycling or a restart. Copy, Read aloud and a shared or PDF chat give each question with
its choices, one per line; a card written as plain text reads as that text, as the card shows it.
