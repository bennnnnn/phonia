# Recall — On-Device QA Matrix

Manual QA checklist for iOS and Android before store submission. Run against a **dev build** (not Expo Go) for native features; use **Expo Go + Dev User** for quick smoke only.

**Automated backend smoke (no device):** `./scripts/qa-smoke.sh`  
**Full local gate:** `./scripts/dev.sh check` (same as `./scripts/check.sh`)

---

## Environment setup

| Step | iOS Simulator | Physical iOS | Android emulator | Physical Android |
|------|---------------|--------------|------------------|------------------|
| API running | `./scripts/dev.sh api` | same + LAN IP | same | same + `./scripts/set-lan-ip.sh` |
| Mobile start | `./scripts/dev.sh mobile-sim` | `./scripts/dev.sh mobile` | Expo dev build | Expo dev build |
| `EXPO_PUBLIC_API_URL` | `http://127.0.0.1:8000` | `http://<lan-ip>:8000` | `http://10.0.2.2:8000` (emu) or LAN | `http://<lan-ip>:8000` |

---

## 1. Authentication

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 1.1 | Google Sign-In (dev build) | ☐ | ☐ | Requires native build + configured client IDs |
| 1.2 | Apple Sign-In (dev build, iOS) | ☐ | n/a | |
| 1.3 | Dev User (Expo Go) | ☐ | ☐ | `DEV_AUTH_ENABLED=true` on API |
| 1.4 | Session persists after app restart | ☐ | ☐ | JWT in secure store |
| 1.5 | Auto sign-out on expired refresh | ☐ | ☐ | Revoke refresh in Redis or wait 30d |
| 1.6 | Sign out clears tokens + Google session | ☐ | ☐ | |

---

