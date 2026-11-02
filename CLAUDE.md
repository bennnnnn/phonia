# CLAUDE.md — Recall (Personal AI Chat)

A personal mobile AI chat app that remembers the user's preferences, projects, and context across chats. Mobile = Expo React Native. Backend = FastAPI. Models routed via LiteLLM. This file is the **engineering map** (rules, layers, catalog, seams). Product status lives in [FEATURES.md](./FEATURES.md). Architecture migration: [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md). Math: [docs/math.md](./docs/math.md) (tutoring roadmap: [docs/MATH_TUTORING_TICKETS.md](./docs/MATH_TUTORING_TICKETS.md)). Physics: [docs/physics.md](./docs/physics.md) (interactive scenes roadmap: [docs/INTERACTIVE_SCENES_TICKETS.md](./docs/INTERACTIVE_SCENES_TICKETS.md)). Chemistry: [docs/chemistry.md](./docs/chemistry.md). Making math/physics/chemistry true peer subjects at the type level: [docs/SUBJECT_SEPARATION_TICKETS.md](./docs/SUBJECT_SEPARATION_TICKETS.md) (complete: `PhysicsIntent` is a peer of `MathIntent`). Engineering standards (layers, subject isolation, size limits, CI gates): [docs/ENGINEERING_STANDARDS.md](./docs/ENGINEERING_STANDARDS.md). Structure work from the 2026-10-31 review (chat's modules below it, one decision per turn, a subject registry, the phone's thread owner), each proven to change no behaviour: [docs/STRUCTURE_TICKETS.md](./docs/STRUCTURE_TICKETS.md). Reading a question with a model into a typed, server-checked request (a measured experiment, finding 1 of the 2026-10-31 structure review): [docs/MODEL_READER.md](./docs/MODEL_READER.md). Launch: [docs/PRODUCTION.md](./docs/PRODUCTION.md), [docs/SCALING.md](./docs/SCALING.md), [docs/QA_MATRIX.md](./docs/QA_MATRIX.md), [docs/ROLLBACK.md](./docs/ROLLBACK.md). Security: [SECURITY.md](./SECURITY.md).

**This is not a week-one MVP.** Approximate size (app code, excluding generated/`node_modules`):

| Tree | Lines | Notes |
|------|-------|-------|
| `apps/api/app` | ~168k Python | ~290k with tests |
| `apps/mobile` | ~100k TS/TSX | ~157k with tests; vendor inlined separately |

Do not review or extend the app from the historical MVP screen list. Use **Domain catalog** and **Seams**.

## Golden Rules (read first)

1. **Never put provider API keys in the mobile app.** Keys live only in the backend `.env`. The app talks only to our API, with one exception: live talk sends its WebRTC offer to OpenAI's realtime endpoint with a short-lived client secret the backend mints (`apps/mobile/features/speech/model/realtimeSdp.ts`); the permanent key never leaves the server.
2. **Use product model aliases, never provider names**, in app/business code: `free-chat`, `smart-chat`, `title-model`, `memory-model`. Alias → provider mapping lives in `models/model_catalog.py` (runtime availability: `services/model_health.is_available`) (LiteLLM calls go through `gateways/litellm_gateway.py`).
3. **Never send full chat history to the model.** Build context from injected memory + the recent window (default hard cap 20 messages; token budget also trims) only.
4. **Topic generation, memory extraction, and other post-turn work are best-effort background jobs.** They must never raise into the chat request path or block streaming. Enqueue from `modules/chat/post_turn.py` via `core/jobs/`.
5. **No arbitrary code execution — one sandboxed exception.** Code in messages is rendered/highlighted only, with a single exception: **HTML/CSS/JS may be previewed in a sandboxed WebView** (and charts/diagrams rendered from model output). Never execute Python, shell, or any other language, and never run code anywhere except inside the isolated preview WebView (no app token is ever exposed to it). The preview WebView requires a dev build — it does not work in Expo Go.
6. **All LLM structured outputs are validated with Pydantic** before they touch the DB.
7. **Symbolic math runs server-side only (SymPy), and never on the event loop.** Solves and the maths, physics and chemistry readers run in the SymPy process pool (`core/sympy_executor.py`); a turn reads its message there once and keeps the answers (`core/readings.py`; the test suite fails on SymPy or a reading run on the loop). Math lives in `modules/math/`. Physics is a peer subject in `modules/physics/`, not a corner of math. The mobile app renders verified results and structured `geometry` / `graph` / `simulation` fences — it never solves equations on-device, and a `simulation` scene is a *sampled path* it walks, never motion it re-derives. Pipeline map: [docs/math.md](./docs/math.md).

## Service Overview

**What it does:** authenticated users chat with LLMs; the app persists chats, auto-generates titles, injects structured personal memory, and layers productivity (to-dos and reminders) plus rich rendering. Recall does not connect to calendars or email inboxes.

**Domain concepts:**

