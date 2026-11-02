"""Chat prompt copy: the hints, notes and contracts a reply's prompt is built from.

Split by domain (math, format, teaching, …). What a message says (the readers that
pick which copy a turn gets) is ``modules/turn_reading`` (structure ticket ST-04).
"""

from app.modules.chat.prompt_constants.capabilities import (
    CAPABILITIES_FORMAT_HINT,
    PHOTO_LOOKUP_HINT,
    SETTINGS_ASK_REMINDER,
    SETTINGS_IN_APP_HINT,
)
from app.modules.chat.prompt_constants.chart import CHART_FORMAT_HINT
from app.modules.chat.prompt_constants.checklist import CHECKLIST_FORMAT_HINT
from app.modules.chat.prompt_constants.clarify import CLARIFY_CARD_HINT
from app.modules.chat.prompt_constants.coding import (
    CODE_INK_REMINDER,
    code_question_hint,
)
from app.modules.chat.prompt_constants.conversation import (
    CONTINUE_HINT,
    CORRECTION_HINT,
    REPEATED_GREETING_HINT,
    repeated_greeting_hint,
)
from app.modules.chat.prompt_constants.diagrams import (
    DIAGRAM_KIND_HINT,
    MERMAID_FORMAT_HINT,
    SEQUENCE_FORMAT_HINT,
    mermaid_format_hint,
)
from app.modules.chat.prompt_constants.format import (
    BIOLOGY_PRESENTATION_HINT,
    CALLOUT_FORMAT_HINT,
    COMPACT_RESPONSE_FORMAT_HINT,
    COMPARISON_FORMAT_HINT,
    FORMAT_CONTRACT,
    HOWTO_FORMAT_HINT,
    QUOTE_FORMAT_HINT,
    SHORT_RESPONSE_FORMAT_HINT,
    STATISTICS_PRESENTATION_HINT,
    STEPS_FORMAT_HINT,
    TONE_FORMAT_GUARD,
    UNIVERSAL_FORMAT_BASELINE,
)
from app.modules.chat.prompt_constants.grounding import (
    FACT_GROUNDING_HINT,
    WEB_SEARCH_OFF_HINT,
)
from app.modules.chat.prompt_constants.learning_plan_contract import learning_plan_daily_contract
from app.modules.chat.prompt_constants.length import (
    BREVITY_REQUEST_HINT,
    MIXED_LENGTH_HINT,
    STYLE_HINTS,
)
from app.modules.chat.prompt_constants.math import MATH_FENCE_SAFETY_HINT
from app.modules.chat.prompt_constants.practice import QUIZ_FORMAT_HINT
from app.modules.chat.prompt_constants.privacy import (
    ADVICE_PERSONALIZE_HINT,
    BROAD_SELF_ANSWER_HINT,
    CAREER_PERSONALIZE_HINT,
    CLARIFICATION_HINT,
    DAY_PLANNING_ANSWER_HINT,
    EXAMPLE_PERSONALIZE_HINT,
    PRIVACY_HINT,
    PROFILE_FACT_HINT,
)
from app.modules.chat.prompt_constants.routing import (
    CONFIRM_FOLLOW_THROUGH_HINT,
    LIGHTWEIGHT_REPLY_HINT,
    NEW_PROBLEM_HINT,
    PERSONAL_DISCLOSURE_HINT,
)
from app.modules.chat.prompt_constants.solving import VERIFIED_SOLVE_SAFETY_HINT
from app.modules.chat.prompt_constants.teaching import (
    LEARNING_PLAN_HINT,
    STANDING_PREFERENCE_HINT,
    TEACHING_HINT,
    WALKTHROUGH_HINT,
    programming_lesson_contract,
)
from app.modules.chat.prompt_constants.unclear import UNCLEAR_MESSAGE_HINT
from app.modules.chat.prompt_constants.visuals import (
    ANSWER_PHOTO_HINT,
    IMAGE_GEN_HONESTY_HINT,
    IMAGE_GEN_UNAVAILABLE_HINT,
    VISUALIZATION_HINTS,
    WHERE_IS_PHOTO_HINT,
)
from app.modules.chat.prompt_constants.writing import (
    COPY_DELIVERABLE_HINT,
    NON_DRAFT_TURN_HINT,
    WRITING_LINE_HINT,
    draft_followup_hint,
    is_bare_writing_line,
    writing_format_hint,
)

__all__ = [
    "ADVICE_PERSONALIZE_HINT",
    "ANSWER_PHOTO_HINT",
    "BIOLOGY_PRESENTATION_HINT",
    "BREVITY_REQUEST_HINT",
    "BROAD_SELF_ANSWER_HINT",
    "CALLOUT_FORMAT_HINT",
    "CAPABILITIES_FORMAT_HINT",
    "CAREER_PERSONALIZE_HINT",
    "CHART_FORMAT_HINT",
    "CHECKLIST_FORMAT_HINT",
    "CLARIFICATION_HINT",
    "CLARIFY_CARD_HINT",
    "CODE_INK_REMINDER",
    "COMPACT_RESPONSE_FORMAT_HINT",
    "COMPARISON_FORMAT_HINT",
    "CONFIRM_FOLLOW_THROUGH_HINT",
    "CONTINUE_HINT",
    "COPY_DELIVERABLE_HINT",
    "CORRECTION_HINT",
    "DAY_PLANNING_ANSWER_HINT",
    "DIAGRAM_KIND_HINT",
    "EXAMPLE_PERSONALIZE_HINT",
    "FACT_GROUNDING_HINT",
    "FORMAT_CONTRACT",
    "HOWTO_FORMAT_HINT",
    "IMAGE_GEN_HONESTY_HINT",
    "IMAGE_GEN_UNAVAILABLE_HINT",
    "LEARNING_PLAN_HINT",
    "LIGHTWEIGHT_REPLY_HINT",
    "MATH_FENCE_SAFETY_HINT",
    "MERMAID_FORMAT_HINT",
    "MIXED_LENGTH_HINT",
    "NEW_PROBLEM_HINT",
    "NON_DRAFT_TURN_HINT",
    "PERSONAL_DISCLOSURE_HINT",
    "PHOTO_LOOKUP_HINT",
    "PRIVACY_HINT",
    "PROFILE_FACT_HINT",
    "QUIZ_FORMAT_HINT",
    "QUOTE_FORMAT_HINT",
    "REPEATED_GREETING_HINT",
    "SEQUENCE_FORMAT_HINT",
    "SETTINGS_ASK_REMINDER",
    "SETTINGS_IN_APP_HINT",
    "SHORT_RESPONSE_FORMAT_HINT",
    "STANDING_PREFERENCE_HINT",
    "STATISTICS_PRESENTATION_HINT",
    "STEPS_FORMAT_HINT",
    "STYLE_HINTS",
    "TEACHING_HINT",
    "TONE_FORMAT_GUARD",
    "UNCLEAR_MESSAGE_HINT",
    "UNIVERSAL_FORMAT_BASELINE",
    "VERIFIED_SOLVE_SAFETY_HINT",
    "VISUALIZATION_HINTS",
    "WALKTHROUGH_HINT",
    "WEB_SEARCH_OFF_HINT",
    "WHERE_IS_PHOTO_HINT",
    "WRITING_LINE_HINT",
    "code_question_hint",
    "draft_followup_hint",
    "is_bare_writing_line",
    "learning_plan_daily_contract",
    "mermaid_format_hint",
    "programming_lesson_contract",
    "repeated_greeting_hint",
    "writing_format_hint",
]
