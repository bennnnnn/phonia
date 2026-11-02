#!/usr/bin/env bash
# Creates GitHub issues from the recall-app-review (claude/recall-app-review-tge8il).
# Run from repo root: ./scripts/create-review-issues.sh
set -euo pipefail
cd "$(dirname "$0")/.."

create() {
  local title="$1"
  local labels="$2"
  local body="$3"
  gh issue create --title "$title" --label "$labels" --body "$body"
}

EPIC=$(gh issue create \
  --title "Code review tracker: Recall end-to-end (claude/recall-app-review-tge8il)" \
  --label "enhancement,priority/high" \
  --body "$(cat <<'EOF'
Tracking issue for the end-to-end code review (34 findings + nits).

**Start here (top 5 user/on-call impact):**
1. Reasoning leaks into smart-chat replies (#TBD)
2. Streaming re-renders whole chat screen (#TBD)
3. Post-turn background jobs lifecycle (#TBD)
4. Auth/WS rate limit bypass (#TBD)
5. Todo delete silently un-does on failure (#TBD)

Sub-issues will be linked below as they are created.
EOF
)")

echo "Epic: $EPIC"

link() {
  local num="$1"
  gh issue comment "$EPIC" --body "- #$num"
}

# --- Chat & streaming (API) ---

n=$(create \
  "[HIGH] Fix DeepSeek reasoning tag stripper (wrong match strings)" \
  "bug,priority/high,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Chat & streaming core

**Location:** `apps/api/app/gateways/litellm_gateway.py:54-55`

**Problem:** `_THINK_OPEN` / `_THINK_CLOSE` are set to `" Dodd"` and `"doable in"` instead of DeepSeek-R1 `<think>` / `</think>` tags. Comments describe redacted thinking blocks; the filter is a no-op.

**Symptom:** Smart-chat replies that emit inline reasoning stream raw chain-of-thought into the user bubble and persist it to the DB.

**Fix:** Correct the tag constants; add a regression test for split-chunk stripping.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[HIGH] Await or track post-turn background jobs task lifecycle" \
  "bug,priority/high,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Chat & streaming core

**Location:** `apps/api/app/services/chat/stream.py:419-443`, `apps/api/app/routers/ws.py:81-86`

**Problem:** `_finalize_task` (memory extraction, topic gen, todo/project sync, compaction, suggestions) is created via `asyncio.create_task`. Production WS/SSE paths only await `_finalize_db_task`, not the jobs chain.

**Symptom:** Jobs may fail silently after DB finalize; lifecycle is untracked on disconnect/cancel paths.

**Fix:** Explicit task registry or await jobs after user-visible `done`; ensure failures are logged and retried where appropriate.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Release DB session before LLM/web-search during turn prep" \
  "bug,priority/medium,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Chat & streaming core

**Location:** `apps/api/app/services/chat/turn_prep.py:427-515`

**Problem:** DB session wrapping `build_stream_prompt_context` also spans `sync_todos_before_reply` (non-streaming LLM) and web-search/MCP augmentation — not just calendar/Gmail as documented in FEATURES.md.

**Symptom:** Neon connection held idle during external LLM + Tavily/DuckDuckGo calls on every turn; pool pressure under concurrent load.

**Fix:** Short-session pattern: load context, release session, run external calls, re-open for writes if needed.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Stop generation should close upstream LiteLLM stream" \
  "bug,priority/medium,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Chat & streaming core

**Location:** `apps/api/app/services/chat/stream.py:340-354`

**Problem:** On cancel, the token loop breaks but `.aclose()` is never called on the LiteLLM async generator.

**Symptom:** Provider stream keeps running after user taps Stop — tokens and cost accrue invisibly.

**Fix:** Call `aclose()` on cancel; verify in tests.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Collapse duplicate ChatNotFoundError/ModelUnavailableError handlers in stream.py" \
  "enhancement,priority/low,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Chat & streaming core (nit)

**Location:** `apps/api/app/services/chat/stream.py`

**Problem:** Three near-identical `except ChatNotFoundError` / `except ModelUnavailableError` blocks duplicate the following `except Exception` body.

**Fix:** Collapse into shared handler; no behavior change expected.
EOF
)")
link "$n"; echo "#$n"

# --- Memory ---

n=$(create \
  "[MEDIUM] Re-embed memory sections after consolidation rewrite" \
  "bug,priority/medium,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Memory

**Location:** `apps/api/app/background/memory_consolidation.py:50`

**Problem:** Extraction re-embeds changed sections; consolidation calls `upsert_sections` but never updates the stored vector.

**Symptom:** Semantic recall ranks consolidated text by pre-rewrite embedding until a later extraction touches the section.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Align NULL-confidence handling in semantic vs fallback memory paths" \
  "bug,priority/medium,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Memory

**Location:** `apps/api/app/repositories/memories.py:36` vs `apps/api/app/services/memory.py:55-58`

**Problem:** In-memory ranking treats NULL confidence as 1.0; SQL path filters `confidence >= min_confidence` where NULL fails in Postgres.

**Symptom:** Legacy/manual memories with no confidence appear in fallback path but vanish during semantic search.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Add safety checks for memory consolidation overwrites" \
  "bug,priority/medium,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Memory

**Location:** `apps/api/app/gateways/litellm_gateway.py:554-557`

**Problem:** Consolidation prompt asks model to rewrite full section; `upsert_sections` fully overwrites text with no diff or dropped-fact detection.

**Symptom:** One bad consolidation turn can permanently delete facts the model omitted.

**Fix:** Consider append-then-merge, diff logging, or validation before overwrite.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Prevent semantic memory cache warmer from writing stale data after invalidation" \
  "bug,priority/medium,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Memory

**Location:** `apps/api/app/services/memory.py:173-218`

**Problem:** Detached cache warmer can write to Redis after `invalidate_memory_block` if a memory changed between DB read and Redis write — no version stamp.

**Symptom:** Up to cache TTL (~120s), chat context may include deleted or pre-update memory.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Accept partial valid sections when one memory extraction section fails validation" \
  "enhancement,priority/low,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Memory

**Location:** `apps/api/app/gateways/litellm_gateway.py:385-389`

**Problem:** Pydantic validates the whole extraction batch; one bad section drops all proposed updates for the turn.

**Fix:** Validate per-section; persist valid sections, log/reject invalid ones.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Tune semantic memory selection (min similarity, injection cap)" \
  "enhancement,priority/low,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Memory (nit)

**Problem:** No minimum-similarity floor on semantic selection (only confidence cutoff). Configured injection cap (15) exceeds 5 fixed memory types, making cap a no-op today.

**Fix:** Revisit thresholds when pgvector recall ships or cap is enforced.
EOF
)")
link "$n"; echo "#$n"

# --- Voice, cache & compression ---

n=$(create \
  "[MEDIUM] Bound speech transcription request body before full decode" \
  "bug,priority/medium,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Voice, cache & compression

**Location:** `apps/api/app/models/schemas.py:591`, `apps/api/app/routers/speech.py:69-91`

**Problem:** `SpeechTranscriptionIn.audio_base64` has no `max_length`; router parses/decodes full JSON body before service-layer 5MB check. No global body-size limit in `main.py`.

**Symptom:** Oversized base64 payloads fully buffered in memory on the mobile JSON path.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Refund speech quota on non-HTTPException upload failures" \
  "bug,priority/low,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Voice, cache & compression

**Location:** `apps/api/app/routers/speech.py:63-95`

**Problem:** Quota reserved before try; `except HTTPException` refunds non-429 errors but unexpected exceptions during body parsing skip refund.

**Symptom:** Dropped/malformed uploads can burn a daily transcription slot.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Use injected Redis client in web search cache helper" \
  "enhancement,priority/low,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Voice, cache & compression (nit)

**Location:** `apps/api/app/services/web_search/search_cache.py:85`

**Problem:** `_search_with_cache` overwrites the `redis` parameter with `get_redis_client()`, defeating DI in tests.
EOF
)")
link "$n"; echo "#$n"

# --- Integrations ---

n=$(create \
  "[MEDIUM] Check calendar write scope before MCP write hints" \
  "bug,priority/medium,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Integrations

**Location:** `apps/api/app/services/chat_tools.py`, `apps/api/app/services/calendar.py:412-414`

**Problem:** Non-MCP path checks `has_write_access`; MCP path adds write hint from keyword match only.

**Symptom:** Users without write access get unmaterialized calendar proposal cards.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Add idempotency lock for calendar proposal confirm" \
  "bug,priority/medium,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Integrations

**Location:** `apps/api/app/services/calendar.py:363-397`

**Problem:** `confirm_create_event` reads Redis proposal, creates event, deletes key after success — no lock or idempotency key.

**Symptom:** Double-tap or retried request can create duplicate calendar events.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Tighten fuzzy todo matching to reduce wrong-item actions" \
  "bug,priority/low,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Integrations

**Location:** `apps/api/app/services/todos.py:300-327`

**Problem:** Fallback matching uses substring containment and can ignore topic; slightly off wording can complete/delete wrong todo.

**Fix:** Stricter matching, confirmation threshold, or topic-scoped fallback.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Parallelize Gmail message detail fetches during sync" \
  "enhancement,priority/low,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Integrations

**Location:** `apps/api/app/gateways/google_gmail_gateway.py:183-222`

**Problem:** Up to 30 message details fetched sequentially; periodic sync processes users sequentially too.

**Fix:** `asyncio.gather` with concurrency cap (mirror calendar gateway).
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Fix MCP calendar adapter to pass CalendarEvent dataclasses" \
  "bug,priority/low,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Integrations (latent)

**Location:** `apps/api/app/gateways/mcp/calendar_adapter.py:20-29`

**Problem:** Passes raw dicts into `find_conflicting_events` which expects `CalendarEvent` instances. Unreachable today — only sympy MCP adapter is wired.

**Fix:** Map dicts to dataclasses before Phase 3 proactive nudges enable this adapter.
EOF
)")
link "$n"; echo "#$n"

# --- Security & infrastructure ---

n=$(create \
  "[HIGH] Apply WebSocket rate limit per message, not only at connect" \
  "bug,priority/high,area/security,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Security & infrastructure

**Location:** `apps/api/app/routers/ws.py:217-224`

**Problem:** 30/min limiter runs once after auth, before the message loop.

**Symptom:** Open connection can send unlimited messages; only daily token quota remains as coarse guard.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[HIGH] Do not trust client X-Forwarded-For for rate limiting without proxy validation" \
  "bug,priority/high,area/security,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Security & infrastructure

**Location:** `apps/api/app/routers/auth.py:33-39`, `apps/api/app/core/rest_rate_limit.py:21-33`

**Problem:** Rate limit keys use first hop of `X-Forwarded-For` with no trusted-proxy check.

**Symptom:** Callers can rotate spoofed IPs to bypass login brute-force and REST rate limits.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Reject wildcard CORS in production config validation" \
  "bug,priority/medium,area/security,area/infra" \
  "$(cat <<'EOF'
**Source:** Code review — Security & infrastructure

**Location:** `apps/api/app/core/config.py:188-189`

**Problem:** `validate_production_settings` rejects empty CORS but allows explicit `*` with `allow_credentials=True`.

**Fix:** Fail startup if production CORS includes wildcard.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Fix Apple JWKS cache invalidation on signing key rotation" \
  "bug,priority/medium,area/security,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Security & infrastructure

**Location:** `apps/api/app/gateways/apple_auth.py:38-48`

**Problem:** Kid-miss path assigns `_jwks_cache = None` locally without `global` — module cache never clears.

**Symptom:** Apple sign-in can fail for up to 1h after key rotation instead of refetching on miss.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Gate DLQ admin endpoints on admin role, not dev_auth flag alone" \
  "bug,priority/medium,area/security,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Security & infrastructure

**Location:** `apps/api/app/routers/admin.py:32-56`

**Problem:** `/admin/dlq` and replay reachable by any authenticated user when `dev_auth_enabled=true`.

**Symptom:** Staging users can read other users' failed job payloads (memory extraction bodies, etc.).
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Handle RevenueCat TRANSFER webhook for subscription moves" \
  "bug,priority/low,area/api" \
  "$(cat <<'EOF'
**Source:** Code review — Security & infrastructure

**Location:** `apps/api/app/routers/webhooks.py:29-38`

**Problem:** TRANSFER events between app-user-ids are not handled.

**Symptom:** Old owner may stay Pro and new owner Free until explicit sync.
EOF
)")
link "$n"; echo "#$n"

# --- Mobile chat feel ---

n=$(create \
  "[HIGH] Isolate streaming token updates from full chat screen re-render" \
  "bug,priority/high,area/mobile" \
  "$(cat <<'EOF'
**Source:** Code review — Mobile chat feel

**Location:** `apps/mobile/hooks/useChat.ts:56-59`, `apps/mobile/hooks/useChatMessageList.tsx:73`

**Problem:** Each WebSocket token updates top-level `streamingDraft` state; ChatHeader, ChatComposer, and all mounted ChatMessageRow reconcile every token.

**Symptom:** Janky streaming on longer chats — main lever for "feels like Claude."

**Fix:** Memoize static chrome; update only streaming row (refs, split state, or targeted subscription).
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Add SSE fallback for regenerate and edit message" \
  "bug,priority/medium,area/mobile" \
  "$(cat <<'EOF'
**Source:** Code review — Mobile chat feel

**Location:** `apps/mobile/hooks/useChat.ts:459-550`

**Problem:** `sendMessage` falls back to HTTP SSE when WS is down; `regenerateResponse` and `editMessage` hard-fail without SSE path.

**Symptom:** On flaky networks, send works but regenerate/edit fail inconsistently.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Animate composer with keyboard instead of static offset snap" \
  "enhancement,priority/medium,area/mobile" \
  "$(cat <<'EOF'
**Source:** Code review — Mobile chat feel

**Location:** `apps/mobile/hooks/useChatScroll.ts:181-194`, `apps/mobile/lib/chatComposerLogic.ts:69-112`

**Problem:** Keyboard height via raw listener + plain state; composer jumps instead of tracking keyboard curve.

**Fix:** Reanimated keyboard hook or KeyboardAvoidingView synced to native animation.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Debounce or unify competing auto-scroll during streaming" \
  "bug,priority/medium,area/mobile" \
  "$(cat <<'EOF'
**Source:** Code review — Mobile chat feel

**Location:** `apps/mobile/hooks/useChatScroll.ts:142-148`, `apps/mobile/components/chat/ChatMessageList.tsx:58-62`

**Problem:** Imperative `scrollToEnd` on every token length change runs alongside FlashList `maintainVisibleContentPosition` — no debounce unlike end-of-stream rAF pattern.

**Symptom:** Occasional micro-jitter during fast streaming.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Expand FlashList getItemType for varied assistant content shapes" \
  "enhancement,priority/low,area/mobile" \
  "$(cat <<'EOF'
**Source:** Code review — Mobile chat feel

**Location:** `apps/mobile/lib/messageListLayout.ts:7-9`

**Problem:** Recycling only distinguishes user vs assistant; assistant rows vary (text, quiz, vocab, calendar cards).

**Symptom:** Brief layout jump when recycled cell switches layouts during fast scroll.
EOF
)")
link "$n"; echo "#$n"

# --- Mobile screens ---

n=$(create \
  "[HIGH] Show error alert when todo or list delete API fails" \
  "bug,priority/high,area/mobile" \
  "$(cat <<'EOF'
**Source:** Code review — Mobile screens

**Location:** `apps/mobile/app/todos.tsx:404-471`

**Problem:** Optimistic delete on failure only triggers silent refresh — unlike toggle/due-date handlers which show Alert.

**Symptom:** Item disappears then reappears with no explanation — reads as app corruption.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Close drawer on Android hardware back button" \
  "enhancement,priority/medium,area/mobile" \
  "$(cat <<'EOF'
**Source:** Code review — Mobile screens

**Location:** `apps/mobile/components/DrawerShell.tsx`

**Problem:** No `BackHandler` listener; back falls through to router while drawer is open.

**Fix:** Intercept back when drawer open; close drawer first.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Add loading state on Integrations screen to avoid connected flash" \
  "bug,priority/medium,area/mobile" \
  "$(cat <<'EOF'
**Source:** Code review — Mobile screens

**Location:** `apps/mobile/app/settings/integrations.tsx`

**Problem:** Calendar/Gmail status starts null → shows "Not connected" until async refresh completes.

**Symptom:** Connected users briefly see wrong state every visit.

**Fix:** Skeleton/loading until first fetch resolves.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[MEDIUM] Add retry UI on Projects list fetch failure" \
  "bug,priority/medium,area/mobile" \
  "$(cat <<'EOF'
**Source:** Code review — Mobile screens

**Location:** `apps/mobile/app/projects/index.tsx:379-380`

**Problem:** Error renders bare text with no retry — unlike Memory/Todos StateView pattern.

**Fix:** Use shared StateView with translated retry action.
EOF
)")
link "$n"; echo "#$n"

n=$(create \
  "[LOW] Default StateView retryLabel should use i18n, not hardcoded English" \
  "enhancement,priority/low,area/mobile" \
  "$(cat <<'EOF'
**Source:** Code review — Mobile screens (nit)

**Location:** `apps/mobile/components/StateView.tsx:25`

**Problem:** `retryLabel` defaults to literal `"Retry"`. Current call sites pass translated labels; future reuse may regress.

**Fix:** Require label prop or default via `t('common.retry')`.
EOF
)")
link "$n"; echo "#$n"

echo ""
echo "Done. Epic: $EPIC"
