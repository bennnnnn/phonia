# Recall — Feature Coverage & Roadmap

A reference of what the app does **today** versus what is **deferred** to a future version.
Recall is a personal AI chat app: a snappy chatbot with clean formatted answers, multi-model
support, and long-term memory of the user. Mobile = Expo (React Native). Backend = FastAPI +
Neon Postgres + Upstash Redis + LiteLLM (OpenRouter).

**Legend**
- ✅ Implemented
- ⚠️ Partial / with caveats
- 🔜 Deferred (planned)

---

## 1. Authentication (sign up & sign in)
- ✅ **Google sign-in** — single "Continue with Google" button (requires native dev build + the
  Google config plugin / iOS URL scheme to be set).
- ✅ **Account creation** — automatic on first Google sign-in (no separate sign-up flow).
- ✅ **Dev login** — "Continue as Dev User" for Expo Go / local development (gated by
  `DEV_AUTH_ENABLED`, blocked in production).
- ✅ **Sessions** — JWT (HS256) access token (1h) + Redis-backed refresh token (30d), stored in
  secure storage; `POST /auth/refresh` and `POST /auth/logout` with access-token revocation.
- ✅ **Session recovery and account boundaries** — atomic secure credential pairs and Redis
  rotation; temporary failures preserve sign-in; startup offers Retry when validation is
  unavailable; old-account requests, cache writes and background sync cannot restore a
  signed-out account.
- ✅ **Auto sign-out on 401** — refresh is attempted first; definitive rejection signs out,
  while temporary refresh failures preserve the session for retry.
- ✅ **Sign out** — revokes server tokens, clears local storage, and signs out of Google.
- ✅ **Sign in with Apple** — iOS only (hidden on Android); requires Apple capability on App ID.
- 🔜 Email/password, magic links, multi-device session management.
- ⚠️ **Simulator Keychain** — unsigned simulator builds cannot use Keychain (`errSecMissingEntitlement`). Configure Apple development signing and rebuild before verifying session persistence and native Google/Apple callbacks. Credentials stay in secure storage.

## 2. Conversations (chats)
- ✅ **New chat** — from the header `＋` and the drawer; created **lazily** on the first message
  (no empty "New chat" rows pile up).
- ✅ **Chat list** — grouped by **Today / Yesterday / Earlier**, newest first; refreshes when the
  drawer opens.
- ✅ **Open & load history** — full message history loads when a chat is opened.
- ✅ **Rename** — via the in-chat `⋯` menu (modal editor).
- ✅ **Delete** — via the in-chat `⋯` menu with a confirmation prompt (DB-level cascade removes its
  messages).
- ✅ **Search** — full-text search across chats and messages via the drawer search bar
  (backend `/search` with debounce + pagination).
- ✅ **Search reliability** — account/query changes immediately
  invalidate old results and requests; first-page and pagination failures offer Retry.
  Results use stable ordering and a consistent page/count database snapshot, and opening
  a message cancels obsolete navigation work.
- ✅ **Pin** — pin/unpin a chat (chat `⋯` menu + drawer long-press); pinned chats show in a
  **Pinned** section at the top of the drawer.
- ✅ **Share / Export** — share a conversation as a markdown transcript via the **native OS
  share sheet** (Messages, Mail, Files, …); export a chat as PDF from the in-chat `⋯` menu.
  Chat `⋯` + drawer long-press (share/pin/archive/delete);
  no backend. This is **not** a
  ChatGPT-style public `chatgpt.com/share/…` URL — anyone with that kind of link could
  read the thread without signing in. Public web links are a separate privacy feature
  (not started; do not assume we have them).
