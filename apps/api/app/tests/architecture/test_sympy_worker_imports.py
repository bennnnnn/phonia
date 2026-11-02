"""SymPy pool workers must stay small: no model client, no web or DB stack.

Each API process runs ``sympy_max_workers`` (3) spawned workers, each its own
Python process. The math package once imported the LiteLLM gateway at module
top, which put litellm, openai and tiktoken into every worker: about 237 MB per
worker after the warm-up solve instead of about 86 MB. Reading a message runs
there too (``core/readings.py``): turn prep's package ``__init__`` once pulled in
the prompt builder and the database engine, 310 MB a worker. So the jobs run
here once each, and what they import at call time counts too.
"""

from __future__ import annotations

import subprocess
import sys

from app.tests.architecture.boundary_support import APP_ROOT

# What the functions handed to ``run_sympy`` and ``read_off_loop`` import and run.
_WORKER_JOBS = (
    "from app.modules.chat.turn_prep.reading import warm_pool_worker",
    "warm_pool_worker()",
    "import app.modules.math.tools.block",
    "import app.modules.math.fence",
    "import app.modules.chemistry.fence",
    "from app.core.config import Settings",
    "settings = Settings(_env_file=None)",
    "exchange = [{'role': 'user', 'content': 'solve 2x + 3 = 7'},"
    " {'role': 'assistant', 'content': 'x = 2'}]",
    "from app.modules.chat.turn_prep.reading import ask_turn_readings",
    "ask_turn_readings('A car goes from 0 to 100 km/h in 8 s. Find a, and also solve"
    " 2x + 3 = 7', prior_user='hi', prior_model=None, lesson_active=False,"
    " has_image_attachment=False, settings=settings)",
    "from app.modules.math.tools.prompt import read_math_request",
    "read_math_request('graph y = x^2', has_image_attachment=False,"
    " image_math_extract=None, needs_math=None, prior_user_messages=[])",
    "from app.modules.physics.prompt import solve_physics_request",
    "solve_physics_request('A 2 kg ball falls 5 m. Find its speed.', settings, None)",
    "from app.modules.chat.turn_prep.followups import read_prompt_inputs, resolve_subject_followup",
    "read_prompt_inputs('how?', exchange)",
    "resolve_subject_followup('how?', exchange)",
    "from app.modules.chat.related_questions import accepted_questions, follow_up_topic",
    "follow_up_topic('solve 2x + 3 = 7', 'x = 2', exchange, allow_general=True)",
    "accepted_questions('solve 2x + 3 = 7', ['What if 2x + 3 = 9?'])",
    "from app.services.subjects.dispatch import maybe_direct_subject_reply",
    "from app.modules.chemistry.context import _solve_locally",
    "_solve_locally('How many moles are in 18 g of water?')",
)
_HEAVY = ("litellm", "openai", "tiktoken", "sqlalchemy", "fastapi")


def test_sympy_worker_does_not_import_the_model_client_or_web_stack() -> None:
    script = "\n".join(
        [
            "import sys",
            *_WORKER_JOBS,
            f"print(','.join(m for m in {_HEAVY!r} if m in sys.modules))",
        ]
    )
    result = subprocess.run(  # noqa: S603 - fixed argv: this interpreter and literal jobs
        [sys.executable, "-c", script],
        cwd=APP_ROOT.parent,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    loaded = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    assert loaded == "", f"SymPy worker imports pulled in: {loaded}"


# What the document pool's jobs import and run (``core/document_executor.py``).
_DOCUMENT_JOBS = (
    "import io, pypdf",
    "writer = pypdf.PdfWriter()",
    "writer.add_blank_page(width=200, height=200)",
    "buffer = io.BytesIO()",
    "writer.write(buffer)",
    "from app.modules.attachments.text_extract import extract_in_worker",
    "extract_in_worker('application/pdf', buffer.getvalue(), 1000)",
    "from app.modules.attachments.pdf_render import render_in_worker",
    "render_in_worker(buffer.getvalue(), 1, 1.0, 1_000_000)",
)


def test_document_worker_does_not_import_the_model_client_or_web_stack() -> None:
    script = "\n".join(
        [
            "import sys",
            *_DOCUMENT_JOBS,
            f"print(','.join(m for m in {_HEAVY!r} if m in sys.modules))",
        ]
    )
    result = subprocess.run(  # noqa: S603 - fixed argv: this interpreter and literal jobs
        [sys.executable, "-c", script],
        cwd=APP_ROOT.parent,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    loaded = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    assert loaded == "", f"Document worker imports pulled in: {loaded}"
