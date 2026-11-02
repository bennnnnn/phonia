"""When a chat turn should hit pre-stream SymPy."""

from __future__ import annotations

import app.modules.math.match.homework_cues as cues
import app.modules.math.match.need_signals as signals
from app.modules.math.match.need_signals import NeedSignal
from app.modules.math.match.scan import has_math_keyword, prepare

# Cheap lexical signals, asked before any extractor runs. The order is only
# speed: the line is maths when any one of them fires.
NEED_SIGNALS: tuple[NeedSignal, ...] = (
    signals.named_rectangle,
    signals.drawn_shape,
    signals.shape_with_measures,
    signals.keyword_equation,
    signals.bare_equation,
    signals.bare_arithmetic,
    signals.complex_arithmetic,
    signals.make_subject,
    signals.coordinate_vector,
    signals.graph_request,
    signals.inequality,
    signals.calculus,
    signals.numerical_method,
    signals.solve_request,
    signals.discrete,
    cues.percent_cue,
    cues.everyday_cue,
    cues.sequence_cue,
    cues.identity_cue,
    cues.curve_plot_cue,
    cues.coordinate_cue,
    cues.probability_cue,
    cues.structure_cue,
    cues.calculus_cue,
    cues.trig_cue,
)


def needs_symbolic(text: str, *, has_image_attachment: bool = False) -> bool:
    cleaned = prepare(text)
    if cleaned is None:
        return False
    if not cleaned and not has_image_attachment:
        return False
    from app.services.subject_scan import scanner_camera_subject

    if has_image_attachment and scanner_camera_subject(cleaned) == "math":
        return True
    # The raw text: prepare() folds the newline that ends a camera caption.
    if scanner_camera_subject(text) not in (None, "math"):
        return False
    lower = cleaned.lower()
    if has_image_attachment and has_math_keyword(lower):
        return True
    if any(signal(cleaned, lower) for signal in NEED_SIGNALS):
        return True
    # Last, the requests only a grammar can read. Extraction reuses these reads.
    from app.modules.math.tools.extractors.detection import an_extractor_reads

    return an_extractor_reads(cleaned, lower)