- **user** — Google or Apple sign-in; editable profile + preferences; `plan` (`free` | `plus` | `pro`) is driven by RevenueCat. What a plan includes and its numbers are decided in one place, `modules/billing/entitlements.py` (`can_use`, `allowance`); every number is a setting in `core/settings/plans.py`.
- **chat** — a conversation; has an auto-generated title.
- **message** — one turn (`user` | `assistant` | `system`).
- **memory** — one retrievable fact per row (`status` `active` | `superseded` | `muted`), cap 150 active. `topic` files each fact into a Claude-style page (`modules/memory/topics.py`: You = profile, preferences; Topics = interests, tech-stack, schedule, recent-work, goals, side-projects, notes; Areas = `area:<slug>` with a title row in `memory_areas`); `type` (`profile` | `preference` | `project` | `fact` | `focus`) follows the topic and sets prompt priority. Sensitive topics are not auto-stored unless the user said “remember” or opted in. Extraction is post-turn; a one-time `memory_history_scan` reads recent chats, only adds missing facts, and skips lines older than the user's last hand edit (`users.memory_edited_at`). What a chat line tells memory (remember, forget, mute, reset, correct) is `modules/memory/commands.py`; which facts a turn reads (query, profile, everything, or the work scope for programming turns) and the notes for memory off or unavailable are `modules/chat/prompt_memory.py`. Memory off means no personal recall, chat-history RAG included.
- **model alias** — product-level model name mapped to a provider by the gateway.
- **quota** — per-user daily token budget (free tier 100k/day).
- **todo** — a lightweight task the user tracks; optionally linked to a chat.
- **suggestion** — retired: the old proactive prompts are no longer generated or served. Stored rows are kept only for the data export and account deletion until a later release drops the table.
- **search** — full-text lookup across the user's chats and messages.
- **attachment** — an uploaded image/file (R2 in production) with extracted text chunked into `attachment_chunks` for retrieval.
- **push token** — a registered Expo device token for reminder/nudge notifications.

