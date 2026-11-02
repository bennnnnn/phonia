"""Mermaid diagram cues and hints: flowcharts, sequence diagrams and named kinds."""

from app.modules.turn_reading.diagrams import (
    is_diagram_kind_question,
    is_mermaid_question,
    is_sequence_diagram_question,
)

MERMAID_FORMAT_HINT = (
    "This turn is a flowchart. Lead with a ```mermaid fence — not a numbered "
    "list, not HTML/SVG, and not a joke setup ('let's brew up some fun'). "
    "At most one short sentence, then the fence. Do not interview for steps.\n"
    "Match the process they asked for. If they named steps or said ~N steps, "
    "emit those nodes — do not invent a 2-box story.\n"
    "Linear process: flowchart TD, one rectangle per step, --> between them. "
    "Start/end may use stadium ([...]); decisions use diamonds.\n"
    "Node labels must not contain raw parentheses — they break the parser. "
    'Quote any label that needs extra words: E["Grind beans"] not '
    "E[Grind Beans (Medium Grind)].\n"
    "Example shape only:\n"
    "```mermaid\n"
    "flowchart TD\n"
    "    start([Start]) --> step[Do the work] --> done([Done])\n"
    "```"
)

SEQUENCE_FORMAT_HINT = (
    "This turn is a sequence diagram, not a flowchart. Lead with a ```mermaid "
    "fence using sequenceDiagram — not flowchart TD, not a numbered list, and "
    "not a joke setup. At most one short sentence, then the fence.\n"
    "Participants and messages they named; do not invent a 2-box story.\n"
    "Example shape only:\n"
    "```mermaid\n"
    "sequenceDiagram\n"
    "    participant Client\n"
    "    participant Server\n"
    "    Client->>Server: request\n"
    "    Server-->>Client: response\n"
    "```"
)


DIAGRAM_KIND_HINT = (
    "This turn names a diagram Recall draws from a ```mermaid fence. Lead with that "
    "fence — never an image, HTML/SVG, ASCII art, or a list in its place, and no joke "
    "setup. At most one short sentence, then the fence. Use the Mermaid type that fits "
    "what they named:\n"
    "- decision tree, org chart, family tree, process map: flowchart TD; a question is a "
    "diamond Q{Need speed?} with labelled edges Q -->|Yes| A[Go]\n"
    "- state machine or state diagram: stateDiagram-v2 with [*] --> Red and "
    "Red --> Green : timer\n"
    "- mind map or concept map: mindmap, then root((Topic)) with each child indented two "
    "spaces more than its parent; plain words only, no brackets or parentheses\n"
    "- ER diagram: erDiagram with MEMBER ||--o{ LOAN : borrows\n"
    "- class diagram: classDiagram; Gantt chart: gantt; user journey: journey\n"
    'In a flowchart, quote a label that needs parentheses: A["Grind beans (medium)"].'
)


def mermaid_format_hint(text: str) -> str | None:
    """The hint for a requested Mermaid diagram, most specific first."""
    if is_sequence_diagram_question(text):
        return SEQUENCE_FORMAT_HINT
    if is_diagram_kind_question(text):
        return DIAGRAM_KIND_HINT
    if is_mermaid_question(text):
        return MERMAID_FORMAT_HINT
    return None
