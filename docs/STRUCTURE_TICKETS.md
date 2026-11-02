# Recall — Structure tickets

An outside review of the whole repository (2026-10-31) graded the runtime platform strong and the
product-logic layer weak. Its first three fixes landed as their own PRs, and none of them changes
behaviour:

- the finalize fallback keeps the safety passes (#2153);
- shrink-only guards for deferred-import cycles, silent excepts, empty phone catches and long phone
  functions (#2151, #2157);
- one `turn_trace` log line per turn (#2158) and a request id from the phone (#2159);
- STEM coverage held entry by entry (#2161).

This doc plans the rest: the structural findings (review §3–§8). Every number below was measured
again on `origin/main` (3cc348eff) with `git grep`; where it differs from the review, both are given.

Paths: API paths are relative to `apps/api/app/`; phone paths are relative to `apps/mobile/`.

The rule for every ticket: **a structure ticket changes no behaviour, and proves it.** It lands
alone, after the open PRs #2145–#2161, and its PR shows the proof below. A behaviour change found
on the way is its own PR with its own regression test.

## How "no behaviour change" is proven

Each ticket's PR runs these before and after and shows the diff is empty:

1. **The decision diff.** Each turn of the behaviour battery (`tests/behavior/cases.py`), the
   behaviour sweep (`tests/behavior/sweep_corpus/`) and the three STEM corpora is run, and the
   `turn_trace` record (#2158) collected for it, with timings dropped. The fields compared are the
   route reason, plan part kinds, prompt rule names, tools offered and called, the checked subject
   and op id, the money product, and the finalize passes that changed the text and their length
   deltas. ST-00 builds this harness.
2. **The STEM snapshot** (`tests/behavior/stem_snapshot.json`, #2161): no entry is answered or drawn
   that wasn't before, and none stops.
3. **The golden prompts** (`tests/modules/chat/test_prompt_golden.py`, `test_prompt_cache_layout.py`,
   `tests/architecture/test_prompt_copy.py`): byte for byte.
4. **The guards only shrink.** The import-cycle baseline (#2151,
   `tests/architecture/import_cycle_baseline.json`), silent excepts, the API function and file size
   baselines, and the phone function-size and empty-catch baselines (#2157). A ticket that moves code
   lowers a baseline in the same PR; none may raise one.

## Snapshot

| Measure | Review | Measured | Where |
|---|---|---|---|
| Modules `chat` imports | 11 | 11 (math 33 lines, attachments 25, images 18, web_search 13, memory 12, billing 10, physics 8, chemistry 8, account 8, money 4, todos 2) | `modules/chat/**` |
| Modules that import `chat` | 9 | 9 (todos 6 files, images 5, memory 3, speech 3, account 2, web_search 2, attachments, math, physics), plus `background/` ×3 and `services/subject_solving.py` | |
| Upward edges allow-listed | 11 | 11 | `tests/architecture/test_module_direction.py:28` `_UPWARD` |
| Function-level `app.` imports | 718 | 725 | indented `from app.`/`import app.` lines outside tests |
| Cycles counting deferred imports | 14, largest 109 files | 14, largest 50 modules / 123 imports (the review's 109 counted a wider graph) | #2151 baseline |
| Turn plan computed | 5 places | 5 recomputations after the pooled one (`turn_prep/reading.py:42`): `turn_prep/context.py:399`, `turn_prep/augment.py:92`, `turn_intercepts.py:319`, `finalize_parts.py:62`, `tool_loop/parts.py:23` (`turn_plan`, called again from `stream_paths.py:161`, `tool_loop/parts.py:35`, `tool_loop/selection.py:234`) | |
| `is_lightweight_chat_turn` | 13 calls / 11 files | 13 / 11; `turn_prep/mode.py:188` passes the prior reply, `model_routing/route.py:195` doesn't | |
| `is_teaching_request` | 11 call sites | 11 calls / 9 files | |
| `detect_subject` | 14 | 15 calls / 11 files | |
| `StreamContext` fields / files that change it after build | 45 / 8 | 45 / 8 (`finalize_parts`, `finalize_passes`, `finalize_text`, `stream_entry`, `stream_paths`, `stream_pipeline`, `turn_prep/context`, `turn_resources`) | `modules/chat/turn_prep/context.py` |
| Finalize passes / `FALL_BACK` | 34 / 25 | 40 / 26 by 2026-11-01 (18 text, 8 effects; ES-22's "20" is stale); 40 / 8 after ST-06's on-error default, the effects only | `modules/chat/finalize_passes.py` |
| Subject name `Literal` | 4 files | 7 declarations in 6 files: `chat/stream_status.py:33,48`, `chat/turn_prep/followups.py:35`, `images/schemas.py:50`, `services/solving.py:65`, `services/subject_scan.py:8` (with "biology"), `services/subject_solving.py:29` | |
| Chat files importing a subject directly | 22 | 22 | |
| `services/subject_solving.py` reaching into subject internals | `EQUATION_RE`, `parse_reaction`, `curve_points` | 16 subject imports, 13 of them deferred (`chemistry.request`, `.species`, `.input_text`, `.context`, `.reading`, `.block`, `.direct`; `math.tools.school.curve_points`, `math.tools.direct`; `physics.direct`, …); importers: `chat` (11 files) and `images` (2) | 494 lines |
| Two `FormulaSpec` types | yes | `modules/chemistry/catalog.py:19` and `services/law_binding/spec.py:122`, beside `chemistry/formula_record.py:13 FormulaLaw` and `law_record.py:24 ChemistryLaw` | |
| Multi-part splitters | 4 | 6 files: `services/question_parts.py`, `physics/split_parts.py`, `physics/parts.py`, `chat/prompt_constants/multi_part.py`, `chat/tool_loop/parts.py`, `chat/finalize_parts.py` | |
| `ChatScreen` | 480-line function, 47 hooks, 5 refs | lines 48–527 (480), 47 hook calls, 1 `useRef` of its own (the other refs arrive from hooks) | `features/chat/screens/ChatScreen.tsx` |
| Files calling `setMessages` | 10 | 9: `features/chat/hooks/useChat`, `useChatActions`, `useChatPaging`, `useChatRouteLoader`, `useChatSend`, `useRestoreFailedSend`, `features/chat/model/chatTurnEffects`, `features/images/hooks/useImageGeneration`, `features/speech/hooks/useLiveTalk` | |
| Flat `lib/` files | 155 (about 35 feature code) | 155 | `lib/*.ts(x)` |
| Phone functions over 100 lines | 121 | 128 | #2157 baseline |
| Fence lists outside `fenceRegistry` | 4 files | 3: `lib/markdown/document.ts:20-56` (its own `DocumentBlock` union and ids), `lib/markdown/plain.ts:416-420` (quiz, clarify), `lib/fenceDispatch.ts:97` (geometry, graph JSON kinds). `lib/copyBlock.ts` reads the registry. | |
| mypy strict | core, gateways, billing, todos, memory | the same, plus `models.schemas`, `repositories`, `services.quota`, three attachments files; not chat, math, physics or chemistry (145,460 lines) | `apps/api/pyproject.toml:130` |
| CI | one pytest job, 45 min | one `test` job, `timeout-minutes: 45`, plain `pytest --cov` with no workers; the STEM and behaviour sweeps run inside it | `.github/workflows/api-ci.yml:55,61,120` |

---

## P0 — The proof harness

### ST-00 — The decision diff: one trace per sweep turn, compared before and after

**Status: done.** Run it on main and on the change, then compare:

```
cd apps/api
uv run python -m app.tests.behavior.decisions dump /tmp/before.json   # on main
uv run python -m app.tests.behavior.decisions dump /tmp/after.json    # on the change
uv run python -m app.tests.behavior.decisions diff /tmp/before.json /tmp/after.json
```

A dump covers 5,048 turns (battery 292, sweep 3,060, chemistry 320, maths 543, physics 833) in
about two minutes; `diff` prints "no decision changed" or the changed turns grouped by field, and
exits 1. `--corpus` and `--only` narrow a dump. Two dumps of one commit are identical
(`tests/behavior/test_decisions.py`).

- **Problem:** the behaviour harness (`tests/behavior/harness.py:329` `route_case`) runs a turn
  "the way `stream_entry` runs it" without calling `stream_entry`, so no `turn_trace` is begun or
  emitted. The STEM sweep and battery check outcomes (a card, a route), not the decisions behind
  them, so a refactor can change why a turn was routed and still pass.
- **Change:**
  - `route_case` begins a trace (`begin_turn_trace`) and returns its record on `Route`.
  - A script `python -m app.tests.behavior.decisions dump <out.json>` writes one record per corpus
    turn (battery, sweep, three STEM corpora), timings dropped and keys sorted. A second command,
    `diff <before> <after>`, prints changed turns grouped by field.
  - The ticket template (this doc's top) asks every ST PR for the empty diff.
- **Seam:** the trace record becomes the contract for "what a turn decided", testable offline.
- **Tests:** a unit test that two runs of the same corpus give identical dumps. The harness runs on
  a frozen clock (`SWEEP_NOW`) and the thread SymPy executor.
- **Conflicts:** needs #2158 (trace) and #2161 (snapshot) merged.
- **Risk:** low (tests only). **Size:** S.

## P1 — Cheap, no app code

### ST-01 — CI: parallel tests and the sweeps in their own job (Actions minutes)

- **Problem:** one job runs ~34,600 tests serially with coverage (`api-ci.yml:120`), near its
  45-minute limit. In October the account ran out of Actions minutes, and every PR was blocked
  until the budget was raised. Billing is per job-minute, so serial wall time is the cost.
- **Change:**
  - Add `pytest-xdist` and run `-n auto`. The database tests share one Postgres. Locally, two runs
    on one database hung at ~94% with sessions left "idle in transaction". So mark the database
    tests `xdist_group("db")` and run with `--dist loadgroup`, or give each worker its own database
    (`DATABASE_URL` + `PYTEST_XDIST_WORKER`).
  - Move the behaviour and STEM sweeps to a second job that runs only when `modules/` or
    `tests/behavior/` change (the `changes` job already filters paths).
  - Keep the coverage gate by combining the workers' coverage (`pytest-cov` does this under xdist).
- **Proof:** the same pass/fail list on the same commit, serial and parallel. Then three CI runs in
  a row with no flake.
- **Conflicts:** none in app code; `api-ci.yml` and `pyproject.toml` only.
- **Risk:** medium (shared-state tests surface as flakes). **Size:** M.

### ST-02 — mypy strict on chat and the subjects, as a ratchet

- **Problem:** strict typing covers the low-risk packages. The four packages that decide replies
  (145,460 lines) are checked only non-strictly.
- **Change:**
  - Run `mypy --strict` over `app.modules.chat`, `math`, `physics` and `chemistry` in a test that
    counts errors per module against a checked-in baseline that may only fall (the ES file-size
    ratchet pattern).
  - Add a package to the strict `overrides` list in `pyproject.toml` as soon as it reaches 0.
- **Proof:** type-only. The decision diff is empty by construction; run it once to confirm.
- **Conflicts:** none until a package is cleaned; cleaning PRs then conflict with whatever touches
  the same files.
- **Risk:** low. **Size:** S for the ratchet, L to burn it down.
- **Status:** the ratchet runs in API CI and `scripts/check.sh` (`scripts/check_mypy_strict.py`,
  baseline `scripts/mypy_strict_baseline.json`). Measured with `--strict --follow-imports=silent`,
  the four packages had 46 errors, not the thousands their size suggested: chat 2, chemistry 4,
  math 35, money 2, physics 3. Chat reached 0 and joined the strict overrides (its tests now
  import names from the modules that define them). A `# type: ignore` counts as an error of its
  file and whole-file escapes fail outright, so 51 remain recorded: math 35, physics 8,
  chemistry 6, money 2.

## P2 — Chat stops being both the orchestrator and a library

### ST-03 — `conversation`: chats, messages and turn records below chat

**Status: done (storage half).** `modules/conversation/` owns the three repositories (private),
`history` (reads), `service` (writes), `turn_record` (a turn chat did not stream) and
`history_rag`. Chat reads and writes through those operations (`turn_deps` adapts them to
`ChatsRepo`/`MessagesRepo`), and `finish_turn` moved into chat's `post_turn.py`. Two edges
left `_UPWARD`: attachments and memory now import only conversation. `history_rag` gets
memory's switch from its job (`background/message_indexing.py`) instead of importing memory,
and `chunk_text` moved to `services/chunking.py`: both would otherwise make a
conversation ↔ memory or conversation ↔ attachments cycle. The decision diff over 5,048
corpus turns printed "no decision changed".

Still upward, for reasons this ticket does not own: account (deleting an account drops
chat's cached follow-up questions), images and speech (a non-streamed turn sets off chat's
post-turn jobs; images also reads a cut cue, speech chat's presentation), and to-dos (chat's
confirmation and locale cues). The cues are ST-04's; the post-turn jobs need a seam of their
own. Chat's lazy `__getattr__` stays while modules import those cues. The #2151 cycle
baseline did not move: its cycles are file-level ones inside the subjects and chat.

- **Problem:** six modules use chat as their message repository. `chat.history` is imported by
  `account/export.py:35`, `attachments/workflow.py:36`, `images/{generation,intent,search,turn_references}.py`,
  `memory/extract_backlog.py:17`, `speech/{live_talk,realtime}.py` and `todos/{card_retime,crud,spoken_clauses}.py`.
  `chat.turn_record` is imported by `images/generation.py:42`, `images/search.py:40` and
  `speech/live_talk.py:18`, and `chat.service` by `account/lifecycle.py:25`, `todos/proposals.py:277`
  and `background/data_retention_scheduler.py:26`. These are most of `_UPWARD`'s 11 edges, and the
  reason `chat/__init__.py:114` has a lazy `__getattr__`.
- **Change:**
  - New `modules/conversation/` owns chats and messages: the repository, `history`,
    `turn_record`, and `history_rag` (its indexing job too).
  - `chat` imports it like any other module. Every edge above points down.
  - Delete the matching `_UPWARD` entries and, once nothing needs it, the lazy `__getattr__`.
- **Seam:** a domain that stores conversations without knowing how a reply is made. The web
  client and any future surface depend on it, not on chat.
- **Proof:** the decision diff and golden prompts are unchanged (no logic moves). `_UPWARD` and the
  #2151 cycle baseline shrink, and the PR lowers them.
- **Conflicts:** #2158 (`turn_intercepts.py`, `stream_entry.py`), #2160 and #2154 (only if
  `money` imports history by then). Import lines only.
- **Risk:** low to medium (import paths; patch targets in tests change). **Size:** M.

### ST-04 — `turn_reading`: the text cues out of chat's prompt constants

**Status: done.** `modules/turn_reading/` holds the readers from 25 `prompt_constants` files: seven
moved whole (`locale_cues`, `stuck`, `profile_ask`, `question_kinds`, `writing_kind`,
`writing_locales`, `writing_purpose`) and 18 split, the readers out and the copy kept
(`routing`, `coding`, `chart`, `teaching`, `visuals`, `lesson_flow`, `school_question`, …);
the personal and advice readers became `personal.py`. Two size exceptions left the baseline
(`prompt_constants/routing.py` 561 → 31 lines, `teaching.py` 597 → 175).
It imports only services, so the direction test places it with the leaves (`_LAYER_OF`) and
a subject may ask it. `chart_names_no_curve` takes maths' reader as an argument (the
dispatcher passes it) instead of importing maths, and the chemistry fence hint moved to
`chemistry/reply_policy.py`, beside chemistry's other prompt hints. Chat no longer exports
any reader. Four upward edges left `_UPWARD`: maths, to-dos, web search and the subject
dispatcher import no chat. The decision diff over 5,048 corpus turns printed "no decision
changed". The #2151 cycle baseline did not move: its 50-module cycle lies wholly inside
maths and has no chat edge.

The leak pass's rules (`prompt_rule_text`) read the moved constants from their new homes, so
every rule string is the same (162) and so are the 4-grams within each (13,922;
`test_prompt_rule_text.py` holds both). Only the order the rules are joined in changed, which
moves 88 of the 14,393 grams that straddle two adjacent rules. Taking the readers' word lists
out of the leak grams, or not counting grams across rules, is a behaviour change for its own PR.

Left in `prompt_constants`: `shared_numbers.py` (its hint reads the same private regexes as
its reader; split it with the copy-selection work) and `reactions.clock_is_relevant` (a
prompt decision that reads `reply_meta`). Still upward: account, images, physics and speech,
for presentation and the post-turn jobs, not for reading.

- **Problem:** subjects and other modules import chat to read the user's words:
  - `todos/offer_reply.py:56` and `web_search/chat_bound.py:28` take `is_short_confirmation`;
  - `math/followup.py:111` and `speech/live_talk_tools.py:20` take `is_lightweight_chat_turn`;
  - `todos/classification.py:65` takes `has_locale_cue`;
  - `web_search/detection.py:9` imports from chat too;
  - `services/subject_solving.py:150,190,341` takes `has_code_syntax`, `chart_names_no_curve` and
    `attach_chemistry_fence_hint`.

  `chat/prompt_constants/` holds 141 functions and the classifier regexes. Nobody debugging routing
  looks in "constants".
- **Change:**
  - New `modules/turn_reading/` holds the pure readers of a message (no IO, no prompt text):
    confirmations, lightweight turns, locale cues, code syntax, the emoji pattern.
  - `prompt_constants/` keeps only prompt copy.
  - Other modules import `turn_reading`, never chat.
  - The model reader (`docs/MODEL_READER.md`) is not a pure reader: it calls a model and reads
    the subjects' menus, so it lives in `modules/model_reader/`, never here.
- **Seam:** the place ST-05's arbiter lives, and the one list of "what a message says" other
  modules may ask.
- **Proof:** the decision diff is unchanged, and the #2151 cycle baseline shrinks again (the 50-module
  cycle loses its chat edges). The test that guards that modules import chat only through its public
  files then forbids importing `turn_reading` back from chat internals.
- **Conflicts:** #2160 (`prompt_constants/routing.py` `EMOJI`), #2147 (`CODE_TALK`, school notes),
  #2150 (`whole_question`, `turn_prep/augment.py`), #2149.
- **Risk:** low to medium. **Size:** M.

## P3 — One decision per turn

### ST-05 — A frozen `TurnReading`, built once by one arbiter

- **Problem:** the turn's decisions are recomputed where they are used, sometimes with different
  inputs:
  - the plan: the 5 recomputations above;
  - "lightweight": `mode.py:188` passes the prior reply, `route.py:195` doesn't, so one turn can be
    light in one place and not another;
  - teaching: 11 calls / 9 files;
  - subject: 15 calls / 11 files.

  `core/readings.py` memoises by function name plus arguments (`_key`, line 71), so a caller with
  different arguments recomputes silently. `StreamContext` has 45 fields that 8 files change after
  build. Precedence is spread over first-match lists and the 10-step chain in `subject_solving.py`;
  money is not ordered against the subjects at all.
- **Change:**
  - A frozen dataclass `TurnReading` (plan, subject, lightweight, teaching, lesson, geo, search
    need, money product, each with a reason code) is built once in the SymPy pool by
    `turn_reading.arbiter.read_turn(text, prior)`, next to today's `turn_prep/reading.py`.
  - Every caller above reads the field instead of calling the function. The functions stay as the
    arbiter's private inputs.
  - The arbiter's reason codes are what `turn_trace` records (#2158 already has `route` reason codes).
  - `StreamContext` carries the reading. Fields it duplicates are deleted, one per PR.
- **Seam:** "what is this turn" has one owner and one precedence order, written down in the arbiter.
- **Proof:** the decision diff must be empty. Any difference is a precedence choice the old code made
  inconsistently: list it, pick one in a separate behaviour PR first, then land this.
- **Conflicts:** #2150, #2147, #2153, #2158 (all touch chat decision code). It must come after
  them.
- **Risk:** medium to high (precedence hidden in call order). **Size:** L. Land it in steps:
  plan first, then lightweight, then teaching, then subject.
- **Status, step 1 (the plan): done.**
  - `turn_reading.turn.TurnReading` (frozen: the message, the chemistry setting, the plan and
    a `plan_reason`: `one_request`, `several_requests` or `read_declined`) is built once by
    `chat.turn_prep.reading.read_turn` right after the pooled read, and kept for the turn
    (`core.readings.keep_for_turn`). The plan types moved from `chat/turn_plan.py` to
    `turn_reading/plan.py`.
  - Every place that planned the message again now asks `plan_of(text, settings)`, which
    returns the turn's plan when `text` is the turn's message: `turn_prep/context.py`,
    `turn_prep/augment.py`, `turn_intercepts.py` (the reply picture), `finalize_parts.py`,
    `emoji_placement.py`, `stream_paths.py` (the web verdict), `tool_loop/parts.py`
    (`open_parts`; its `turn_plan` wrapper is gone) and `tool_loop/selection.py`. The pooled
    read and a money follow-up's earlier lines still plan their own texts.
  - `plan_reason` is on the turn's trace line. Decision diff over the five corpora: no
    decision changed (`--added plan_reason`: one_request ×5,006, several_requests ×42). In
    those corpora every `plan_of` call read the turn's own reading.
  - **Precedence question, kept as today:** where the tool loop is not handed the user's
    own words it plans `last_user_content(messages)`, the prompt's last user line, stripped,
    which can also carry attached file text: `tool_loop/forced_search.py`,
    `tool_loop/reply_calls.py`, and `tool_loop/rounds.py` when its caller passes no
    `user_text` (and the round context's `user_text`). That is the turn's message on most
    turns; when it is not, those calls plan their own text, as before. (`selection.py`'s
    `_tools_for_user` gets the caller's text and reads the turn's reading.) The behaviour
    harness does not run the tool rounds, so passing the turn's reading down instead of the
    line is a behaviour PR of its own.
  - A plan the pool read before a later read gave up stands (`read_turn` asks the kept
    `plan_turn` reading first, as `@reading` does); only a message the pool never planned
    is `read_declined`.
- **Status, step 2 (small talk): done, and smaller than counted.**
  - Small talk already had one owner per turn: `turn_prep/mode.classify_turn_mode`, read
    against the loaded window once per turn path (new turn, regenerate; prep and persist
    classify only when no mode was passed), carried as `ctx.lightweight_turn`. It now
    names why: `_TurnMode.lightweight_reason` is `social`, `answers_offer` (a short reply
    to the last reply's question or offer), `answers_card` (the turn after a clarify card)
    or `not_light`, and `lightweight` is exactly `social`. The reason is on the trace line.
  - Of the 13 calls to `is_lightweight_chat_turn` counted above, 10 are not the turn's
    decision: they read other text (suggested follow-ups, earlier lines, live talk's spoken
    query, a fragment against its equation) or compose the reader into a reader of their
    own. Moving them onto the turn would read the wrong text.
  - **Precedence questions, kept as today:** `model_routing/route.py` (routing runs in the
    pool, before the window is read) and `answer_photo_offer.py` (the bare query) ask about
    the turn's own message without its place, so "no" after an offer is small talk there
    and an answer to the turn's mode. In the five corpora that is 33 turns
    (`answers_offer`). Choosing is a behaviour PR of its own.
  - `tests/architecture/test_turn_decisions.py` lists every caller with why; a new one fails
    until it reads `ctx.lightweight_turn` or is listed. The list only shrinks.
  - Decision diff: no decision changed (`--added lightweight_reason`: not_light ×5,021,
    answers_offer ×33, social ×20).
  - `_TurnMode` is not folded into `TurnReading` yet: the mode needs the loaded window, which
    the regenerate path reads after the message. Merging them is the last step, once teaching
    and subject have one owner each.
- **Status, step 3 (teaching): done.**
  - `TurnReading.teaching_reason` (`teach`, `no_cue`, `too_long`, `learning_plan`,
    `preference`, `procedure`) is read once with the plan; `TurnReading.teaching` is exactly
    `teach`. `turn_reading.teaching.teaching_reason` is the reader, and `is_teaching_request`
    is now `teaching_reason(text) == "teach"`. The reason is on the trace line.
  - The 9 places that read teaching from the turn's message ask
    `turn_reading.turn.teaching_of(text)`, which answers from the reading when `text` is the
    turn's message and reads any other text on its own: `turn_prep/mode.py` (advice memory),
    `prompt_format.py` (the layout hint and the style turn), `prompt_sections.py` (the advice
    hint, a part's shape hints, the lesson contract section), `message_notes.py` (the emoji
    note), `lesson_again.py` and `model_routing/route.py` (routing runs in the pool, whose
    readings are seeded from the turn's memo, so it may hold a reading, possibly an earlier
    turn's; `teaching_of` answers from a reading only when its text is the text asked, and
    the reader depends on the text alone, so the answer is the same either way). No
    precedence question: every caller passes the turn's message or another text it reads
    itself, as before.
  - The reader is called directly only by `read_turn` (the reading), `teaching_of` (another
    text), `is_teaching_request` itself, and two readers of other lines: `lesson_progress.py`
    (the chat's earlier user lines) and `turn_reading/lesson_flow.py` (the line before the
    reply). `tests/architecture/test_turn_decisions.py` holds that list of direct callers of
    `is_teaching_request` and `teaching_reason`, found through each file's imports (aliases
    and module-qualified calls included); it polices who calls the reader, not how often a
    turn reads it. Step 2's small-talk list is held the same way.
  - Decision diff: no decision changed (`--added teaching_reason`: no_cue ×5,063, teach ×9,
    preference ×1, too_long ×1).
- **Status, step 4 (subject): done.**
  - The subject order (code, a scanned caption, closed chemistry, physics, a curve physics
    cannot read, symbol givens, chemistry-shaped, maths, a chart, chemistry off, a chemistry
    question, none) is written once, in `services/which_subject.py` (now
    `services/subjects/order.py`: `read_subject_reason`, a pool reading that returns the
    subject and the step that decided it, `SubjectReading`), moved out of `subject_solving.py`
    (now `services/subjects/dispatch.py`), which keeps its 500-line limit and re-exports
    `SubjectName`. `_subject_of_text` (and so `detect_subject` and `read_subject`) returns its
    subject; the order and every branch are unchanged.
  - `TurnReading` holds the message's subject as the pool read it with the turn's attachment
    flag and chemistry setting (`subject`, `subject_reason`); `read_turn` takes it from the
    turn's memo and never reads it on the loop (`not_read` when the pool did not read it,
    `read_declined` when the pool gave up). The reason is on the trace line. Turn load
    reads the message before it knows the turn's photo; the prompt's read with the photo
    builds the reading again with the subject read under that flag, so an image turn's
    trace names the subject its photo gave.
  - Chat code asks `chat.turn_prep.reading.subject_of(text, has_image_attachment=…,
    chemistry_enabled=…)`, which answers from the reading only for the turn's message read
    with the same flags, and otherwise reads as `detect_subject` did: `turn_prep/mode.py`
    (food advice), `prompt_memory.py` (a work turn) and `prompt_format.py` (a how-to's
    layout). Routing (`model_routing/route.py`) keeps calling `detect_subject`: it runs in
    the pool, before the reading is kept, and importing the reading there grew an import
    cycle.
  - **Precedence questions, kept as today:** those three ask with `detect_subject`'s
    defaults (no image attachment, chemistry on) and routing with the chemistry setting but
    no attachment flag, while the
    turn's subject fetch (`turn_prep/augment.py`, `read_subject`) uses the turn's image flag
    and image maths extract. With chemistry switched off, or a photo attached, they can name
    a different subject than the fetch. Choosing is a behaviour PR of its own.
  - Every direct caller of `detect_subject`, `read_subject`, `_subject_of_text` and
    `read_subject_reason` is listed with why in `tests/architecture/test_turn_decisions.py`:
    the pool's reads, the subject fetches, readers of other text (a request's own text, an
    earlier line, a related question) and images' intent readers, which read a send before
    any chat turn and may not import chat.
  - Decision diff over 5,106 turns: no decision changed (`--added subject_reason`: none
    ×3,495, physics ×775, math ×538, chemistry_closed ×228, chemistry_question ×26,
    chemistry_shaped ×17, code ×16, chart ×11). The STEM snapshot, battery and sweep pass
    unchanged, and the STEM sweeps take the same time.
  - A test that begins a turn outside a task (a sync test) would leave its readings in the
    worker's context, and every later test on the worker would then run inside that turn;
    `conftest.py` clears the turn after each test.
- **Precedence chosen (behaviour PR): homework before the user's place.**
  - "A ball is dropped from a height of 20 m. How long does it take to reach the ground?" was
    answered "I don't have your location yet": the travel-time reader claimed it before
    physics, and its only guard, `web_search.weather.is_worked_problem`, wanted two stated
    measurements.
  - `is_worked_problem` asks `turn_reading.turn.is_homework`: the turn's reading
    (`TurnReading.subject`, read in the pool) gives the message physics, maths or chemistry,
    solved or not, and no request in it asks about a place on its own words. Its requests
    (`turn_reading.turn.request_units`; those that ask about a place are kept as
    `TurnReading.place_requests` with each one's subject)
    are the plan's parts when the plan splits the message, else its sentences. A request a
    proximity or weather reader claims alone (`web_search.asks_about_a_place`), and that no subject claims, keeps its reader:
    "What's the weather like today? Also solve 2x + 3 = 7" and "Will it rain tomorrow? And
    what's 15% of 80?" still search, and "How far is the nearest gas station? My car does 30
    mpg" still asks for the place. A travel-time sentence ("How long does it take to reach
    the ground?") stays the homework's. Nothing is read on the loop for it: the pool reads
    the subject of each such request (`reading._read_place_requests`).
  - Every reader of the user's place defers to `is_worked_problem` unless the line says it is
    about where the user is (`around_the_user`: "near me", "near here", "in my area", "from my
    location"; not "from here", "from me" or a bare "here", which exercises say). The readers are
    places, distances and travel times, and local weather; the location ask, the location sent
    with a search, the geo prompt hints and the places card build on them. "how hot is it
    here" is now a weather question.
  - Decision diff (new look-alikes added on both sides): 22 turns changed, all of them new
    entries. 13 are now solved by physics (`time_to_ground`, `drop_height`) where main asked
    for the location. 5 homework lines no subject solves no longer get the location ask, and
    "how hot is it here" now does.
  - Follow-up, one request at a time: 5 turns changed, all of them look-alikes. The gas-station
    line asks for the place again (it was a `gap`). The weather beside maths or physics gets its
    location hint back. "How far is the nearest pharmacy? Also, a ball is dropped…" asks for the
    place, as before #2224. Two `gap`s are older than #2224: a one-request line routed to maths
    runs no search for the weather in it, and the plan splits a problem's second question off
    as a `live` part without its givens.

### ST-06 — Finalize passes declare their order and their kind

**Status: done (declarations).** Every pass in `finalize_passes.FINALIZE_PASSES` declares
`kind` and the contracts its comments and docstrings used to hold, as `after` / `before`
(`EVERY_OTHER` for the first pass); the vocabulary and `STOPPED_REPLY_PASSES` live in
`finalize_contracts.py`. `TEXT` only returns the reply (SymPy pool work included); `EFFECT`
writes anything outside it: ctx/outcome fields, the committed text, usage counters, the status
callback, Redis or the database, or a model call. 10 passes are effects (`untrusted_media`,
`answer_photo`, `reply_picture`, `math_fences` (status), `claim_check` (model call, usage,
status), `settings_card`, `money_card`, `search_sources`, `instant_usage`, `clarify_card`), 30
are text. 12 passes declare contracts: `control_tokens` first; `drop_cut_reminder_fence` before
`close_fences`; `prepare_model_reply` and `answer_labels` before the passes that land a card;
`untrusted_media` before the server's photo, picture and chips; `search_links` after
`untrusted_media`; `reply_picture` after `answer_photo`; `formula_charts` after `math_fences`;
`claim_check` before `search_sources`; `close_fences` after the passes that read the model's
fences; `clarify_card` after `close_fences`; `prose` after all fence enrichment (the fence
readers, the server's media, the settings and money cards, the closer). `test_finalize_passes`
holds the order to them, names a pass with no kind or a contract naming no pass, pins the
effect passes, and keeps every safety pass (#2153 `closed=`) ahead of every other effect, a
rule stricter than #2153's fallback needs, on purpose: every effect works on cleaned text.
`FinalizePass` refuses a kind that is neither at construction. Nothing reorders and nothing
behaves differently: the decision diff printed "no decision changed". The reason for a contract
stays in the comment above its pass; the pinned order in
`test_the_passes_run_in_one_declared_order` is the list a new pass joins.

**Status: done (on-error default).** A pass's kind now sets what an exception in it does.
A text pass goes on: the failure is logged under the pass's name (`logger.exception`, a
timeout as a warning), the turn trace lists it (`passes_failed`), and the next pass gets the
text the failed one was given; the passes after it run. A safety text pass (`control_tokens`,
`prepare_model_reply`, `prompt_leaks`) hands on its closed strip of that text instead, and is
replayed if a later effect falls back, as #2153 had it. An effect pass falls back
(`FALL_BACK`). `FinalizePass.on_error` is written only where a pass departs from its kind:
the subject fence passes' recoveries, `chemistry_enrich`'s old step name, and the two effects
that go on (`math_fences`, `claim_check`). Of the 40 passes, 26 fell back (18 text, 8
effects); now 8 do, the effects `untrusted_media`, `answer_photo`, `reply_picture`,
`settings_card`, `money_card`, `search_sources`, `instant_usage`, `clarify_card`.
`test_finalize_pass_failures` raises inside each real pass in turn: each of the 32 that go on
hands on its input and every later pass runs; each of the 8 that fall back still stops the
passes, with only the fallback's safety passes after it. On the normal path the decision diff
printed "no decision changed".

- **Problem:** the order of the 40 passes is a tuple. The contracts between them ("before the fence
  repair below can close it", "before a subject lands its card") are comments. Text passes and
  passes with side effects (photos, chips, settings and money cards, instant usage) are mixed, and
  26 were `FALL_BACK`: one exception skipped every later pass. The review counted 30 → 34 in five
  days; the code held 40 by 2026-11-01.
- **Change:**
  - `FinalizePass` gains `after: frozenset[str]`, `before: frozenset[str]` and
    `kind: Literal["text", "effect"]`. A test checks the tuple order against the declared
    constraints and that safety passes (#2153 `closed=`) precede every effect pass.
  - The default `on_error` becomes "log and continue" for text passes. Effect passes keep `FALL_BACK`.
    This changes behaviour only on failure; it lands as its own PR with a test per pass.
  - A new pass needs one line in this doc's table of passes and a reason.
- **Proof:** on the normal path, the decision diff and golden prompts are byte-identical; the order
  test pins today's order.
- **Conflicts:** #2149, #2153, #2158 (all in `finalize_passes.py`).
- **Risk:** low (declarations), medium (the on-error default). **Size:** M.

## P4 — Subjects plug in

### ST-07 — A `SubjectAdapter` registry like `ToolAdapter`

- **Problem:** the neutral dispatcher `services/subject_solving.py` (494 lines) imports 16 subject
  internals. 22 chat files import a subject directly, and the subject name is a `Literal` in 7
  places. Each subject builds its own entry point, fence, direct reply and follow-up in its own
  shape: chemistry has `FormulaSpec`, `FormulaLaw` and `ChemistryLaw`, and a second `FormulaSpec`
  lives in `services/law_binding`. Six files split multi-part questions with different grammars.
  The promise that biology needs no edit in another subject does not hold.
- **Change:**
  - `services/subject_registry.py` defines `SubjectAdapter` (name, `detect`, `read`, `solve`,
    `fence`, `hints`, `direct_reply`, `followups`, `status_phase`). It is registered like
    `gateways/mcp` registers tools.
  - Each subject's `__init__` registers one adapter. `subject_solving.py` loops over the registry.
  - The `Literal`s become the registry's names. Chat imports the registry, never a subject.
  - Precedence between subjects moves into ST-05's arbiter, with money registered as a peer.
  - The part splitters converge on `services/question_parts.py` in a follow-up ticket.
- **Seam:** biology is a new module plus one registration line.
- **Proof:** the decision diff and STEM snapshot are unchanged. `test_module_direction` gains "chat
  imports no subject", and the #2151 cycle baseline loses the subject edges.
- **Conflicts:** #2148, #2150, #2152, #2155, #2156 (subject readers), #2154/#2160 (money).
- **Risk:** medium. **Size:** L. Land it in steps: the registry, then chat's subject imports
  behind it, then the `Literal`s.
- **Status, step 1 (the registry): done.**
  - `services/subjects/` is the subjects' package: `registry.py` (new), `order.py` (was
    `services/which_subject.py`) and `dispatch.py` (was `services/subject_solving.py`). Three
    flat `subject_*` files would have been a domain with no package
    (`tests/services/test_service_layout.py`). `subject_scan.py` stays a flat leaf: the
    subjects import it, and the package imports the subjects.
  - `registry.py` defines `SubjectAdapter`, a protocol like `ToolAdapter` with what the
    dispatcher asks of every subject: `name`, `solve` (a `SubjectRequest` to a
    `SubjectAugmentation`) and `direct_reply`. `SUBJECTS` names each subject's adapter, one
    entry each: `modules/math/subject.py`, `modules/physics/subject.py`,
    `modules/chemistry/subject.py`, each listed public by its package. They hold what the
    dispatcher's private `_augment_*` and `_direct_*` functions held, unchanged.
  - `dispatch.py` (388 → 179 lines) asks `subject_adapter(name)` and imports no subject;
    `test_module_direction.py` holds that. The package sits in layer 2.
  - `SubjectName` and `SubjectAugmentation` moved to `services/solving.py`, the leaf below
    every subject, and the registry re-exports the name: the registry imports the subjects,
    and the pure solvers reach `solving`, so the list of names sits below both.
    `test_subject_registry.py` holds one adapter per name.
  - Registration is the tuple, not a call in each subject's `__init__`: the SymPy pool's
    spawned workers import only what a job names (the direct reply runs there), so a call in
    an `__init__` registers nothing until something imports every subject; the tuple is that
    import, typed and in one place, as `services/mcp` registers the model's tools.
  - The order between subjects stays `order.py`'s (ST-05), so a subject that competes with
    another for a line also adds its step there. Dispatcher-only public files left the
    subjects' lists: `math.tools.direct`, `physics.direct` and `.prompt`, `chemistry.block`,
    `.direct` and `.reading`.
  - Decision diff over 5,232 turns: no decision changed.
- **Status, step 2a (chat's prompt copy and follow-ups): done.** Chat files that import a
  subject: 25 → 16 (53 import lines → 35).
  - The adapter gains `hints` (`services/subject_hints.py`, `SubjectHints`, moved from chat's
    `prompt_subjects`; it adds the follow-up hints and chemistry's copy the leak pass reads
    beside chat's visuals rules), `asks` (the subject's cue: `needs_symbolic_math`,
    `needs_physics`, `is_chemistry_question`) and `followups` (`problem`, `continues`,
    `previous_result`, `asks_to_see`, `shown_problem`; a subject with nothing to read there
    answers None or False).
  - Chat reads them there: `prompt_subjects`, `prompt_sections` (the three follow-up
    sections), `prompt_rule_text`, `tool_loop/rounds` (maths' closing policy after a SymPy
    round), `turn_prep/followups` (maths' five follow-up readers, in their order, are now
    `MathFollowups.problem`), `continuation_subject`, `prompt_window` and `turn_intercepts`
    (chemistry's "show me both" after a shape answer; the pool reads the adapter's bound
    method).
  - The maths-notation rule moved to `services/math_notation.py`: maths' pack and chat's
    every-turn maths-ink rule both state it.
  - What only chat's prompt and follow-ups read left the subjects' public lists:
    `math.followup` and `.reply_policy`; `physics.followup`, `PHYSICS_REPLY_POLICY` and
    `physics_prompt_hints`; `chemistry.followup`, `.reply_policy` and `.shape_followup`.
  - `SUBJECT_HINTS` keeps its order (physics, maths, chemistry, then chat's statistics and
    biology): the leak pass joins its rules in that order. `prompt_rule_text()` hashes the
    same before and after.
  - Decision diff over 5,232 turns: no decision changed.
- **Status, step 2b (chat's finalize passes): done.** Chat files that import a subject:
  16 → 14.
  - The adapter gains `fence` (`SubjectFence`): `needs_check`, `check`, `recover`,
    `unverified_note`, `draws` and `draw` (fences the subject draws in the pool: maths'
    formula charts, chemistry's molecules), and `tidy` (maths' text plots on a graph
    turn). `check` and `draw` take positional arguments: the pool runs the bound methods.
  - `finalize_subjects` asks the three fences in the passes ST-06 declared, in the same
    order and under the same gates. `ChatTurnDeps.math_fence` is maths' `fence`
    (`turn_deps`' own `MathFences` protocol is gone); tests swap it under the generic names.
  - `math.fence` and `.chart_formula`, `physics.fence`, and `chemistry.context` and
    `.fence` left the subjects' public lists.
  - Decision diff over 5,232 turns: no decision changed.
- **Status, step 2c (chat's readers, routing, warm-up and instant reply): done.** Chat files
  that import a subject: 14 → 10.
  - The adapter gains `reads` (the subject's intent: `extract_*_intent` is not None),
    `fast_lane` (Auto routing's lane from the subject's own read), `instant_reply` (maths'
    reply to a bare expression), `warm` (maths' pool warm-up solve), `solve_timeouts`
    (maths' record of a pre-solve that ran out of time) and `followups.continues_alone`
    (maths' "graph it").
  - Physics' routing lane moved from chat's `model_routing/physics.py` to
    `modules/physics/lane.py` (`physics_fast_lane`; `_physics_solves` stays a reading), and
    maths' "stays fast" check into `MathSubject.fast_lane`. `model_routing/route.py` keeps
    its order and asks each subject's lane where it asked physics' route or the maths
    check; chemistry's lane is always fast, as before.
  - `turn_prep/reading.py` (the pool's reads and its warm-up, which runs every subject's
    `warm`), `tool_loop/selection.py`, `prompt_builder.py`, `turn_prep/augment.py` and
    `turn_prep/instant.py` ask the adapters. `math.sympy_warmup` and
    `.tools.solve_timeouts` left maths' public list.
  - Decision diff over 5,232 turns: no decision changed.
- **Status, step 2d (the photo and the tool loop): done.** Chat files that import a subject:
  10 → 4, all money's (step 2e).
  - The adapter gains two capabilities a subject has or not (None): `photo` (`SubjectPhoto`,
    reading its problem off a turn's photo) and `tool` (`SubjectTool`, how the tool loop
    checks calls to the model tool it owns: `refuses`, `call_matches`, `draws_curve`,
    `asks_for_earlier_curve`). Maths has both; physics and chemistry neither.
  - Chat's `turn_prep/camera_math.py` moved to `modules/math/camera.py`
    (`read_camera_maths`); chat hands it a loader that keeps the bytes for the vision
    injection. `tool_loop/calls.py` asks maths' `tool` where it imported `tool_check`,
    `text_plot` and the trig-domain check.
  - `MathImageExtract` reaches chat through the registry, the type of what `photo` reads.
    Maths' public list keeps only what the order, the solving types and the model reader
    import, beside `subject`.
  - Decision diff over 5,232 turns: no decision changed.
- **Status, step 2e (money as a peer): done.** Chat imports no subject: 4 files → 0.
  - `modules/money/subject.py` holds `MoneyPeer` (`prepare`, `prepare_standing`, `finish`,
    `owns`), and the registry names it `MONEY` beside the subjects. It imports the service
    when a turn asks: the service loads the web search and the database models, which a
    SymPy pool worker that loads the registry must not.
  - `turn_prep/money.py`, `finalize_money.py`, `turn_prep/augment.py` and
    `turn_prep/context.py` ask `MONEY`; `MoneyTurn` reaches chat's annotations through the
    registry. Money's public list is its `subject`.
  - Money is no `SubjectName`: it has no solve, fence or direct reply, and a money turn has
    no subject solve (`turn_prep/augment.py`), the precedence it had.
  - Decision diff over 5,232 turns: no decision changed.
- **Status, step 3 (the names): done.** ST-07 is done.
  - The subject-name `Literal`s are the registry's `SubjectName`: chat's status phases
    (`stream_status`) and follow-up subject (`FollowupSubject` is gone), the picture intent's
    `subject` (`images/schemas`, its OpenAPI unchanged) and the scanner's subjects
    (`ScannerSubject` is `SubjectName` and biology, whose caption the phone sends). The model
    reader's `Subject` keeps its own order, part of its measured prompt;
    `test_subject_registry.py` holds its set, and the scanner's, to the registry's.
  - `test_module_direction.py` gains `test_chat_imports_no_subject`: no chat file imports
    maths, physics, chemistry or money, an annotation's import included.
  - The #2151 cycle baseline did not move: none of its cycles held a chat–subject edge.
  - Decision diff over 5,232 turns: no decision changed.

## P5 — Phone

### ST-08 — One owner of the thread; `ChatScreen` split by concern

- **Problem:** `ChatScreen` is a 480-line function with 47 hook calls (`ChatScreen.tsx:48-527`). Nine
  files write `setMessages`, two of them outside chat (`useImageGeneration`, `useLiveTalk`), so the
  pure reducer `features/chat/model/chatTurnState.ts` is not the thread's single owner.
- **Change:**
  - Every write becomes a reducer command (picture turn, live-talk turn, page load, restore). The
    hooks dispatch, and `setMessages` is called only by `useChat`.
  - `ChatScreen` keeps layout. Composer wiring, drawer, scanner and live-talk overlays move to
    `features/chat/components/` with their hooks.
  - Lower the #2157 baseline for `ChatScreen`.
- **Proof:** the full jest suite, `ChatScreenRenders.test.tsx`, and the reducer's tests extended
  with the new commands. No server change, so the decision diff doesn't apply. The #2157
  function-size baseline drops.
- **Conflicts:** #2159 (`features/chat/model/wsTransport.ts`, `sse.ts`, `useChat.test.tsx`).
- **Risk:** medium (stream edge cases: Stop, regenerate, reconnect). **Size:** L.

**Status: done (thread owner half).** Every other writer of the thread changes it through
`editThread(update, source, chatId?)`, a `thread_edit` step of the turn reducer
(`features/chat/model/threadEdit.ts` names the 15 sources; `useThreadEdits` builds the writer and
handles a deleted attachment). An edit naming its chat (a picture's, once it has one) waits
while another chat is on screen and lands when its chat is shown. The picture and live-talk hooks name their own source, so they
need no import from chat. `lib/__tests__/threadOwner.test.ts` holds, by type rather than spelling,
that only `useChat` and the reducer's command runner touch the setter, and that no other file
holds a list of messages in React state or a setter for one.

**Status: done (screen split).** `ChatScreen` is 354 lines (was 480): the composer's
surroundings (mic, live talk, attachment sheet, maths scanner and the heights they add) are
`useChatComposerWiring`, called where those hooks ran, so hook order is unchanged; the header
menu's sheets get their props from `chatMenuSheetProps`. Nothing that renders changed: the same
components get the same props.

### ST-09 — Feature code out of `lib/`; fences read only the registry

- **Problem:** `lib/` has 155 flat files, about 35 of them feature code (billing, notifications,
  auth, places, chat streaming). Billing, notifications, the maths scanner and the HTML preview
  have no feature folder, so the boundary test can't see them. Three files keep fence lists beside
  `lib/fenceRegistry.ts` (table above).
- **Change:**
  - Move each feature's files to `features/<name>/` (billing, notifications, scanner, preview,
    places). Leave re-export shims for one release only if a native module path needs it.
  - `FenceSpec` gains the properties those lists encode (document block kind, plain-text
    rendering, JSON kind), and the three files read them.
- **Proof:** full jest, typecheck and lint. The phone boundary test is extended to the new folders.
  `latexLeakCorpus` and the fence parity fixtures pass unchanged.
- **Conflicts:** #2159 (`lib/api/client.ts`, `lib/sentry.ts`), #2157 (baseline paths move: update
  the keys, not the sizes).
- **Risk:** low to medium (import paths). **Size:** M.
- **Status (part 1):** billing (`features/billing/`: RevenueCat, the upgrade sheet and its hook),
  notifications (`features/notifications/`: push token, registration, Android channels) and the
  scanner (`features/scanner/`: camera, crop, read-back, its API slice) are features. The boundary
  test sees them; the scanner's two composition entries are gone (it is a feature that imports
  attachments' public modules), and app start (`hooks/useBootstrapSync.ts`) and sign-out
  (`contexts/AuthContext.tsx`) are listed as the composition points they are. Measured, not
  moved: places and the HTML preview are fence rendering the shared markdown and rich renderers
  use, so they go to `lib/` domain folders, not features (part 2); `lib/scanner/subjects.ts` and
  `lib/cameraPermission.ts` stay shared (shared code and two features use them).
- **Status (part 2):** code only chat uses moved into `features/chat` (9 components, the
  settings-proposal card and its hook, the assistant-content hook, the streaming draft context,
  store and timing, client geo, the unit converter, view ownership, PDF export and print); the PDF
  page HTML into `features/attachments`. Places (`lib/places/`, with `PlacesListBlock` in
  `components/rich/`) and the HTML preview (`lib/preview/`: run document, sandbox, page file, tap,
  heights, script strip) are `lib/` domain folders: the shared markdown and rich renderers draw
  them, so they are not one feature's code. Flat `lib/` files: 155 → 123.
- **Status (part 3):** the three fence lists kept beside the registry are rows now:
  `plainReader` (the bodies copy and read-aloud draw with their own reader: worked lines, quiz,
  clarify, array), `inDocument` (a card's label in a shared document, or its copy text) and
  `bareJson` (geometry and graph draw from a ```json fence of their JSON). `plain.ts`,
  `document.ts` and `fenceDispatch.ts` read them; the renderers stay in their files. Proven
  identical on 3,328 replies (the behaviour sweep's plus every such fence the tests use, alone,
  in prose and in a list): 9,890 document, copy and speech outputs and 126 dispatch decisions.
  The other fence-id lists read rows too: the drafts (`draft`: email, message, social), the
  molecule cards' fallback label (`inDocument: "molecule"`) and the maths fence tags in
  `fenceRetag.ts` and `calculationLayout.ts` (which also lays out an unregistered ```equation
  tag, kept as the one stated extra).

## Order

1. Merge #2145–#2161.
2. ST-00, ST-01 and ST-02. These are tests and CI only, and every later ticket uses them.
3. ST-03, then ST-04. Each lowers the cycle baseline.
4. ST-06. Its declarations land before ST-05 moves decisions it depends on.
5. ST-05, in four PRs (plan, lightweight, teaching, subject).
6. ST-07.
7. ST-08 and ST-09, independent of the API tickets, any time after #2157 and #2159.

## Not doing

- **Letting a model read the question into a typed intent** (review §1) stays a measured
  experiment, not a ticket. Before any code depends on it, measure on the STEM corpora translated
  into the app's other 8 languages plus a fresh English holdout:
  - **reach:** questions answered, by subject and language;
  - **accuracy:** wrong checked answers must be 0;
  - **latency:** the added time to first token at p50 and p95;
  - **cost:** per 1,000 turns;
  - **the regex layer:** the same numbers, as the baseline.

  If the experiment wins, the regex layer is frozen: a new phrasing becomes a corpus entry, not a
  rule.
- **Storing the raw reply** is #2158's follow-up. It needs a migration and a decision about Neon
  storage, and belongs with that PR's owner.
- **Renaming `core/` or `gateways/`.** CLAUDE.md already says not to.