## 2. Chat streaming

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 2.1 | Send message → tokens stream | ☐ | ☐ | WebSocket primary path |
| 2.2 | Stop generation mid-stream | ☐ | ☐ | Partial reply kept exactly as it was when you tapped Stop: it does not grow or change when the reply settles, and reopening the chat shows the same text. "Generation stopped." under it. Stop before any text appears: no reply is left (a regenerate keeps the old answer). |
| 2.3 | Regenerate last assistant reply | ☐ | ☐ | |
| 2.4 | User bubble long-press copies only | ☐ | ☐ | No edit / resend (banned UX) |
| 2.5 | New chat created on first message | ☐ | ☐ | No empty chat rows |
| 2.6 | Offline banner when API unreachable | ☐ | ☐ | |
| 2.7 | Quota exceeded shows plan-aware alert | ☐ | ☐ | Free vs Pro copy |
| 2.8 | Teach-me lesson, one step at a time | ☐ | ☐ | “Teach me python dictionary step by step”: one line on how it will go, a complete short outline, then only `Step 1/N` with a plain explanation, one small code example, and a low-pressure question/optional check. Right / “ok” / “next” → `Step 2/N`. Plausible wrong → targeted correction with a fresh example, then `Step 2/N` (no retry gate). “I’m confused” / “why?” → keep `Step 1/N`, explain differently, preserve the step heading. Keyboard smash → brief acknowledgment and `Step 2/N`, never replay Step 1. Last step → short recap. “Just give me everything” → full reference. “How to install python step by step” / “Walk me through changing a tire” stay numbered how-tos. |
| 2.9 | Full named-duration learning roadmap | ☐ | ☐ | Try “Create a 70-day Python plan”, “70-day roadmap for Python”, and “Teach me Python over the next 70 days.” Result is a complete mobile-scannable progression (`Foundations → Core skills → Projects`) with explicit ordered `Day 1` through `Day 70` entries, compact `Topic → Practice/build → Done when` lines, 4–6 tagged runnable examples across phases, checkpoints, milestones, and an honest production-experience caveat. First useful text should normally arrive in the app’s under-6-second telemetry bands. “I studied Python for 70 days and now plan to apply for jobs” must not trigger a new roadmap. |
| 2.10 | Composer typing | ☐ | ☐ | Empty: “Reply to Recall”, caret level with the middle of + and send. Type a long message: at each wrap the box grows upward by one line and the line being typed stays level with the buttons, with no up-and-down jumps. Delete back to one line, or send: the box returns to one line. Largest text size: nothing clips. |
| 2.11 | A reply that stalls mid-stream | ☐ | ☐ | Hold the provider stream after the first words (a proxy breakpoint between the API and OpenRouter; the phone's own network stays up): after 20 s without new text, "Still working on it… Tap Stop to end the reply." shows under the reply; VoiceOver/TalkBack reads it. Stop works. New text clears it. The server gives up after its idle limit (30 s in production) and keeps what arrived. |

---

## 3. Rich rendering

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 3.1 | Markdown (bold, lists, tables) | ☐ | ☐ | |
| 3.2 | Code blocks + syntax highlight | ☐ | ☐ | Rounded card, no header bar or language label; copy icon floats top-right and turns into ✓. A long line scrolls sideways and does not run under the copy icon at the end. HTML fence: play button sits beside copy. Light and dark. |
| 3.3 | Math / LaTeX | ☐ | ☐ | |
| 3.4 | Geometry / graph SVG | ☐ | ☐ | Works in Expo Go |
| 3.5 | HTML preview (WebView) | ☐ | ☐ | Dev build only |
| 3.6 | Chart / Mermaid (WebView) | ☐ | ☐ | Dev build only |
| 3.7 | PDF attachment preview | ☐ | ☐ | Dev build. A one-page PDF and one near the 10 MB cap: the card shows page 1; the viewer pages through to the end and pinch-zooms. |
| 3.8 | A link in a chart card opens only on a tap | ☐ | ☐ | Dev build. Ask for a Vega-Lite bar chart with an `href` channel to `https://example.com`: tapping a bar opens the browser once. A card whose page script runs `location = "tel:123"` (or `window.open("https://example.com")`) on load or on a timer opens nothing while no finger is on the card. |

---

## 4. Attachments & voice

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 4.1 | Image attach + send | ☐ | ☐ | |
| 4.2 | PDF attach + preview | ☐ | ☐ | |
| 4.3 | Speech → transcription → composer | ☐ | ☐ | Dev build; mic works with typed text too |
| 4.4 | Cancel voice recording (no upload) | ☐ | ☐ | Dev build |
| 4.5 | Read aloud (assistant + vocab) | ☐ | ☐ | Dev build; cloud TTS + device fallback |
| 4.6 | Export chat as PDF from the ⋯ menu | ☐ | ☐ | Full thread; headings/lists/code preserved |
| 4.7 | Export learning topic as PDF | ☐ | ☐ | Vocab words / trivia facts from project screen |
| 4.8 | Daily image cap enforced (free) | ☐ | ☐ | |
| 4.9 | Daily speech STT / TTS caps | ☐ | ☐ | Free: no voice input (the mic opens the plans) and read-aloud uses the phone's voice only. Plus and Pro: 200 dictations and 100 natural read-alouds a day (`core/settings/plans.py`); over the cap shows the limit message. |
| 4.10 | Dictation with the microphone denied | ☐ | ☐ | Turn Recall's microphone off in system Settings, tap the mic: "Microphone access needed" alert; no recording starts and nothing uploads. Airplane mode after recording: "network" message, not a transcription failure. |
| 4.11 | A geotagged photo leaves without its location | ☐ | ☐ | Attach a photo with GPS (taken with camera location tagging on), small (a screenshot-sized crop under 2048 px) and full size, from the library, the camera and Files; also a scanner capture and a profile photo. Download each stored file (Library → ⋮ → Save, or `GET /attachments/{id}/file`) and run `exiftool -gps:all -xmp:all <file>`: nothing. Portrait photos stay upright; a PNG with transparency keeps it; an animated GIF still animates. |

---

## 5. Memory, todos, projects

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 5.1 | Memory screen — view + delete | ☐ | ☐ | |
| 5.2 | Memory toggle in Settings | ☐ | ☐ | |
| 5.3 | Natural profile fact carries into a new chat | ☐ | ☐ | Say “As a software engineer at Uber…” without “remember”; later advice should use it naturally |
| 5.4 | Durable reply preference is learned and applied | ☐ | ☐ | “From now on, keep answers concise and scannable”; a later unrelated turn should follow it without announcing memory |
| 5.5 | “What do you know about me?” gives a safe useful summary | ☐ | ☐ | Work, interests, preferences, goals, projects are allowed; never dump email, exact location, inbox, schedule, or sensitive facts |
| 5.6 | Relevant detail from an older chat is recalled on an ordinary turn | ☐ | ☐ | User should not need to say “remember” or “last time” |
| 5.7 | Correction and forget commands update recall | ☐ | ☐ | New employer supersedes old; explicit forget removes the fact from future prompts |
| 5.8 | Todos CRUD + reminders | ☐ | ☐ | |
| 5.9 | Teach-me chat lesson advances one step | ☐ | ☐ | Ordinary chat, not a Learning screen |

---

## 6. Reminder cards

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 6.1 | "Remind me to call mom tomorrow at 6pm" shows a card; nothing is saved until Add is tapped | ☐ | ☐ | |
| 6.2 | Completing, moving or deleting a to-do from chat shows a card; the list changes only on tap | ☐ | ☐ | |
| 6.3 | "What's on my calendar?" says Recall does not connect to calendars and answers from To-do | ☐ | ☐ | Calendar/Gmail removed |

---

## 7. Push & monetization

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 7.1 | Push permission + token registration | ☐ | ☐ | Dev build |
| 7.2 | Reminder push (scheduled) | ☐ | ☐ | Worker process must run |
| 7.3 | RevenueCat paywall + Pro unlock | ☐ | ☐ | Sandbox purchases |
| 7.4 | Pro quota (500k) reflected in Settings | ☐ | ☐ | |

---

## 8. Android keyboard (known risk area)

| # | Test | Android | Notes |
|---|------|---------|-------|
| 8.1 | Composer visible when keyboard open | ☐ | `softwareKeyboardLayoutMode: resize` |
| 8.2 | Send button reachable with keyboard up | ☐ | |
| 8.3 | Rotate device — layout recovers | ☐ | |

---

## 9. Theme & i18n

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 9.1 | System / Light / Dark appearance | ☐ | ☐ | Settings → Appearance |
| 9.2 | Switch locale — UI strings update | ☐ | ☐ | At least one non-English locale |
| 9.3 | Dark theme on non-chat screens | ☐ | ☐ | Known partial rollout |

---

## 10. Composer AI features

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 10.1 | Image generation (every plan) — composer send → inline image | ☐ | ☐ | No prompt sheet; sends immediately. Daily cap per plan: Free 3, Plus 10, Pro 15 (`core/settings/plans.py`); over it shows the limit message. |
| 10.2 | Image gen intent detected from plain prompt (no attach-menu row) | ☐ | ☐ | Intent → `/images/generate`; no second modal |
| 10.3 | Web search — source chips under reply, open source URL | ☐ | ☐ | `WEB_SEARCH_ENABLED=true`; MCP tool path wraps hits + chips; one Tavily reservation per turn; Redis reserve fail → DuckDuckGo (uncapped); no Tavily key → DDG. "Searching — “…”" ends when the search does: the wait for the answer shows typing dots only. |
| 10.4 | Math scanner — open, torch, pinch-zoom, tap-focus, photos, corner-resize, pan | ☐ | ☐ | Dev build (camera). Close + cancel work. Tap inside the crop to focus. No front camera. |
| 10.5 | Math scanner — capture → adjust crop → Solve → “I read this as” | ☐ | ☐ | “Reading the problem…” shows at once; the reading lands in an editable field (a hint line when it was hard to read). Edit a digit → **Solve** sends `Show steps: …` as text and the reply solves the edited problem. **Send photo** works before the read finishes and sends the crop. **Retake** returns to the camera. iOS: the field stays above the keyboard. |
| 10.6 | Math scanner — unreadable photo, and biology | ☐ | ☐ | Blank paper or airplane mode: “Couldn't read that…”, Solve disabled, **Send photo** still sends. Biology subject: Solve sends the crop directly, no read-back. |
| 10.6a | Physics scanner — read-back, Solve, Send photo | ☐ | ☐ | Physics subject, capture “A ball is dropped from 80 m. What is its speed just before it hits the ground?”: “I read this as” shows the problem as plain text (`2 × 10^-6 C`, `30°`, never `\times` or `\mathrm`). **Solve** sends the text alone, with no photo, and the instant reply shows Given / Required / Formula / Substitution / Answer `39.6 m/s`. **Send photo** sends the crop with `I read this as: …`; the streamed reply carries the verified answer card. A photo with no reading gets the physics note, never math hints. |
| 10.7 | Math lessons — steps for each traced kind | ☐ | ☐ | Balanced style: `solve 2x+3<7`, `solve -3x+2>=8` (flip when dividing by −3), `-2 < 3x+1 <= 7`, `solve 2x+3y=12, x-y=1`, `differentiate x^2 sin(x) step by step` (product rule), `integrate x(x^2+1)^5` (u-substitution), `integrate x e^x` (by parts). Numbered steps render, `$…$` labels typeset, answer chip last; inequalities keep the number line. Short style: chip only. |
| 10.8 | Check my work | ☐ | ☐ | `check my work` + lines `2x + 3 = 11`, `2x = 14`, `x = 7`: line 2 ✗ with the sign explanation and a fixed continuation ending in `x = 4`. Same with “don't give me the answer”: only the hint question, no fix, no chip. All-correct lines: ✓ on each, “Every step checks out.”, check line, chip. |
| 10.9 | Word problems | ☐ | ☐ | “Maria is three times as old as her son. Together their ages add up to 48. How old is her son?” → **Let** / **Equations** (with the quoted words) / steps / “her son's age: 12 years”. A problem the model misreads or cannot close falls back to a normal streamed reply without a verified claim. |
| 10.10 | Reference photo lookup | ☐ | ☐ | "Show me a photo of a human ear": typing dots with "Finding a photo — “human ear”", never the image-generation card (dot game, "Sketching it out", a percentage); the photo lands in the chat. |

---

## 11. Chat-driven settings & suggestions

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 11.1 | Settings proposal card appears (e.g. "switch to dark mode") | ☐ | ☐ | Accept applies; reject dismisses. Only the theme: "use the pro model", "be funnier" or "reply in Spanish from now on" get no card and the reply names the Settings page |
| 11.2 | Appearance change via chat (dark/light/system incl. "default") | ☐ | ☐ | "default" → system; no "could not update" error |
| 11.3 | Follow-up questions appear under a real question's answer | ☐ | ☐ | Up to three one-line questions on the same topic; none after small talk, a draft or a reminder; tap sends it |
| 11.4 | Custom instructions in Settings → Personalization applied to prompts | ☐ | ☐ | Verify via a prompt that reflects them |

---

## 12. Search & navigation

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 12.1 | Drawer search — full-text across chats/messages | ☐ | ☐ | Results show snippet + chat; tap opens chat |
| 12.2 | Link preview card under a message with URL | ☐ | ☐ | Domain line + title; tap opens in browser |
| 12.3 | Drawer open/close via edge pan + hamburger | ☐ | ☐ | No stray taps; mic press doesn't open drawer |
| 12.4 | New chat from drawer FAB; first message creates the chat | ☐ | ☐ | No empty chat rows left behind |

---

## 13. Account, profile & data controls

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 13.1 | Onboarding completes and lands on chat | ☐ | ☐ | First-run only |
| 13.2 | Edit profile fields (name, age, country, job) | ☐ | ☐ | Saves + reflects in Settings |
| 13.3 | Data controls — export my data | ☐ | ☐ | Produces a downloadable archive |
| 13.4 | Data controls — delete account | ☐ | ☐ | Confirms; clears sessions + data |
| 13.5 | Sign out, then sign back in — state restores | ☐ | ☐ | Memories, chats, preferences persist |

---

## 14. Banned UX regressions (must NOT appear)

These were explicitly removed. If any reappears, it's a regression.

| # | Must NOT appear | iOS | Android | Notes |
|---|----------------|-----|---------|-------|
| 14.1 | "✨ Recalled N memories" chip on assistant messages | ☐ | ☐ | Backend may send `recalled`; UI must not surface |
| 14.2 | Show more / Show less on assistant message bodies | ☐ | ☐ | Code-block fold is OK; assistant body stays unfolded |
| 14.3 | `chat.model_fallback` / "switched to…" / "summarized" chips | ☐ | ☐ | Backend may send; UI must not surface |
| 14.4 | Image-gen prompt sheet / attach-menu "Generate image" | ☐ | ☐ | Composer-only; no second intercept |
| 14.5 | Project filter chips / "Link to project" on reminders | ☐ | ☐ | Schedule has no Learning link |
| 14.6 | Empty-state body / "Add" button duplicating the FAB | ☐ | ☐ | Schedule empty: icon + title only |
| 14.7 | Drawer Lists row / shopping checklist UI | ☐ | ☐ | Lists feature removed; do not reintroduce |
| 14.8 | User-message edit / resend (pencil, truncated re-run) | ☐ | ☐ | Long-press on a user bubble is copy only |

---

## 15. Physical-device stress (do not skip on simulators)

These need a **dev build on hardware**. Simulator FPS and memory are not evidence. Do not record invented frame rates — note jank (stutter, hitch, freeze) in **Blockers** with device model + OS.

**Devices:** one recent iPhone, one low-end Android (≤6 GB RAM, e.g. a mid-tier 2022–2023 phone). Optional: older iPhone (A13 / 4 GB) if available.

| # | Test | iOS | Low-end Android | Notes |
|---|------|-----|-----------------|-------|
| 15.1 | Open a thread with **200+ messages**, tap **Load earlier** until 200+ rows are in the list, then fling-scroll both directions | ☐ | ☐ | Opening a chat only fetches 40 messages. Keep tapping Load earlier until the list actually has 200+. FlashList should not freeze; cells recycle. Watch memory. |
| 15.2 | Stream a **~2k token** assistant reply (long explanation) | ☐ | ☐ | First token promptly; scroll stays usable; no multi-second freeze at `done`. |
| 15.3 | Stream a **~5k token** reply (or two stacked long turns) | ☐ | ☐ | Same as 15.2. If the model caps lower, note actual length. |
| 15.4 | Thread with **math** (`$…$` / display) plus a **chart** and **Mermaid** WebView | ☐ | ☐ | Scroll past each fence; expand/collapse chart if clipped; no blank WebViews after scroll-back. |
| 15.5 | Stack **geometry + graph + chemistry** in one thread, then background the app 30s and return | ☐ | ☐ | SVGs/WebViews recover; no white cards. |
| 15.6 | While a reply is streaming, confirm Send is **Stop** and a second send cannot start | ☐ | ☐ | The send control is Stop during `streamActive`; a second send is rejected. Stop cancels. Typing indicator is honest. |
| 15.7 | Immediately after `done`, send another message | ☐ | ☐ | Send is back; composer stays responsive; no double-send. |
| 15.8 | 10 minutes of mixed chat (send, scroll, open drawer, rotate if Android) | ☐ | ☐ | Thermal/jank after warmup. Stop if the OS kills the app. |
| 15.9 | Stream a lesson with a quiz and a table | ☐ | ☐ | "Teach me Python dictionaries step by step" (answer "next" until a `Your turn` quiz), and ask for a comparison table. Watch every frame: no raw JSON (`"question"`, `"options"`) and no line of `\|` pipes ever shows; the quiz appears as a card when its fence closes, the table as a table once its header row is complete; the list does not jump at fence close or at done. |
| 15.10 | Stop, then leave and come back | ☐ | ☐ | Stop mid-reply, wait 5 s, background the app and reopen the chat: the stopped text is identical at every step (no extra words, card or sources appear). |

**Pass bar:** the chat remains usable (scroll, send, stop) on the low-end Android. Cosmetic hitch on first WebView mount is OK; a multi-second freeze or crash is a blocker.

---

## 16. Accessibility layout stress

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 16.1 | Maximum system text size / Dynamic Type | ☐ | n/a | Chat title, multiline messages, count pills, Settings, sheets, and composer text do not clip; first chat row stays below the measured header. |
| 16.2 | Maximum Android font size and display size | n/a | ☐ | Repeat 16.1; math tabs, converter keys, unit chips, swap, and close controls remain reachable and at least 44dp. |
| 16.3 | Narrow phone portrait layout | ☐ | ☐ | Use the narrowest supported simulator/emulator; long translated labels wrap or truncate intentionally without overlapping header actions. Open and close the drawer and confirm the first message keeps its inset. |
| 16.4 | Reduce Motion enabled | ☐ | ☐ | Navigation, drawer, sheets, lesson transitions, streaming chrome, and loading states remain understandable without required motion or flicker. |
| 16.5 | VoiceOver / TalkBack chat flow | ☐ | ☐ | With the screen reader on: type and send a message; while it streams, the send control reads "Stop generating"; "Reply ready" is announced once when it finishes (not per token); swiping reads the reply (the caret is never read); Copy, Regenerate and the thumbs are labelled; a quiz's options and Check answer are reachable. |

---

## 17. UI kit (menus, dialogs, pickers, share)

Rebuild the dev client once first: the native date/time picker module was removed.

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 17.1 | Chat ⋮, drawer long-press, To-dos ⋮, photo viewer ⋮ open the same popover | ☐ | ☐ | Drops from the button (or the finger), flips above near the bottom edge, closes on outside tap and Android back. |
| 17.2 | Delete a chat, a to-do and a photo | ☐ | ☐ | Themed dialog with a red Delete; Cancel and outside tap keep the item. |
| 17.3 | Open a confirm or a picker from inside the to-do editor sheet | ☐ | ☐ | Floats above the sheet (iOS `FullWindowOverlay`); the sheet stays put. |
| 17.4 | Quiet hours start: tap 9 on the dial, then drag to 31 | ☐ | ☐ | Hand glides, number under it turns white, a tick per number, hour then minutes, OK saves. |
| 17.5 | Time picker keyboard mode | ☐ | ☐ | The keyboard does not cover OK; 13 on a 12-hour clock turns red and disables OK. |
| 17.6 | 24-hour device setting | ☐ | ☐ | Inner ring shows 00 and 13–23; no AM/PM. |
| 17.7 | To-do date: arrows, swipe, and the year list | ☐ | ☐ | Week starts on the locale's day; today has a ring; OK keeps the time of day. |
| 17.8 | Chat ⋮ → Share | ☐ | ☐ | Share sheet appears, the OS share menu opens on top; after closing it, Copy shows a check and PDF exports. |
| 17.9 | TalkBack / VoiceOver on the clock dial | ☐ | ☐ | One adjustable control; swipe up/down changes the value; the time is read out. |
| 17.10 | Light and dark mode on the pickers, share sheet, menus and header plates | ☐ | ☐ | Dial and boxes stand out from the dialog in dark mode. |

## 18. Memory pages (Claude-style)

Use a real model (not `MOCK_LLM_ENABLED`). Memory must be on in Settings.

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 18.1 | In a new chat say your job, city, a project you are building by name, and "keep answers short" | ☐ | ☐ | Within a minute Memory shows Profile, Preferences and an Area named after the project, each with a summary and today's date. |
| 18.2 | Open Memory for the first time on an account with older chats | ☐ | ☐ | "Reading your recent chats…" shows, then pages from those chats appear without leaving the screen. |
| 18.3 | Type "You can disagree with me more" in the box and send | ☐ | ☐ | A toast repeats what changed; Preferences shows the new line; the box clears. |
| 18.4 | Open a page, tap a fact | ☐ | ☐ | Edit and Delete appear at the finger; Edit saves new text; Delete asks first. |
| 18.5 | Delete a whole page | ☐ | ☐ | Confirm dialog, then back to the list without the page. |
| 18.6 | Say "I have a peanut allergy", then "I'm building a dating app" | ☐ | ☐ | The allergy is not saved unless you said "remember" or turned on sensitive topics; the dating app is saved as a project. |
| 18.7 | Composer with the keyboard open | ☐ | ☐ | The box sits above the keyboard (iOS) and the list still scrolls; Android resizes. |
| 18.8 | Switch accounts with Memory open | ☐ | ☐ | The next account never shows the previous account's pages. |
| 18.9 | While "Reading your recent chats…" shows, delete a fact you said in an older chat | ☐ | ☐ | The fact stays deleted after the banner goes away. |
| 18.10 | Turn on airplane mode, delete two facts, then turn it off | ☐ | ☐ | Both deletes fail and both facts come back; nothing else on the page changes. |

---

## 19. iPad (App Review tests here too)

`app.json` has `supportsTablet: true`, so the app ships to iPad and App Review may run it there. iPhone apps on iPad still rotate: Expo lists every iPad orientation so the app can join Split View. Use a real iPad or the iPad simulator, production or preview build.

| # | Test | iPad | Notes |
|---|------|------|-------|
| 19.1 | Sign in with Apple and with Google, then onboarding | ☐ | Lands on chat. |
| 19.2 | Send, stream, stop and regenerate in portrait and landscape | ☐ | Composer above the keyboard, also with a hardware keyboard attached; messages keep their width. |
| 19.3 | Rotate mid-stream, open the drawer, rotate back | ☐ | No clipped header, stray overlay, or drawer stuck half open. |
| 19.4 | Split View and Slide Over at ⅓, ½ and ⅔ width | ☐ | Layout reflows like a narrow phone; nothing overlaps. |
| 19.5 | Attach a photo (library and camera) and a PDF | ☐ | Pickers open as popovers or sheets and return the file. |
| 19.6 | Chat ⋮ → Share, a photo's ⋮ → Save, and export to PDF | ☐ | iPad share sheets need an anchor: the sheet opens from the button and never crashes. |
| 19.7 | Maths scanner: capture → Solve | ☐ | Camera preview fills the frame in both orientations. |
| 19.8 | Mic dictation; Live Talk (Pro sandbox) | ☐ | Both prompts show the microphone text from 20.1. |
| 19.9 | Plan sheet: buy Plus in the sandbox, then restore | ☐ | Prices load; both buttons enabled. |
| 19.10 | Settings pages and the time and date pickers | ☐ | Dialogs centred; tap targets at least 44 pt. |

---

## 20. Store build (production or preview profile)

Checks only a release build shows. A dev build carries dev-launcher keys and different permission text.

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 20.1 | First mic use (dictation) | ☐ | ☐ | iOS prompt: "Recall uses the microphone so you can dictate messages and talk with Recall in Live Talk." Never "Allow Recall to access your microphone". |
| 20.2 | First camera use: attach a photo, and the maths scanner | ☐ | ☐ | iOS prompt: "Recall uses the camera so you can take photos to attach in chat and scan math problems from your notes or worksheets." |
| 20.3 | Location question ("where am I?") | ☐ | ☐ | While-in-use prompt only; iOS never offers "Always". No Face ID or Motion prompt anywhere. |
| 20.4 | First launch | ☐ | n/a | No "find and connect to devices on your local network" prompt. |
| 20.5 | Read-aloud, then press Home; start Live Talk, then press Home | ☐ | ☐ | Read-aloud stops; Live Talk hangs up. No audio keeps playing; Android shows no media notification. |
| 20.6 | Save a chat image (Android 13+), and on an Android 10–12 device | ☐ | ☐ | 13+: saves with no permission prompt. 10–12: the storage prompt appears once, then it saves. Photo attach works with no media permission on 13+. |
| 20.7 | App Store Connect / Play Console processing | ☐ | ☐ | No ITMS-90683 or ITMS-91053 email; Play shows no foreground-service or photo/video permission declaration request. |

---

## 21. Live Talk (Pro, dev build on a physical device)

FEATURES calls device barge-in a release gate. Simulator Live Talk is half-duplex.

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 21.1 | Start | ☐ | ☐ | Pro account: tap the waveform. Start chime, then the orb; say a sentence and Recall answers aloud. Close: both turns are in the chat as messages. |
| 21.2 | Mute | ☐ | ☐ | Tap the mic: it turns red and Recall does not hear you; tap again and it does. |
| 21.3 | Barge-in | ☐ | ☐ | Talk over Recall while it speaks: playback stops at once, the cut reply reads "Generation stopped.", and your new turn is answered. |
| 21.4 | Airplane mode mid-session | ☐ | ☐ | Turn airplane mode on while Recall talks: an error shows and no audio keeps playing; close Live Talk. Back online: the turns so far are in the chat, and Settings → Account minutes dropped by at most the session's reservation (15 min; a session whose end never reached the server keeps it). |
| 21.5 | Microphone denied | ☐ | ☐ | Turn Recall's microphone off in system Settings, start Live Talk: "Microphone access needed" with Open Settings (opens Recall's settings page), never "needs a dev build"; no minutes are used. |
| 21.6 | VoiceOver / TalkBack | ☐ | ☐ | The orb reads "Live talk, listening" / "Live talk, thinking" (hint "Cancel waiting") / "Live talk, Recall is speaking", and each change is announced. There is still no Listening/Speaking text on screen. |

---

## 22. Library

| # | Test | iOS | Android | Notes |
|---|------|-----|---------|-------|
| 22.1 | Upload in chat → Library | ☐ | ☐ | Attach a photo and a PDF in a chat: both appear in drawer → Library (Uploaded, Files), and search finds them by name. A generated image is under Generated; a lookup photo ("show me an ear") is not in Library. |
| 22.2 | Delete the chat | ☐ | ☐ | Delete that chat: its files stay in Library; long-press shows no Open chat. Use in chat attaches the file to the current chat. |
| 22.3 | Airplane mode | ☐ | ☐ | Open Library offline: failed thumbnails show Retry and stay; back online, Retry loads them. A failed upload never leaves a ghost tile. |
| 22.4 | Delete from Library | ☐ | ☐ | Delete a file: confirm dialog; the tile goes only after the server confirms; it no longer opens from the old chat. |

---

## Sign-off

| Platform | Build profile | Tester | Date | Pass/Fail |
|----------|---------------|--------|------|-----------|
| iOS | development / production | | | |
| iPad | production / preview | | | |
| Android | development / production | | | |

**Blockers:** document any failures with device model, OS version, and steps to reproduce.
