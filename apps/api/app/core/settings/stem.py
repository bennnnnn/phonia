"""Maths, physics and chemistry: SymPy bounds and pool, model extraction, scan OCR."""

from pydantic import AliasChoices, BaseModel, Field


class StemSettings(BaseModel):
    math_tools_enabled: bool = True
    chemistry_enabled: bool = True
    # A calculation no solver checked: the model writes its parts in a ```worked block and
    # the server lays them out as a verified reply (``chat.worked_turn``). Off: the model
    # writes the layout itself, as before.
    worked_layout_enabled: bool = True
    math_max_expr_length: int = 256
    # Polynomial solve shape bound — refuse before the 5s SymPy pool, not
    # only by character length (x^40 is short and still pathological).
    math_max_poly_degree: int = 8
    # Dense enough for a smooth SVG polyline; larger dumps (300+) blow up
    # chat bubbles and FallbackMarkdown when the rich renderer dies.
    math_graph_max_points: int = 96
    # SymPy solve/simplify/integrate run on a worker thread (they're sync, CPU-bound);
    # this bounds how long a single pathological expression can occupy that thread
    # before the chat turn falls back to an unverified reply. Every subject's solve:
    # maths, physics and chemistry (it was math_solve_timeout_seconds; that env name
    # is still read for one release).
    stem_solve_timeout_seconds: float = Field(
        default=5.0,
        validation_alias=AliasChoices("stem_solve_timeout_seconds", "math_solve_timeout_seconds"),
    )
    # Isolated 1-worker process slots (not one shared N-worker pool — a
    # timeout must SIGTERM only the runaway). Interactive slot wait is *not*
    # the 5s solve timeout; 1+1=x must not sit 60s behind an integral.
    sympy_max_workers: int = 3
    sympy_queue_wait_seconds: float = 2.0
    # Reading a message (its subject, plan and maths and physics intents) runs in the same
    # pool (core/readings.py). Normal messages read in milliseconds; past this the turn
    # reads no subject and the model answers without a verified solve.
    subject_read_timeout_seconds: float = 3.0
    # modules/math/image_extract.py's vision-chat call is a network round trip, not
    # local synchronous SymPy work — reusing stem_solve_timeout_seconds's 5s
    # budget (sized for CPU-bound solve/integrate) cut off OCR calls that
    # were still legitimately in flight.
    math_image_extract_timeout_seconds: float = 20.0
    # Gate-fired-but-regex-extract-None turns get one hidden structured
    # extraction call on a fast alias before the honesty note (the "Couldn't
    # verify under a correct ∫ x²" path). Only that already-failing path pays;
    # gate-miss and regex-hit turns make no LLM call. The result is never
    # trusted — it reaches the user only when SymPy verifies it. If the primary
    # structured provider times out or returns invalid JSON, the configured
    # secondary provider gets one bounded attempt before the path declines.
    math_llm_extract_enabled: bool = True
    math_llm_extract_timeout_seconds: float = 2.5
    # Algebra word problems ("three times as old", "tickets cost $5 and $8"):
    # a bounded structured call translates them into unknowns and equations,
    # with one provider-independent retry on timeout or invalid JSON. Results
    # reach the user only when every number is stated in the problem and SymPy
    # finds exactly one solution in the stated domain.
    math_word_problems_enabled: bool = True
    math_word_problem_timeout_seconds: float = 3.0
    # The word-problem translation and the extraction above run side by side;
    # this bounds them together. It sits a little above the longer of the two
    # (two 3 s translation attempts), so it only stops a call that outlives its
    # own timeout; a finished extraction is used when the translation runs long.
    math_model_intent_budget_seconds: float = 7.0
    # A model reads each question beside the patterns, and the turn's trace line says
    # whether the two agree (docs/MODEL_READER.md). Off: a measurement, not a feature;
    # nothing it reads reaches a reply. Each of its two calls has this long: the measured
    # p95 of a call (docs/MODEL_READER.md); the turn never waits for the read.
    model_reader_shadow_enabled: bool = False
    # The share of STEM turns read in shadow when it is on (0 none, 1 every one): each read
    # costs two model calls.
    model_reader_shadow_rate: float = 0.1
    model_reader_timeout_seconds: float = 3.5
    # POST /{math,physics,chemistry}/scan/read runs OCR (Mathpix, then vision)
    # so the student can confirm what the camera read before it is solved.
    # Per user, per hour, shared by every subject's reader (it was
    # math_scan_read_rate_limit_per_hour; that env name is still read for one release).
    scan_read_rate_limit_per_hour: int = Field(
        default=60,
        validation_alias=AliasChoices(
            "scan_read_rate_limit_per_hour", "math_scan_read_rate_limit_per_hour"
        ),
    )
    # One read answers within this many seconds of arriving, every reader and
    # fallback included (later steps get what earlier ones left). It stays
    # below the phone's timeout (SCAN_READ_TIMEOUT_MS in features/scanner/api.ts,
    # this plus 5 s for the upload), so a slow read ends as "could not read".
    scan_read_deadline_seconds: float = 20.0
    # Dedicated math OCR (Mathpix). Empty keys keep the Gemini vision path.
    # Images always send metadata.improve_mathpix=false — student homework is
    # not opted into Mathpix QA storage.
    mathpix_app_id: str = ""
    mathpix_app_key: str = ""
    mathpix_enabled: bool = True
    mathpix_timeout_seconds: float = 8.0
    # Below this 0..1 confidence, a Mathpix transcription still needs Gemini.
    mathpix_confidence_min: float = 0.72