- ✅ **Manage from the drawer** — long-press any chat for **Pin/Unpin · Share · Archive · Delete**.
- ✅ **Library** — drawer **Library** → paginated grid of the user’s verified attachments
  (generated images, uploaded images, and files — not web lookup / reference photos,
  which stay on the chat). Tabs: All / Generated / Uploaded / Files.
  Search is a case-insensitive substring on filename, MIME type, and the **linked message
  body**. For generated images that includes the **previous user message** (the draw
  prompt) and the prompt stored on `original_filename`, not only the assistant
  `[Image: …]` marker. Tap an image for a fullscreen viewer: black page, Close on the
  left, More (⋮) / Download / white Share pill on the right, nothing at the bottom;
  swipe for the next photo (it loads the next page near the end), pinch or double-tap
  to zoom, and it follows the photo by id so a delete never acts on the wrong one.
  Toasts show inside the viewer. Long-press (or a screen reader's actions) for Use in
  chat / Open chat / Share / Delete. Share hands over the file through expo-sharing
  (Android's RN Share would send only a path); generated images get a slugged file
  name with a real extension. Tap a file to read it (PDF and text in-app; other types open on
  the device). The attach sheet also opens Library. Deleting a chat leaves
  its uploads and generated files in Library (Open chat hides when the thread is gone). Lookup
  photos stay on the chat only. Explicit Library
  delete removes the file. A failed thumbnail stays with Retry; the row is dropped
  only after the server confirms the file is gone. Opening Library warms the All page
  from the drawer tap (20s cache, same window as Memory); tab snapshots avoid a
  wrong-grid flash. Logout, chat delete, upload, and image-gen invalidate it.
- ✅ **Attachment reliability** — picker and Library completions
  stay in their account and conversation; pagination failures retain rows with Retry.
  Downloads use distinct cache files, verify cached files still exist, and clear on logout.
  Temporary storage failures preserve attachment records; failed object deletions remain
  queued for cleanup. Local upload retries cannot overwrite an existing Library file.
- ✅ **Photos leave without their metadata** — every picked photo (library, camera, Files,
  scanner, profile) is uploaded as a re-encode with no EXIF, GPS or XMP, upright; PNG and
  WebP keep their format, the rest become JPEG, and a GIF keeps its frames with its
  metadata blocks dropped (`features/attachments/model/attachmentPrep.ts`).
- ✅ **Archive** — drawer long-press and in-chat `⋯` menu; archived chats show in a separate
  section and are excluded from the main list.
- ✅ **Multi-select** — drawer **Select** mode: tap rows to choose, then bulk **Archive** or
  **Delete** (with confirm).
- ✅ **Chat management reliability** — manual titles survive delayed
  generation; pin/archive updates are atomic; drawer and header changes stay in sync.
  Bulk partial failures preserve successful actions, and stale reads cannot restore
  deleted chats. Saved history and title polling respect navigation and account changes.
- 🔜 Chat-list pagination beyond the current 200-row limit; pins take priority within it.
- 🔜 Folders.

## 3. Messaging behaviour
- ✅ **Streaming** — token-by-token over WebSocket; the reply appears as it's generated.
  Ordinary turns show typing dots only (no “loading memory / working on it” staircase).
  Status labels are reserved for real extra work while it runs: web search, files, math,
  a reference-photo lookup ("Finding a photo") and image gen; the server sends
  `composing` once a tool is done, so its label never outlives it. Hard turns say what
  they are doing once it has run a second: "Thinking… 12s" while a model reasons
  (counted from when it was asked; its reasoning is never shown), "Planning the answer…"
  for a slow tool-selection round, and "Checking the answer…" (or "Finding a photo…")
  under a streamed reply whose last step runs before it saves; the label goes when that
  step ends, and at `stream_end` at the latest. After the first
  token, 20 s without new text shows "Still working on it… Tap Stop". A card fence
  (quiz, steps, array, places, any data-bodied registry fence) is a quiet placeholder
  until it closes, a table waits for its delimiter row, and verified-solve markers or
  text-written tool calls never reach the phone. Turn start overlaps waiting for the previous reply to persist
  with user/quota load (regenerate still waits first so it does not miss that reply).
  Attachment-chunk probes run only when they can apply;
  time/location answers skip a database checkout.
- ✅ **Stop generation** — cancel mid-stream (send button becomes a stop button, until the
  reply's text is all in: at `stream_end` Send works again, and a turn sent then goes out
  once that reply's `done` lands, or once a reload finds the saved reply when no `done`
  comes in 12 s; a reply whose save fails then says “This reply wasn’t saved.”); the partial reply
  is kept and marked incomplete (same “Generation stopped.” footer as a provider
  drop or token-limit cut). The kept text never changes after Stop: the cancel frame
  says how much the phone drew (`shown_chars`), the server saves that text made safe
  and laid out (no verified card, note, sources or reminder card added), and a Stop
  before any text shows saves nothing. Hard WS/SSE disconnect with tokens already
  streamed also finalizes (same as soft stop). **New chat / leave does not abort SSE** (Stop still
  does); leftover events are ignored for the next thread. `GET /messages` waits for
  the in-flight SSE producer the same way it waits on WS.
- ✅ **Per-thread composer drafts** — text is saved per chat (and a separate New Chat slot).
  Opening another thread restores that draft and clears attachment and in-progress
  dictation so they cannot send into the wrong conversation.
- ✅ **Clarifying questions as a tap card, like ChatGPT** ([docs/clarify.md](./docs/clarify.md)) —
  when the best answer depends on what the user means or wants ("What is the best country?")
  and memory and the chat do not say, Recall starts the answer (the strongest few options,
  one bold line each), asks "**But let me ask you one thing.** What do you mean by *best*?",
  and ends on a `clarify` card: 1-3 questions, 2-8 emoji-led choices each, the first one
  picked, and one full-width button named for what it does ("Find my best country"). The
  button sends one sentence ("Recommend the best country for me. Main priority: Making money.
  Geographic preference: Anywhere. Compare the strongest options…"), and the next reply opens
  with a direct recommendation for the user, then the full answer. Typing instead also works.
  Never for facts, problems, greetings, reminders, pictures or drafts with a purpose. The
  server checks the card before it is saved (`chat/clarify_card.py`,
  `finalize_text.settle_clarify`), shows it to the model in history as one "Asked:" line, and
  gives the next message what to answer (`chat/clarify_turn.py`).
- ✅ **Teach-me lessons (ChatGPT's lesson shape)** — “teach me X”, “help me learn X”,
  “I want to learn X” (and the teach verbs in the other app languages) and “help me
  understand two sum” / “walk me through quicksort”. One idea (“teach me Python
  dictionaries”) gets exactly that lesson; a whole subject (“teach me Python”, “cooking”,
  “English”) first gets 5-8 topics in learning order and one question about where to
  start, and the answer (“3”, “start”, “I'm a beginner”) starts Lesson 1 there. A lesson is
  a complete reply: a one-line hook tied to the user's goal or level from memory (one fitting emoji),
  `### Lesson 1: <topic>`, 3-5 numbered sections (`### 1. Understand the problem`, …) with
  real-world examples, code explained line by line with its output, an `array` card for
  values over their indexes, a trace as `steps` cards, cost in math ($O(n)$) and a
  comparison table, then `### N. Your turn` with a `quiz` card (pick an option, **Check
  answer**, see why; checked on the phone, nothing is sent) and one line previewing the
  next lesson. A `quiz` or `array` fence whose JSON is broken still reads: the question,
  lettered options and a **Show answer** tap, or the list's values as text
  (`lib/lesson/lessonFences.ts` loose readers); a fence counts as finished once its braces close. The next turn grades a typed answer (“Correct! 🎉” or a
  short fix), then teaches Lesson N+1 from the preview; confusion re-explains the same
  lesson a new way, random input is not graded, and “everything at once” / a cheat sheet
  wins. A day or more after the last lesson, the next one opens with a two-line recap and a
  warm-up quiz. Each lesson keeps one ordinary memory line per chat (“Learning Python:
  reached Lesson 3, Dictionaries … Covered: …”, `lesson_progress` job, no LLM; a hand edit
  to memory after the lessons began keeps it out), so “teach me Python” in a new chat
  offers to pick up where they stopped. Prompt: `modules/chat/prompt_constants/teaching.py`
  and `lesson_flow.py`. Procedures (“teach me how to
  install Docker” / “walk me through changing a tire”) keep the how-to steps.
- ✅ **Follow-through, not templates** — a short “yes/go/sure” after an offer is
  not a greeting. A short answer (“no”, “got it”) to a question or lesson step
  loads the recent messages and continues the thread. “One sentence” / briefly beats chart, compare, and how-to
  layout. Sequence diagrams use `sequenceDiagram`, not a flowchart. Bare
  “write me an email” asks one purpose question; a named purpose still drafts
  now. Real/my chart data without numbers asks once instead of inventing a
  sample as the answer. “Continue” / “keep going” resumes the last reply where it
  stopped, never a restart or recap, and the window keeps that reply whole even past the
  token budget; “fix that” works on the last reply. A correction (“no, I said I'm
  vegetarian”, “actually I meant Python 2, not 3”) carries a short contract beside the
  user turn: apply it, drop the old assumption, no long apology
  (`prompt_constants/conversation.py`). “In detail” / “deep dive” gets the detailed length;
  one sentence for one part and detail for another gets each its own. A reply's last line
  loses a generic closer (“Let me know if you have any other questions”, “Hope this
  helps”), never inside a fence, a quote or a draft the user asked for
  (`modules/chat/generic_closer.py`). A photo too blurry or cropped to read gets what is
  unclear and a request for a clearer one (`attachments/vision_notes.py`).
- ✅ **Send stays busy until accepted** — after Send, the composer clears so the next
  draft can be typed, but Send and Attach stay disabled until upload/create finishes.
  A failed turn restores into an empty composer and does not overwrite a newer draft.
- ✅ **Regenerate** — re-run the last assistant reply.
- ✅ **Message folding** — long **user** messages collapse past ~320px with a fade +
  **Show more / Show less** (disabled while a reply is still streaming). Assistant replies do
  **not** fold (code blocks may still fold). Do not reintroduce assistant-body folding.
- ✅ **Copy** — copy a whole message (keeps code syntax, `$`, identifiers, and
  ` ```answer ` results; skips reminder/control JSON). Dedicated copy per code
  block. Read-aloud uses a separate spoken form (prose + the visible result;
  a short label for charts/diagrams; never control JSON).
- ✅ **Like / dislike** — thumbs up/down persist per message (saved to the backend and restored on
  load); tapping the active rating clears it.
- ✅ **Per-message model** — the model used is recorded on each message.
- ✅ **Web search** — when the user's question needs fresh facts, the owned tool loop runs Tavily
  (or the DuckDuckGo fallback) and the reply carries source chips (skipped on short A–D replies); if
  the model skips `web_search` on a turn the search gate says needs live results, the backend
  searches once. Empty hits inject a no-results instruction so the reply cannot look live from
  training data. One Tavily
  reservation per turn. A Redis reserve failure (or a missing user) fails closed to **DuckDuckGo
  only** — DDG is uncapped (latency only). Search cache keys include `user_id`. The search gate is
  deterministic (`should_web_search`: skip rules, the explicit fast path, then the heuristic); the
  LLM classifier that once sat behind it was off in production and is gone. A turn the gate
  neither searches nor rules out (chitchat, the user's own facts, a reminder, a sum, a greeting,
  pasted code, the time somewhere) offers `web_search` to the reply's own model call
  (`tool_loop/reply_calls.py`, `reply_search_tool_enabled`, on): the model answers at once, or
  calls the tool and answers in a second call that reads the results, with source chips. "Who won
  the champions league" and "the population of Ethiopia" search now; a reply that needs no search
  costs nothing more.
  An explicit request always searches: "do a search", "search it online", "google it", "check
  that online", typos like "seearch" (`web_search/command.py`). When the request names no topic,
  or a follow-up says "she" or "it", one cheap call reads the last turns and writes the query
  (`services/conversation_reference.py`); the tool loop never searches the request's own words.
- ✅ **Voice input (STT)** — mic in the composer records on-device (`expo-audio`, **dev build**),
  transcribes via OpenAI `gpt-4o-mini-transcribe`, and injects the transcript as normal text. Plus
  and Pro, **200/day**; on Free the mic opens the plans (the server refuses Free with 403). Not
  available in Expo Go.
- ✅ **Live talk (Pro)** — waveform on the composer opens a **WebRTC**
  speech-to-speech session (OpenAI Realtime `gpt-realtime-2.1`). Server VAD
  ends your turn; the orb never shows “Transcribing…”. Physical devices enable
  echo cancellation and barge-in; iOS Simulator retains half-duplex. Free and Plus
  open the plans. Pro: **60 minutes per UTC calendar month**. Each session reserves up to
  15 minutes at mint (refused under 1 minute left), the phone hangs up when its reservation
  ends, and `POST /speech/live/end` settles the reservation to the time the server measured
  (a session that never reports keeps the whole reservation). Settings → Account shows the
  minutes left. Tap the mic (next to close) to mute so Recall
  cannot hear you; it turns red. Playback is not paused. No Listening/Speaking
  labels on screen; screen readers hear each phase (listening, thinking, speaking) as
  it changes. A denied microphone asks for access with Open Settings. The normal composer stays so you can type and attach in voice mode.
  Typing a draft hides mute and close so the field uses the full row; they
  return when the draft is empty. Spoken turns are saved as normal chat
  messages (what you said + the reply) so they are in the thread when you
  close. Spoken sessions get the same stored-memory snapshot as text chat
  plus bounded read-only memory lookup and web search.
  Search sources use the existing reply chips. The chat header (drawer / ⋮) stays
  available. Needs `OPENAI_API_KEY` — OpenRouter has no Realtime API.
- ✅ **Read aloud (TTS)** — defaults to OpenAI **gpt-4o-mini-tts** PCM
  (`POST /speech/tts` lead then rest, rest bound to the lead hash so it cannot steal
  another utterance's unbilled quota) and starts playback on the first sentence.
  The legacy fast alias maps to the same OpenAI model; an explicit phone-voice choice
  is preserved. The natural (cloud) voice is Plus and Pro, **100/day**; Free reads with the
  phone's own voice and never calls the server (which refuses Free with 403).
  Settings disclose AI-generated audio. Mic permission is not required.
  Cloud 502 falls back to on-device `expo-speech` (a speech 502 is not an API outage).
  Cloud clip playback needs a **dev build** (`expo-audio`); Expo Go still reads aloud via
  device TTS. JSON `POST /speech/tts` remains for non-streaming clients.
- 🔎 Physical-device barge-in and live provider verification remain release gates;
  offline tests cannot establish echo quality or interruption timing.

## 4. Formatting & rendering
- ✅ **Markdown** — headings, **bold**/*italic*, bullet & numbered lists (ink-colored
  markers), blockquotes, links, inline code (monospace on a light tinted pill, also in
  lesson cards; code such as `x = 5` is never drawn as maths), horizontal rules.
- ✅ **Code blocks** — a rounded card. A language-tagged fence shows that language
  in the top corner (Python, JavaScript). An untagged fence is a teaching snippet
  (`name = "john"`) and has no label and no guessed keyword colors. Copy floats in
  the opposite corner. Syntax colors mark keywords, strings, and numbers; names
  stay in the body ink. Horizontal scroll.
  Fenced bodies stay opaque to math/table beautification (`$$` in a Python string,
  a quoted GFM table, ASCII boxes in ` ```text `).
- ✅ **Syntax highlighting** — **Prism.js** token coloring for 40+ languages (comments, strings,
  numbers, keywords); heuristic fallback for unknown langs.
- ✅ **Tables** — styled (header shading, borders, cell padding).
- ✅ **Inline images** — Markdown `![alt](url)` images render (contained, rounded).
- ✅ **Image generation (every plan)** — Type an image request in the composer and send (e.g. "draw me a
  cat" or "Dog" then "Image"); the user bubble keeps that wording (not rewritten to "Generate
  image: …"). Daily caps: Free **3**, Plus **10**, Pro **15**, stored as chat attachments. No separate
  prompt sheet, and the model must not send people to DALL-E / Midjourney. Stop
  mid-generation keeps the user message and shows canceled/failed + Retry. While it works, the
  card is a dot field with an accent wave (a Skia shader in builds with Skia; a band under a
  dotted cover in Expo Go), a stage line ("Sketching it out" … "Almost there") and an estimated
  percentage; tapping it starts a small dot game. Tap the result to
  view full-screen and save via the system share sheet. Only the server reads the request:
  the tap paints the bubble and typing dots first, and when a send might be a picture or a
  photo the composer then asks `POST /images/intent` (a picture is drawn under that bubble), which
  answers with the chat turn's own reading of the text and the chat's recent turns
  (`docs/fixtures/image_intent_cases.json`), and draws what it answers, so "show the steps"
  after a picture is chat. A maths, physics or chemistry turn is never a picture: "draw
  ethanol" gets the structure and "A lens has focal length 15 cm. Where's the image?" gets the
  optics; art ("a cartoon atom for our chemistry club poster") still draws. If the server
  can't answer within 3 seconds the send goes to chat, and the chat turn still draws a typed
  picture request.
- 🔜 **Music generation** — same composer-send path as image gen (no prompt sheet): user asks
  to generate a track, we generate a clip, store it as an audio attachment, and show a **compact
  inline player** on the assistant message (play/pause + scrub + duration — not a full-screen
  Now Playing UI). Pro + daily cap. Catalog alias + gateway (provider TBD); reuse
  `expo-audio` / attachment URLs. Do not start until image-gen’s storage/cap path is the
  template. Not TTS / not humming into the mic.
- ✅ **Math / LaTeX** — inline `$...$` renders in dedicated KaTeX Computer Modern faces (italic variables, upright digits/operators, superscripts, scalable continuous radicals, tight stacked fractions);
  display ` ```math` renders as **MathJax-SVG** (`MathSvgView` + `mathjax-full`, lazy-loaded
  and LRU-cached, themed via `currentColor`) on every build — no WebView — with a readable
  `MathText` fallback if conversion fails. Native builds use **Skia** for inline function
  graphs, the expanded pinch/pan graph explorer, number-line solutions, and shaded
  two-dimensional inequalities, with SVG as the Expo Go / stale-client fallback. Bare arithmetic (`12+3=15`) and identifiers (`x2`) are typeset as
  supplied — the renderer does not invent exponents. Composer keypad OCR still maps
  `x2` → `x^2`. Server-side **SymPy** solves equations and samples graphs. Closed
  verified answers (`1+1=x`, factor a quadratic) return directly without an LLM
  turn. **Lessons** are server-rendered from verified `key_steps` for every
  supported equation/system/inequality unless the user explicitly asks for
  “just the answer”; an adjacent “how?” replays that same checked trace instead
  of asking the model to invent steps. Coverage includes equations (linear,
  pure-power, quadratic), linear and compound inequalities,
  2×2 linear systems, derivatives rule by rule, and indefinite integrals by
  method (u-substitution and integration by parts included). SymPy checks every
  line before it is shown; other explanations still stream.
- ✅ **Primary-school written arithmetic** — the API owns exact column traces for
  addition carries, subtraction regrouping across zeros, multiplication carries
  and partial products, and long division with bring-down rows/remainders. Decimal
  operands stay exact and terminating division shows placeholder zeros. Mobile
  renders the canonical trace in a dedicated Computer Modern card; “show steps”
  and an adjacent “how?” reuse it, while answer-only and hint turns cannot leak it.
- ✅ **Teaching pictures** — a closed request can draw place value and base-ten blocks,
  a number bond, a ten frame, an equal-group array, fraction bars, a fraction number
  line, an integer jump that starts negative, a decimal comparison, half-up rounding
  to a named place, polynomial or synthetic division, the unit circle at a standard
  angle, a quartile box plot, a frequency table, a stem-and-leaf plot, a short integer
  histogram, stated scatter points, a fair coin or die tree, or a point translation,
  reflection, rotation, or dilation. The picture is server-owned and the answer chip
  stays the verified value. “Just the answer” hides the picture. Multi-digit sums keep
  the column trace.
- ✅ **Check my work** — “check my work”, “where did I go wrong” or a bare column of
  worked lines: each line is checked against line 1 with SymPy (one unknown,
  polynomial sides up to degree 2). The reply marks every line, names the first
  slip (a sign lost moving a term, one side only, multiplying where dividing undoes,
  an inequality not reversed, a half-expanded bracket, a lost root, …) and
  continues from the corrected line with verified steps. “Don't finish it for me”
  / “just a hint” names the slip as a question and never shows the fix or answer.
- ✅ **Word problems** — consecutive integers, two ages, tickets at two prices and
  mixtures are read by the server's templates; the reply shows the setup, the verified
  steps and the answer. Other ages, sums and prices get one structured call
  (`title-model`, flag `math_word_problems_enabled`) that translates the problem into
  unknowns and equations; when every number is stated and SymPy finds exactly one
  solution in the stated domain, the model gets that setup to check against the words,
  never as a verified card. A process that never ends gets no setup. Recall attaches geometry, graph, and
  algebra ` ```answer ` after the stream when the model did write. The composer **math keypad** inserts
  LaTeX on one 6 × 6 grid per page: Basics (digits, the four operations, x and y, fractions,
  roots, powers), Symbols (relations, sets, geometry), Trig, Calc and Greek, each ending in
  ← → ⌫. A key types into the box the caret is in; → leaves it. Converter sends a
  "convert … to …" question with **Ask**. See [docs/math.md](./docs/math.md).
- ✅ **Recurring pay through a date** — questions such as “I make $3,400 every two
  weeks; how much by December 11?” use the device-local date and a deterministic
  calendar calculator, not a chat model or web search. The reply shows complete
  periods, remainder days, payment dates, the today-is-a-payday alternative, and
  daily proration so the counting assumption is never hidden.
- ✅ **Physics** — server-side extractors and pure solvers (see
  [docs/physics.md](./docs/physics.md)). Verified operations are the
  formula catalog, one entry per `physics_op`. Answers have
  three significant figures and upright units, in the unit the question asks for
  ("in kWh", "in psi"); scientific notation is read whole (`2 × 10^-6 C`); a solve that skips
  a stated value of a kind it uses, leaves out a stated force, speed, length or angle, or
  answers a different quantity than the one asked, is declined. A student's own result
  ("I got 19.8 m/s") is checked, never used as a given, and a planet named in a side
  question ("would it be different on Mars?") does not replace Earth in the main one. A question the phrase extractors miss is read straight into a
  catalog law when it states the law's inputs and asks for its result (SUVAT for any
  unknown including u, d = vt in the written units, a dropped body's height, a
  horizontal launch, weight, Atwood, a pull against friction, lifting power, Kepler
  around a named planet, rotational KE; `Q = It` for I, `Q = CV` for any unknown,
  resistivity, `τ = RC`, RC charging and discharging, capacitors in series and parallel,
  an ideal transformer, `E = V/d`, `F = qE`, `W = qV` for a named electron or proton,
  a solenoid's field, a string or pipe's resonance, Snell for θ₂, a diffraction
  grating's angle, lens power, `f = R/2`, `m = −v/u`; the ideal-gas law for any
  unknown, Boyle, Charles, Gay-Lussac and the combined gas law, `Q = mcΔT` for any
  unknown, water mixtures, latent heat, expansion, kinetic theory (`v_rms`, mean and
  most probable speed, `⟨E_k⟩ = 3/2 kT`), a diatomic gas's `U`, absolute pressure,
  apparent weight, a floating fraction, capillary rise; photon momentum, threshold
  frequency and wavelength, stopping potential, decay constant, activity, mean life,
  the fraction remaining; hydrogen transitions, the Bohr radius, quantum-oscillator
  levels, relativistic momentum and energy, `E² = (pc)² + (mc²)²`, velocity addition,
  the Schwarzschild radius, the Boltzmann ratio and `S = k ln Ω`, energy-time
  uncertainty, and an orbit's period from its height); see "Adding a law" in
  docs/physics.md. An answer is in the unit its like givens share (two µF capacitors
  give µF). The STEM sweep (`app/tests/behavior/stem_sweep.py`, 753 physics turns) runs
  homework questions through the real chat path and fails CI on any wrong verified
  number, misread turn, reply out of shape or broken picture; it answers 574 of 597.
  Maths (458 turns, 339 of 362 answered) and chemistry (203 turns, 166 of 175) have their
  own sets.
  Mechanics:
  1D gravity kinematics, SUVAT in all four rearrangements plus s = vt − ½at², projectile (range,
  max height, time of flight, impact speed, launch angle from a range), scalar
  F=ma with resultants and components, KE / PE / work / power (including
  `W = Fd cos θ` and `P = Fv cos θ` when an angle is stated, the work-energy
  theorem, and mechanical-energy conservation for gravity or a spring), a physical
  pendulum, a conical pendulum, and the speed to just complete a vertical loop, momentum /
  impulse / 1D collisions, friction (`f = μN`, incline acceleration, `μ = tanθ`
  at the slipping angle, minimum force to move), circular motion
  (`a_c`, `F_c`, period, RPM and `ω = v/r`), springs and SHM (`F = kx`, `U`, spring and
  pendulum periods, `f = 1/T`, `v_max = Aω`), torque and moment balance.
  Beyond mechanics: **circuits** (Ohm's law, power, n-resistor networks,
  `Q = It`, `E = Pt`, `C = Q/V`, terminal voltage, one-junction Kirchhoff
  and a one-battery series loop, inductor emf and energy, RL growth and decay,
  sinusoidal RMS, reactance, series impedance, LC resonance, and average
  resistor power),   **waves** (`v = fλ`,
  `f = 1/T`, Doppler for a moving source or a moving observer of a stationary
  source, with a stated speed of sound and either party's speed in any unit, and the
  school form when both speeds are stated, plus a sound level and radiation pressure), **optics** (thin lens/mirror, speed-derived refractive
  index, magnification, Snell, critical
  angle), **thermal** (`Q = mcΔT`, `PV = nRT` for the missing pressure, volume,
  amount, or temperature, monatomic `U = 3/2 nRT`, isobaric `W = PΔV`,
  adiabatic `PV^γ` when gamma is stated, Carnot refrigerator and heat-pump
  COP, Newton's law of cooling, and Otto efficiency), **gravitation**
  (`F = GMm/r²`, orbital and escape velocity, surface gravity, potential,
  potential energy, orbital energy, and the circular Kepler period, with a
  named-body table), **fluids** (`P = F/A`, `ρgh`, upthrust, density, continuity,
  flow rate, horizontal Bernoulli, Bernoulli with both heights stated, and
  Poiseuille), **rotation** (`ω = θ/t`, moment of inertia, `L = Iω`, rotational KE,
  constant-α kinematics including θ = (ω₀+ω)t/2, `τ = Iα`, `τ = ΔL/Δt`, isolated `Iω` conservation,
  rolling without slipping, the parallel-axis theorem, and a two-gear train),
  **magnetism** (`F = BIL`, `F = qvB`, `Φ = BA`, and `sin θ` / `cos θ` when an
  angle is stated; Gauss for a sphere, shell, line, and sheet; Faraday's
  magnitude),   **materials** (`σ = F/A`,
  `ε = ΔL/L`, `E = σ/ε`, shear modulus, bulk modulus, and Poisson's ratio) and **modern** (`E = hf` or `hc/λ`, de Broglie, half-life,
  `E = mc²`).
  **What it refuses is the design.** An unstated collision type, a 2D collision,
  a diverging lens (the sign conventions disagree), an absolute temperature
  written as bare "degrees" (27 °C and 27 K differ elevenfold), efficiency from
  two temperatures (that is Carnot), a Doppler question with no stated
  direction, a price ("find the cost"), a magnification from a virtual image's
  distance, a moment of inertia for a "wheel" (the shape *is* the answer), a
  planet described but not named, buoyancy without a submerged volume, a
  Bernoulli question with neither horizontal flow nor both heights, an adiabatic
  process with no gamma, a Kirchhoff loop that is not one battery plus
  series resistors, a fall with no stated height, a series-parallel network, heating
  through boiling or melting, and a statement that asks nothing — all
  return no verified block rather than a plausible wrong number. Depth pressure
  says "gauge"; the magnetic force and flux state the perpendicular case when no
  angle is given; a pendulum period states the small-angle approximation; a
  level-ground range states equal launch and landing height; work and power
  state a parallel force when no angle is given; horizontal Bernoulli states
  that the height terms cancel. Those assumptions appear once,
  in the Formula section. Special relativity (Lorentz factor, time dilation,
  length contraction), entropy change, double-slit interference, Malus, Brewster,
  the infinite square well, hydrogen levels, and the Heisenberg relation are in
  the catalog. Still unverified, and answered without a verified block:
  the Schrödinger equation (wave functions), Planck's distribution, and general
  relativity beyond the Schwarzschild radius. Nuclear binding energy and mass defect are chemistry when the
  nuclear mass is supplied. A test keeps that list off the
  catalog. Every complete, single-request verified physics
  answer returns directly with Given / Required / Formula / Substitution / Answer,
  without waiting on the language model. A question in parts the result does not all
  answer, a yes or no about a value, and a side question go to the model with the
  verified block, so no part is dropped. Each answer carries one picture.
  - Trajectory ` ```graph ` fences are for SUVAT (position or velocity against time), a speed
    asked of a fall (`v(t)` beside the fall), and SHM.
  - A projectile or a drop is one labelled ` ```simulation ` scene instead of a path graph. It
    shows the ledge it leaves, R, H and θ as measure lines, and strobe ghosts.
  - Scene schema v2 also draws:
    - inclines that slide;
    - free-body boxes with labelled arrows;
    - Atwood machines on a pulley;
    - orbits with the planet to scale;
    - a ball on a string;
    - pendulums;
    - springs with an unstated amplitude, drawn at a display size;
    - collisions and recoils;
    - charges.
  - Circuits, ray diagrams (lens, concave or plane mirror, refraction) and waves (travelling,
    strings, open and closed pipes) are diagrams the phone lays out from the spec
    (`components/rich/diagrams/`).
  - Every picture has screen-reader alt text and a translated title.
  - 162 of the 163 STEM-sweep questions that want a picture get one (see
    [docs/physics.md](./docs/physics.md#pictures)).

  Trajectories and simulation scenes render in native Skia and autoplay;
  `=` stops and `<` restarts playback. A dot walks the sampled points, which the
  solver spaces by uniform time, so the motion is real rather than eased.
  Reduce Motion keeps the static curve. The solver gate is the union of those extractor cues, and every
  param declares an SI dimension (Pint reads a bare `pa` as a *petayear*, so a
  missing entry is a wrong answer, not a missing check). Moon/Mars gravity is a
  whole-token match (`marsh` stays Earth). See [docs/physics.md](./docs/physics.md).
- ✅ **Chemistry (typed verified pipeline)** — `ChemistryIntent` extraction and deterministic
  solvers, one module per topic for each, share one species model: formula, composition,
  charge, and phase. The catalog (`catalog.py`) is the one list of operations. Labelled
  templates read first; a question in its own words is read by the binder, on the law engine
  physics shares (`services/law_binding/`). The local table is all 118 elements. Verified
  work covers atom-and-charge balancing (including redox half-equations); amount conversions,
  an element's mass in a sample, average atomic mass from isotopes, and empirical and
  molecular formulas; mass, solution, and gas stoichiometry with limiting reagent, from a
  written equation or a reaction told in words ("how much water if i burn 4g of h2": the fuel's
  oxides, or the product named, balanced or declined), and its follow-ups ("what if i only had
  16g of o2"); solution
  concentration, dilution with the stock volume, mole fraction, and colligative properties;
  strong/weak acid–base pH, `Ka`/`Kb`, percent ionization, buffers after addition, titration
  regions, and a neutralization's unknown concentration; Dalton, wet gases, gas density,
  Graham's law, and Henry's law; calorimetry, `q = nΔH`, Hess, formation, and bond enthalpy, and
  two-point Clausius–Clapeyron; phase-aware
  `Kc`/`Kp`, ICE, `Ksp` from a salt's formula, and precipitation; zero/first/second-order
  kinetics and two-point Arrhenius; cell, Nernst, electrolysis mass and time, and a school
  galvanic cell; one-missing-product nuclear equations and mass defect; Beer–Lambert;
  electron configuration, oxidation state, formal charge, and single-center VSEPR
  (water 104.5°, ammonia 107°, carbon-centered HCN, and resonance counts); RDKit functional
  groups, CIP stereochemistry, and isomer class; a PubChem IUPAC name when that
  property is returned; five one-product named reactions; coordination names and
  first-row crystal-field spin and magnetic moment; calibration, gravimetric,
  standard addition, sample standard deviation, standard error, percent error,
  relative uncertainty, and chromatography Rf; IR and 1H NMR correlation ranges,
  the n+1 rule, and the molecular ion; and Michaelis–Menten. The gas laws, `Q = mcΔT`, and
  decay are physics' laws, answered in L, atm, kJ, and °C when a chemistry question asks
  them. mM, µM, nM, and kcal are read through Pint. Answers keep the precision the question
  was written in: the fewest significant figures among the measured givens (2–4), typed
  values echoed as typed. Balance, stoichiometry, VSEPR, titration, ICE, and galvanic
  answers also append a server-owned `chem_scene` the phone only draws. Complete typed
  questions return a textbook worked solution: Given / Required / named Formula / Substitution
  (with units, each conversion its own row) / Answer; a procedure (balancing, a table
  lookup, a configuration) shows its rule under Method and checks it under Working. The
  answer is one server ` ```answer ` fence tagged `notation: chemistry` so formulas and
  units are not typeset as algebra. Curved-arrow mechanisms
  and biochemical pathways stay model-only. RDKit / SymPy + PubChem still verify structures, descriptors, elements,
  and compounds. Structures use ` ```smiles ` (alias ` ```chemistry `); the server attaches
  ` ```molecule3d ` for the first two valid molecules. Chemically aware 2D layout remains
  smiles-drawer; interactive 3D renders on a native Skia canvas, with an SVG fallback for
  Expo Go or a stale native client. See [docs/chemistry.md](./docs/chemistry.md).
- ✅ **Geometry diagrams** — ` ```geometry` JSON fences render labeled shapes (rectangle, circle,
  triangle, trapezoid, sector, …) via native SVG (`react-native-svg`; works in Expo Go).
- ✅ **Function graphs** — ` ```graph` JSON fences plot y=f(x) from server-computed point arrays
  via native SVG.
- ✅ **Charts** — `chart` / `vega` / `vega-lite` fences render inline via a sandboxed WebView
  (Vega; needs a dev build). One contract: the chart hint shows bar, line, scatter with a
  regression best-fit layer, histogram, pie and box plot (`prompt_constants/chart_shapes.json`, every one
  drawn in the phone's tests); the phone also reads a `series` chart and a Chart.js config. Data
  must be inline: a body it cannot draw, or one Vega draws no marks for, shows a note, the data as
  a table and the source, never a blank card. A chart of a formula is sampled by SymPy into a
  ` ```graph` (`modules/math/chart_formula.py`); the phone never evaluates one. A chart of the
  user's own numbers is not a maths turn.
- ✅ **HTML/CSS/JS preview** — `html` fences get a sandboxed WebView preview ("run" → modal) plus
  "open in browser" (needs a dev build; see the code-execution policy below). Run may load
  scripts/styles only from `cdn.jsdelivr.net`, `unpkg.com`, `cdnjs.cloudflare.com`, and Google
  Fonts — not open `https:`.
- ✅ **Rich blocks** — callouts only for a real `> Warning:` or a short `> Note:`
  (GitHub `[!WARNING]` / `[!NOTE]` too), key-value, comparison, step lists, and
  email/message/social "copy" cards. EmailCard edits persist into the stored
  ` ```email ` fence so Copy, follow-ups, and reopen see the same draft.
- ✅ **Fence ownership** — [fenceRegistry.ts](apps/mobile/lib/fenceRegistry.ts) marks each
  fence `model` / `server` / `legacy`. New turns: Markdown plus a small model-facing
  set (`copy` / drafts, `mermaid`, `chart`, `math`, lesson `quiz` / `array` / `steps`,
  chemistry source). Server attaches
  verified `answer` / `graph` / `geometry`, `sources`, and `places`. Layout fences
  (`steps`, `comparison`, `keyvalue`, `quote`, `clock`, `callout`)
  still render for history; the prompt must not choose them. A `>` quote card is
  only a citation whose last line is `— Name`. `details` / `collapse` / `summary`
  and HTML `<details>` unwrap to a bold title plus markdown. Reminder
  (`reminder_proposal`) and settings (`settings_proposal`) control fences stay outside the
  registry; a leftover `calendar_proposal` in an old message is stripped for display.
  Leftover `vocab_quiz` fences in old messages are stripped for display.
- ✅ **Answer photos** — an answer mainly about something worth seeing (a place,
  landmark, animal, plant, person, food, product) gets one real photo above the text,
  without "show me": the model opens the reply with a hidden ```photo query (“where is
  Ethiopia” → `Ethiopia location map`), the search starts while the text streams, and the
  finished reply carries the photo (`modules/images/answer_photo.py`). Abstract topics,
  code, math, advice and lessons get none. Each photo uses one search from the daily photo
  limit; a spent limit, a miss or a slow search just leaves the answer without one.
- ✅ **Mermaid diagrams** — inline SVG render via sandboxed WebView (dev build); source toggle +
  copy + Mermaid Live link; Expo Go shows source + external editor hint.
- ✅ **PDF attachments** — uploaded PDFs show a file card + inline first-page preview (pdf.js in
  sandboxed WebView, dev build); tap opens full viewer with share/export. Inline extract
  is the first 25 pages / ~12k characters; the model is told when later pages were
  unread. A RAG miss is not treated as “not in the file.”
- ✅ **Deeper file retrieval** — indexing reads up to 500 text-layer PDF pages / 200k
  characters (256 chunks by default), independently of the small inline excerpt.
  Scanned-PDF OCR on the index job is a separate ceiling (20 pages / 200k chars,
  not 500 vision pages). Stored coverage drives the RAG prefix so OCR files are
  not described as 500-page extracts. Existing indexes require re-upload/reindex
  to gain the expanded coverage.
- ✅ **Office text** — XLSX cells/formula text and PPTX text/tables/speaker notes.
  No formula execution, macros, embedded chart/image understanding, or external-link loading.
- ✅ **Image edits** — owned reference bytes reach the image provider; hidden copies
  preserve edit inputs. Regeneration replaces the assistant using the original input.
- 🔜 **Collaborative cursors / shared docs** — multi-user editing not in scope for v1 personal app.

## 5. Models & routing
- ✅ **Multiple tiers** — six chat models, none of them coding models. Free: Qwen3.7 Flash
  (everyday, Auto's fast lane), Claude Haiku 5.5 (`free-chat`, backup) and GLM 5.3 Flash (hard and
  maths turns). Paid adds DeepSeek V4.1 Flash (`smart-chat`), GLM 5.2 (Auto's maths lane) and
  GPT-6 Luna. On Pro, Auto's everyday turns go to Claude Haiku 5.5 (`ROUTING.everyday_strong`,
  `entitlements.has_strong_everyday_model`, one switch per plan in `core/settings/plans.py`); it
  keeps photo turns too. Hard and maths turns keep their lanes on every plan. No OpenRouter-auto
  “Max” chip.
- ✅ **Manual switching** — model selection lives in Settings → Models (settings-only by
  design; the composer picker was removed to keep the composer single-purpose). Respected
  per chat turn. With Auto off, every message goes to one model: the screen names it
  ("Messages use") and lets the user pick it among the models switched on.
- ✅ **Chat settings from natural language** — small allowlist, confirm-then-write
  (the same card a reminder change gets): model (Flash / Pro / Auto, nicknames like “GPT” → GPT-6 Luna),
  tone (funny / professional / casual / soft), app language, and appearance
  (light / dark / system — applied on-device). Respects `enabled_models` + plan.
  No open settings tool.
- ✅ **Auto routing** — an **Auto** option (Settings → Models) picks Flash vs Pro per message via a
  fast heuristic (length, code fences, reasoning keywords). Explicit chat tutoring and substantive
  learning roadmaps use the low-latency fast lane (Qwen3.7 Flash) with strict step/day and tagged-example
  contracts; hard reasoning remains on Pro. Short follow-ups of a hard turn inherit that turn’s tier;
  a new topic drops back to Flash. No extra LLM call.
- ✅ **Multi-provider** — a **model catalog** (`models/model_catalog.py`) defines provider, model,
  key, base URL, and pricing per entry. All chat aliases route through **OpenRouter** via LiteLLM
  (`gateways/litellm_gateway.py`). Adding a model is a catalog entry + OpenRouter slug.
- ✅ **Model availability** — `GET /models` reports each model's availability (key present)
  and price; Settings → Models lists the available models (it shows no prices).
- ✅ **Live latency/health** — a breaker per provider model (aliases on one model share it)
  over Redis rolling samples: every model a turn tried leaves one, blamed on the model that
  failed (partway through a reply too), with how fast its provider started. Timeouts, 5xx,
  rate limits, dropped connections, empty replies and first-reply caps count; a request the
  provider refused (4xx) does not. All models, the photo lanes included, are read in one
  round trip per turn. An open model is skipped by Auto, fallbacks and the photo lane; after
  a 30 s cool-down a turn about to try it claims its one probe first, so only a turn that
  tries it uses the probe up. `GET /models` exposes `healthy`, `latency_p50_ms`, and sample
  count. Settings shows degraded on the model list; detailed timing remains available
  through the API.
- ✅ **Fast failover** — a model that shows nothing gives way to the next in its chain after
  3 s on the everyday lane, 4 s for a model that always thinks, or 8 s on a paid reasoning
  lane; its first text or reasoning ends the wait, and the idle and wall-clock caps still
  bound the rest. Prompts past ~24k characters get a second more per 40k; a request with an
  image, and the last model in the chain, get no cap. Never once text or thinking has
  reached the phone.
- 🔜 **User-tunable routing rules** (custom per-message heuristics beyond Auto + enabled set).

## 6. Memory (remembering the user)
- ✅ **Automatic extraction** — every substantive user turn by default
  (`memory_extract_every_n_turns=1`; always on turn 1). Only unmistakable greetings and
  acknowledgements skip the memory model; natural self-descriptions and durable reply-style
  corrections are evaluated without requiring phrases such as “I am” or “remember.” Ops can
  raise N to skip intermediate LLM cost. Each pass includes
  user messages not processed by the previous pass (per-chat extract cursor), so a fact
  on turn 2 is not dropped if the chat ends there. Explicit “remember this” / “forget that”,
  a mute ("stop mentioning my job") and a correction ("that's wrong, I'm at Stripe now")
  still extract when N>1. No remember/forget chip or confirmation sheet.
- ✅ **Forget, mute, reset** (`modules/memory/commands.py`) — "forget that I use React"
  deletes the fact the phrase names, never a broader one sharing a word ("builds Recall with
  React Native") or someone else's ("my sister lives in Nairobi"). "Stop mentioning my job" /
  "don't bring up my divorce again" **mutes** the fact (kept, never injected, its past-chat
  snippets dropped); a do-not-mention preference is kept even when sensitive. "Forget
  everything you know about me" and "stop remembering things about me" get a one-line reply
  pointing to Settings → Memory: chat changes no setting but the theme. Explicit facts and hand edits are
  never evicted by the 150 cap. Sweep look-alikes: `sweep_corpus/memory_controls.json`.
- ✅ **Extraction hygiene** — only what the user's own lines state or clearly show (the
  projects they build, the stack they build with, their job, goals, routines, recurring
  interests); never assistant restatements. Transcript is the **user line only**, capped ~4k
  (head+tail); attachment OCR / untrusted blocks stripped before extract; memory wrapped as
  first-party notes (fence kept); account email injected only for email/draft/inbox intents.
- ✅ **Extraction reliability (2026-09)** — name, job, employer, school, city, home country and
  languages are `normal` sensitivity (the `identity` label means gender identity, immigration
  status or disability), and a dating-app project is not a relationship fact. A failed model
  pass keeps the chat's extract cursor and retries on the next turn (3 tries, then moves on);
  a small-talk-only batch moves the cursor so it cannot hide later lines; failures log
  `memory_extract_model_failed`.
- ✅ **Memory documents (Claude-style)** — each fact has a `topic` that files it into a page:
  **You** (Profile, Preferences), **Topics** (Interests, Tech stack, Schedule, Recent work,
  Goals, Side projects, Other) and **Areas** — one page per major project or part of life
  (`area:<slug>`, title and one-line summary in `memory_areas`, named by the model). Facts
  stay atomic rows; `type` follows the topic and still drives prompt priority.
- ✅ **Reads your recent chats once** — the first time the Memory screen opens, a
  `memory_history_scan` job reads the user lines of the 20 most recent non-quiz chats and
  records `users.memory_history_scanned_at`; the screen shows "Reading your recent chats…"
  until it finishes. Chats are read newest first and a pass only adds facts memory is
  missing, so an old line never overrules a newer fact. Lines written before the user's last
  hand edit (`users.memory_edited_at`: a delete, edit, mute, clear, or a "forget …" or
  plain-words edit that changed saved facts) are skipped, so a deleted fact cannot come back.
  A chat the model or database could not read is retried on a later pass (30 minutes apart,
  3 passes at most); the chats already read are skipped.
- ✅ **Plain-words edits** — a box under the pages ("You can disagree with me more", "Keep
  lists under five things") calls `POST /memories/instruct`; the model turns it into fact
  edits (saved like "remember this") and replies in a sentence. 30 edits per hour per user.
- ✅ **Typed memories** — `profile` · `preference` · `project` · `fact` · `focus` (grouping
  categories, not a 20-type taxonomy). Each row is one atomic fact (the old one-paragraph-per-type
  unique constraint is gone). Cap **150 active** facts per user.
- ✅ **Quality controls** — confidence threshold, de-duplication / pair-merge (newer fact
  wins), score-and-pack packing (never mid-fact prefix cut), identity core (the name and reply
  preferences). An add matches by exact text only.
- ✅ **Prompt injection** — identity core always; remaining facts packed by cosine + importance +
  recency until `memory_inject_max_chars` (1500). Similarity bar stays `memory_min_similarity`
  (0.35); a fact with no vector needs a word in common with the question. Scopes
  (`get_memory_block(scope=…)`): by query; with the profile page (career, "what's my job?");
  everything ("what do you know about me"); **work** (programming and "my app / my backend"
  turns: the tech-stack page and what the user builds, no query embed). An embed timeout
  injects the identity core plus word matches, uncached, and warms the key the turn read.
  Each fact line carries "(said YYYY-MM)" and "unconfirmed" under 0.6 confidence. A failed
  read is reported (`MemoryLoadReport`), never cached, and the reply says memory couldn't
  load instead of "I don't have that saved"; memory off / saving paused / no earlier chat
  found each get one line on the turns they bear on (`modules/chat/prompt_memory.py`). Health / legal / finance / relationship stay **stripped on casual turns** (stored
  `sensitivity` first, regex defense-in-depth) and inject only when the ask is in-domain.
  Life-domain advice ("what should I eat", "I need dinner", "plan a workout")
  injects **memory only**. Ordinary need/plan phrasing
  counts, not just "recommend" / "what should I".
- ✅ **Semantic recall** — when `semantic_memory_enabled` (default on), the user's latest message
  is embedded and the top matching memories are selected (cosine similarity on stored embeddings;
  falls back to scored packing when embeddings are missing).
- ✅ **Memory screen** — `GET /memories/documents`: You / Topics / Areas rows with a summary
  and the last-updated date. A page shows its title, last updated, summary and each fact as a
  bullet with the chat it came from; tap a fact to edit, mute / unmute or delete it (a muted
  fact reads "Muted · not used in chats"), **Delete** removes the page
  (`DELETE /memories/documents/{topic}`). `PATCH /memories/{id}` updates text or status;
  `DELETE /memories/{id}` deletes one fact with the versions it superseded; `DELETE /memories`
  clears all. A delete, clear or mute also purges the past-chat snippets that repeat it, so
  chat-history recall cannot bring a deleted fact back.
- ✅ **Memory toggle** — off means no personal recall: no new learning, no saved facts in
  replies, no chat-history retrieval or indexing, no instant profile answers (saved facts
  remain until deleted). Opt-in **include sensitive topics**. **Delete and turn off** is one
  API.
- 🔜 **Temporary Chat** — a thread that does not extract or inject long-term memory. Deferred;
  do not implement until this line is promoted.
- ✅ **Memory management reliability** — account and navigation
  changes invalidate old dialogs, reads, and feedback; independent section edits compose,
  and pending writes remain exclusive across screen visits. Failed refreshes retain saved
  rows with Retry. Manual changes clear stale embeddings and invalidate derived caches;
  delayed background writes cannot overwrite changed/deleted sections and recheck the
  learning toggle before saving.
- ✅ **Structured profile fields** — name, age, country, and job are discrete account fields
  (editable in Settings → Profile) and injected into the chat system profile block.
- ✅ **Attachment RAG** — chunk + embed PDF/doc text into pgvector; retrieve top chunks
  into the system prompt on **later turns in the same chat** (`chat_id` on chunks — **not**
  a user-wide file library). Prepare uses the **text layer only**; scanned-PDF vision OCR
  runs on the **index job**, not the pre-stream path. First turn uses the inline
  text-layer excerpt. File chip shows “still indexing” until chunks exist; inject
  includes filename (and `[page n]` when known). Invalidated on attachment delete. Flag: `attachment_rag_enabled`
  (default on).
  Reusing a retained Library file in another chat schedules a separate index job;
  late jobs recheck ownership, verification, and the current chat before replacing chunks.
- ✅ **Chat-history semantic RAG** — background `message_index` embeds past turns into
  `message_chunks` (pgvector). Turn start retrieves a small top-k, excluding the recent
  window. Golden Rule 3 still holds — never the full transcript. First index also
  backfills the user's recent 40 messages so older chats are searchable after one turn.

## 7. Context management & performance
- ✅ **Token-budget window** — recent turns are kept verbatim up to a token budget
  (`context_token_budget`, with a hard message cap), never the whole transcript.
- ✅ **History compression** — turns that fall outside the token budget are folded into a rolling
  per-chat **summary** (batched, runs on the durable job queue), so long chats keep context
  without bloating the prompt.
- ✅ **Memory caching** — the assembled memory block is cached in Redis per user (with
  invalidation on new/deleted memories) instead of rebuilt every turn.
- ✅ **Provider context caching** — OpenRouter/provider prompt-prefix caching when the upstream
  model supports it (transparent to the app).
- ✅ **Snappy delivery** — async backend, streaming, virtualized message list; DB connection is
  released during the model stream.
- ✅ **Parallelized pre-stream reads** — memory, todos, recent titles, and attachment
  RAG gather on separate short-lived sessions so the prompt path stays concurrent without
  sharing one `AsyncSession`.
- ✅ **Slim casual turns** — coaching / chit-chat uses a compact format + math-safety hint (not
  the full visualization/math-solver pack), keeps bounded personal memory and semantic history
  available for continuity, and skips web/math/chem prefetch unless the turn is rich or actually
  needs search, math or chemistry. Exact greetings and
  acknowledgements stay on the zero-retrieval fast path; “good morning!” or “how are you?”
  (an opener that asks for nothing) gets the compact format and no photo offer, while
  “good morning, what's the capital of Peru?” is answered in full.
- ✅ **Prompt token budgeting UI** — Settings → Account → Usage shows how much of
  today's limit is left. The composer
  shows a local draft estimate when the text is large enough to matter.
- 🔜 Response caching.

## 8. Titles / topics
- ✅ **Auto title** — a concise title is generated after the first exchange (cheap model).
- ✅ **Backfill** — missing titles are generated when a chat is opened.
- ✅ **Manual rename** — overrides the generated title.

## 9. Quotas & usage
- ✅ **Daily token limit** — enforced in Redis with atomic **reserve → adjust → refund** (can't be
  bypassed by parallel requests). Free **100k**/day; Plus and Pro **500k**/day
  (`DAILY_TOKEN_LIMIT` / `_PLUS` / `_PRO`).
- ✅ **Plan-aware enforcement** — every cap reads the plan through
  `modules/billing/entitlements.py` (`allowance`, `can_use`); each number is a
  `core/config.py` setting with `_plus` / `_pro` variants.
- ✅ **Usage meter** — the share of today's limit left, as the Usage row's value in Settings → Account.
- ✅ **Real token accounting** — uses the provider's reported usage when available.
- ✅ **Paid plans** — higher daily limits when entitled; see [§12 Monetization](#12-monetization).

## 10. Settings & profile
- ✅ **Account settings** — the avatar at the top of Settings opens **Profile**: a centered
  avatar with a pencil badge opens the name and photo editor (a camera badge picks and
  previews a photo; Save profile persists both). Profile also holds age / country / job and
  use current location. There is no username. Settings → Account shows the email (with how
  you sign in under it), the plan (free opens the upgrade sheet, which also restores a
  purchase; Pro manages the subscription in the store) and today's usage. Persisted on
  `users` and injected into the chat system prompt (see [§6](#6-memory-remembering-the-user)).
- ✅ **Settings chrome** — Account / Experience / Assistant / Notifications & Connected apps /
  Data & privacy / Help & about / Sign out. Every page builds from one kit in
  `features/account/components/settingsUi.tsx` (`SettingsPage`, `SettingsGroup`, link /
  value / switch / menu rows, `useSettingsAction` for confirm + busy + error) over the
  app's `ListRow` / `ListGroup`. Rows that open a page show a chevron. Groups carry
  sentence-case headings; current values sit beneath row titles; overview explanations
  stay in accessibility hints. Nested screens omit row icons except connected-app marks.
  Choice rows (appearance, accent, language, style, tone, voice, speed, reminder lead)
  open a floating popup — they do **not** expand inside the gray card.
- ✅ **Experience** — Appearance (System / Light / Dark), Accent color, Language and
  Haptics, all on the Settings page itself. Appearance, accent and haptics are saved on
  the device; Haptics off silences every `lib/haptics` call.
- ✅ **Personalization** — tone labels, emoji and custom instructions. Stored tone ids stay
  `soft` / `casual` / `professional` / `funny`. Emoji (`users.emoji_use`: `off` /
  `some` / `more`, every account starts at `some`) is the one emoji rule in the prompt
  (`modules/chat/response_tone.emoji_hint`): a few lead headings and list labels, never in
  numbers, maths, code, cards, a worked solution, a draft or a painful reply; no tone
  speaks about emoji. The finalize pass `emoji_use` (`modules/chat/emoji_placement.py`)
  keeps it whatever the model wrote: at A few an emoji moves to the front of its label
  and any in a sentence goes; at None they all go unless the user wrote one. There is no response-length setting:
  each message sets its own ("briefly", "in detail"), and how hard a turn thinks is
  automatic (`modules/chat/model_routing/thinking.py`). The old `users.response_style` column is
  neither read nor returned, and goes in a later release (docs/ROLLBACK.md).
- ✅ **Voice** — the voice (`users.tts_voice`, one of the voices both read-aloud and live
  talk speak; Default keeps the server's), read-aloud speed (0.75×–1.5×, on the device,
  pitch kept) and Use on-device voice (offline device speech instead of cloud read-aloud).
- ✅ **Memory** — on/off, Manage saved memories, clear all (`DELETE /memories`).
- ✅ **Notifications** — push (On only if pref and OS permission) with its own switch per
  kind under it, today to-do reminders
  (`users.push_*_enabled`; the scheduler skips a kind that is off, and to-do reminders
  off also stops the on-device ones). Reminder lead, email reminders, quiet hours.
- ✅ **Models** — Auto and model toggles. Developer diagnostics are omitted from this screen.
- ✅ **Data controls** — archived chats, archive all, delete all chats (Library stays),
  export, delete account.
- ✅ **Security** — session list + revoke + sign out of all devices. Removing a device stops its
  access token at once (the session id is revoked), not when the token expires. No MFA.
- ✅ **Help & about** — Contact support (only when `EXPO_PUBLIC_SUPPORT_EMAIL` is set),
  Report a problem / Send feedback via the OS share sheet (version, plan, locale),
  Privacy, Terms, Open-source licenses (`lib/licenses.generated.json`, rebuilt by
  `pnpm oss-licenses`; a test fails when it is stale) and the version. No fake Help Center URL.
- ✅ **Sidebar controls** — search uses a translucent white surface and border; the
  user's profile photo or initials open Settings beside New chat.
- ✅ **Sign out** — asks first.
- ✅ **Data export** — exports profile and settings, chats and their messages, every memory row
  and memory area, todos, attachments, suggestions, daily usage, push devices (no token) and
  product events as JSON via the native share sheet (`GET /auth/me/export`). Shows a progress
  screen while the archive builds.
- ✅ **Account deletion** — permanently deletes the account and all its data (`DELETE /auth/me`),
  then signs out: rows, stored files, and (in the worker's `storage_sweep`) every Redis key
  that names the user.
- ✅ **Language / i18n** — `react-i18next` with English, Spanish, French, Amharic, German, Italian, Portuguese, Russian, and Turkish.
- ✅ **Dark / light theme** — screens use `useTheme()` with system or manual appearance in
  Settings → Appearance.
- ✅ **Local todo reminders** — on a device the server holds no push token for, on-device
  notifications (via `expo-notifications`; requires a dev build for full native support),
  scheduled exactly at each to-do's `notify_at`, and written again when the app's language, the
  phone's 12/24-hour clock or its zone changes. Never both: a device with a token gets push only.
- ✅ **Remote push (MVP)** — Expo push tokens registered with the backend; todo-due
  notifications (requires dev build + EAS project ID). One instant for every channel: the server
  works out when a reminder goes out (`services/reminder_timing.reminder_at`: the user's lead time,
  when due if its due time was set inside that window (`todo_items.due_set_at`, which no other
  edit moves), moved to the end of quiet hours on the user's clock) and sends it on every to-do it
  returns as `notify_at`; push and email send at it, and a late cycle still waits out quiet hours.
  The clock is the phone's: it reports its zone the moment it changes (the OS's clock event, each
  return to the foreground). The badge, Home and the editor's Remind at show `notify_at`; for a
  due time the editor has not saved, it asks `GET /todos/reminder-preview`. The phone works out none.
- ✅ **Email reminders** — opt-in todo-due emails (Resend); Settings
  toggle; worker scheduler only (welcome + Pro receipt unchanged).

## 11. Navigation & UX
- ✅ **Drawer** — custom slide-in: search, New chat, chat history, profile + settings.
  A cold start shows the chats the account had last time while the list is read again.
- ✅ **Opening a chat** — the last page shows at once (kept after every finished turn) and Send
  works on it: a message sent before the server's page lands shows at once and goes out once
  that page is in (at most 4 s later), so it shows once, below the page. Stopped or left before
  then, it goes back to the composer unsent (New Chat's if the chat was deleted elsewhere). A page
  that lands after the 4 s is merged once nothing of the message that went first is left on screen
  (it was refused), else the chat is read again when that turn is over. A chat reopened within
  20 s of this phone keeping its page is not read again, unless the app went to the background
  since or the drawer's last read of the chat list (once per session, or on pull to refresh) shows
  the chat changed; rows the server's page left unchanged are not redrawn.
- ✅ **Chat screen** — single-purpose composer, top-right `＋` (new) and `⋯` (Share / Rename /
  Pin / Delete).
- ✅ **States** — login, loading, empty chat ("How can I help?"), empty memory, drawer offline/retry.
- ✅ **Onboarding** — a first-run welcome screen (value props + "Get started"), shown once before
  the first sign-in.
- ✅ **AI data consent** — agreed by signing in: the sign-in page says under its buttons "By
  continuing, you agree to the Terms and Privacy Policy, and that your chats and voice are
  processed by third-party AI providers." beside the Terms and Privacy links, and every
  Google, Apple and dev sign-in sends `ai_data_consent: true`, so the server stores
  `users.ai_data_consent_at` with the sign-in and a new account opens the chat. An account
  without it (from before this, withdrawn, or signed in by a client that sends no flag)
  sees once what goes to which outside service (AI models via OpenRouter, OpenAI voice,
  Mathpix math photos, Tavily search, optional location) with a privacy-policy link; Agree
  stores it (`PATCH /auth/me` `ai_data_consent`), Not now signs out to the sign-in page.
  Every signed-in screen waits on it (the root layout's
  `features/auth/components/AiConsentRedirect.tsx` sends it to `app/consent.tsx`); the web
  client keeps its own consent screen after sign-in. The server holds the same line (`core/consent.py`): a
  chat turn (WebSocket and SSE), speech (transcribe, read aloud, a live talk key or tool) and a
  scan read-back are refused with `consent_required` (an error frame with
  `user_message_saved: false`, or HTTP 403) until the account agrees, and the phone answers it
  with the consent screen (any feature hands it on with `notifyConsentRequired()`,
  `lib/api/consentRefusal.ts`). Settings → Data controls shows when the account agreed and
  can withdraw it, which brings the consent screen back. Image generation, attachment uploads and
  memory instructions are not gated yet.
- ✅ **Polish** — light haptic taps on key actions (Android via the built-in API) + chip fade-in
  animation.
- ✅ **iOS haptics** — `expo-haptics` on real devices (graceful no-op on Android / Expo Go).
- ✅ **Screen transitions** — shared stack presets: iOS-native push + back gestures on nested
  stacks, fade for auth/onboarding, fade-from-bottom for drawer utility screens (memory, todos).
- ✅ **Shared Button / type / space / motion tokens** — primary CTAs via `components/Button`;
  `lib/type.ts`, `lib/space.ts`, `lib/motion.ts` for high-traffic roles (incremental migration).
- ✅ **Full typography/spacing ownership on screens** — `app/*` screens and settings
  chrome use `Type` / `Space` for body, caption, label, title, and display roles.
  Compact chip/pill controls stay specialized (not the shared Button). Login
  wordmark and 11px stat chips keep their one-off sizes.

**UX decisions from the 2026-09 frontend audit (do not relitigate):**
- Model selection is **settings-only** (Settings → Models); no composer model picker.
- User-message copy stays **long-press only** (with a "Long press to copy"
  accessibility hint); no visible copy button on user bubbles.
- Onboarding keeps a single CTA.
- Schedule secondary meta uses the shared `Type.caption` token — no new
  pill component.

## 12. Monetization
- ✅ **Three plans** — `users.plan` is `free` | `plus` | `pro` (display names "Plus" / "Pro"
  live in i18n only, `plans.*`). Free: every model in the free pool, 3 AI images a day, no
  voice input, no natural read-aloud, no live talk. Plus: every model, Pro-size daily limits,
  voice input and read-aloud, 10 images a day, no live talk. Pro: everything in Plus, 15
  images a day and 60 live talk minutes a month. Prices live in the stores; the app shows
  the offering's localized price. One place decides: `modules/billing/entitlements.py`.
- ✅ **Subscriptions (RevenueCat)** — mobile purchase flow via lazy-loaded `react-native-purchases`
  (dev/production builds only; skipped in Expo Go). Two entitlements (`plus`, `pro`; `pro`
  keeps the single-plan id so earlier subscribers stay on the top plan), offering packages
  `plus_monthly` / `pro_monthly`. Plus → Pro on Android replaces the Plus subscription
  (prorated); on iOS both share one subscription group. Restore purchases supported.
  RevenueCat is configured once per signed-in user (an account switch is a `logIn`).
- ✅ **Backend entitlement** — every event that can change access re-reads the subscriber
  over REST (EXPIRATION, refunds, TEMPORARY_ENTITLEMENT_GRANT, REFUND_REVERSED included); a
  TRANSFER moves the plan to `transferred_to` and drops it from `transferred_from`;
  BILLING_ISSUE, SUBSCRIPTION_PAUSED and auto-renew-off CANCELLATION keep access until
  EXPIRATION. Redis `SET NX` claim; missing `event_id` hashes the canonical payload;
  done-marker after success. `POST /auth/me/sync-subscription`; an hourly reconcile re-checks
  every paid row. `GET /billing/plans` gives the paywall each plan's features and numbers.
- ✅ **Plans sheet** — free sees Plus and Pro side by side; Plus sees the step up to Pro; a
  purchase whose server refresh fails says the plan will update (never "purchase failed").
  Settings → Account shows the plan, live talk minutes left (Pro) and "Upgrade to Pro" (Plus).
- ✅ **Dev plan toggle** — the plans sheet shows **Enable Plus / Enable Pro (dev only)**
  (development builds only; `POST /auth/me/pro-dev?plan=`).
- 🔜 App Store / Play billing polish, promotional offers, family plans.

## 13. Platform, security & infrastructure
- ✅ **Backend** — FastAPI (async), WebSocket streaming, layered (routers → services →
  gateways/repositories).
- ✅ **Data** — Neon Postgres via SQLAlchemy + Alembic migrations; Upstash Redis for quota/cache.
- ✅ **Model gateway** — LiteLLM with product aliases mapped to providers; mock mode runs the whole
  app with no API keys.
- ✅ **Security** — Google ID-token verification (incl. `email_verified`), rate limiting on
  auth + WebSocket, production config guards (no dev auth / mock / weak secret in prod),
  locked-down CORS.
- ✅ **Ops** — `/health` liveness + `/health/ready` (Postgres; Redis reported as
  `ok`/`degraded` without draining the fleet) + `/health/dependencies` (503 when
  Postgres or Redis is down, kept 5 s per process; the phone's connection check),
  graceful shutdown, DB connection pooling.
- ✅ **Quality** — CI (Postgres + Redis services, ruff, mypy, pytest with coverage gate).
- ✅ **Background jobs** — title / memory / compression are enqueued to a **durable Redis Stream**
  and processed by an in-process worker (consumer group). Jobs survive process restarts, and an
  entry left unacked by a crash is reclaimed on the next startup (at-least-once).
- ✅ **Dedicated worker process** — Fly `app` (`PROCESS_ROLE=api`) + `worker` (`python -m
  app.worker_main`); local/dev default `process_role=all` keeps a single process. Scale with
  `fly scale count app=1 worker=1`. Multi-instance worker fleets remain a later ops concern.
- ✅ **Sentry** — optional DSN init on API + mobile (no-op when unset).
- ✅ **Sentry / request logs** — `before_send` drops `WebSocketDisconnect` /
  `ClientDisconnect`, strips request bodies and auth headers, tags `request_id`.
  One structured access line per HTTP request (`event=http_request`; JSON in
  production). Health probes and CORS preflight are skipped. No bodies or query
  strings.

## 14. Schedule & suggestions
- ❌ **Lists** — removed. No shopping/packing checklists in the drawer or chat. Do not
  reintroduce a Lists row, list composer, or undated checklist UI.
- ✅ **Schedule** — dated items (formerly Reminders) with optional repeat
  (`daily` / `weekdays` / `weekly` / `monthly`). New reminder Repeat is a single
  dropdown (not wrapping chips). Repeats fire a **device push** only
  (notification bar), not email. After a successful server todo push, a recurring
  item advances `due_at` and clears `notification_sent_at` so the next occurrence
  can fire. Chat can set `repeat` on the ` ```reminder `
  fence (create, complete, uncheck, delete, set_due). After the fence applies, the
  reply appends the saved result (`Set: Call Mom — Friday, Jul 19, 3:00 PM · weekly.`)
  or a failure line — it does not promise a change that has not happened. A clear
  “mark done”, “reopen”, “delete”, or “move … to Monday at 8pm” is applied from
  those words when the fence is missing or mislabeled, and that turn does not
  run the background extractor again. “Make it everyday”, “make it 8:00 AM”,
  and “put it in Health” change that reminder’s repeat, clock, or category.
  “It” means the latest one. Asking what is scheduled answers from the saved
  rows. A create with no clock asks when instead of inventing one. A reply
  that is only a clock (“6”) finishes that reminder on the day already named,
  and a time that has already passed is not saved. A success sentence is kept
  only when that row actually changed. Route
  `focus=reminders` still works; `focus=schedule` is an alias.
  `/todos?focus=list` redirects to Schedule.
- ✅ **Schedule reliability** — normal reminder saves use the
  accepted API payload; failed saves preserve drafts. Account/focus guards, coordinated
  list reads and row mutations, Android date-then-time selection, serialized local
  notifications, and conditional server recurrence/delivery writes protect reminder state.
  Opening Schedule lands on overdue and today. All tasks stays in the menu.
  Schedule loads through immutable-ID cursor pages so edits between pages cannot hide
  existing reminders. Recurring reminders are excluded from email; one-shot email
  finalization cannot mark a concurrently edited occurrence as delivered.
- ✅ **Todos API** — create, check off, delete dated reminders; `due_at` is required
  on create and cannot be cleared on update. Recurring without a due date stays invalid.
  Chat extract skips undated adds.
- ✅ **Reminder cards** — a to-do change from chat is a card the user taps: **Save reminder**,
  **Mark done**, **Move**, **Delete** (` ```reminder_proposal `; always, and no background job
  writes a reminder from a reply). The reminder rules run unchanged inside `todos/write_log.recording()`, where the
  repository plans its writes instead of making them; `todos/proposals.py` keeps them in Redis
  for a day. `POST /todos/proposals/{id}/confirm` makes them once (a second tap answers the
  same), refuses a one-off time that has passed or a row deleted since, and marks the card
  `"status": "saved"` in the chat so it reads Saved after a reload.
- ✅ **Chat changes to-dos in English; other languages read them** — the server checks a
  chat to-do change against the user's own words (the time they said, "mark it done"),
  and that reading is English. A message in another app language reads its to-dos in chat
  ("¿qué tengo hoy?" loads the list) but adds or changes them in To-do: the reply says so in
  one line and ends on an **Open To-do** button (` ```todo_link `). A ` ```reminder ` the
  model writes anyway becomes the button, never the English "When should I remind you?";
  a reply with no line of its own gets one from the server, in that language. The
  language is read from the message (`todos/chat_language.py`): another script, or two
  words only Spanish, French, German, Italian, Portuguese or Turkish use; any English to-do
  word keeps a mixed message English. A message with no language of its own ("a las 5",
  "17:00", "sí") follows the user's previous message, then their app language, so the
  answer to a question asked in Spanish never writes either. Live talk follows the same
  rule: speech in another language never saves a reminder.
- ✅ **LLM todo sync** — ` ```reminder ` fences and the spoken rules become reminder cards
  (above); with cards off they apply on persist (create + mutations), and a background job
  recovers missed writes from chat (dated items only). The job is off while cards are on,
  since it would write without one. Injects
  Schedule + overdue summary into the system prompt. “What time is my flight / meeting /
  …” loads Schedule on the first turn. Typed “remind me …” also classifies
  as a Schedule turn. Live Talk injects a compact Schedule snapshot and applies the same
  clocked “remind me … today/tomorrow at …” persist heuristic (no invented times; tools
  stay read-only).
- ✅ **Due dates** — `due_at` on items; mobile date/time picker on Reminders; relative
  labels in prompts (overdue, due today, due in N days); user timezone synced from
  device (`users.timezone`).
- ✅ **Local due reminders** — schedules a device notification at due time **when
  push is off**; resyncs on login, foreground, and todo changes; tap opens **that
  reminder** on Schedule. Lead time configurable (5 / 10 / 15 / 30 / **60 min**
  before due). With push on, the server owns due-at (`server_todo_push_enabled` defaults
  true) and local scheduling is skipped so both do not fire. Turning push off cancels
  leftover local alerts then re-schedules them on-device.
- ✅ **Follow-up questions** — up to three short questions (one line each, about 3–9 words) under the latest reply, about what the user just asked: a why, a what-if and a next step for a maths, physics, chemistry or biology problem, and the next things a person would ask for any other real question with a full answer. Small talk, drafts, personal updates, reminders and settings get none. One `memory-model` call per eligible turn after `done` (`modules/chat/related_prompts.py`), cached per message for reopen; rows in `features/suggestions/components/RelatedPromptLines.tsx`. The old proactive chips built from other chats are gone from the app, and the `suggestions` job, its generator and the `/suggestions` routes are removed; stored rows stay in the data export until a later release drops the table.
- 🔜 1-hour-early **email/push** nudges beyond the local lead picker.

## 15. Code execution policy
- ⚠️ **Sandboxed HTML/CSS/JS preview only** — `html` fences can be previewed/run in an isolated
  WebView (no app token is exposed to it), and charts render via a sandboxed Vega WebView.
  HTML Run CSP allowlists known CDNs (jsDelivr, unpkg, cdnjs, Google Fonts); it does not allow
  arbitrary `https:` script/`fetch`.
- 🔒 **No other code execution** — all other code (Python, shell, etc.) is rendered/highlighted
  only, and nothing runs outside the sandboxed preview WebView. (By design.)

## 16. Model tools

**Google Calendar and Gmail are removed.** Recall does not connect to a calendar or an email
inbox: To-do holds the user's own tasks and reminders, and the prompt tells the model to say so
plainly rather than suggest connecting an account. Migration `0106_drop_google_integrations`
drops `user_calendar_connections`, `user_gmail_connections` and `suggested_reminders`, the two
push switches for email suggestions and calendar meetings, and the `gmail` to-do source. It
deletes stored Google refresh tokens without revoking them at Google (a migration makes no
network calls). The legacy pre-stream tool round (`mcp_tools_enabled`, `chat/tools.py`) went
with them; it only ever carried the calendar hint. Sign-in with Google is unchanged and needs
only `GOOGLE_CLIENT_ID`.

- ✅ **MCP gateway** — `gateways/mcp/` with registry + module-owned adapters (`web_search`,
  `sympy`, `generate_image`, `search_image`). Tools are owned by Recall; arbitrary user MCP
  servers stay out of scope.
- ✅ **Full tool-calling loop** — **on by default**, but **not on every turn.**
  Ordinary chat streams immediately. Pre-stream `complete_with_tools` runs only
  when the turn still looks like web search (the deterministic search gate),
  unsolved math, or image gen. If that round
  finishes without tools, the text is shown — the stream does not call the model
  a second time. Pydantic-validated args, bounded by `mcp_tool_loop_max_rounds`.
  Heuristic SymPy still runs before the stream so homework does not wait on a tool
  call; web search is the loop's (with the loop off, nothing searches).
- ✅ **Golden rules preserved** — product aliases in services; structured outputs validated with
  Pydantic before DB writes.

---

## 17. Language learning (removed)

The dedicated language-learning product (vocabulary classes, lesson maps, SM-2 practice, `/projects`, and the Learning drawer) has been removed. Chat still teaches math, physics, chemistry, and programming, including “teach me…” lessons and multi-day study roadmaps. Those stay in ordinary chat. There is no Learning screen, API or table; a lesson chat keeps only one ordinary memory line (`lesson_progress`).

## 18. Money (loans, cards, savings)

- "What is my mortgage for 300k at 1%?", a car payment, a card payoff, a savings goal: the server reads the numbers, works them from the catalog's formulas (`modules/money/`) and the model writes the words around them.
- A new term or rate right after a money reply ("what if i only do 3 years instead", "what about 6.5%?") is the last request with that change, worked by the server with a new card; any other what-if (a new price, a down payment, a payment) and a what-if about something else ("3 sets instead" after a workout) are the model's, as before.
- Today's average rate comes from one web search read into a checked structured answer (plausible for the product, recent, from a page the search returned), cached per product (a used car apart from a new one), term and country. The server's note compares the user's rate with it ("1% is not a realistic 30-year fixed mortgage rate…"), with its date and a source link; no checked average, no note.
- A `calculator` card under the reply has sliders for the inputs and live readouts; the phone evaluates the server's formula tree and never solves. Design and contract: `docs/money.md`.

## Deferred to upcoming version(s)
A consolidated list of what's intentionally **not** (or only partially) in this version.

- 🔜 **Verified biology** — not in this version. A photographed biology crop can still be sent as a picture. When a verified biology subject is added, it is its own module on `services/law_binding`, the way chemistry is. It is not more physics, and the subject chain stays the hardcoded math, physics, and chemistry order until that module exists.
- ✅ **Symbolic physics models** — a stated equation can be checked. A school question is still a catalog binding of the words the student used. New coverage grows that way, one law at a time.

### Already shipped (keep for audit trail)
- ✅ **Full MCP / multi-turn tool loop** — LiteLLM `tools=` rounds; `MCP_TOOL_LOOP_ENABLED`
  defaults **on**. Heuristic math/search still run. See [§16](#16-model-tools).
- ✅ **Attachment RAG** — pgvector chunk + embed over uploaded PDF/docs **in that chat**
  (`chat_id`); top-k into later turns. **Not** a per-user file library across chats.
  Text-layer extract on prepare; vision OCR on the index job only. File chip shows
  indexing until chunks exist; wrapped inject includes filename.
- ✅ **Camera math solver** — attach sheet “Solve math with camera” → VisionCamera live frame + adjustable crop + torch / pinch-zoom / photos. On-device ML Kit text recognition runs only inside the live crop and marks the frame ready after repeated stable reads; live frames never hit a paid OCR endpoint. Camera shots are cropped from the live frame immediately (no second crop/Solve step); imported photos retain the adjustable still-image crop. Math then shows **I read this as** (`POST /math/scan/read`: Mathpix, then `vision-chat`, no solve). The student edits the reading if needed and taps **Solve**, which sends it as text through the full math pipeline, or **Send photo**, which sends the crop at once with the checked reading so the turn does not read it again. Physics and chemistry read back the same way through their own readers (`POST /physics/scan/read`, `POST /chemistry/scan/read`: `vision-chat` plain text, no Mathpix kinds); physics turns OCR LaTeX into typed text (`2 × 10^-6 C`, `30°`), and **Solve** sends that text alone, so a photographed physics problem gets the same verified instant reply as a typed one. A physics photo sent with its reading is verified from that reading; one without gets the physics note, never math hints. The three readers share one guard (`services/scan_read.py`: payload limits, spend cap, per-user rate). A refused read (reader off, photo too large, rate limit, spend cap) names itself the same way for every subject (`features/scanner/model/scanReadError.ts`). Biology camera scans send the live crop directly. Mathpix runs only on the captured math crop when `MATHPIX_APP_ID`/`MATHPIX_APP_KEY` are set (`improve_mathpix=false`); SymPy verifies. Camera capture needs a **dev build**. Unverified fall-through is labeled (`Couldn't verify this with SymPy.`) only when the reply contains math.
- ✅ **Web search** — Tavily primary + DuckDuckGo fallback; sources on assistant messages
  (hidden on short A–D replies).
- ✅ **Structured profile fields** — name / age / country / job (Settings + prompt injection).
- ✅ **Vision + image gen** — image attachments route to vision models; a later
  plain-text follow-up in the same chat rehydrates the last image(s). If the file
  is gone, the model is told not to guess from a prior caption. Image generation
  from the composer on send (daily cap per plan; no separate prompt sheet).
- ✅ **Per-chat Redis prepare lock** — `chatprep:{chat_id}` around prepare + stream; concurrent
  turns get `ChatBusyError` / `code: "busy"` (#536).
- ✅ **Math display rendering** — display math renders as MathJax-SVG (`MathSvgView`;
  replaced the WebView host from #537). Wide formulas scroll horizontally inline.
- ✅ **Algebra `canonical_fence` / ` ```answer ` rewrite** — SymPy attaches canonical answer
  fences; post-stream `validate_math_fences` rewrites drifted finals (#538). Multi-root
  answers group ± reals and conjugates (`x^6 = 1` → three `aligned` lines, not six
  clipped commas).
- ✅ **Persist assistant reply on hard WS/SSE disconnect** — mid-stream `CancelledError` with
  tokens finalizes like soft stop (#539).
- ✅ **RevenueCat webhook atomic claim** — Redis `SET NX` claim before processing; done-marker
  after success (#535).

### Later / future (not the current coding backlog)
- 🔜 **Live voice accents** — design a dedicated live voice menu with accent choices.
  Deferred until a later UI pass; do not restore the old Device / Enhanced read-aloud menu.
- ✅ **Push-token re-bind hardening** — cross-user Expo token moves require a matching
  install `device_id` (stable id persisted on device; Expo removed `installationId`).
  Mismatched device → 403; successful rebinds log + Sentry breadcrumb. Residual risk:
  attacker with both the Expo token and the install id can still rebind; full device
  attestation remains deferred.
- ✅ **Message id time-ordering (uuid7)** — new `messages.id` values use UUID v7
  (`app.core.ids.uuid7`) so `(created_at, id)` cursors stay time-stable; existing
  uuid4 rows are unchanged.
- 🔜 **Full locale translation** — key-set parity is enforced (**960** keys); ~350 strings still
  English in non-en locales (Claude review wave 3 strings are keyed; prose translation deferred).
- ✅ **Full chat-history semantic RAG** — `message_chunks` + `message_index` job + top-k
  at turn start (excludes the recent window). Same shape as attachment RAG.
- ✅ **Scanned-PDF OCR** — text-layer `pypdf` on **prepare** (no vision). Empty PDFs
  render pages (`pypdfium2`) and transcribe via `vision-chat` on the **index job**,
  then the same excerpt + attachment RAG path. Inline OCR stays at 6 pages / 12k
  chars; index OCR uses 20 pages / 200k chars (`attachment_ocr_index_*`). Coverage is
  stored on the attachment and the RAG prefix uses those ceilings, not a static
  500/200k claim. Not a second extract pipeline.
- ✅ **Owned tool loop enabled** — `mcp_tool_loop_enabled` defaults true. Heuristic
  SymPy still runs. Web search is the tool loop (source chips + wrap; forced search if
  the model skips). See [§29](#29-next-actions-product-decisions).
- 🔜 **Plugins / arbitrary user MCP servers** — owned server-side tools only today.
  Google Docs + GitHub (and similar) are later owned integrations, not user-hosted MCP.
- 🔜 **Code execution** beyond sandboxed HTML/chart preview — later, not now. Keep the
  sandboxed WebView exception until then.
- 🔜 **Collaborative cursors / shared docs** — real-time co-editing; personal app only today.
- 🔜 **Web client** — slice 1 shipped (login + chat stream); see [Web client](#web-client-planned) below.
- 🔜 **RenderDocument v2** — versioned ordered block schema, same document live and on
  history reload. Not started; P0 kept `message.content` plus a trailing sources fence.
- ⚠️ **Web output parity** — GFM tables, named source links, and human fallbacks for
  JSON rich fences are in slice 1. KaTeX, Mermaid, Vega, and sandboxed HTML remain later.
- 🔜 **Claim-level citations** and attachment filename / page / chunk identity in the
  answer contract (today: one source list, RAG chunks without user-facing file metadata).
- 🔜 **Six visual families** — restyle existing rich cards onto one document / artifact /
  result / visual / evidence / action shell.
- ✅ **Hide raw reasoning** from the assistant answer — status/waiting while the model
  works; CoT is not copied onto the bubble or kept as `reasoning_preview`. Do not
  reintroduce recalled-memory chips.
- ✅ **One molecule card** — adjacent `smiles`/`chemistry` + `molecule3d` collapse
  in the client to one card (2D default, optional 3D). Persist still stores both
  fences. Standalone `molecule3d` stays 3D-only. Web slice 1 skips the second
  “Chemical structure” label for that pair. Verified compute coverage is
  [docs/chemistry.md](./docs/chemistry.md); do not treat SMILES rendering as the
  whole chemistry product.
- ✅ **Chemistry intent boundary** — `modules/chemistry/schemas/ChemistryIntent` separates
  extraction, solving, and presentation. Incomplete questions deliberately stay on the
  model path; only successful deterministic results receive verified labels.
- 🔜 Folders, editing arbitrary older messages, user-tunable routing rules, family plans,
  response caching, full duplex live voice (later).
- 🔜 **Math scanner capture-quality** — on-device blur/glare/perspective correction and a
  real homework-photo OCR benchmark (handwritten/printed, lighting, tilt). Torch, zoom,
  and Mathpix routing on the chat turn are shipped; do not market “industry-leading OCR”
  until that corpus exists.
- 🔜 **Production R2 + store polish** — attachment *code* is done; prod R2 secrets and App Store /
  Play billing polish are **future owner ops**, not a product coding task.
- ✅ **Mobile UI systems (audit 2026-08)** — P0 contrast tokens, switch/chip labels, 44pt
  `IconButton` on named undersized controls, PDF/math pinch-zoom, AppSheet
  dialog/focus/pan, AuthScrollLayout, gallery filter wrap, drawer width cap,
  SheetFormHeader, Space/Radius/Type (deleted `layout.ts`), StrokeIcon→Icon,
  Reduce Motion helpers, in-tree ActionBanner overlay host, recoverable
  `Alert.alert` sweep, and unused UI file cleanup. Do not restyle or
  reintroduce banned UX.
- ✅ **Mobile consumer polish (audit 2026-09)** — generic `StateView` errors use
  an alert icon (cloud-offline only for real connectivity); usage on the Settings page;
  quieter chat-header chrome; drawer profile opens Settings; Home overdue uses warning,
  not danger; composer send/stop/dismiss use `Icon`. Web remains a later project.
- ✅ **One UI kit (2026-09)** — `apps/mobile/ui/` is the single source for controls
  (catalog: `apps/mobile/ui/README.md`; dev gallery at Settings → Help & about → UI kit):
  - **Icons:** Lucide line icons at one stroke weight, plus multicolor brand marks.
  - **Menus:** every menu is one anchored popover; choices use a checked `SelectMenu`.
  - **Dialogs:** themed `confirmDialog` / `alertDialog` replace system alerts; passing errors are toasts.
  - **Pickers:** an Android-style clock time picker (dial, AM/PM, 24-hour inner ring,
    keyboard entry) and a calendar date picker with a year list, used for quiet hours
    and to-dos. The native datetimepicker module is removed.
  - **Share:** a ChatGPT-style share sheet (preview card with copy, Share / Copy / PDF) for
    chats and the drawer.
  - **Controls:** round header buttons, pill `Button`s, one `Chip`, `SegmentedControl`,
    `ListRow`, and `TextField`.

  Lint keeps features from rebuilding any of these. Public share links are still not built.

**Not implemented (future — do not start now).** Remaining 🔜 / partial items in this file:

| Area | Still not built |
|------|-----------------|
| Auth | Email/password, magic links, multi-device session management |
| Chats | Folders; public unauthenticated share URLs; edit arbitrary older messages |
| Messaging | Reactions, read receipts; full duplex live voice; music generation (composer send + compact inline player) |
| Models | User-tunable routing rules; response-cache; NL daily-goal setting |
| Todos | 1-hour-early email/push nudges |
| Attachments | **User-wide attachment RAG** (chunks are per `chat_id`; later turns in that chat only) |
| Integrations | Google Docs, GitHub; user MCP servers |
| Platform | Web client; code execution beyond HTML sandbox; virus scan |
| i18n | ~350 locale strings still English; legal privacy/terms bodies English-only |
| Polish | App Store / Play / family plans |
| Launch ops | Neon / Redis / R2 / Fly / EAS; landing page; on-device QA; prod R2 secrets |

### Future — owner ops (was “Pre-deployment TODO”)

Infra + store steps live in Lists → **Launch** (local Dev User) and
[`docs/PRODUCTION.md` § Owner actions](./docs/PRODUCTION.md#owner-actions-you--not-code).
**Future — not the current backlog.** Code cannot finish these.

- ⚠️ **R2 storage credentials** — the `R2StorageGateway` is wired and tested, but attachments
  run on local fallback until `STORAGE_BACKEND=r2` + `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` /
  `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` secrets are set. (Code done; creds pending.)
- ⚠️ **Production env secrets** — `validate_production_settings` enforces
  `OPENROUTER_API_KEY`, `CORS_ORIGINS`,
  `REVENUECAT_WEBHOOK_AUTH` (plus DB/Redis/Google/JWT/dev-flags). `ENVIRONMENT` now
  **defaults to `production` (fail-closed)** — local `.env` / `.env.example` must set
  `ENVIRONMENT=development`.
- 🔜 **Mobile gate + on-device pass** — **future.** `pnpm typecheck && pnpm lint && pnpm test`
  locally, then an iOS **and** Android dev-build pass (Google Sign-In, HTML/chart WebView,
  push, RevenueCat, deck Modal, autoscroll, markdown throttle).
- 🔜 **Frontend launch-readiness (audit, deferred)** — Pressable a11y coverage, `textTertiary`
  contrast, tablet readable-width, icon stroke unification, web KaTeX/Mermaid/Vega /
  stream virtualization, QA matrix assistive-tech pass. Not the current
  backlog.
- ✅ **FlashList migration** — `ConversationList` and Schedule now use `FlashList`
  (v2, auto-measured). Chat drawer rows are virtualized; the calendar day-view
  renders in the header (bounded/structured, not row-virtualized). Verify
  scroll/layout on-device.
- ✅ **i18n extraction (reminders / share / urgent)** — keys wired in `todoReminders`,
  `homeUrgentTodos`, `share.ts`, and push channel names; translated in all 9 locales.
- 🔜 **Locale prose translations** — **future.** Key-set parity is enforced (**960** keys);
  ~350 non-en values are still English. Structural i18n is complete.
- 🔜 **Legal page bodies** — **future.** `/legal/privacy`, `/legal/terms` and
  `/legal/delete-account` (the Play "Delete account URL") remain English-only markdown on the
  API (nav titles are localized); the contact is `SUPPORT_EMAIL`.
- ✅ **DB session scope in `_prepare_chat_turn`** — attachment S3 reads and web-search
  augmentation run outside the DB session.
- ✅ **Background-job DLQ** — failed jobs (including unknown type / bad JSON) go to
  `recall:jobs:dlq` before ACK. Stream trim uses pending MINID so approximate maxlen
  cannot drop unacked entries.
- ✅ **JWT refresh / logout** — 1h access + refresh rotation; mobile auto-refresh on 401.
- ✅ **HTTP SSE chat fallback** — `POST /chats/{id}/messages/stream` when WebSocket fails.
  New chat does not abort the fetch; Stop still does. The producer is registered as
  in-flight so `GET /messages` can wait out a leave. After a socket failure the next sends
  use SSE for 10 s (doubling to 5 min, reset by a reply over the socket, a network change
  or another chat), then the socket again; it used to stay SSE for the rest of the chat.
- ✅ **Chat socket recovery** — the socket reopens when the user starts to write after the
  server's idle close, is rebuilt after an access-token refresh, and is replaced on a network
  change (a reply in flight is probed instead). A send with no `start` within 3 s is probed
  (ping/pong); a dead socket's send is replayed over SSE under the message's
  `client_message_id`, which the server runs at most once (`modules/chat/client_message.py`);
  a resend it already took gets `duplicate` and the phone follows the first turn.

### Architecture review follow-ups (Jul 2026)

Shipped after the Phase 1/2 code review (and follow-up PRs):

- ✅ Fail-closed `ENVIRONMENT` default (`production`); tests set `development` via conftest
- ✅ Job DLQ for unknown type / bad payload; pending-aware stream trim
- ✅ Remove dead `quota.can_spend`; parallel attachment byte deletes
- ✅ `attachment_index` enqueued on the post-turn jobs path (not mid `prepare_chat_turn`)
- ✅ Token-based Redis locks for push / email / orphan-reaper schedulers
- ✅ WS handshake IP rate limit before `accept()`; core `user_id` FKs `ON DELETE CASCADE`
- ✅ Alembic `transaction_per_migration` so future `CREATE INDEX CONCURRENTLY` can use
  `op.get_context().autocommit_block()`
- ✅ Enum-like CHECK constraints — memories (type, status, sensitivity), users plan and response tone, and message role/feedback. Project, quiz-mode, and item-status checks left with the learning tables.
- ✅ Mobile: in-chat delete syncs drawer + cache; mount chat-load `catch`; memoized contexts;
  removed unused `showContextSummarized`; bootstrap listener cleanup race; draft discard on
  background; a11y labels on key icon-only controls
- ✅ **Real-SQL repository tests** — `test_*_db.py` for chats / messages / memories / usage
- ✅ **RTL test infra** — `@testing-library/react-native` + WebView sandbox / mount-queue tests
  (expand coverage over time; foundation is in)
- ✅ **Deferred WebView mount queue** — `useDeferredWebViewMount` caps concurrent chart/Mermaid/chemistry
  WebViews so multi-block messages stay smooth (math is SVG-native now, no WebView)
- ✅ **Hung-worker heartbeat** — `is_worker_alive` tracks loop heartbeat, not only `task.done()`
- ✅ **Claude review waves (#533–#539)** — product/reliability fixes + deferred items: chatprep
  lock, math expand, algebra answer fences, hard-disconnect persist, RevenueCat SET NX
  (see [Already shipped](#already-shipped-keep-for-audit-trail))

Still open (non-blocking / larger effort):

- ✅ **Multi-file HTML preview** — same-reply ` ```html ` + ` ```css ` +
  ` ```javascript ` fences are inlined for the sandboxed Run preview (relative
  names only; leftover CSS/JS appended). Single self-contained ` ```html ` still
  works. No folders, no extra execution surface.
- 🔜 Broader RTL coverage beyond the initial WebView / mount-queue suite
- 🔜 Locale prose + legal page bodies (future; see owner-ops list above)

### Review audit follow-ups (PR #129, Jul 2026)

Shipped in the audit PR or follow-up commits: push ticket-vs-receipt semantics, 600s scheduler
lock, attachment byte verification on GET, graph `points: []` rejection, live model badge via
`stream_end` + `resolved_model`, day-planning quiz stats, instant project day-item cache.

Still open (non-blocking):

- ⚠️ **Android chat keyboard** — `softwareKeyboardLayoutMode: resize` is set for Reanimated's
  `useAnimatedKeyboard`; needs an **Android dev-client rebuild** and on-device composer smoke test
  (iOS confirmed smooth; Android unverified).
- ✅ **Memory consolidation (pair-merge)** — exact duplicate facts are deleted without an LLM
  call; near-duplicate pairs (token Jaccard) merge with the same ≥20% anchor gate. Triggered
  on GET /memories as before.

### Multimodal & attachments

Shared **attachments substrate** (presigned upload, `attachments` table, local or R2 storage,
magic-byte validation, daily caps). Blobs never live in Postgres.

| Capability | Status |
|------------|--------|
| Presigned upload + confirm + orphan reaper | ✅ Shipped (local default; R2 when `STORAGE_BACKEND=r2` + secrets). Unconfirmed original uploads reap after `attachment_pending_orphan_hours` (default **1h**) so a killed-app image slot can refund the same UTC day. Hidden clones stay until `attachment_orphan_grace_hours` (default **24h**) — that billed window is intentional, not a leak. |
| Image upload → vision-chat routing (Qwen3.7 Flash, GLM 5.3 Flash backup, via OpenRouter) | ✅ Shipped |
| Image generation (composer send, daily cap per plan: 3 / 10 / 15) | ✅ Shipped |
| Reference-photo lookup (`show me an ear` / what-X-looks-like / "can you show me…" / "send me a photo of X"; "show me her image" reads who from the chat; Tavily + mirrored attachment; not listed in Library) | ✅ Shipped (free+Pro; daily cap; flag `image_search_enabled`) |
| Answer photos (one real photo above an answer about something worth seeing, no "show me"; the model's hidden ```photo query, searched while the text streams) | ✅ Shipped (free+Pro; same daily cap and flag) |
| Library (drawer grid of generated + uploaded images and files; lookup photos stay on the chat) | ✅ Shipped (local blobs under `~/.recall/attachments`, not `/tmp`) |
| PDF / doc upload + server text extract into prompt | ✅ Text-layer PDFs / DOCX + scanned-PDF OCR (page render → vision) |
| PDF inline preview (pdf.js WebView, dev build) | ✅ Shipped |
| Audio in (Whisper STT → composer) | ✅ Shipped (dev build) |
| Live talk (speech-to-speech, Pro, 60 min/month) | ✅ WebRTC + OpenAI Realtime; physical-device barge-in implemented, live validation pending; Simulator half-duplex |
| Audio out (read aloud) | ✅ Cloud TTS + device `expo-speech` fallback (no mic required; 502 ≠ API down) |
| Music generation (composer send + compact inline player) | 🔜 Later (Pro + daily cap; not TTS) |
| pgvector RAG over **this chat’s** attachments | ✅ Shipped (`attachment_rag`; flag on by default; not a user-wide corpus) |
| Camera math solver UX | ✅ Shipped (vision extract → SymPy subset; **dev build** for camera) |
| Full chat-history corpus RAG | ✅ Shipped (`message_chunks`; flag on by default) |
| Full duplex voice mode | 🔎 Physical-device implementation; release validation pending |

Notes: multimodal routes through whichever catalog model supports the modality (vision/image-gen
aliases on OpenRouter). Multimodal calls cost more than text — gated by plan + daily caps
(images, speech).

### Web client

A **web version that reuses this same API** — one backend, multiple clients. Slice 1 is in `apps/web`; later slices are not.

- 🔜 **Shared API + types** — the web app consumes the same HTTP/WebSocket endpoints and
  request/response shapes; eventually extract the `lib/api.ts` types/client into a package both
  apps import. Mobile uses Bearer JWT; the web client uses an in-memory access token plus an
  httpOnly refresh cookie.
- 🔜 **Web-specific swaps** — native Google Sign-In → web OAuth (GIS is in slice 1);
  the `react-native-webview` previews → a real `<iframe>` / native HTML.
  Keep rich-block rendering behind components so only the renderer differs per platform.
- 🔜 **Backend** — add the web origin(s) to `cors_origins` (CORS is locked down by env) and allow
  them on the WebSocket; no other backend change needed.
- ✅ **Approach decided** — separate Vite + React + TypeScript app at `apps/web` (not
  react-native-web of `apps/mobile`). Expo's FlashList/Reanimated/SecureStore/`expo-audio`/
  `react-native-webview` don't port to a browser without a multi-month effort.
- ✅ **Slice 1 shipped** — login (Google Identity Services + dev), chat list (create/open),
  chat view with SSE streaming (`start`/`token`/`status`/`stream_end`/`done`/`error`),
  stop (abort), regenerate, GFM markdown (including tables and images). Source links
  render under the reply; JSON rich fences (graph/chart/places/…) degrade to a short
  label instead of a code dump. Adjacent SMILES + molecule3d share one
  “Chemical structure” label (no 2D/3D viewer yet). No KaTeX/Mermaid/Vega/HTML iframe yet.
  Access token is in memory; refresh is an httpOnly cookie + CSRF (`X-CSRF-Token`) on the
  web origin (mobile stays Bearer + secure-store). Reload bootstraps via `POST /auth/refresh`.
  CORS origin documented in `apps/api/.env.example` — cookie sessions need an explicit
  `CORS_ORIGINS` list (empty `*` disables cookies). Follows the mobile chat-ux-bans.
- 🔜 **Later slices** — rich fences (math/charts/Mermaid/sandboxed HTML preview), Memory/
  settings/attachments/image gen, `packages/api-types` extracted from
  `lib/api/types.ts`, Apple Sign-In on web, prod deploy.

---

## 28. Product catalog (PM reference)

Internal product snapshot for leadership, engineering, design, GTM, and App Store review.
**Status:** pre–public launch on `main`. Supersedes one-off chat summaries when they disagree.

### Mission
Recall is a **personal AI utility** — not a generic chatbot. It remembers who you are, helps you
act (reminders, drafts, settings), and teaches in ordinary chat (math, physics, chemistry,
programming, and “teach me…” lessons). One trusted assistant combining ChatGPT-grade conversation
with durable memory and everyday productivity.

### Strategic pillars
| Pillar | Meaning |
|--------|---------|
| Chat that feels fast | Streaming, stop/regenerate, rich answers, status while working |
| Memory that compounds | User facts + past-chat RAG — the namesake |
| Utility beyond chat | Schedule, reminders |
| Trust & control | Export, delete account, confirm-before-write cards, quota transparency |
| Monetize fairly | Free tier with limits; Plus for voice; Pro adds live talk |

### Release plan
| Phase | Scope | Status |
|-------|--------|--------|
| MVP (mobile) | Chat + memory + Schedule + attachments | ~95% code-complete |
| Launch readiness | Provisioning, store builds, landing page, OAuth verification, on-device QA, R2 secrets | 🔜 Future (owner ops) |
| v1.1 | Remaining web slices (rich fences, Memory/settings), locale prose, legal localization | 🔜 Future |
| Next (product) | — | Done (tool loop, scanned-PDF OCR, chat-history RAG) |
| Later | Google Docs, GitHub, code execution, duplex voice, folders / family plans | 🔜 Future |

Notes already on `main` (not waiting on v2): Fly api/worker split ✅, attachment RAG ✅,
chat-history RAG ✅, LiteLLM tool loop **on by default** (ordinary chat skips the pre-stream round) ✅, structured profile ✅,
drawer FTS search ✅.

### Rich rendering (§4 summary)
| Capability | Status |
|------------|--------|
| Markdown, tables, math, geometry/graph SVG, charts, HTML sandbox | ✅ Shipped |
| Prism.js syntax highlighting | ✅ Shipped |
| Mermaid inline (WebView, dev build) | ✅ Shipped |
| PDF preview in chat | ✅ Shipped (tap card → viewer modal) |
| Collaborative cursors / shared docs | 🔜 Deferred (personal app; no multi-user) |

### Attachments & multimodal
| Shipped | Not done |
|---------|----------|
| Presigned upload, magic-byte validation, daily image cap | Production R2 secrets (future owner ops) |
| Vision routing for images + scanned-PDF OCR (**index job**, not prepare) | — |
| PDF text extract + pgvector RAG **per conversation** | User-wide attachment corpus |
| Chat-history corpus RAG (pgvector top-k, not full transcript) | — |
| Camera math solver (vision extract → SymPy subset) | Virus scan / enterprise DLP |
| PDF inline preview in message bubble | — |

### Voice
| Shipped | Not done |
|---------|----------|
| Record → OpenAI `gpt-4o-mini-transcribe` → composer (app-language hint, no-speech gate) | Live provider verification |
| Live Talk WebRTC + OpenAI `gpt-realtime-2.1` (Pro, 60 min/month; server VAD, physical-device barge-in, bounded read-only tools; Schedule snapshot + clocked reminder persist off audio path). Needs `OPENAI_API_KEY`. | Physical-device echo/interruption checks; heard-word transcript alignment |
| Device TTS + cloud TTS (`POST /speech/tts` lead/rest JSON, daily caps) | — |

### Cost guards (recent)
| Guard | Free | Plus | Pro |
|-------|------|------|-----|
| Daily tokens | 100k | 500k | 500k |
| Speech transcriptions/day | 0 (not included) | 200 | 200 |
| Speech TTS (read aloud)/day | 0 (phone voice only) | 100 | 100 |
| AI images/day | 3 | 10 | 15 |
| Live talk | not included | not included | 60 min/month |
| Tavily searches/day | 20 (then DDG only) | 150 | 150 |
| R1 / smart-chat quota weight | 3.5× token charge | Same | Same |

### Integrations
| Shipped | Not done |
|---------|----------|
| MCP adapters + LiteLLM tool loop **on by default** (not every turn) | Google Docs, GitHub; user MCP servers |
| Google Calendar and Gmail were shipped, then **removed** (§16) | — |

### Future — launch ops (owner, not product code)
1. Cost guards (speech, Tavily, R1 weight) ✅
2. 🔜 Provision Neon, Redis, R2, Fly, EAS
3. 🔜 Landing page + support URL
4. 🔜 On-device QA matrix (iOS + Android)
5. 🔜 R2 production attachments

### Explicitly not v1
Multi-user teams, collaborative editing, video generation, public unauthenticated share URLs,
arbitrary user MCP servers, gamification (XP/badges). **OpenRouter / product aliases are the intended model setup** — not a gap.

**Next (product):** none — tool loop, scanned-PDF OCR, and chat-history RAG are done.

**Future (not implementing now):** launch ops (provision, landing page, on-device QA, prod
R2); Google Docs + GitHub; code execution (beyond the HTML sandbox); duplex voice;
remaining web slices; locale prose + legal bodies; folders / family plans; **user-wide attachment RAG**.

---

## 29. Next actions (product decisions)

Compiled from the ChatGPT-gap review. One concern per PR. Do not treat OpenRouter as a
weakness. No video generation. Native share is enough unless we later decide we want
**public unauthenticated URLs** (we do not have those today).

### Done (this product pass)

1. ✅ **Owned tool loop on** — `mcp_tool_loop_enabled` defaults true. Adapters:
   `web_search`, `sympy` (if math on), `image_gen` (if image gen on),
   `search_image` (if image search on). Heuristic SymPy still runs. Web search is
   the owned tool loop (source chips + wrap); a skipped `web_search` still runs
   one cached search. Add Docs/GitHub later as owned tools — not user MCP servers.
2. ✅ **Scanned-PDF OCR** — text-layer extract on prepare (no vision); empty PDFs
   render pages → `vision-chat` on the **index job** (20 pages / 200k chars, not 500
   vision calls) → same excerpt + chunk/embed RAG. Coverage is stored; the prompt
   prefix uses those ceilings. No second pipeline.
3. ✅ **Chat-history semantic RAG** — `message_index` after finalize; top-k at turn
   start excluding the recent window. Golden Rule 3: never dump the full transcript.
4. ✅ **Reply-quality Lane 2** — “yes/go” follows the prior offer; requested length
   and type beat keyword templates; one question when an email has no purpose or
   a real-data chart has no numbers.
5. ✅ **Reply-quality Lane 3** — interrupted streams are marked incomplete; file
   excerpt/page caps are disclosed to the model; image follow-ups rehydrate prior
   photos; frozen table rows share height; grouped bars keep their offset. No new
   cards, chips, or surfaces.
6. ✅ **EmailCard one draft** — edits on Done (and a debounce / send flush) rewrite
   the first ` ```email ` fence on that assistant message. Card Copy, whole-reply
   Copy, “make that shorter”, and reopen agree. Not user-message edit.
7. ✅ **Advice memory on ordinary phrasing** — “I need a quick dinner tonight”
   and “plan a workout for me” load the same memory-only path as
   “what should I eat” / “recommend a workout”.

### Future (not implementing now)

- Launch ops: provision Neon / Redis / R2 / Fly / EAS; landing page + support URL;
  on-device QA (iOS + Android); production R2 secrets.
- Google Docs, GitHub (owned integrations).
- **User-wide attachment RAG** — chunks stay per `chat_id`; later turns in that chat only.
- Full duplex live voice (talk over playback without tapping).
- Code execution beyond the sandboxed HTML/chart WebView.
- Web client (same API).
- Locale prose + legal page bodies.
- Public share URLs only if we explicitly want unauthenticated read links.
- Folders, family plans, response-cache / prompt-budget UI, user-tunable routing.

### Not doing

- Video generation.
- Custom GPTs / arbitrary user MCP servers as the way to “make tools strong.”
- Calling rented models a product gap.