**Rich rendering:** markdown, tables, math, callouts, code highlighting, sandboxed HTML/CSS/JS preview, charts (Vega), Mermaid, geometry SVG, native Skia math graphs (SVG fallback), physics scenes, free-body diagrams, circuit schematics, ray diagrams and waves (`simulation`, schema v2: [docs/physics.md](./docs/physics.md#pictures)), chemistry (SMILES), lesson cards (`quiz` with Check answer, `array` index boxes, `steps` trace), money `calculator` cards (sliders the phone redraws from the server's formula trees, `docs/money.md`), clarifying questions (`clarify`: tap choices, the first one picked; the card's button sends them as the user's message). Fence identity lives in `apps/mobile/lib/fenceRegistry.ts`.

**Owned tool loop, on by default:** module-owned adapters (`web_search`, `sympy`, `generate_image`, `search_image`) register through `gateways/mcp/` and run via `modules/chat/tool_loop/`. `mcp_tool_loop_enabled` defaults to `true` (it is the loop's kill switch: off, nothing searches). Heuristic SymPy still runs before the stream; web search is the loop's. A turn the loop leaves alone offers `web_search` to the reply's own model call (`tool_loop/reply_calls.py`, `reply_search_tool_enabled`): the model answers, or searches and answers in a second call. See `docs/math.md` and `FEATURES.md` §16.

**Not in scope (v1):** execution of non-web code or execution outside the sandboxed preview WebView; multi-user/teams; full duplex / interruptible voice; arbitrary user MCP servers. Attachment RAG, chat-history RAG, and live talk (Pro, monthly minutes) are shipped. `apps/web` is slice 1 only (login + chat SSE); remaining web surfaces are deferred.

## Architecture

Monorepo:

```
recall/
  apps/
    mobile/        # Expo React Native — app/ routes + features/ product ownership
    api/           # FastAPI — modules/ product ownership + shared infrastructure
    web/           # Vite slice 1: login + chat SSE (not react-native-web)
  docs/            # math.md, chemistry.md, PRODUCTION.md, QA_MATRIX.md, ROLLBACK.md
  CLAUDE.md
  FEATURES.md
  SECURITY.md
```

Backend ownership (`apps/api/app/`) is a modular monolith: every product domain is a module
under `modules/`. Only the legacy admin, health, legal and models routers stay in `routers/`:

```
app/
  main.py              # app factory, middleware, router registration
  worker_main.py       # Fly worker: jobs + schedulers (no public API)
  worker_health.py     # worker liveness probe
  modules/             # product domains; one owner each
  core/                # application infrastructure; must not import modules
  gateways/            # external systems; must not import modules
    mcp/               # adapter protocol + registry (not the adapters)
  repositories/        # shared persistence still used while domains migrate
  routers/             # legacy HTTP until that domain is a module
  services/            # leaves several owners share (quota, time, STEM text); not one module's code
    law_binding/ mcp/ quota/ subjects/
  exceptions.py        # shared domain exceptions
  models/              # orm/ (SQLAlchemy) + schemas/ (Pydantic: HTTP, math/, tools)
  background/          # job handlers + periodic schedulers
    handlers.py        # job-type → handler register (imported at startup)
  content/             # static legal copy
  tests/               # ~39k
```

A module may import another module only through that module's public files
(`api`, `schemas`, `service`, `crud`, or the package surface). Repositories
and extractors stay inside the owning module. Do not rename `core/` or
`gateways/` to `platform/`.

### Transaction ownership

- Services own multi-step database units. They call repository writes with
  `commit=False`, commit once after every write succeeds, and roll back the
  service-owned transaction on failure.
- Repository write functions keep `commit=True` only as a compatibility default
  for standalone single-operation callers. With `commit=False`, they may flush
  to materialize IDs or constraints but must not commit or roll back.
- Cache invalidation, job enqueue, and other external side effects happen after
  the owning service commits. Slow provider calls should run outside an open DB
  transaction; a workflow may therefore use separate short transaction phases
  (for example, memory text then embedding writes).
- A caller that explicitly passes `commit=False` to a composable service owns
  both the eventual commit and rollback. Do not add a generic unit-of-work layer
  unless repeated concrete workflows require more than these boundaries.

**Streaming:** WebSocket (`modules/chat/ws_api.py`) preferred (stop-generation); SSE fallback (`modules/chat/stream_api.py`). Both share `modules/chat/stream_events.py` for `done` / `error` payloads. A cancel message aborts the active LLM task.

**Clients & the API contract:** the backend is a client-agnostic HTTP/WebSocket API with JWT auth. Mobile uses Bearer + `expo-secure-store`. `apps/web` uses an in-memory access token plus an httpOnly refresh cookie. Keep `apps/mobile/lib/api.ts` the **barrel** over `lib/api/*.ts` (single network boundary for mobile). Rich-block rendering should stay swappable; only platform bits differ per client.

## Domain catalog

What exists in code today. Product caveats: FEATURES.md.

| Domain | API | Mobile |
|--------|-----|--------|
| Auth / account | `modules/account/` (HTTP `/auth`: sign-in, sessions, profile, settings proposals, export, delete); per-request token check in `core/access_tokens.py` | `features/auth/` (login, onboarding), `features/account/` (settings screens); `app/login.tsx`, `onboarding.tsx`, `app/settings/*` routes only |
| Chat history | `modules/chat/` (HTTP `/chats`) | drawer history; `features/chat/api.ts` |
| Chat stream | `modules/chat/` (`ws_api.py` WebSocket, `stream_api.py` SSE; `stream_entry.py`, `turn_deps.py`, `turn_prep/`, `stream_pipeline.py`, `stream_paths.py`, `finalize_passes.py`, `turn_settle.py`, `post_turn.py`; a picture, photo lookup or voice turn saves through conversation's `turn_record` and chat's `finish_turn`) | `features/chat/` (`screens/ChatScreen.tsx`, `hooks/useChat*.ts`, `components/`, `model/` stream, socket and cache); `app/index.tsx` route only |
| Memory | `modules/memory/` (HTTP `/memories`, `/memories/documents`, `/memories/instruct`) | `features/memory/`; `app/memory/` routes only (list + `[key]` page) |
| Models / quota | `routers/models.py`, `models/model_catalog.py`, `services/quota/`; the user's pool in `modules/billing/plan.py`, Auto's pick and the reasoning pass in `modules/chat/model_routing/` | `features/account/screens/ModelsSettingsScreen.tsx` (settings only, no composer picker; with Auto off it names and sets the model messages use) |
| Search | `modules/search/` (HTTP `/search`) | `features/search/`; drawer search |
| Clarifying questions | `modules/chat/clarify_card.py` (the `clarify` card checked at finalize), `clarify_turn.py` (history line, the turn after a card), `prompt_constants/clarify.py`; [docs/clarify.md](./docs/clarify.md) | `components/rich/ClarifyCard.tsx` (the card), `lib/clarify/clarifyCard.ts` (the sent message, read back onto its card) |
| Follow-up questions | `modules/chat/related_prompts.py` (after `done`; rules in `related_questions.py`; the old `/suggestions` routes and job are removed; `modules/suggestions/` keeps only the table reads for export) | `features/suggestions/` (`RelatedPromptLines`) |
| Todos / reminders | `modules/todos/` (HTTP `/todos`; chat changes wait for a tap: `write_log.py` + `proposals.py`, `POST /todos/proposals/{id}/confirm`; the reply above an untapped card claims nothing, `reply_claims.py`; chat changes them only from an English message, another language gets an Open To-do button, `chat_language.py`) | `features/todos/` (`ReminderProposalCard`, `TodoLinkButton`); `app/todos.tsx` route only |
| Home | (none: the phone builds it) | `features/home/`; a translated greeting with the first name + one overdue reminder, from the to-dos it already holds |
| Attachments + RAG | `modules/attachments/` (HTTP `/attachments`) | `features/attachments/`; `app/gallery.tsx` route only |
| Conversation (chats and messages) | `modules/conversation/` (the rows chat writes and other modules read: `history.py` reads, `service.py` writes, `turn_record.py` a turn chat did not stream; its repositories stay private) | (drawer and thread, through chat's `/chats`) |
| Turn reading (what a message says) | `modules/turn_reading/` (the pure readers: a confirmation, a light turn, a locale cue, code, a chart, a lesson step, a school exercise, a writing request; no IO, no prompt text; `turn.TurnReading`, the turn's one reading, and `plan`, its requests). Every module, chat and the subjects included, asks these and never chat; `modules/chat/prompt_constants/` keeps only the copy they choose between | (none) |
| Chat-history RAG | `modules/conversation/history_rag.py` (snippets in `modules/conversation/chunks_repository.py`), `background/message_indexing.py` | (prompt inject only; no extra UI) |
| Image gen (every plan, daily cap) | `modules/images/` (HTTP `/images/generate`; `/images/intent` answers what a composer send is, read by `intent.py`, the chat turn's own reader) | `features/images/`; composer send only, when `/images/intent` answers a picture (`features/images/model/imageIntentPrefilter.ts` only decides whether to ask) |
| Reference-photo lookup (free+Pro) | `gateways/image_search_gateway.py` (Tavily), `modules/images/` (`search`, `lookup_intent`, `search_tool`, `answer_photo`: a photo above an answer about something worth seeing) | `features/images/`; a lookup is a chat send, read before image-gen intent by `modules/images/intent.py` |
| Speech STT/TTS + live talk | `modules/speech/` (HTTP `/speech`) | `features/speech/`; composer mic and live talk |
| Web search | `modules/web_search/`, `gateways/web_search_*.py` | source chips under replies |
| Math (SymPy) | `modules/math/` (`match/`, `tools/`, `solve/`, `fence.py`; HTTP `/math/scan/read`; the SymPy process pool is `core/sympy_executor.py`). Lessons, check my work (`work_check`), word problems (`word_problem`) | `MathText` / `MathView` / `geometry` / `graph`; scanner `features/scanner/` (camera, crop, read-back review) |
| Physics | `modules/physics/` (`catalog/`, `extractors/`, `solvers/`, `extract.py`, `solver.py`, `block.py`, `direct.py`; HTTP `/physics/scan/read`); its law-catalog engine is shared in `services/law_binding/` | same fences; `simulation` scenes (`components/rich/SimulationBlock.tsx`) and diagrams (`components/rich/diagrams/`: circuit, rays, wave); scanner read-back |
| Chemistry (typed solvers / RDKit / PubChem) | `modules/chemistry/` (`catalog.py` is the one operation list; `extractors/` and `solvers/` by topic, run in `registry.py` order; `binding.py` + `laws.py` on the shared `services/law_binding/`; HTTP `/chemistry/scan/read`), `modules/chemistry/schemas/`, `gateways/pubchem_gateway.py` | `lib/chemistry/` (shared with markdown); smiles-drawer 2D + native-first Skia `molecule3d` |
| Push / email out | `modules/notifications/`, `background/*scheduler*` | `features/notifications/` (push token, registration, Android channels); notification settings |
| Billing | `modules/billing/` (`entitlements.py` plan policy, `revenuecat.py` webhook, `subscription.py` REST sync; HTTP `/webhooks/revenuecat`, `/billing/plans`), `gateways/revenuecat_gateway.py` | `features/billing/` (RevenueCat `model/purchases.ts`, `components/UpgradeSheet.tsx`), `lib/plan.ts` |
| Product analytics | `modules/analytics/` (HTTP `/analytics`; events persist through the shared `repositories/product_events.py`, which account export also reads) | `lib/api/analytics.ts` (metadata-only events; never prompts) |
| Money (loans, card payoff, savings) | `modules/money/` (`catalog.py` products as data, `read.py`, `solve.py`, `rates.py` today's average from one checked web search, `note.py`, `fence.py` the `calculator` card; chat side `modules/chat/turn_prep/money.py`, `modules/chat/finalize_money.py`); formulas as trees in `services/law_binding/expression.py`. See `docs/money.md` | `components/rich/` (calculator card with sliders) |
| Link preview | `modules/link_preview/` (HTTP `/link-preview`; SSRF-safe fetch in `gateways/safe_fetch.py`) | `components/LinkPreviewCard.tsx`, `lib/linkPreview.ts` |
| Admin / legal / health | `routers/admin.py`, `legal.py`, `health.py` | `features/account/screens/HelpScreen.tsx`, `AboutScreen.tsx`, `DataControlsScreen.tsx` |
| Rich fences | prompt constants + post-stream fence rewrite | `lib/fenceRegistry.ts`, `components/rich/` |
| i18n | locale on user + prompt | `lib/i18n/*.json` (9 locales; tests hold key parity, placeholders and translation: a value equals English only if `lib/__tests__/i18nTranslated.test.ts` allows it) |

**HTTP surfaces registered in** `main.py`: the module-owned Math, Physics, Chemistry, Memory, To-do, Search, Chat history, Attachments, Images, Speech, Account (`/auth`), Billing webhooks, Notifications push-token (`/users`), Analytics, and Link preview APIs plus the legacy health, legal, admin, and models routers. Chat history (`/chats`) and the chat stream (`/ws/chat`, SSE) are both `modules/chat/`.

**Domain packages:** every product domain lives under `modules/`. `services/` holds only what several owners share (quota, time context, the STEM text leaves); a root file one owner uses moves into that owner (`apps/api/app/tests/architecture/test_services_root.py`). The model catalog is `models/model_catalog.py`. New chat-loop code belongs in `modules/chat/`; new external IO belongs in a gateway, not an API surface.

## Seams (plug in / plug out)

Add or delete at these boundaries. If a change needs eight unrelated files, the seam is missing or being bypassed — say so, don’t silently sprawl.

| Concern | Seam | How to extend | How to remove |
|---------|------|----------------|---------------|
| HTTP/WS endpoint | module `api.py` or legacy `routers/` + `main.py` | Thin API → module/service | Drop registration + tests |
| External API | `gateways/` | One gateway module; mock in tests | Delete gateway; keep service behind a flag if needed |
| MCP / model tools | module `tool.py` or legacy `services/mcp/`; `gateways/mcp/` registry | `register(Adapter)` implementing `ToolAdapter`; `invoke(args, ctx: ToolContext)` gets the turn as an argument | Unregister; `mcp_tool_loop_enabled` defaults **on** |
| Subject (maths, physics, chemistry) | module `subject.py` adapter; `services/subjects/registry.py` (`SUBJECTS`), asked by `services/subjects/dispatch.py`; which subject a line is: `services/subjects/order.py` | A module whose `subject.py` implements `SubjectAdapter` (`solve`, `direct_reply`, `hints`, `asks`, `reads`, `followups`, `fence`, `fast_lane`, `instant_reply`, `warm`, `solve_timeouts`, and `photo` and `tool` when it has them); money is the registry's peer `MONEY` (`modules/money/subject.py`), its name in `SubjectName` (`services/solving.py`), one entry in `SUBJECTS`, and its step in the subject order | Drop the entry, the name and the step; delete the module |
| Background job | module `jobs.py` or legacy `background/handlers.py`; `core/jobs/` queue | Register handler; enqueue off the stream path | Unregister + stop enqueue |
| Feature flag / setting | `core/settings/<section>.py` (joined into `Settings` in `core/config.py`) | One field in its section; gate service entry | Default false; then delete path |
| Model | `models/model_catalog.py`; which alias does which job (Auto's lanes, photos, tool selection) in `models/routing_lanes.py` | Catalog entry + OpenRouter slug + capability flags (`supports_vision`, `supports_tools`, `json_mode`, `context_tokens`; unconfirmed = false). Route by capability, never by name | Remove alias; don’t leave provider names in app code |
| Mobile network | feature `api.ts` or legacy `lib/api/<domain>.ts`, composed in `lib/api.ts` | Add typed API slice using the shared client | Delete API slice; no raw `fetch` in screens |
| Rich fence | `lib/fenceRegistry.ts` (`FENCES`) | Add a `FenceSpec`; one block component; wire render | Delete the spec + component |
| UI primitive | `apps/mobile/ui/` (see `ui/README.md`) | Add or extend one kit component; features import it by path | Delete the component and its callers' use; never fork it inside a feature |
| Chat UI behavior | `features/chat/hooks/useChat*.ts` | Hook owns logic; screen stays thin | Don’t add a second composer intercept |
| i18n string | `lib/i18n/*.json` | Key in `en.json`, translated in every locale (English left in one fails a test) | Delete key from all locale files |
| Banned UX | `.cursor/rules/chat-ux-bans.mdc` | — | If replacing UX, **delete** the old path |

**Flags (defaults in `core/settings/`):** `mcp_tool_loop_enabled` (on), `money_enabled` (on: loan, card and savings questions get server-worked numbers and a calculator card), `worked_layout_enabled` (on: a calculation nothing verified comes as a ```worked block the server lays out, its card with no check), `reply_search_tool_enabled` (on: the reply's model call may search), `math_tools_enabled`, `chemistry_enabled` (on), `math_word_problems_enabled` (on), `web_search_enabled`, `attachments_enabled`, `attachment_rag_enabled`, `attachment_ocr_enabled` (on), `chat_history_rag_enabled` (on), `image_generation_enabled`, `image_search_enabled` (on; real reference-photo lookup, separate from AI generation), `speech_*_enabled`, `push_enabled`, `email_enabled`, `semantic_memory_enabled`, `history_compression_enabled`, `dev_auth_enabled`, `mock_llm_enabled`.

## The chat loop

New chat-loop code → `modules/chat/`. Both transports call `stream_entry.py` with `turn_deps.default_deps()`: a frozen `ChatTurnDeps` holds what a turn uses outside chat (repositories, quota, plan, locks, LiteLLM, image services, todos, web search, the maths fence), and tests pass one with fakes instead of patching. Quota + per-chat prepare lock are owned by `async with turn_resources(...)` (`turn_resources.py`; do not re-introduce hand-managed `owns_lock` / `pre_reserved` flags); `turn_load.py` reads the turn and `turn_intercepts.py` holds the photo and image intercepts.

1. Auth + per-chat prepare lock; wait for the previous turn's pending finalize (`chat/finalize_registry.py`); no turn without the account's AI data consent (`core/consent.py`, `consent_required`)
2. Check + reserve daily quota (Redis)
3. Reference-photo lookup (free+Pro), then image-generation intent interception (Pro) — either may return without an LLM turn; lookup is checked first so "show me an ear" never gets claimed by generation. `modules/images/intent.py` reads both; the phone's composer asks it too (`POST /images/intent`)
4. `turn_prep/`: the message is read once in the SymPy pool, beside the history load (`reading.py`: its plan, subject, maths and physics intents, routing's checks; the turn keeps one `turn_reading.turn.TurnReading` of it, and callers ask `read_turn`/`plan_of` instead of re-planning), then the turn's plan (`intents.py`: the separate requests one message holds, deterministic, no model call; two or more get a multi-part prompt contract, a settings card under the reply and a picture drawn above it, `finalize_parts.py`), memory + recent window, attachments/RAG, chat-history RAG, web search, SymPy pre-solve, physics and chemistry context
5. Owned MCP tool loop (`mcp_tool_loop_enabled`, default on); its search gate and forced search run per request (`tool_loop/parts.py`). A chat to-do change is always a card the user taps
6. Stream via LiteLLM (`gateways/litellm_gateway.py`). A turn the loop left alone carries `web_search`: a call it makes runs, then a second call writes the answer (`tool_loop/reply_calls.py`)
7. Post-stream fence finalization: math (`math/fence.py`), physics (`modules/physics/fence.py`), chemistry (`modules/chemistry/fence.py`), each asked through its subject's adapter (`fence`)
8. Persist assistant + usage in a finalize task (`turn_settle.py`)
9. `enqueue_post_turn_jobs` (`post_turn.POST_TURN_JOBS`, in order) — memory, lesson_progress (after a lesson reply: the chat's one "Learning X: reached Lesson N" memory line, no LLM), topic, compress, message_index (best-effort; must not raise into the stream). A turn's documents get `attachment_index` earlier, as soon as the user's message commits (`turn_prep/persist.py`), so a turn that ends without a reply still indexes them

Steps 6–8 are the only ones on the user's critical path. Everything in step 9 is a durable Redis-Stream job. A turn chat does not stream (a picture or photo intercept, `/images/generate`, live talk) saves its rows through conversation's `turn_record.add_turn_message`, which moves the chat up the drawer, and chat's `finish_turn` (`post_turn.py`) enqueues the same step-9 jobs.

**Jobs registered in** `background/handlers.py`: `topic`, `memory`, `memory_consolidate`, `memory_history_scan`, `lesson_progress`, `compress`, `transactional_email`, `attachment_index`, `message_index`, `storage_sweep`, `account_sweep_backstop` (a deleted account's sweep, scheduled inside the delete's transaction; it skips while the account exists).

**Worker** (`worker_main.py`): consumes that stream and runs the schedulers `process_bootstrap.py` lists (push, email reminders, attachment orphan reaper, billing reconcile, analytics retention, data retention: drafts never sent to and old daily usage rows).

## Mobile map

Expo Router (`apps/mobile/app/`): Login, Onboarding, Chat (`index`), Memory, Todos/Schedule, Settings (profile, preferences, memory, models, voice, notifications, data-controls (web search, location), security, help, about, licenses; every page builds from `features/account/components/settingsUi.tsx`). **Chat history and search are the drawer** (`features/chat/drawer/`, `ConversationList.tsx`), not standalone screens.

- Network: `lib/api.ts` barrel → `lib/api/{client,discover,connectivity,analytics,push,types}.ts` plus feature slices (`features/chat/api.ts`, `features/scanner/api.ts`, `features/auth/api.ts`, `features/account/api.ts`, `features/memory/api.ts`, `features/todos/api.ts`, `features/search/api.ts`, `features/attachments/api.ts`, `features/images/api.ts`, `features/speech/api.ts`)
- Tokens: `expo-secure-store` only
- Chat logic: `features/chat/hooks/useChat.ts` plus focused `useChatSend` / `useChatRegenerate` / … — the screen stays thin. The turn itself (send, socket and SSE frames, Stop, regenerate, dropped connections) is the pure reducer `features/chat/model/chatTurnState.ts`; `useChat` holds it and runs its commands. Chat code reads refs only in callbacks and effects (`react-hooks/refs` is on for `features/chat`)
- Domain libs: `lib/<domain>/` — `math/`, `physics/`, `chemistry/`, `api/`, `markdown/`, `cache/`, `datetime/`, `i18n/`, `speech/`, `places/` (the places fence), `preview/` (the sandboxed HTML and diagram preview). To-dos live in `features/todos/`, not `lib/`. A module belongs in its domain folder, not beside it (`math/html.ts`, not `lib/mathHtml.ts`). What stays flat in `lib/` is genuinely cross-cutting.
- Messages: FlashList; markdown + `components/rich/*` + `components/markdown/*`
- Fences: `lib/fenceRegistry.ts` is the lang/id table; `RichFence` renders
- UI kit: `ui/` — controls (Button, Chip, SegmentedControl, TextField, HeaderButton), `list/` ListRow, `overlay/` (Menu, SelectMenu, `confirmDialog`/`alertDialog`, Sheet), `pickers/` (clock time, calendar date), `share/` ShareSheet, `icons/` (Lucide line icons + BrandMark). Catalog: `ui/README.md`. Lint bans raw `Alert`/`Modal`/`Switch`, `@expo/vector-icons` and the native datetimepicker outside it.
- i18n: `lib/i18n` (9 locales; key parity, placeholders and translation enforced by tests)

## Build / Run Commands

**Starting the app — do it this way.** From the repo root, one terminal, one command:

```bash
./scripts/dev.sh up           # API + iOS Simulator in Expo Go; Ctrl+C stops both
./scripts/dev.sh up phone     # same, for a phone on the same Wi-Fi (scan the QR in Expo Go)
```

`up` keeps the checkout on the latest `main` while it runs (`scripts/follow-main.sh`, every
minute): a merged pull request arrives by itself. The API (`--reload`) reloads it, and every app
connected to Metro reloads (`scripts/reload-app.mjs`, what pressing `r` does). It installs changed
dependencies, restarts Metro when the app's packages changed, and runs new migrations. It moves off a branch
whose commits are all in `main` (a merged pull request, "Rebase and merge" included), never
overwrites a file you edited, and stays on a branch with work `main` lacks; when it can't pull it
says why in the terminal and as a macOS notification. The API log is `tmp/api.log`.

The two-terminal way still works: `./scripts/dev.sh api`, then `./scripts/dev.sh mobile-sim` (or
`mobile`); `./scripts/dev.sh kill-all` stops both.

Expo Go needs no build or signing; log in with dev login there. Only build a native dev client
(`pnpm expo run:ios`, or `pnpm ios:sim` without a signing certificate) when a native-only feature
must be tested. `./scripts/dev.sh` with no argument lists the rest (`setup`, `migrate`, `check`, …).

**Backend** (uses uv):

```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run alembic upgrade head
```

**Mobile** (uses pnpm):

```bash
cd apps/mobile
pnpm install
pnpm expo start          # dev; press i / a for iOS / Android
```

**Gotchas:**

- Run the backend on port 8000 and point the app's `EXPO_PUBLIC_API_URL` at it (use your machine's LAN IP on a physical device, not localhost).
- Native Google Sign-In requires a dev build (`pnpm expo run:ios` / `run:android`), not Expo Go. Use dev auth in Expo Go.
- `pnpm expo run:ios` demands a signing certificate even for the Simulator, because Sign in with Apple's entitlement needs one. For everyday work use `./scripts/dev.sh mobile-sim` (Expo Go, no build). For a native build without a certificate, run `pnpm ios:sim` (leaves Sign in with Apple out of that local build; dev login and Google still work).
- The HTML/JS preview WebView (`react-native-webview`) is a **native module** — it only works in a dev build. After adding/updating it, rebuild the dev client (`pnpm expo run:ios` / `run:android`); in Expo Go the preview falls back to static HTML (scripts stripped) or "Open in browser".

## Testing

**Backend:**

```bash
cd apps/api
uv run pytest
uv run pytest app/tests/modules/chat/test_chat.py
uv run pytest -k memory
```

**Mobile:**

```bash
cd apps/mobile
pnpm test
pnpm typecheck
pnpm lint
```

**Behavior battery:** `apps/api/app/tests/behavior/cases.py` lists ~70 real prompts (STEM,
search, photos and maps, time and location, teaching, format, code, tone, personal) with how each
should route. `test_battery.py` checks that routing offline in CI; a case with a `gap` is a strict
expected failure until the gap is fixed (then delete the `gap` line). `./scripts/dev.sh battery`
sends the same prompts to the running API and writes the replies to `tmp/battery/`
(`--category teaching`, `--only map-where-is`).

**Behavior sweep:** `apps/api/app/tests/behavior/sweep_corpus/*.json` holds ~1,000 turns (a prompt,
any earlier turns, a reply a model might write, and what should happen: `answer`, `save`,
`photo`, `search`, `settings`, …). `sweep.py` routes each one and runs its reply through the real
finalize step over in-memory reminders, and `test_sweep.py` fails on any turn a rule hijacks,
for example "Can you add 3 + 4?" answered "When should I remind you?". Most entries are
look-alikes: everyday messages that use reminder, settings, memory, photo or image words. When
you add or widen a rule that reads the user's words, add its look-alikes here.
`uv run python -m app.tests.behavior.sweep --area todo --show` prints each failing reply. The
sweep runs on a frozen clock (`SWEEP_NOW`), so the time of day never changes a result.

**STEM sweep:** `apps/api/app/tests/behavior/stem_corpus/<subject>/*.json` holds homework questions
with the answer worked independently from the textbook formula, plus look-alikes and questions
that must be declined. `stem_sweep.py` runs each through the real chat path, checks the verified
answer card's number (1%, any unit of the same kind; maths answers are judged by SymPy alone in
`stem_math_judge.py`), the reply's Given/Find/Formula/Substitution/Answer shape, and validates
every `simulation` and `graph` fence. `test_stem_sweep.py` fails on a wrong number, a misread
turn, a reply out of shape or a broken picture, and holds coverage question by question:
`stem_snapshot.json` names every entry each subject answers and draws, so one answered fewer
fails even when another is answered more (`UPDATE_STEM_SNAPSHOT=1` records a change). Physics, maths and
chemistry each have a folder (physics `holdout.json` is questions written after the fixes, kept
honest). An entry with a `gap` is a strict expected failure until the fix deletes the line;
`shared` names the peer subject that owns a law both use (gases, Q = mcΔT and half-lives are
physics'). `uv run python -m app.tests.behavior.stem_sweep math --show`.

**Decision diff:** what each battery, behaviour-sweep and STEM turn decided, as its `turn_trace`
record holds it (route reason, plan, prompt rules, tools, the checked subject and its operation,
the money product, the finalize passes that changed the text), timings dropped.
`uv run python -m app.tests.behavior.decisions dump before.json` on main and `… dump after.json`
on a change, then `… diff before.json after.json`: a change meant to alter no behaviour
(docs/STRUCTURE_TICKETS.md) shows "no decision changed". About two minutes for ~5,000 turns.

**LaTeX on screen:** no reply may show LaTeX source. `docs/fixtures/latex_commands.json` lists every
command the phone draws (inline by its native renderer, display maths by MathJax);
`apps/mobile/lib/math/__tests__/latexCoverage.test.ts` writes it and renders every entry both ways
(`pnpm latex-symbols` after upgrading mathjax-full). `components/markdown/__tests__/latexLeakCorpus.test.tsx`
renders the sweep replies, the shared fixtures and model-style variants, settled and while streaming, and
fails on any source a reader would see; its known gaps only shrink. The STEM sweep holds every
server-written reply to the same list (`app/tests/behavior/latex_check.py`). A command the renderer has
no entry for is never drawn (its argument is) and is reported through `subscribeUnknownLatexCommands`.

**Coverage requirements**

- Backend minimum 80%; critical services (quota, auth, memory) target 90%+.
- `uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=80`
- Do not skip tests to pass coverage. If a path is hard to cover, mock the external call.

## Unit Test Patterns

- Framework: pytest + pytest-asyncio. Async tests for all IO paths.
- Table-driven via `@pytest.mark.parametrize`.
- Mock all external calls — tests must make zero real network calls.
- Naming: `test_<unit>_<behavior>`.

```python
@pytest.mark.parametrize(
    "used, requested, allowed",
    [(0, 1000, True), (29_000, 2000, False), (30_000, 1, False)],
)
async def test_quota_enforced(fake_redis, used, requested, allowed):
    ...
```

**Mobile:** React Native Testing Library; mock `lib/api.ts`; assert on rendered text/markdown.

## Local Dev Setup

**Required services:** Neon Postgres + Upstash Redis (no Docker required). Local API rate limits: Homebrew Redis (`redis://127.0.0.1:6379`) if Upstash free-tier max-requests is exhausted.

> **Neon setup:** use a **direct Neon account** (neon.com), *not* the Vercel-managed integration — the backend is FastAPI (not on Vercel), so that integration adds no value and limits the console/CLI/feature access. Databases live in **AWS us-east-1** (N. Virginia), beside Fly's `iad`: each round trip from the API stays within the region (us-east-2 cost about 10 ms a trip). Until launch, development uses a throwaway free database whose data does not matter; the paid production database is created fresh on deploy day (`docs/PRODUCTION.md` §0). Point `DATABASE_URL` at the development one.

**Env** (`apps/api/.env`):

```
DATABASE_URL=postgresql+asyncpg://...neon...
REDIS_URL=rediss://...upstash...
GOOGLE_CLIENT_ID=...
OPENROUTER_API_KEY=...
JWT_SECRET=...
```

**Mobile** (`apps/mobile/.env`): `EXPO_PUBLIC_API_URL=http://<lan-ip>:8000`

**Dev placeholders:** `DEV_AUTH_ENABLED=true`, `MOCK_LLM_ENABLED=true` (when no API keys).

**Ports:** API 8000, Expo 8081. Health check: `GET /health` → `{"status":"ok"}`.

## Code Conventions

Shape rules (single responsibility, one source of truth, no cycles, file and function size, STEM correctness) are in [docs/ENGINEERING_STANDARDS.md](./docs/ENGINEERING_STANDARDS.md); CI enforces what it can.

**Python:** async/await for all IO; full type hints; Pydantic v2; config via pydantic-settings; ruff for format/lint.

**TypeScript / Mobile:** functional components + hooks; all network via `lib/api.ts`; tokens in expo-secure-store.

## Key Dependencies (external services)

Neon · Upstash Redis · LiteLLM (OpenRouter) · Google OAuth · Apple Sign-In · Tavily (web search) · PubChem · R2 (attachments) · Sentry · RevenueCat

**Database — Neon (serverless Postgres), chosen over Supabase:** we run our own backend, auth (Google/JWT/Apple), and object storage (R2 in production), so we only need a database — not a BaaS bundle (auth/storage/realtime) we wouldn't use. Neon's usage-based pricing + scale-to-zero is cheaper at our scale, branching helps CI/preview, it's plain Postgres (portable, good for the future web client), and `pgvector` runs in the **same DB** for memory embeddings, attachment RAG, and chat-history RAG.

**Shipped beyond the original MVP week:** todos/reminders, attachments + RAG, chat-history RAG, image gen, STT/TTS, live talk, web search, math/physics/geometry/graph, chemistry, rich fences, Pro/RevenueCat, push, Fly `api`/`worker` split, owned MCP tool loop (on by default), web slice 1. Full catalog: FEATURES.md. The dedicated language-learning product and the Google Calendar/Gmail integrations have been removed (migration `0106`).

**Later:** remaining web slices, user MCP servers, LiteLLM Proxy. Not “missing from CLAUDE.md” — deferred on purpose.

## Milestones (MVP week — complete)

The original week-one MVP is done. The table below is historical; current scope is in FEATURES.md and the catalog above.

| Day | Deliverable |
|-----|-------------|
| 1 | Expo app + Google login + basic chat screen |
| 2 | FastAPI + LiteLLM streaming response |
| 3 | Persist + load chat history (Neon) |
| 4 | Markdown/code highlighting, model picker, stop/regenerate |
| 5 | Topic generation + daily token quota (Redis) |
| 6 | Memory extraction + injection |
| 7 | Settings, memory view/delete, polish |
